"""Conservative, transactional migration of pre-V3 Analysis content."""

from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from ..adapters.obsidian.analysis_base_renderer import render_analysis_base
from ..adapters.vault.filesystem import VaultFilesystem, VaultPathSafetyError
from ..adapters.vault.lock import GlobalLock
from ..config.loader import load_config
from ..domain.analysis import (
    ANALYSIS_END_MARKER,
    ANALYSIS_FIELD_ORDER,
    ANALYSIS_START_MARKER,
    ANALYSIS_TYPES,
    REMOVED_ANALYSIS_FIELDS,
    AnalysisValidationError,
    build_analysis_identity,
    validate_analysis_fields,
)
from ..domain.frontmatter import compose_frontmatter, parse_frontmatter
from ..domain.paths import normalize_vault_relative
from .analysis_service import AnalysisService
from .transaction_service import Transaction, TransactionService

_CONFLICT_POLICIES = frozenset({"preserve-user", "overwrite-managed", "fail"})
_REFERENCE_RE = re.compile(r"\[\[(evidence|asset):[^\]]+\]\]", re.IGNORECASE)
_BLOCK_ID_RE = re.compile(
    r"(?m)(?P<prefix>^|[ \t]+)\^ev-[A-Za-z0-9_-]+(?=[ \t]*\r?$)"
)
_OLD_MARKER_RE = re.compile(
    r"(?m)^<!--[ \t]*ovm:(?:analysis-uncertainties|evidence[^:]*|coverage[^:]*|uncertainty[^:]*):(?:start|end)[ \t]*-->[ \t]*(?:\r?\n)?"
)


@dataclass
class _MigrationPlan:
    source: str
    target: str
    text: str
    analysis_id: str
    analysis_type: str
    origin: str
    removed_evidence: int = 0
    removed_assets: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "from": self.source,
            "to": self.target,
            "analysisId": self.analysis_id,
            "analysisType": self.analysis_type,
            "origin": self.origin,
        }


@dataclass
class _MigrationState:
    migrated: list[_MigrationPlan] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)
    manual: list[dict[str, Any]] = field(default_factory=list)
    clean_in_place: list[tuple[str, str]] = field(default_factory=list)
    removed_evidence: int = 0
    removed_assets: int = 0
    analysis_pending: list[str] = field(default_factory=list)
    topic_pending: list[str] = field(default_factory=list)
    theory_pending: list[str] = field(default_factory=list)
    snapshots: dict[str, str | None] = field(default_factory=dict)


class AnalysisMigrationService:
    """Plan, apply, and roll back the safe Analysis migration."""

    def __init__(
        self,
        vault_path: str | os.PathLike[str],
        config: Mapping[str, Any] | None = None,
        *,
        transaction_service: TransactionService | None = None,
        now: Callable[[], str] | None = None,
    ) -> None:
        self.vault_path = Path(vault_path).expanduser().resolve()
        if not self.vault_path.is_dir():
            raise NotADirectoryError(f"Vault root is not a directory: {self.vault_path}")
        self.config = (
            dict(config)
            if config is not None
            else load_config(self.vault_path, require_exists=False)
        )
        self.fs = VaultFilesystem(self.vault_path)
        self.transactions = transaction_service or TransactionService(self.vault_path)
        self.analysis = AnalysisService(
            self.vault_path,
            self.config,
            transaction_service=self.transactions,
            now=now,
        )

    def migrate(
        self,
        dry_run: bool = True,
        apply: bool = False,
        transaction_id: str | None = None,
        conflict_policy: str = "preserve-user",
    ) -> dict[str, Any]:
        """Preview by default; mutate only with ``apply=True, dry_run=False``."""

        if conflict_policy != "preserve-user":
            raise ValueError(
                "analysis migration supports only conflict_policy preserve-user"
            )
        execute = bool(apply and not dry_run)
        state = _MigrationState()
        claimed_targets: set[str] = set()
        for relative in self._scan_markdown_folder(
            self.analysis.analysis_folder,
            origin="analysis",
            state=state,
        ):
            if PurePosixPath(relative).name.casefold() == "index.md":
                continue
            self._consider(
                relative,
                origin="analysis",
                required_type=None,
                state=state,
                claimed_targets=claimed_targets,
            )

        self._scan_legacy_knowledge_folder(
            "Literature/Topic",
            origin="topic",
            required_type="literature_review",
            state=state,
            claimed_targets=claimed_targets,
        )
        self._scan_legacy_knowledge_folder(
            "Literature/Theory",
            origin="theory",
            required_type="concept",
            state=state,
            claimed_targets=claimed_targets,
        )

        transaction = self.transactions.begin(
            transaction_id=transaction_id,
            dry_run=not execute,
        )
        self._stage_plans(transaction, state)
        old_index_removed = self._stage_old_index(transaction, state)
        base_text = render_analysis_base(self.analysis.analysis_folder)
        base_existing = self._snapshot_optional_text(
            self.analysis.analysis_base_path,
            state,
        )
        analysis_base_created = base_existing is None
        if analysis_base_created:
            transaction.write_text(self.analysis.analysis_base_path, base_text)
        elif base_existing != base_text:
            state.manual.append(
                {
                    "path": self.analysis.analysis_base_path,
                    "reasons": [
                        "existing Analysis Base differs from the managed template and was preserved"
                    ],
                }
            )
        transaction.guard(lambda: self._recheck_snapshots(state.snapshots))
        if execute:
            with GlobalLock(self.vault_path, "base"):
                committed = transaction.commit()
        else:
            committed = transaction.commit()
        return {
            **committed,
            "ok": True,
            "dryRun": not execute,
            "applied": execute,
            "migratedAnalyses": [plan.as_dict() for plan in state.migrated],
            "skippedAnalyses": state.skipped,
            "manualReviewRequired": state.manual,
            "removedEvidenceAnchors": state.removed_evidence,
            "removedAssetAnchors": state.removed_assets,
            "oldIndexRemoved": old_index_removed,
            "analysisBaseCreated": analysis_base_created,
            "topicFilesPending": sorted(state.topic_pending),
            "theoryFilesPending": sorted(state.theory_pending),
        }

    def rollback(
        self,
        transaction_id: str,
        *,
        dry_run: bool = False,
        conflict_policy: str = "preserve-user",
    ) -> dict[str, Any]:
        _validate_conflict_policy(conflict_policy)
        if dry_run:
            return self.transactions.rollback(
                transaction_id,
                dry_run=True,
                conflict_policy=conflict_policy,
            )
        with GlobalLock(self.vault_path, "base"):
            return self.transactions.rollback(
                transaction_id,
                conflict_policy=conflict_policy,
            )

    def _consider(
        self,
        relative: str,
        *,
        origin: str,
        required_type: str | None,
        state: _MigrationState,
        claimed_targets: set[str],
    ) -> None:
        try:
            original = self._snapshot_text(relative, state)
            document = parse_frontmatter(original)
        except (OSError, UnicodeError, ValueError) as exc:
            state.manual.append({"path": relative, "reasons": [f"unreadable Markdown: {exc}"]})
            self._mark_pending(origin, relative, state)
            return
        already_v3 = (
            document.fields.get("analysisSchemaVersion") == 1
            and document.fields.get("analysisType") in ANALYSIS_TYPES
            and document.fields.get("analysisId")
        )

        inferred_type = _infer_analysis_type(
            document.fields,
            PurePosixPath(relative).name,
        )
        if required_type is not None and inferred_type != required_type:
            self._mark_pending(origin, relative, state)
            return
        if inferred_type is None:
            state.manual.append(
                {"path": relative, "reasons": ["analysisType could not be inferred reliably"]}
            )
            self._mark_pending(origin, relative, state)
            return
        (
            cleaned_fields,
            field_evidence,
            field_assets,
            unsafe_user_fields,
        ) = _clean_fields(document.fields)
        (
            cleaned_body,
            body_evidence,
            body_assets,
            body_safety_reason,
        ) = _clean_analysis_body(document.body)
        safety_reasons: list[str] = []
        if unsafe_user_fields:
            safety_reasons.append(
                "removed Analysis anchors occur in user-owned frontmatter fields: "
                + ", ".join(unsafe_user_fields)
            )
        if body_safety_reason:
            safety_reasons.append(body_safety_reason)
        if safety_reasons:
            state.manual.append({"path": relative, "reasons": safety_reasons})
            self._mark_pending(origin, relative, state)
            return
        removed_evidence = field_evidence + body_evidence
        removed_assets = field_assets + body_assets
        removed_fields = [
            str(name)
            for name in document.fields
            if str(name).casefold() in REMOVED_ANALYSIS_FIELDS
        ]
        if already_v3:
            requires_cleanup = bool(
                removed_fields
                or removed_evidence
                or removed_assets
                or cleaned_body != document.body
            )
            if not requires_cleanup:
                state.skipped.append({"path": relative, "reason": "already-v3"})
                return
            if cleaned_fields.get("status") == "reviewed":
                cleaned_fields["status"] = "needs_update"
            try:
                self.analysis._validate_primary_source(cleaned_fields)
                self.analysis._validate_figure(cleaned_fields, cleaned_body)
                validated_existing = validate_analysis_fields(
                    cleaned_fields,
                    allow_reviewed=False,
                )
            except (AnalysisValidationError, OSError, UnicodeError) as exc:
                state.manual.append(
                    {
                        "path": relative,
                        "reasons": [f"already-v3 cleanup requires review: {exc}"],
                    }
                )
                self._mark_pending(origin, relative, state)
                return
            state.clean_in_place.append(
                (
                    relative,
                    compose_frontmatter(
                        validated_existing,
                        cleaned_body,
                        omit_empty=False,
                        field_order=ANALYSIS_FIELD_ORDER,
                    ),
                )
            )
            state.removed_evidence += removed_evidence
            state.removed_assets += removed_assets
            state.skipped.append(
                {
                    "path": relative,
                    "reason": "already-v3-cleaned",
                    "removedFields": sorted(removed_fields, key=str.casefold),
                }
            )
            return
        try:
            candidate = self._migration_fields(
                cleaned_fields,
                inferred_type,
                legacy_status=str(document.fields.get("analysisStatus") or ""),
            )
            identity = build_analysis_identity(candidate)
            candidate["analysisId"] = identity.analysis_id
            self.analysis._validate_primary_source(candidate)
            self.analysis._validate_figure(candidate, cleaned_body)
            validated = validate_analysis_fields(candidate, allow_reviewed=True)
        except (AnalysisValidationError, OSError, UnicodeError) as exc:
            state.manual.append({"path": relative, "reasons": [str(exc)]})
            self._mark_pending(origin, relative, state)
            return

        target = self.analysis.analysis_path(inferred_type, identity.filename)
        target_key = target.casefold()
        if target_key == relative.casefold() and target != relative:
            state.manual.append(
                {
                    "path": relative,
                    "reasons": [
                        f"case-only source/target mismatch requires manual review: {target}"
                    ],
                }
            )
            self._mark_pending(origin, relative, state)
            return
        if target_key in claimed_targets:
            state.manual.append(
                {"path": relative, "reasons": [f"multiple legacy notes target {target}"]}
            )
            self._mark_pending(origin, relative, state)
            return
        target_text = self._snapshot_optional_text(target, state)
        if target_text is not None and target != relative:
            target_document = parse_frontmatter(target_text)
            existing_id = target_document.fields.get("analysisId")
            state.manual.append(
                {
                    "path": relative,
                    "reasons": [
                        f"target already exists: {target}"
                        if existing_id != identity.analysis_id
                        else f"duplicate legacy source for existing {identity.analysis_id}"
                    ],
                }
            )
            self._mark_pending(origin, relative, state)
            return
        claimed_targets.add(target_key)
        migrated_text = compose_frontmatter(
            validated,
            cleaned_body,
            omit_empty=False,
            field_order=ANALYSIS_FIELD_ORDER,
        )
        state.removed_evidence += removed_evidence
        state.removed_assets += removed_assets
        state.migrated.append(
            _MigrationPlan(
                source=relative,
                target=target,
                text=migrated_text,
                analysis_id=identity.analysis_id,
                analysis_type=inferred_type,
                origin=origin,
                removed_evidence=removed_evidence,
                removed_assets=removed_assets,
            )
        )

    def _migration_fields(
        self,
        fields: Mapping[str, Any],
        analysis_type: str,
        *,
        legacy_status: str = "",
    ) -> dict[str, Any]:
        values = dict(fields)
        values["analysisSchemaVersion"] = 1
        values["analysisType"] = analysis_type
        values.setdefault("secondaryProfiles", [])
        values.setdefault("tags", [])
        if "status" not in values:
            values["status"] = "ready" if legacy_status == "verified" else "draft"
        if values.get("status") == "verified":
            values["status"] = "ready"
        if "primarySourceKey" not in values and values.get("zoteroKey"):
            values["primarySourceKey"] = values["zoteroKey"]
        if "sourceKeys" not in values and values.get("primarySourceKey"):
            values["sourceKeys"] = [values["primarySourceKey"]]
        source_keys = values.get("sourceKeys")
        if isinstance(source_keys, list):
            values["sourceCount"] = len(source_keys)
            values["sourceFingerprint"] = self.analysis.source_fingerprint(source_keys)
        primary = str(values.get("primarySourceKey") or "")
        if primary and not values.get("primarySource"):
            source = self.analysis._source_note(primary)
            values["primarySource"] = (
                f"[[{source[:-3] if source.casefold().endswith('.md') else source}]]"
            )
        values.setdefault("skillName", "analysis-migration")
        values.setdefault("skillVersion", "1")
        if analysis_type == "literature_review":
            values.setdefault("timeRange", "")
        elif analysis_type == "passage_qa":
            values.setdefault("sourceSubsection", "")
            values.setdefault("sourceParagraph", "")
        elif analysis_type == "figure_qa":
            values.setdefault("targetPanel", "")
            values.setdefault("page", "")
            values.setdefault("imagePath", "")
            values.setdefault("imageExists", False)
        elif analysis_type == "concept":
            values.setdefault("aliases", [])
            values.setdefault("prerequisites", [])
            values.setdefault("relatedConcepts", [])
        return values

    def _scan_legacy_knowledge_folder(
        self,
        relative_folder: str,
        *,
        origin: str,
        required_type: str,
        state: _MigrationState,
        claimed_targets: set[str],
    ) -> None:
        for relative in self._scan_markdown_folder(
            relative_folder,
            origin=origin,
            state=state,
        ):
            before = len(state.migrated)
            self._consider(
                relative,
                origin=origin,
                required_type=required_type,
                state=state,
                claimed_targets=claimed_targets,
            )
            if len(state.migrated) == before and relative not in (
                state.topic_pending if origin == "topic" else state.theory_pending
            ):
                self._mark_pending(origin, relative, state)

    def _stage_plans(self, transaction: Transaction, state: _MigrationState) -> None:
        migrated_sources = {plan.source.casefold() for plan in state.migrated}
        for plan in state.migrated:
            transaction.write_text(plan.target, plan.text)
            if plan.source.casefold() != plan.target.casefold():
                transaction.delete(plan.source)
        for path, text in state.clean_in_place:
            if path.casefold() not in migrated_sources:
                transaction.write_text(path, text)

    def _stage_old_index(
        self,
        transaction: Transaction,
        state: _MigrationState,
    ) -> bool:
        index_relative = f"{self.analysis.analysis_folder}/index.md"
        if state.analysis_pending:
            state.manual.append(
                {
                    "path": index_relative,
                    "reasons": [
                        "generated index was preserved because Analysis notes still require review"
                    ],
                }
            )
            return False
        text = self._snapshot_optional_text(index_relative, state)
        if text is None:
            return False
        if not _is_generated_index(text):
            state.manual.append(
                {
                    "path": index_relative,
                    "reasons": ["index.md is not clearly plugin-generated and was preserved"],
                }
            )
            return False
        transaction.delete(index_relative)
        return True

    def _scan_markdown_folder(
        self,
        relative_folder: str,
        *,
        origin: str,
        state: _MigrationState,
    ) -> list[str]:
        folder = normalize_vault_relative(relative_folder)
        try:
            files, rejected = self.fs.scan_owned_files(folder, recursive=True)
        except (OSError, ValueError) as exc:
            state.manual.append(
                {
                    "path": folder,
                    "reasons": [f"unsafe or unreadable migration folder: {exc}"],
                }
            )
            return []
        for relative in rejected:
            state.manual.append(
                {
                    "path": relative,
                    "reasons": [
                        "linked, reparse-backed, or non-regular path was not scanned"
                    ],
                }
            )
            self._mark_pending(origin, relative, state)
        return [
            relative
            for relative in files
            if PurePosixPath(relative).suffix.casefold() == ".md"
        ]

    def _snapshot_text(
        self,
        relative: str,
        state: _MigrationState,
    ) -> str:
        normalized = normalize_vault_relative(relative)
        content = self.fs.read_bytes_owned(normalized)
        digest = hashlib.sha256(content).hexdigest()
        if (
            normalized in state.snapshots
            and state.snapshots[normalized] != digest
        ):
            raise RuntimeError(f"migration source changed while planning: {normalized}")
        state.snapshots[normalized] = digest
        return content.decode("utf-8")

    def _snapshot_optional_text(
        self,
        relative: str,
        state: _MigrationState,
    ) -> str | None:
        normalized = normalize_vault_relative(relative)
        try:
            exists = self.fs.is_file_owned(normalized)
        except VaultPathSafetyError:
            raise
        if not exists:
            state.snapshots.setdefault(normalized, None)
            return None
        return self._snapshot_text(normalized, state)

    def _recheck_snapshots(self, snapshots: Mapping[str, str | None]) -> None:
        for relative, expected in sorted(
            snapshots.items(),
            key=lambda item: (item[0].casefold(), item[0]),
        ):
            if expected is None:
                if self.fs.is_file_owned(relative):
                    raise RuntimeError(
                        f"migration target appeared after planning: {relative}"
                    )
                continue
            try:
                digest = self.fs.sha256_owned(relative)
            except FileNotFoundError as exc:
                raise RuntimeError(
                    f"migration source disappeared after planning: {relative}"
                ) from exc
            if digest != expected:
                raise RuntimeError(
                    f"migration source changed after planning: {relative}"
                )

    @staticmethod
    def _mark_pending(origin: str, relative: str, state: _MigrationState) -> None:
        if origin == "analysis" and relative not in state.analysis_pending:
            state.analysis_pending.append(relative)
        elif origin == "topic" and relative not in state.topic_pending:
            state.topic_pending.append(relative)
        elif origin == "theory" and relative not in state.theory_pending:
            state.theory_pending.append(relative)


def _infer_analysis_type(fields: Mapping[str, Any], filename: str) -> str | None:
    explicit = fields.get("analysisType")
    if explicit in ANALYSIS_TYPES:
        return str(explicit)
    prefix = filename.upper()
    for marker, analysis_type in (
        ("FR-", "full_read"),
        ("RV-", "literature_review"),
        ("PQ-", "passage_qa"),
        ("FQ-", "figure_qa"),
        ("CP-", "concept"),
    ):
        if prefix.startswith(marker):
            return analysis_type
    if fields.get("zoteroKey") and any(
        name in fields
        for name in ("researchQuestion", "coreContribution", "methodSummary", "mainFinding")
    ):
        return "full_read"
    if fields.get("zoteroKey") and any(
        name in fields for name in ("analysisStatus", "evidenceStatus", "sourceNote")
    ):
        return "full_read"
    return None


_MANAGED_FIELD_NAMES = frozenset(name.casefold() for name in ANALYSIS_FIELD_ORDER)


def _clean_fields(
    fields: Mapping[str, Any],
) -> tuple[dict[str, Any], int, int, list[str]]:
    result: dict[str, Any] = {}
    evidence_count = 0
    asset_count = 0
    unsafe_user_fields: list[str] = []
    for name, value in fields.items():
        field_name = str(name)
        folded_name = field_name.casefold()
        if folded_name in REMOVED_ANALYSIS_FIELDS:
            continue
        if folded_name in _MANAGED_FIELD_NAMES:
            cleaned, removed_evidence, removed_assets = _clean_value(value)
            result[field_name] = cleaned
            evidence_count += removed_evidence
            asset_count += removed_assets
        else:
            result[field_name] = value
            if _value_contains_removed_markup(value):
                unsafe_user_fields.append(field_name)
    return (
        result,
        evidence_count,
        asset_count,
        sorted(unsafe_user_fields, key=lambda value: (value.casefold(), value)),
    )


def _clean_value(value: Any) -> tuple[Any, int, int]:
    if isinstance(value, str):
        return _clean_text(value)
    if isinstance(value, list):
        result: list[Any] = []
        evidence_count = 0
        asset_count = 0
        for item in value:
            cleaned, removed_evidence, removed_assets = _clean_value(item)
            result.append(cleaned)
            evidence_count += removed_evidence
            asset_count += removed_assets
        return result, evidence_count, asset_count
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        evidence_count = 0
        asset_count = 0
        for name, item in value.items():
            cleaned, removed_evidence, removed_assets = _clean_value(item)
            result[str(name)] = cleaned
            evidence_count += removed_evidence
            asset_count += removed_assets
        return result, evidence_count, asset_count
    return value, 0, 0


def _clean_text(value: str) -> tuple[str, int, int]:
    evidence_count = 0
    asset_count = 0

    def replace_reference(match: re.Match[str]) -> str:
        nonlocal evidence_count, asset_count
        if match.group(1).casefold() == "evidence":
            evidence_count += 1
        else:
            asset_count += 1
        return ""

    cleaned = _REFERENCE_RE.sub(replace_reference, value)
    cleaned = _BLOCK_ID_RE.sub(lambda match: match.group("prefix").rstrip(), cleaned)
    cleaned = _OLD_MARKER_RE.sub("", cleaned)
    return cleaned, evidence_count, asset_count


def _clean_analysis_body(value: str) -> tuple[str, int, int, str | None]:
    """Clean only the unique plugin-owned block and preserve all user text."""

    start_count = value.count(ANALYSIS_START_MARKER)
    end_count = value.count(ANALYSIS_END_MARKER)
    if start_count != end_count or start_count > 1:
        return (
            value,
            0,
            0,
            "invalid or duplicate Analysis managed block markers require manual review",
        )
    if start_count == 0:
        if _text_contains_removed_markup(value):
            return (
                value,
                0,
                0,
                "removed Analysis anchors occur outside a managed block; content was preserved",
            )
        return value, 0, 0, None

    start = value.index(ANALYSIS_START_MARKER)
    managed_start = start + len(ANALYSIS_START_MARKER)
    end = value.index(ANALYSIS_END_MARKER, managed_start)
    if start >= end:
        return (
            value,
            0,
            0,
            "invalid Analysis managed block marker order requires manual review",
        )
    finish = end + len(ANALYSIS_END_MARKER)
    outside = f"{value[:start]}{value[finish:]}"
    if _text_contains_removed_markup(outside):
        return (
            value,
            0,
            0,
            "removed Analysis anchors occur outside the managed block; user content was preserved",
        )
    cleaned, evidence_count, asset_count = _clean_text(
        value[managed_start:end]
    )
    return (
        f"{value[:managed_start]}{cleaned}{value[end:]}",
        evidence_count,
        asset_count,
        None,
    )


def _text_contains_removed_markup(value: str) -> bool:
    cleaned, _evidence_count, _asset_count = _clean_text(value)
    return cleaned != value


def _value_contains_removed_markup(value: Any) -> bool:
    if isinstance(value, str):
        return _text_contains_removed_markup(value)
    if isinstance(value, list):
        return any(_value_contains_removed_markup(item) for item in value)
    if isinstance(value, Mapping):
        return any(_value_contains_removed_markup(item) for item in value.values())
    return False


def _is_generated_index(text: str) -> bool:
    lowered = text.casefold()
    start = "<!-- ovm:analysis-index:start -->"
    end = "<!-- ovm:analysis-index:end -->"
    if lowered.count(start) == 1 and lowered.count(end) == 1:
        start_index = lowered.index(start)
        end_index = lowered.index(end, start_index)
        if start_index >= end_index:
            return False
        outside = f"{text[:start_index]}{text[end_index + len(end):]}"
        if not outside.strip():
            return True
    return False


def _validate_conflict_policy(value: str) -> None:
    if value not in _CONFLICT_POLICIES:
        raise ValueError(
            f"conflict_policy must be one of: {', '.join(sorted(_CONFLICT_POLICIES))}"
        )
