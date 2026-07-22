"""Transactional migration from the focused V1 layout to the stable-key V2 layout."""

from __future__ import annotations

import hashlib
import json
import os
import posixpath
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urlparse

from ..adapters.obsidian.base_renderer import render_base
from ..adapters.obsidian.index_renderer import render_index
from ..adapters.obsidian.markdown_renderer import render_note_body
from ..config.defaults import CONFIG_FILENAME
from ..config.loader import load_config
from ..domain.frontmatter import compose_frontmatter, merge_frontmatter, parse_frontmatter
from ..domain.identity import validate_zotero_key
from ..domain.models import ItemState
from ..domain.paths import VaultPaths, to_vault_relative
from .index_service import IndexService
from .transaction_service import Transaction, TransactionService

_CONFLICT_POLICIES = {"preserve-user", "overwrite-managed", "fail", "rename"}
_WINDOWS_ABSOLUTE = re.compile(r"^[A-Za-z]:[\\/]")
_WIKILINK = re.compile(r"(!?\[\[)([^\]|#]+)(#[^\]|]*)?(\|[^\]]*)?(\]\])")
_MARKDOWN_LINK = re.compile(r"(!?\[[^\]]*\]\(\s*)(<[^>]+>|[^\s)]+)([^)]*\))")
_WIKI_IMAGE = re.compile(r"!\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")
_MARKDOWN_IMAGE = re.compile(r"!\[[^\]]*\]\(\s*(?:<([^>]+)>|([^\s)]+))")
_IMAGE_EXTENSIONS = {".avif", ".gif", ".jpeg", ".jpg", ".png", ".svg", ".tif", ".tiff", ".webp"}

_V1_PLUGIN_FIELDS = {
    "type",
    "title",
    "authors",
    "year",
    "doi",
    "publicationTitle",
    "abstract",
    "zoteroKey",
    "zoteroVersion",
    "zoteroSelect",
    "zoteroPdfKeys",
    "zoteroPdfLinks",
    "zoteroAttachmentPaths",
    "attachments",
    "attachmentLinks",
    "pdfStatus",
    "attachmentErrors",
    "mineruStatus",
    "mineruError",
    "mineruExtractedAt",
    "mineruMarkdown",
    "mineruMarkdownLink",
    "mineruImagesFolder",
    "mineruImagesIndex",
    "mineruImagesIndexLink",
    "mineruImageRenameStatus",
}
_MINERU_PLUGIN_FIELDS = _V1_PLUGIN_FIELDS | {
    "parent",
    "parentLink",
    "sourcePdf",
    "sourcePdfLink",
    "imagesFolder",
    "imagesIndex",
    "imagesIndexLink",
}
_RUNTIME_FIELDS = {
    "error",
    "errors",
    "importStatus",
    "lastImportedAt",
    "lastSyncedAt",
    "pipelineStatus",
    "runtimeStatus",
    "sourceHash",
    "sourcePdfSha256",
    "syncStatus",
}


@dataclass(frozen=True)
class _LegacyNote:
    key: str
    source: Path
    source_relative: str
    text: str
    fields: dict[str, Any]
    body: str


@dataclass
class _Move:
    key: str
    kind: str
    source: Path
    target: str

    @property
    def source_id(self) -> str:
        return str(self.source.resolve(strict=False)).casefold()

    def as_dict(self, vault: Path) -> dict[str, Any]:
        return {
            "zoteroKey": self.key,
            "kind": self.kind,
            "from": _display_source(vault, self.source),
            "to": self.target,
        }


@dataclass
class _ItemPlan:
    note: _LegacyNote
    note_target: str
    pdf: _Move | None = None
    mineru: _Move | None = None
    images: list[_Move] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    note_text: str = ""
    mineru_text: str = ""
    state_text: str = ""
    record: dict[str, Any] = field(default_factory=dict)

    def moves(self) -> list[_Move]:
        result = [_Move(self.note.key, "note", self.note.source, self.note_target)]
        if self.pdf:
            result.append(self.pdf)
        if self.mineru:
            result.append(self.mineru)
        result.extend(self.images)
        return result

    def as_dict(self, vault: Path) -> dict[str, Any]:
        return {
            "zoteroKey": self.note.key,
            "sourceNote": self.note.source_relative,
            "targetNote": self.note_target,
            "pdfPath": self.pdf.target if self.pdf else None,
            "mineruPath": self.mineru.target if self.mineru else None,
            "imagePaths": [image.target for image in self.images],
            "warnings": list(self.warnings),
            "moves": [move.as_dict(vault) for move in self.moves()],
        }


class MigrationService:
    """Plan, apply, and roll back one complete V1-to-V2 Vault migration."""

    def __init__(
        self,
        vault_path: str | os.PathLike[str],
        config: Mapping[str, Any] | None = None,
        *,
        transaction_service: TransactionService | None = None,
    ) -> None:
        self.vault_path = Path(vault_path).expanduser().resolve()
        if not self.vault_path.is_dir():
            raise NotADirectoryError(f"Vault root is not a directory: {self.vault_path}")
        self.config = dict(config) if config is not None else load_config(self.vault_path, require_exists=False)
        self.config_path = self.vault_path / CONFIG_FILENAME
        self.paths = VaultPaths(self.vault_path, self.config)
        self.transactions = transaction_service or TransactionService(self.vault_path)

    def migrate(
        self,
        dry_run: bool = True,
        apply: bool = False,
        transaction_id: str | None = None,
        conflict_policy: str = "preserve-user",
    ) -> dict[str, Any]:
        """Preview by default; apply only when ``apply`` is true and ``dry_run`` is false."""

        if conflict_policy not in _CONFLICT_POLICIES:
            raise ValueError(f"unsupported conflict policy: {conflict_policy}")
        execute = bool(apply and not dry_run)
        transaction = self.transactions.begin(transaction_id=transaction_id, dry_run=not execute)
        notes, skipped = self._scan_legacy_notes()
        duplicates, unique_notes = _split_duplicates(notes)
        conflicts: list[dict[str, Any]] = [
            {
                "type": "duplicate-zotero-key",
                "zoteroKey": group[0].key,
                "sources": [note.source_relative for note in group],
                "message": "multiple V1 top-level notes share the same zoteroKey",
            }
            for group in duplicates
        ]

        plans = [self._discover_item(note) for note in unique_notes]
        moves = [move for plan in plans for move in plan.moves()]
        conflicts.extend(self._target_conflicts(moves, conflict_policy))
        _synchronize_move_targets(plans, moves)
        conflicts.extend(_move_graph_conflicts(moves, self.vault_path))
        warnings = [warning for plan in plans for warning in plan.warnings]
        report = self._report(
            transaction,
            execute=execute,
            conflict_policy=conflict_policy,
            plans=plans,
            conflicts=conflicts,
            duplicates=duplicates,
            skipped=skipped,
            warnings=warnings,
        )
        if conflicts:
            return {**report, "ok": False, "canApply": False, "status": "conflict", "changeCount": 0, "operations": []}
        if not plans:
            return {**report, "ok": True, "canApply": True, "status": "noop", "changeCount": 0, "operations": []}

        self._render_plans(plans, moves, transaction.transaction_id)
        rewritten = self._stage_transaction(transaction, plans, moves)
        committed = transaction.commit()
        return {
            **report,
            **committed,
            "ok": True,
            "canApply": True,
            "dryRun": not execute,
            "applied": execute,
            "rewrittenMarkdown": rewritten,
        }

    migrate_v1_to_v2 = migrate

    def rollback(self, transaction_id: str) -> dict[str, Any]:
        """Restore every file from the transaction service's complete backup."""

        return self.transactions.rollback(transaction_id)

    rollback_transaction = rollback

    def _scan_legacy_notes(self) -> tuple[list[_LegacyNote], list[dict[str, Any]]]:
        legacy_root = self.vault_path / "literature"
        if not legacy_root.is_dir():
            return [], []
        notes: list[_LegacyNote] = []
        skipped: list[dict[str, Any]] = []
        for path in sorted(legacy_root.glob("*.md"), key=lambda candidate: candidate.name.casefold()):
            try:
                text = path.read_text(encoding="utf-8-sig")
                document = parse_frontmatter(text)
            except Exception as exc:
                skipped.append({"path": _relative(self.vault_path, path), "reason": "invalid-markdown", "error": str(exc)})
                continue
            raw_key = document.fields.get("zoteroKey")
            if raw_key is None or not str(raw_key).strip():
                skipped.append({"path": _relative(self.vault_path, path), "reason": "missing-zotero-key"})
                continue
            try:
                key = validate_zotero_key(str(raw_key))
            except ValueError as exc:
                skipped.append({"path": _relative(self.vault_path, path), "reason": "invalid-zotero-key", "error": str(exc)})
                continue
            metadata = _filename_metadata(document.fields)
            canonical = self.paths.note(key, **metadata)
            relative = _relative(self.vault_path, path)
            if self._state_points_to(key, relative) or (
                "<!-- ovm:" in document.body and relative.casefold() == canonical.casefold()
            ):
                skipped.append({"path": _relative(self.vault_path, path), "reason": "already-v2", "zoteroKey": key})
                continue
            notes.append(
                _LegacyNote(
                    key=key,
                    source=path.resolve(),
                    source_relative=_relative(self.vault_path, path),
                    text=text,
                    fields=dict(document.fields),
                    body=document.body,
                )
            )
        return notes, skipped

    def _state_points_to(self, key: str, note_path: str) -> bool:
        state_path = self.paths.resolve(self.paths.state(key))
        if not state_path.is_file():
            return False
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return False
        return bool(
            isinstance(state, dict)
            and state.get("schemaVersion") == 2
            and str(state.get("notePath") or "").casefold() == note_path.casefold()
        )

    def _discover_item(self, note: _LegacyNote) -> _ItemPlan:
        metadata = _filename_metadata(note.fields)
        plan = _ItemPlan(note=note, note_target=self.paths.note(note.key, **metadata))

        pdf_values = _field_values(
            note.fields,
            ("attachments", "attachmentLinks", "pdfPath", "attachmentPdfLink", "zoteroAttachmentPaths"),
        )
        pdf_values.extend(_extract_link_targets(note.body))
        pdf_source = _first_existing_reference(
            pdf_values,
            vault=self.vault_path,
            document=note.source,
            suffixes={".pdf"},
        )
        if pdf_source:
            plan.pdf = _Move(note.key, "pdf", pdf_source, self.paths.pdf(note.key, **metadata))

        mineru_values = _field_values(note.fields, ("mineruMarkdown", "mineruMarkdownLink", "attachmentMinerULink", "mineruPath"))
        mineru_source = _first_existing_reference(
            mineru_values,
            vault=self.vault_path,
            document=note.source,
            suffixes={".md"},
            add_markdown_suffix=True,
        )
        if mineru_source is None:
            mineru_source = self._find_mineru_by_key(note)
        if mineru_source:
            mineru_target = self.paths.mineru_markdown(note.key, **metadata)
            plan.mineru = _Move(note.key, "mineru-markdown", mineru_source, mineru_target)
            try:
                mineru_text = mineru_source.read_text(encoding="utf-8-sig")
            except (OSError, UnicodeError) as exc:
                plan.warnings.append(
                    {
                        "type": "unreadable-mineru-markdown",
                        "zoteroKey": note.key,
                        "path": _display_source(self.vault_path, mineru_source),
                        "error": str(exc),
                    }
                )
            else:
                seen: set[str] = set()
                image_index = 0
                for raw_reference in _extract_image_targets(mineru_text):
                    image_source = _resolve_reference(
                        raw_reference,
                        vault=self.vault_path,
                        document=mineru_source,
                    )
                    if image_source is None or image_source.suffix.lower() not in _IMAGE_EXTENSIONS:
                        plan.warnings.append(
                            {
                                "type": "missing-mineru-image",
                                "zoteroKey": note.key,
                                "reference": raw_reference,
                            }
                        )
                        continue
                    source_id = str(image_source.resolve()).casefold()
                    if source_id in seen:
                        continue
                    seen.add(source_id)
                    image_index += 1
                    extension = image_source.suffix.lower().lstrip(".")
                    target = self.paths.mineru_image(note.key, image_index, extension, **metadata)
                    plan.images.append(_Move(note.key, "mineru-image", image_source, target))
        return plan

    def _find_mineru_by_key(self, note: _LegacyNote) -> Path | None:
        candidates: list[Path] = []
        for path in self.vault_path.rglob("*.md"):
            if path.resolve() == note.source or _is_internal(self.vault_path, path):
                continue
            try:
                document = parse_frontmatter(path.read_text(encoding="utf-8-sig"))
            except Exception:
                continue
            if str(document.fields.get("zoteroKey") or "").strip().casefold() != note.key.casefold():
                continue
            note_type = str(document.fields.get("type") or "").strip().casefold()
            if note_type == "mineru-extraction" or "mineru" in path.as_posix().casefold():
                candidates.append(path.resolve())
        return sorted(candidates, key=lambda path: _relative(self.vault_path, path).casefold())[0] if candidates else None

    def _target_conflicts(self, moves: list[_Move], conflict_policy: str) -> list[dict[str, Any]]:
        existing = {
            _relative(self.vault_path, path).casefold(): path.resolve()
            for path in self.vault_path.rglob("*")
            if not _is_internal(self.vault_path, path)
        }
        occupied = set(existing) | {move.target.casefold() for move in moves}
        conflicts: list[dict[str, Any]] = []
        for move in moves:
            occupant = existing.get(move.target.casefold())
            if occupant is None or _same_path(occupant, move.source):
                continue
            if conflict_policy == "overwrite-managed":
                continue
            if conflict_policy == "rename":
                move.target = _allocate_renamed_target(move.target, move.kind, occupied)
                occupied.add(move.target.casefold())
                continue
            conflicts.append(
                {
                    "type": "target-exists",
                    "zoteroKey": move.key,
                    "asset": move.kind,
                    "source": _display_source(self.vault_path, move.source),
                    "target": move.target,
                    "message": "target already exists; use overwrite-managed only after reviewing the preview",
                }
            )
        return conflicts

    def _render_plans(self, plans: list[_ItemPlan], moves: list[_Move], transaction_id: str) -> None:
        imported_at = ItemState.utc_now()
        for plan in plans:
            fields = _clean_fields(plan.note.fields, _V1_PLUGIN_FIELDS)
            fields = _rewrite_value(fields, self.vault_path, plan.note.source_relative, plan.note_target, moves)
            managed = _managed_v2_fields(plan.note.fields, plan.note.key)
            managed["attachmentPdfLink"] = f"[[{plan.pdf.target}]]" if plan.pdf else ""
            managed["attachmentMinerULink"] = f"[[{_without_md(plan.mineru.target)}]]" if plan.mineru else ""
            merged = merge_frontmatter(
                fields,
                managed,
                omit_empty=bool(self.config["frontmatter"]["omitEmpty"]),
                preserve_unknown_fields=True,
                field_order=self.config["frontmatter"]["fieldOrder"],
            )
            body = _rewrite_markdown(
                plan.note.body,
                vault=self.vault_path,
                source_document=plan.note.source_relative,
                output_document=plan.note_target,
                moves=moves,
            )
            legacy_sections, user_body = _split_v1_body(body)
            abstract = str(managed.get("abstract") or legacy_sections.get("abstract") or "")
            zotero_notes = str(legacy_sections.get("zotero-notes") or "")
            bibtex = _bibtex_payload(str(legacy_sections.get("bibtex") or ""))
            body = render_note_body(
                str(managed.get("title") or plan.note.key),
                abstract=abstract,
                pdf_path=plan.pdf.target if plan.pdf else "",
                mineru_path=plan.mineru.target if plan.mineru else "",
                zotero_notes=zotero_notes,
                bibtex=bibtex,
                existing_body=user_body,
                reading_notes_heading=str(self.config["note"]["readingNotesHeading"]),
                embed_pdf=bool(self.config["note"]["embedPdf"]),
                embed_mineru=bool(self.config["note"]["embedMineruMarkdown"]),
                omit_empty=bool(self.config["note"]["omitEmptySections"]),
            )
            plan.note_text = compose_frontmatter(
                merged,
                body,
                omit_empty=bool(self.config["frontmatter"]["omitEmpty"]),
                field_order=self.config["frontmatter"]["fieldOrder"],
            )
            plan.record = {**merged, "notePath": plan.note_target, "lastImportedAt": imported_at}

            if plan.mineru:
                mineru_document = parse_frontmatter(plan.mineru.source.read_text(encoding="utf-8-sig"))
                mineru_fields = _clean_fields(mineru_document.fields, _MINERU_PLUGIN_FIELDS)
                mineru_fields = _rewrite_value(
                    mineru_fields,
                    self.vault_path,
                    _relative(self.vault_path, plan.mineru.source),
                    plan.mineru.target,
                    moves,
                )
                canonical_mineru = {
                    "title": str(plan.note.fields.get("title") or mineru_document.fields.get("title") or plan.note.key),
                    "zoteroKey": plan.note.key,
                    "sourcePdf": f"../{PurePosixPath(plan.pdf.target).name}" if plan.pdf else "",
                }
                mineru_fields = {**canonical_mineru, **mineru_fields}
                mineru_body = _rewrite_markdown(
                    mineru_document.body,
                    vault=self.vault_path,
                    source_document=_relative(self.vault_path, plan.mineru.source),
                    output_document=plan.mineru.target,
                    moves=moves,
                )
                plan.mineru_text = compose_frontmatter(mineru_fields, mineru_body, omit_empty=True)

            state = ItemState(
                zotero_key=plan.note.key,
                zotero_version=_integer_or_none(plan.note.fields.get("zoteroVersion")),
                note_path=plan.note_target,
                pdf_path=plan.pdf.target if plan.pdf else "",
                mineru_path=plan.mineru.target if plan.mineru else "",
                copied_pdf_sha256=_hash_file(plan.pdf.source) if plan.pdf else "",
                mineru_source_sha256=_hash_file(plan.pdf.source) if plan.pdf and plan.mineru else "",
                last_imported_at=imported_at,
                last_mineru_at=imported_at if plan.mineru else "",
                last_transaction_id=transaction_id,
                status="ready",
                errors=[],
            ).as_dict()
            plan.state_text = json.dumps({key: value for key, value in state.items() if value is not None}, ensure_ascii=False, indent=2) + "\n"

    def _stage_transaction(self, transaction: Transaction, plans: list[_ItemPlan], moves: list[_Move]) -> list[str]:
        destination_ids = {move.target.casefold() for move in moves}
        source_ids = {move.source_id for move in moves}
        for plan in plans:
            transaction.write_text(plan.note_target, plan.note_text)
            if plan.pdf:
                transaction.copy(plan.pdf.source, plan.pdf.target)
            if plan.mineru:
                transaction.write_text(plan.mineru.target, plan.mineru_text)
            for image in plan.images:
                transaction.copy(image.source, image.target)

        rewritten: list[str] = []
        index_path = str(self.config["literature"]["index"])
        base_path = str(self.config["literature"]["base"])
        reserved = destination_ids | {index_path.casefold(), base_path.casefold()}
        for path in sorted(self.vault_path.rglob("*.md"), key=lambda candidate: _relative(self.vault_path, candidate).casefold()):
            if _is_internal(self.vault_path, path):
                continue
            relative = _relative(self.vault_path, path)
            if str(path.resolve()).casefold() in source_ids or relative.casefold() in reserved:
                continue
            try:
                before = path.read_text(encoding="utf-8-sig")
            except (OSError, UnicodeError):
                continue
            after = _rewrite_markdown(before, self.vault_path, relative, relative, moves)
            if before != after:
                transaction.write_text(relative, after)
                rewritten.append(relative)

        deleted: set[str] = set()
        for move in moves:
            source_relative = _try_relative(self.vault_path, move.source)
            target_path = self.paths.resolve(move.target)
            if source_relative is None or _same_path(move.source, target_path):
                continue
            source_key = source_relative.casefold()
            if source_key in deleted:
                continue
            transaction.delete(source_relative)
            deleted.add(source_key)

        for plan in plans:
            transaction.write_text(self.paths.state(plan.note.key), plan.state_text)

        if not self.config_path.exists():
            transaction.write_text(CONFIG_FILENAME, json.dumps(self.config, ensure_ascii=False, indent=2) + "\n")

        overlays = [plan.record for plan in plans]
        index_service = IndexService(self.vault_path, self.config)
        existing_records = index_service.records(overlays)
        transaction.write_text(
            index_path,
            render_index(
                existing_records,
                index_service.wiki_topics(),
                recent_limit=int(self.config["index"]["recentLimit"]),
                base_path=base_path,
            ),
        )
        transaction.write_text(
            base_path,
            render_base(str(self.config["literature"]["root"]), str(self.config["base"]["name"])),
        )
        return rewritten

    def _report(
        self,
        transaction: Transaction,
        *,
        execute: bool,
        conflict_policy: str,
        plans: list[_ItemPlan],
        conflicts: list[dict[str, Any]],
        duplicates: list[list[_LegacyNote]],
        skipped: list[dict[str, Any]],
        warnings: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "transactionId": transaction.transaction_id,
            "dryRun": not execute,
            "applied": False,
            "conflictPolicy": conflict_policy,
            "sourceRoot": "literature",
            "items": [plan.as_dict(self.vault_path) for plan in plans],
            "itemCount": len(plans),
            "plannedMoves": [move.as_dict(self.vault_path) for plan in plans for move in plan.moves()],
            "duplicates": [
                {"zoteroKey": group[0].key, "sources": [note.source_relative for note in group]}
                for group in duplicates
            ],
            "conflicts": conflicts,
            "skipped": skipped,
            "warnings": warnings,
        }


def _split_duplicates(notes: list[_LegacyNote]) -> tuple[list[list[_LegacyNote]], list[_LegacyNote]]:
    groups: dict[str, list[_LegacyNote]] = defaultdict(list)
    for note in notes:
        groups[note.key.casefold()].append(note)
    duplicates = [group for group in groups.values() if len(group) > 1]
    unique = [group[0] for group in groups.values() if len(group) == 1]
    duplicates.sort(key=lambda group: group[0].key.casefold())
    unique.sort(key=lambda note: note.key.casefold())
    return duplicates, unique


def _synchronize_move_targets(plans: list[_ItemPlan], moves: list[_Move]) -> None:
    note_targets = {move.key.casefold(): move.target for move in moves if move.kind == "note"}
    for plan in plans:
        plan.note_target = note_targets.get(plan.note.key.casefold(), plan.note_target)


def _allocate_renamed_target(target: str, kind: str, occupied: set[str]) -> str:
    path = PurePosixPath(target)
    suffix = path.suffix
    stem = path.stem
    if kind == "mineru-image":
        match = re.fullmatch(r"(.+-fig)(\d+)", stem, flags=re.IGNORECASE)
        if match:
            width = max(2, len(match.group(2)))
            index = int(match.group(2)) + 1
            while True:
                candidate = (path.parent / f"{match.group(1)}{index:0{width}d}{suffix}").as_posix()
                if candidate.casefold() not in occupied:
                    return candidate
                index += 1
    index = 1
    while True:
        candidate = (path.parent / f"{stem}-migrated-{index:02d}{suffix}").as_posix()
        if candidate.casefold() not in occupied:
            return candidate
        index += 1


def _split_v1_body(body: str) -> tuple[dict[str, str], str]:
    """Extract known V1 managed sections and retain every user-owned section."""

    normalized = body.replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"\A\s*# [^\n]*\n*", "", normalized, count=1)
    headings = list(re.finditer(r"(?m)^##[ \t]+([^\n]+?)[ \t]*$", normalized))
    aliases = {
        "abstract": "abstract",
        "pdf": "pdf",
        "mineru": "mineru",
        "mineru extraction": "mineru",
        "zotero notes": "zotero-notes",
        "zotero notes & annotations": "zotero-notes",
        "zotero notes and annotations": "zotero-notes",
        "bibtex": "bibtex",
    }
    managed: dict[str, str] = {}
    user_parts: list[str] = []
    prefix = normalized[: headings[0].start()].strip() if headings else normalized.strip()
    if prefix:
        user_parts.append(prefix)
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(normalized)
        section_text = normalized[heading.end() : end].strip()
        name = " ".join(heading.group(1).strip().casefold().split())
        managed_name = aliases.get(name)
        if managed_name:
            managed.setdefault(managed_name, section_text)
        else:
            user_parts.append(f"## {heading.group(1).strip()}\n\n{section_text}".rstrip())
    return managed, "\n\n".join(user_parts).rstrip() + ("\n" if user_parts else "")


def _bibtex_payload(section: str) -> str:
    match = re.search(r"(?ms)```(?:bibtex)?[ \t]*\n(.*?)\n```", section.strip())
    return match.group(1).strip() if match else section.strip()


def _move_graph_conflicts(moves: list[_Move], vault: Path) -> list[dict[str, Any]]:
    target_to_moves: dict[str, list[_Move]] = defaultdict(list)
    sources: dict[str, list[_Move]] = defaultdict(list)
    for move in moves:
        target_to_moves[move.target.casefold()].append(move)
        source_relative = _try_relative(vault, move.source)
        if source_relative:
            sources[source_relative.casefold()].append(move)
    conflicts: list[dict[str, Any]] = []
    for move in moves:
        source_relative = _try_relative(vault, move.source)
        target_path = vault.joinpath(*PurePosixPath(move.target).parts)
        if source_relative and source_relative != move.target and source_relative.casefold() == move.target.casefold():
            conflicts.append(
                {
                    "type": "case-only-move",
                    "zoteroKey": move.key,
                    "source": source_relative,
                    "target": move.target,
                    "message": "case-only moves cannot be represented safely by the transaction service",
                }
            )
        elif source_relative and _same_path(move.source, target_path):
            continue
    for target, claimed in target_to_moves.items():
        if len(claimed) > 1:
            conflicts.append(
                {
                    "type": "duplicate-target",
                    "target": claimed[0].target,
                    "sources": [_display_source(vault, move.source) for move in claimed],
                    "message": "multiple migration assets resolve to the same V2 target",
                }
            )
        source_claims = sources.get(target, [])
        if source_claims and not all(_same_path(move.source, claimed_move.source) for move in claimed for claimed_move in source_claims):
            conflicts.append(
                {
                    "type": "target-is-migration-source",
                    "target": claimed[0].target,
                    "sources": [_display_source(vault, move.source) for move in source_claims],
                    "message": "a V2 target is also a different asset's V1 source",
                }
            )
    return conflicts


def _managed_v2_fields(fields: Mapping[str, Any], key: str) -> dict[str, Any]:
    zotero_pdf_link = fields.get("zoteroPdfLink") or _first_scalar(fields.get("zoteroPdfLinks"))
    return {
        "title": fields.get("title") or key,
        "itemType": fields.get("itemType") or "",
        "year": fields.get("year"),
        "journal": fields.get("journal") or fields.get("publicationTitle") or "",
        "tags": fields.get("tags") or [],
        "doi": fields.get("doi") or "",
        "url": fields.get("url") or "",
        "abstract": fields.get("abstract") or "",
        "zoteroKey": key,
        "zoteroPdfLink": zotero_pdf_link or "",
    }


def _clean_fields(fields: Mapping[str, Any], plugin_fields: set[str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in fields.items():
        if key in plugin_fields or key in _RUNTIME_FIELDS or _contains_absolute_path(value):
            continue
        result[key] = value
    return result


def _contains_absolute_path(value: Any) -> bool:
    if isinstance(value, str):
        candidate = _unwrap_reference(value)
        lowered = candidate.casefold()
        return bool(
            _WINDOWS_ABSOLUTE.match(candidate)
            or candidate.startswith(("/", "\\\\"))
            or lowered.startswith("file://")
        )
    if isinstance(value, Mapping):
        return any(_contains_absolute_path(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(_contains_absolute_path(item) for item in value)
    return False


def _filename_metadata(fields: Mapping[str, Any]) -> dict[str, Any]:
    author = _first_scalar(fields.get("authors")) or fields.get("firstAuthor") or ""
    if isinstance(author, Mapping):
        author = author.get("lastName") or author.get("name") or ""
    return {
        "firstAuthor": str(author),
        "year": fields.get("year") or "",
        "shortTitle": fields.get("title") or "",
    }


def _field_values(fields: Mapping[str, Any], names: Iterable[str]) -> list[str]:
    result: list[str] = []
    for name in names:
        result.extend(_string_values(fields.get(name)))
    return result


def _string_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        result: list[str] = []
        for nested in value.values():
            result.extend(_string_values(nested))
        return result
    if isinstance(value, (list, tuple, set)):
        result = []
        for nested in value:
            result.extend(_string_values(nested))
        return result
    return []


def _first_scalar(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return value[0] if value else ""
    return value


def _integer_or_none(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _extract_link_targets(text: str) -> list[str]:
    found: list[tuple[int, str]] = []
    found.extend((match.start(), match.group(2)) for match in _WIKILINK.finditer(text))
    found.extend((match.start(), match.group(2).strip("<>")) for match in _MARKDOWN_LINK.finditer(text))
    return [target for _position, target in sorted(found, key=lambda item: item[0])]


def _extract_image_targets(text: str) -> list[str]:
    found: list[tuple[int, str]] = []
    found.extend((match.start(), match.group(1)) for match in _WIKI_IMAGE.finditer(text))
    found.extend((match.start(), match.group(1) or match.group(2)) for match in _MARKDOWN_IMAGE.finditer(text))
    return [target for _position, target in sorted(found, key=lambda item: item[0])]


def _first_existing_reference(
    values: Iterable[str],
    *,
    vault: Path,
    document: Path,
    suffixes: set[str],
    add_markdown_suffix: bool = False,
) -> Path | None:
    for raw in values:
        candidate = _resolve_reference(raw, vault=vault, document=document, add_markdown_suffix=add_markdown_suffix)
        if candidate is not None and candidate.suffix.lower() in suffixes:
            return candidate
    return None


def _resolve_reference(
    raw: str,
    *,
    vault: Path,
    document: Path,
    add_markdown_suffix: bool = False,
) -> Path | None:
    value = unquote(_unwrap_reference(raw)).strip()
    if not value or value.startswith(("#", "zotero://", "http://", "https://")):
        return None
    value = value.split("#", 1)[0].split("?", 1)[0]
    if value.casefold().startswith("file://"):
        parsed = urlparse(value)
        value = unquote(parsed.path)
        if parsed.netloc:
            value = f"//{parsed.netloc}{value}"
        if re.match(r"^/[A-Za-z]:/", value):
            value = value[1:]
    portable = value.replace("\\", "/")
    raw_path = Path(portable)
    candidates: list[Path]
    if _WINDOWS_ABSOLUTE.match(portable) or portable.startswith(("/", "//")):
        candidates = [raw_path]
    elif portable.startswith(("./", "../")):
        candidates = [document.parent / raw_path, vault / raw_path]
    else:
        candidates = [vault / raw_path, document.parent / raw_path]
    expanded: list[Path] = []
    for candidate in candidates:
        expanded.append(candidate)
        if add_markdown_suffix and not candidate.suffix:
            expanded.append(candidate.with_suffix(".md"))
    for candidate in expanded:
        try:
            resolved = candidate.expanduser().resolve()
        except OSError:
            continue
        if resolved.is_file():
            return resolved
    return None


def _unwrap_reference(value: str) -> str:
    text = value.strip().strip('"\'')
    wiki = _WIKILINK.search(text)
    if wiki:
        return wiki.group(2).strip()
    markdown = _MARKDOWN_LINK.search(text)
    if markdown:
        return markdown.group(2).strip("<>")
    return text.strip("<>")


def _rewrite_value(value: Any, vault: Path, source_document: str, output_document: str, moves: list[_Move]) -> Any:
    if isinstance(value, str):
        rewritten = _rewrite_markdown(value, vault, source_document, output_document, moves)
        move = _match_move(value, vault, source_document, moves)
        return _format_target(move.target, value, output_document, markdown=False) if move else rewritten
    if isinstance(value, Mapping):
        return {key: _rewrite_value(item, vault, source_document, output_document, moves) for key, item in value.items()}
    if isinstance(value, list):
        return [_rewrite_value(item, vault, source_document, output_document, moves) for item in value]
    if isinstance(value, tuple):
        return [_rewrite_value(item, vault, source_document, output_document, moves) for item in value]
    return value


def _rewrite_markdown(text: str, vault: Path, source_document: str, output_document: str, moves: list[_Move]) -> str:
    def wiki(match: re.Match[str]) -> str:
        raw = match.group(2)
        move = _match_move(raw, vault, source_document, moves)
        if move is None:
            return match.group(0)
        target = _format_target(move.target, raw, output_document, markdown=False)
        return f"{match.group(1)}{target}{match.group(3) or ''}{match.group(4) or ''}{match.group(5)}"

    def markdown(match: re.Match[str]) -> str:
        raw = match.group(2).strip("<>")
        move = _match_move(raw, vault, source_document, moves)
        if move is None:
            return match.group(0)
        target = _format_target(move.target, raw, output_document, markdown=True)
        wrapped = f"<{target}>" if match.group(2).startswith("<") else target
        return f"{match.group(1)}{wrapped}{match.group(3)}"

    return _MARKDOWN_LINK.sub(markdown, _WIKILINK.sub(wiki, text))


def _match_move(raw: str, vault: Path, source_document: str, moves: list[_Move]) -> _Move | None:
    value = _unwrap_reference(raw).split("#", 1)[0].split("?", 1)[0]
    source_path = vault.joinpath(*PurePosixPath(source_document).parts)
    resolved = _resolve_reference(value, vault=vault, document=source_path, add_markdown_suffix=True)
    if resolved is not None:
        resolved_id = str(resolved).casefold()
        for move in moves:
            if move.source_id == resolved_id:
                return move
    portable = value.replace("\\", "/").strip("./")
    for move in moves:
        relative = _try_relative(vault, move.source)
        if relative and portable.casefold() in {relative.casefold(), _without_md(relative).casefold()}:
            return move
    if "/" not in portable:
        candidates = [
            move
            for move in moves
            if portable.casefold() in {move.source.name.casefold(), move.source.stem.casefold()}
        ]
        if len(candidates) == 1:
            return candidates[0]
    return None


def _format_target(target: str, raw: str, output_document: str, *, markdown: bool) -> str:
    if markdown:
        parent = PurePosixPath(output_document).parent.as_posix()
        relative = posixpath.relpath(target, parent or ".")
        return relative
    return _without_md(target) if not raw.casefold().endswith(".md") and target.casefold().endswith(".md") else target


def _without_md(path: str) -> str:
    return path[:-3] if path.casefold().endswith(".md") else path


def _relative(vault: Path, path: Path) -> str:
    return to_vault_relative(vault, path)


def _try_relative(vault: Path, path: Path) -> str | None:
    try:
        return _relative(vault, path)
    except ValueError:
        return None


def _display_source(vault: Path, path: Path) -> str:
    return _try_relative(vault, path) or "<external-source>"


def _same_path(first: Path, second: Path) -> bool:
    first_resolved = first.resolve(strict=False)
    second_resolved = second.resolve(strict=False)
    if first_resolved.exists() and second_resolved.exists():
        try:
            return os.path.samefile(first_resolved, second_resolved)
        except OSError:
            pass
    return first_resolved == second_resolved


def _is_internal(vault: Path, path: Path) -> bool:
    relative = _try_relative(vault, path)
    return bool(relative and (relative == ".obsidian-vault-mcp" or relative.startswith(".obsidian-vault-mcp/")))


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
