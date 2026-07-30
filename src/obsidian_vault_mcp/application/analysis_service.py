"""Transactional read/write service for the five V3 Analysis note types."""

from __future__ import annotations

import hashlib
import os
import re
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from ..adapters.vault.filesystem import VaultFilesystem, VaultPathSafetyError
from ..config.loader import load_config
from ..domain.analysis import (
    ANALYSIS_END_MARKER,
    ANALYSIS_FIELD_ORDER,
    ANALYSIS_START_MARKER,
    ANALYSIS_TYPES,
    REMOVED_ANALYSIS_FIELDS,
    AnalysisValidationError,
    build_analysis_identity,
    combined_source_fingerprint,
    markdown_source_fingerprint,
    metadata_source_fingerprint,
    normalize_identity_text,
    validate_analysis_fields,
)
from ..domain.errors import TransactionConflictError
from ..domain.frontmatter import compose_frontmatter, merge_frontmatter, parse_frontmatter
from ..domain.identity import validate_zotero_key
from ..domain.paths import (
    VaultPaths,
    naming_metadata_from_fields,
    normalize_vault_relative,
)
from .transaction_service import TransactionService

_CONFLICT_POLICIES = frozenset({"preserve-user", "overwrite-managed", "fail"})
_IMAGE_EMBED_RE = re.compile(r"!\[\[[^\]]+\]\]|!\[[^\]]*\]\([^)]+\)|!\[[^\]]*\]\s*\[[^\]]*\]")
_HTML_IMAGE_RE = re.compile(r"<\s*img\b", re.IGNORECASE)
_REMOVED_REFERENCE_RE = re.compile(r"\[\[(?:evidence|asset):", re.IGNORECASE)
_REMOVED_BLOCK_ID_RE = re.compile(r"(?m)(?:^|\s)\^ev-[A-Za-z0-9_-]+(?:\s*$)")

_ANALYSIS_PATH_DEFAULTS = {
    "folder": "Literature/Analysis",
    "base": "Literature/Analysis/Analysis.base",
    "fullReadsFolder": "Literature/Analysis/full-reads",
    "reviewsFolder": "Literature/Analysis/reviews",
    "passageQaFolder": "Literature/Analysis/qa/passages",
    "figureQaFolder": "Literature/Analysis/qa/figures",
    "conceptsFolder": "Literature/Analysis/concepts",
}
_ANALYSIS_TYPE_FOLDER_KEYS = {
    "full_read": "fullReadsFolder",
    "literature_review": "reviewsFolder",
    "passage_qa": "passageQaFolder",
    "figure_qa": "figureQaFolder",
    "concept": "conceptsFolder",
}


class AnalysisService:
    """Validate, locate, and transactionally persist V3 Analysis notes."""

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
        self.fs = VaultFilesystem(self.vault_path)
        self.config = dict(config) if config is not None else load_config(self.vault_path, require_exists=False)
        self.paths = VaultPaths(self.vault_path, self.config)
        self.transactions = transaction_service or TransactionService(self.vault_path)
        self._now = now or _utc_now
        self.analysis_folder = self._analysis_path("folder")
        self.analysis_base_path = self._analysis_path("base")
        self.literature_root = _config_path(
            self.config,
            "literature",
            "root",
            default="Literature",
        )
        self._validate_analysis_layout()

    def write(
        self,
        fields: Mapping[str, Any],
        managed_content: str,
        *,
        dry_run: bool = False,
        transaction_id: str | None = None,
        conflict_policy: str = "preserve-user",
        reviewed_by_user: bool = False,
    ) -> dict[str, Any]:
        """Write one Analysis note while preserving every user-owned region."""

        _validate_conflict_policy(conflict_policy)
        _validate_managed_content(managed_content)
        if not isinstance(fields, Mapping):
            raise AnalysisValidationError("analysis fields must be an object")
        incoming = dict(fields)
        removed_incoming = sorted(str(name) for name in incoming if str(name).casefold() in REMOVED_ANALYSIS_FIELDS)
        if removed_incoming:
            raise AnalysisValidationError(f"removed V2 Analysis field is not supported: {removed_incoming[0]}")
        provisional = dict(incoming)
        if "analysisType" not in provisional:
            raise AnalysisValidationError("missing common Analysis field: analysisType")
        analysis_type = str(provisional["analysisType"])
        if analysis_type not in ANALYSIS_TYPES:
            raise AnalysisValidationError(f"unsupported analysisType: {analysis_type}")

        # Identity can be derived before locating an existing file because its
        # inputs are immutable by contract.
        provisional.setdefault("analysisId", "")
        if not provisional["analysisId"]:
            provisional["analysisId"] = build_analysis_identity(provisional).analysis_id
        identity = build_analysis_identity(provisional)
        if provisional["analysisId"] != identity.analysis_id:
            raise AnalysisValidationError(f"analysisId must match stable identity {identity.analysis_id}")
        relative_path = self.analysis_path(analysis_type, identity.filename)
        try:
            existing_bytes = self.fs.read_bytes_owned(relative_path)
        except FileNotFoundError:
            existing_bytes = None
        except (OSError, VaultPathSafetyError) as exc:
            raise AnalysisValidationError(
                f"unsafe Analysis target path: {relative_path}"
            ) from exc
        existing_text = (
            existing_bytes.decode("utf-8")
            .replace("\r\n", "\n")
            .replace("\r", "\n")
            if existing_bytes is not None
            else ""
        )
        expected_target_sha256 = (
            hashlib.sha256(existing_bytes).hexdigest()
            if existing_bytes is not None
            else None
        )
        existing_document = parse_frontmatter(existing_text) if existing_text else None
        if existing_document is not None and conflict_policy == "fail":
            raise TransactionConflictError(
                f"Analysis note already exists: {relative_path}",
                stage="plan",
            )
        if existing_document is not None:
            existing_id = str(existing_document.fields.get("analysisId") or "")
            if existing_id and existing_id != identity.analysis_id:
                raise AnalysisValidationError(f"Analysis path is owned by a different analysisId: {existing_id}")
            if not existing_id and conflict_policy != "overwrite-managed":
                raise AnalysisValidationError("Analysis target has no analysisId; use overwrite-managed only after review")
        duplicate_paths = [item["path"] for item in self._scan() if item["analysisId"] == identity.analysis_id and item["path"] != relative_path]
        if duplicate_paths:
            raise AnalysisValidationError(f"duplicate analysisId {identity.analysis_id}: {', '.join(duplicate_paths)}")

        old_fields = existing_document.fields if existing_document is not None else {}
        preserved_old_fields = {name: value for name, value in old_fields.items() if str(name).casefold() not in REMOVED_ANALYSIS_FIELDS}
        merged = merge_frontmatter(
            preserved_old_fields,
            incoming,
            omit_empty=False,
            preserve_unknown_fields=True,
            field_order=ANALYSIS_FIELD_ORDER,
        )
        merged["analysisSchemaVersion"] = 1
        merged["analysisId"] = identity.analysis_id
        merged.setdefault("status", "ready")
        merged.setdefault("secondaryProfiles", [])
        merged.setdefault("tags", [])

        source_keys = _source_key_values(merged.get("sourceKeys"))
        current_fingerprint = self.source_fingerprint(source_keys)
        supplied_fingerprint = incoming.get("sourceFingerprint")
        if supplied_fingerprint not in {None, ""} and str(supplied_fingerprint).lower() != current_fingerprint:
            raise AnalysisValidationError("sourceFingerprint does not match the current source documents")
        merged["sourceFingerprint"] = current_fingerprint
        self._validate_primary_source(merged)
        self._validate_figure(merged, managed_content)
        old_body = existing_document.body if existing_document is not None else ""
        next_body = replace_analysis_block(old_body, managed_content)
        old_fingerprint = str(old_fields.get("sourceFingerprint") or "").lower()
        if old_fingerprint and old_fingerprint != current_fingerprint and next_body == old_body:
            merged["status"] = "needs_update"

        old_semantic = {name: value for name, value in preserved_old_fields.items() if name not in {"createdAt", "updatedAt"}}
        next_semantic = {name: value for name, value in merged.items() if name not in {"createdAt", "updatedAt"}}
        managed_change_requires_review = next_body != old_body or next_semantic != old_semantic
        if (
            str(old_fields.get("status") or "") == "reviewed"
            and "status" not in incoming
            and not reviewed_by_user
            and managed_change_requires_review
            and merged.get("status") == "reviewed"
        ):
            merged["status"] = "ready"

        timestamp = _validated_now(self._now())
        old_created = str(old_fields.get("createdAt") or "")
        old_updated = str(old_fields.get("updatedAt") or "")
        merged["createdAt"] = old_created or str(merged.get("createdAt") or timestamp)
        merged["updatedAt"] = old_updated or str(merged.get("updatedAt") or timestamp)

        review_was_preserved = str(old_fields.get("status") or "") == "reviewed" and "status" not in incoming and not managed_change_requires_review
        allow_reviewed = reviewed_by_user or review_was_preserved
        validated = validate_analysis_fields(merged, allow_reviewed=allow_reviewed)
        next_fields = merge_frontmatter(
            preserved_old_fields,
            validated,
            omit_empty=False,
            preserve_unknown_fields=True,
            field_order=ANALYSIS_FIELD_ORDER,
        )
        candidate = compose_frontmatter(
            next_fields,
            next_body,
            omit_empty=False,
            field_order=ANALYSIS_FIELD_ORDER,
        )

        if candidate != existing_text:
            next_fields["updatedAt"] = timestamp
            validated = validate_analysis_fields(next_fields, allow_reviewed=allow_reviewed)
            candidate = compose_frontmatter(
                merge_frontmatter(
                    preserved_old_fields,
                    validated,
                    omit_empty=False,
                    preserve_unknown_fields=True,
                    field_order=ANALYSIS_FIELD_ORDER,
                ),
                next_body,
                omit_empty=False,
                field_order=ANALYSIS_FIELD_ORDER,
            )

        transaction = self.transactions.begin(
            item_key=sorted(source_keys)[0],
            transaction_id=transaction_id,
            dry_run=dry_run,
        )
        transaction.write_text(relative_path, candidate)
        transaction.guard(
            lambda: self._assert_target_snapshot(
                relative_path,
                expected_target_sha256,
            )
        )
        committed = transaction.commit()
        return {
            **committed,
            "analysisId": identity.analysis_id,
            "analysisType": analysis_type,
            "analysisPath": relative_path,
            "sourceFingerprint": current_fingerprint,
            "updatedAt": str(validated["updatedAt"]),
        }

    def get(
        self,
        *,
        analysis_id: str | None = None,
        analysis_type: str | None = None,
        source_key: str | None = None,
        question: str | None = None,
    ) -> dict[str, Any]:
        """Query by id, type, source key, or normalized duplicate question."""

        if analysis_type is not None and analysis_type not in ANALYSIS_TYPES:
            raise AnalysisValidationError(f"unsupported analysisType: {analysis_type}")
        if source_key is not None:
            try:
                source_key = validate_zotero_key(source_key)
            except ValueError as exc:
                raise AnalysisValidationError(str(exc)) from exc
        normalized_question = normalize_identity_text(question) if question is not None else ""
        warnings: list[dict[str, str]] = []
        scanned = self._scan(include_body=True, warnings=warnings)
        duplicate_ids: dict[str, list[str]] = defaultdict(list)
        for item in scanned:
            duplicate_ids[item["analysisId"]].append(item["path"])
        duplicates = {key: paths for key, paths in sorted(duplicate_ids.items()) if key and len(paths) > 1}
        if analysis_id and analysis_id in duplicates:
            raise AnalysisValidationError(f"duplicate analysisId {analysis_id}: {', '.join(duplicates[analysis_id])}")

        analyses: list[dict[str, Any]] = []
        for item in scanned:
            if analysis_id is not None and item["analysisId"] != analysis_id:
                continue
            if analysis_type is not None and item["analysisType"] != analysis_type:
                continue
            if source_key is not None and source_key not in item["sourceKeys"]:
                continue
            item_question = _analysis_question(item["fields"])
            if question is not None and normalize_identity_text(item_question) != normalized_question:
                continue
            analyses.append(self._with_source_state(item, warnings=warnings))
        analyses.sort(key=lambda item: (str(item["analysisType"]), str(item["analysisId"])))
        result: dict[str, Any] = {
            "ok": True,
            "count": len(analyses),
            "analyses": analyses,
            "duplicates": duplicates,
            "duplicateQuestion": question is not None and len(analyses) > 1,
            "warnings": sorted(
                warnings,
                key=lambda item: (
                    item["code"],
                    item["path"],
                    item["message"],
                ),
            ),
        }
        if analysis_id is not None:
            result["analysis"] = analyses[0] if len(analyses) == 1 else None
        return result

    def source_fingerprint(self, source_keys: Sequence[str]) -> str:
        """Calculate the persisted source fingerprint for one or more keys."""

        keys = _source_key_values(source_keys)
        fingerprints = {key: self._source_fingerprint(key) for key in keys}
        return combined_source_fingerprint(fingerprints)

    def analysis_path(self, analysis_type: str, filename: str) -> str:
        if analysis_type not in ANALYSIS_TYPES:
            raise AnalysisValidationError(f"unsupported analysisType: {analysis_type}")
        if PurePosixPath(filename).name != filename or not filename.endswith(".md"):
            raise AnalysisValidationError("Analysis filename must be one portable Markdown filename")
        folder_key = _ANALYSIS_TYPE_FOLDER_KEYS[analysis_type]
        return normalize_vault_relative(f"{self._analysis_path(folder_key)}/{filename}")

    def rollback(
        self,
        transaction_id: str,
        *,
        dry_run: bool = False,
        conflict_policy: str = "preserve-user",
    ) -> dict[str, Any]:
        _validate_conflict_policy(conflict_policy)
        return self.transactions.rollback(
            transaction_id,
            dry_run=dry_run,
            conflict_policy=conflict_policy,
        )

    def _source_fingerprint(self, key: str) -> str:
        main_note = self._source_note(key)
        try:
            document = parse_frontmatter(self.fs.read_text_owned(main_note))
        except VaultPathSafetyError as exc:
            raise AnalysisValidationError(f"unsafe source note path: {exc.relative_path}") from exc
        mineru = self.paths.mineru_markdown(
            key,
            **naming_metadata_from_fields(document.fields),
        )
        try:
            if self.fs.is_file_owned(mineru):
                return markdown_source_fingerprint(self.fs.read_text_owned(mineru))
        except VaultPathSafetyError as exc:
            raise AnalysisValidationError(f"unsafe MinerU source path: {exc.relative_path}") from exc
        return metadata_source_fingerprint(document.fields)

    def _assert_target_snapshot(
        self,
        relative_path: str,
        expected_sha256: str | None,
    ) -> None:
        if expected_sha256 is None:
            try:
                target_exists = self.fs.is_file_owned(relative_path)
            except (OSError, VaultPathSafetyError) as exc:
                raise RuntimeError(
                    f"Analysis target became unsafe after planning: {relative_path}"
                ) from exc
            if target_exists:
                raise RuntimeError(
                    f"Analysis target appeared after planning: {relative_path}"
                )
            return
        try:
            actual = self.fs.sha256_owned(relative_path)
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"Analysis target disappeared after planning: {relative_path}"
            ) from exc
        except (OSError, VaultPathSafetyError) as exc:
            raise RuntimeError(
                f"Analysis target became unsafe after planning: {relative_path}"
            ) from exc
        if actual != expected_sha256:
            raise RuntimeError(
                f"Analysis target changed after planning: {relative_path}"
            )

    def _source_note(self, key: str) -> str:
        try:
            validated = validate_zotero_key(key)
        except ValueError as exc:
            raise AnalysisValidationError(str(exc)) from exc
        exact = normalize_vault_relative(f"{self.literature_root}/{validated}.md")
        try:
            if self.fs.is_file_owned(exact):
                return exact
            candidates, rejected = self.fs.scan_owned_files(
                self.literature_root,
                recursive=False,
            )
        except VaultPathSafetyError as exc:
            raise AnalysisValidationError(f"unsafe source note path: {exc.relative_path}") from exc
        rejected_markdown = [relative for relative in rejected if PurePosixPath(relative).suffix.lower() == ".md"]
        if rejected_markdown:
            raise AnalysisValidationError(f"unsafe source note candidate: {rejected_markdown[0]}")
        matches: list[str] = []
        for candidate in candidates:
            if PurePosixPath(candidate).suffix.lower() != ".md":
                continue
            try:
                document = parse_frontmatter(self.fs.read_text_owned(candidate))
            except VaultPathSafetyError as exc:
                raise AnalysisValidationError(f"unsafe source note path: {exc.relative_path}") from exc
            except (OSError, UnicodeError, ValueError):
                continue
            if document.fields.get("zoteroKey") == validated:
                matches.append(candidate)
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise AnalysisValidationError(f"multiple source notes have zoteroKey {validated}")
        raise AnalysisValidationError(f"sourceKey does not exist in the Vault: {validated}")

    def _validate_primary_source(self, fields: Mapping[str, Any]) -> None:
        key = str(fields.get("primarySourceKey") or "")
        if not key:
            return
        source = self._source_note(key)
        target = source[:-3] if source.casefold().endswith(".md") else source
        expected = f"[[{target}]]"
        if fields.get("primarySource") != expected:
            raise AnalysisValidationError(f"primarySource must be {expected}")

    def _validate_figure(self, fields: Mapping[str, Any], managed_content: str) -> None:
        if fields.get("analysisType") != "figure_qa":
            return
        raw_path = fields.get("imagePath")
        if not isinstance(raw_path, str):
            raise AnalysisValidationError("imagePath must be a string")
        path_exists = False
        if raw_path:
            normalized = normalize_vault_relative(raw_path)
            try:
                path_exists = self.fs.is_file_owned(normalized)
            except VaultPathSafetyError as exc:
                raise AnalysisValidationError(f"unsafe Figure Q&A imagePath: {exc.relative_path}") from exc
        declared = fields.get("imageExists")
        if type(declared) is not bool or declared != path_exists:
            raise AnalysisValidationError("imageExists must match the actual imagePath filesystem state")
        if _HTML_IMAGE_RE.search(managed_content):
            raise AnalysisValidationError("Figure Q&A HTML image embeds are not supported; use the validated imagePath")
        if not declared and _IMAGE_EMBED_RE.search(managed_content):
            raise AnalysisValidationError("missing-image Figure Q&A must not embed an image")

    def _with_source_state(
        self,
        item: dict[str, Any],
        *,
        warnings: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        result = dict(item)
        fields = dict(item["fields"])
        result.update(fields)
        try:
            current = self.source_fingerprint(fields.get("sourceKeys") or ())
            changed = current != str(fields.get("sourceFingerprint") or "").lower()
            result["currentSourceFingerprint"] = current
        except (AnalysisValidationError, OSError, UnicodeError) as exc:
            changed = True
            result["sourceError"] = str(exc)
            result["currentSourceFingerprint"] = None
            message = str(exc)
            if warnings is not None and message.startswith("unsafe "):
                relative = message.rsplit(": ", 1)[-1]
                warnings.append(_analysis_warning(relative, message))
        result["sourceChanged"] = changed
        result["storedStatus"] = fields.get("status")
        result["effectiveStatus"] = "needs_update" if changed else fields.get("status")
        if changed:
            result["status"] = "needs_update"
        return result

    def _scan(
        self,
        *,
        include_body: bool = False,
        warnings: list[dict[str, str]] | None = None,
    ) -> list[dict[str, Any]]:
        try:
            candidates, rejected = self.fs.scan_owned_files(
                self.analysis_folder,
                recursive=True,
            )
        except VaultPathSafetyError as exc:
            if warnings is None:
                raise AnalysisValidationError(f"unsafe Analysis scan path: {exc.relative_path}") from exc
            warnings.append(_analysis_warning(exc.relative_path, str(exc)))
            return []
        if rejected:
            if warnings is None:
                raise AnalysisValidationError(f"unsafe Analysis candidate: {rejected[0]}")
            warnings.extend(
                _analysis_warning(
                    relative,
                    "Analysis scan skipped a linked, reparse, or non-regular path",
                )
                for relative in rejected
            )
        result: list[dict[str, Any]] = []
        for relative in candidates:
            if PurePosixPath(relative).suffix.lower() != ".md":
                continue
            try:
                document = parse_frontmatter(self.fs.read_text_owned(relative))
            except VaultPathSafetyError as exc:
                if warnings is None:
                    raise AnalysisValidationError(f"unsafe Analysis candidate: {exc.relative_path}") from exc
                warnings.append(_analysis_warning(exc.relative_path, str(exc)))
                continue
            except (OSError, UnicodeError, ValueError) as exc:
                if warnings is not None:
                    warnings.append(
                        {
                            "code": "unreadable-analysis",
                            "path": relative,
                            "message": str(exc),
                        }
                    )
                continue
            analysis_id = document.fields.get("analysisId")
            analysis_type = document.fields.get("analysisType")
            if not isinstance(analysis_id, str) or not analysis_id:
                continue
            if analysis_type not in ANALYSIS_TYPES:
                continue
            source_keys = document.fields.get("sourceKeys")
            source_keys = list(source_keys) if isinstance(source_keys, list) else []
            item = {
                "analysisId": analysis_id,
                "analysisType": analysis_type,
                "sourceKeys": source_keys,
                "path": relative,
                "fields": dict(document.fields),
            }
            if include_body:
                item["body"] = document.body
            result.append(item)
        return result

    def _analysis_path(self, name: str) -> str:
        return _config_path(
            self.config,
            "analysis",
            name,
            default=_ANALYSIS_PATH_DEFAULTS[name],
        )

    def _validate_analysis_layout(self) -> None:
        root = PurePosixPath(self.analysis_folder)
        for name in (*_ANALYSIS_TYPE_FOLDER_KEYS.values(), "base"):
            path = PurePosixPath(self._analysis_path(name))
            try:
                path.relative_to(root)
            except ValueError as exc:
                raise AnalysisValidationError(f"analysis.{name} must stay inside analysis.folder") from exc


def replace_analysis_block(body: str, managed_content: str) -> str:
    """Replace only the one plugin-owned Analysis block in a Markdown body."""

    if not isinstance(body, str) or not isinstance(managed_content, str):
        raise AnalysisValidationError("Analysis body and managed content must be strings")
    _validate_managed_content(managed_content)
    normalized = body.replace("\r\n", "\n").replace("\r", "\n")
    start_count = normalized.count(ANALYSIS_START_MARKER)
    end_count = normalized.count(ANALYSIS_END_MARKER)
    if start_count != end_count or start_count > 1:
        raise AnalysisValidationError("invalid or duplicate Analysis managed block markers")
    rendered_content = managed_content.rstrip("\n")
    rendered = f"{ANALYSIS_START_MARKER}\n{rendered_content}\n{ANALYSIS_END_MARKER}" if rendered_content else f"{ANALYSIS_START_MARKER}\n{ANALYSIS_END_MARKER}"
    if start_count:
        start = normalized.index(ANALYSIS_START_MARKER)
        end = normalized.index(ANALYSIS_END_MARKER, start)
        if start >= end:
            raise AnalysisValidationError("invalid Analysis managed block marker order")
        finish = end + len(ANALYSIS_END_MARKER)
        return normalized[:start] + rendered + normalized[finish:]
    if not normalized:
        return rendered + "\n"
    separator = "\n\n" if not normalized.startswith("\n") else "\n"
    return f"{rendered}{separator}{normalized}"


def _validate_managed_content(value: str) -> None:
    if not isinstance(value, str):
        raise AnalysisValidationError("managed content must be a string")
    if ANALYSIS_START_MARKER in value or ANALYSIS_END_MARKER in value:
        raise AnalysisValidationError("managed content must not contain a managed block marker")
    if _REMOVED_REFERENCE_RE.search(value):
        raise AnalysisValidationError("Analysis content must not contain removed reference anchors")
    if _REMOVED_BLOCK_ID_RE.search(value):
        raise AnalysisValidationError("Analysis content must not contain removed block ids")


def _validate_conflict_policy(value: str) -> None:
    if value not in _CONFLICT_POLICIES:
        raise ValueError(f"conflict_policy must be one of: {', '.join(sorted(_CONFLICT_POLICIES))}")


def _source_key_values(value: Any) -> list[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise AnalysisValidationError("sourceKeys must be an array of Zotero keys")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise AnalysisValidationError("sourceKeys must contain strings")
        try:
            key = validate_zotero_key(item.strip())
        except ValueError as exc:
            raise AnalysisValidationError(str(exc)) from exc
        if key in result:
            raise AnalysisValidationError("sourceKeys must not contain duplicates")
        result.append(key)
    if not result:
        raise AnalysisValidationError("sourceKeys cannot be empty")
    return result


def _analysis_question(fields: Mapping[str, Any]) -> str:
    for name in ("question", "reviewQuestion"):
        value = fields.get(name)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def _analysis_warning(path: str, message: str) -> dict[str, str]:
    return {
        "code": "unsafe-vault-path",
        "path": path,
        "message": message,
    }


def _config_path(
    config: Mapping[str, Any],
    section: str,
    name: str,
    *,
    default: str,
) -> str:
    section_value = config.get(section)
    raw = section_value.get(name, default) if isinstance(section_value, Mapping) else default
    if not isinstance(raw, str):
        raise AnalysisValidationError(f"{section}.{name} must be a Vault-relative path")
    return normalize_vault_relative(raw)


def _validated_now(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AnalysisValidationError("now() must return an ISO-8601 timestamp")
    normalized = value.strip()
    try:
        datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AnalysisValidationError("now() must return an ISO-8601 timestamp") from exc
    return normalized


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
