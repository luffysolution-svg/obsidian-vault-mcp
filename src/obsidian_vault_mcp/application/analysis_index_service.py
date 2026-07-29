"""Deterministic Literature/Analysis index rebuilding."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ..adapters.vault.filesystem import VaultFilesystem
from ..adapters.vault.lock import GlobalLock
from ..config.loader import ConfigLoader
from ..config.schema import validate_config
from ..domain.analysis import STRUCTURED_READING_SECTIONS
from ..domain.errors import FrontmatterError, IdentityError, TransactionConflictError
from ..domain.frontmatter import parse_frontmatter
from ..domain.identity import validate_zotero_key
from ..domain.paths import VaultPaths, normalize_vault_relative
from .analysis_service import (
    AnalysisService,
    _load_uncertainty_state,
    _note_link,
    _validate_conflict_policy,
    analysis_section_text,
    replace_managed_block,
)
from .transaction_service import TransactionService

ANALYSIS_INDEX_BLOCK = "analysis-index"
_SECTION_TITLE = dict(STRUCTURED_READING_SECTIONS)


class AnalysisIndexService:
    """Rebuild one stable row per Analysis note without scanning other literature folders."""

    def __init__(
        self,
        vault_path: str | Path,
        config: Mapping[str, Any] | None = None,
    ) -> None:
        self.vault_path = Path(vault_path).expanduser().resolve()
        self.config = (
            validate_config(config)
            if config is not None
            else ConfigLoader(self.vault_path).load(require_exists=False)
        )
        self.fs = VaultFilesystem(self.vault_path)
        self.paths = VaultPaths(self.vault_path, self.config)
        self.analysis = AnalysisService(self.vault_path, self.config)
        self.transactions = TransactionService(self.vault_path)
        self.analysis_folder = normalize_vault_relative(str(self.config["analysis"]["folder"]))
        self.index_path = self.paths.analysis_index

    def rebuild(
        self,
        *,
        dry_run: bool = False,
        transaction_id: str | None = None,
        conflict_policy: str = "preserve-user",
    ) -> dict[str, Any]:
        _validate_conflict_policy(conflict_policy)
        rows = self.rows()
        managed = _render_index(rows)
        existing = self.fs.read_text(self.index_path) if self.fs.exists(self.index_path) else ""
        if existing:
            document = parse_frontmatter(existing)
            if document.fields.get("zoteroKey"):
                raise IdentityError("Analysis index path conflicts with a zoteroKey-owned note")
        if existing and conflict_policy == "fail":
            raise TransactionConflictError(f"Analysis index already exists: {self.index_path}", stage="plan")
        rendered = replace_managed_block(existing, ANALYSIS_INDEX_BLOCK, managed)
        transaction = self.transactions.begin(transaction_id=transaction_id, dry_run=dry_run)
        transaction.write_text(self.index_path, rendered)
        if dry_run:
            result = transaction.commit()
        else:
            with GlobalLock(self.vault_path, "index"):
                result = transaction.commit()
        return {**result, "indexPath": self.index_path, "rowCount": len(rows), "rows": rows}

    def rows(self) -> list[dict[str, Any]]:
        folder = self.paths.resolve(self.analysis_folder)
        if not folder.is_dir():
            return []
        rows: list[dict[str, Any]] = []
        seen: dict[str, str] = {}
        for path in sorted(folder.glob("*.md"), key=lambda item: (item.name.casefold(), item.name)):
            relative = self.fs.relative(path)
            if relative == self.index_path:
                continue
            try:
                document = parse_frontmatter(path.read_text(encoding="utf-8"))
                key = validate_zotero_key(str(document.fields.get("zoteroKey") or ""))
            except (OSError, UnicodeError, FrontmatterError, IdentityError) as exc:
                raise ValueError(f"invalid Analysis note {relative}: {exc}") from exc
            if key in seen:
                raise IdentityError(f"duplicate Analysis zoteroKey {key}: {seen[key]} and {relative}")
            seen[key] = relative
            try:
                main_path, main_document = self.analysis._main_note(key)
            except FileNotFoundError:
                main_path, main_document = "", None
            main_fields = main_document.fields if main_document is not None else {}
            title = str(document.fields.get("title") or main_fields.get("title") or key)
            source_note = str(document.fields.get("sourceNote") or (_note_link(main_path) if main_path else ""))
            uncertainty_state = _load_uncertainty_state(self.fs, key)
            uncertainty_count = sum(
                str(item.get("status") or "") in {"pending", "unresolved"}
                for item in uncertainty_state.get("items", [])
                if isinstance(item, Mapping)
            )
            evidence_state = str(document.fields.get("evidenceStatus") or "unverified")
            rows.append(
                {
                    "zoteroKey": key,
                    "year": main_fields.get("year") or document.fields.get("year") or "",
                    "title": title,
                    "mainNote": source_note,
                    "analysisNote": _note_link(relative),
                    "researchTopic": _section_digest(document.body, "research-question"),
                    "theoreticalFoundation": _section_digest(document.body, "theoretical-foundation"),
                    "researchMethod": _section_digest(document.body, "research-methods"),
                    "oneLinePositioning": _section_digest(document.body, "mechanisms")
                    or _section_digest(document.body, "findings"),
                    "oneLineType": "agent_synthesis",
                    "analysisStatus": "verified" if uncertainty_count == 0 and evidence_state == "complete" else "draft",
                    "evidenceStatus": evidence_state,
                    "imageStatus": self._image_status(key),
                    "uncertaintyCount": uncertainty_count,
                    "updatedAt": str(document.fields.get("updatedAt") or ""),
                }
            )
        rows.sort(key=_row_sort_key)
        return rows

    def rollback(
        self,
        transaction_id: str,
        *,
        dry_run: bool = False,
        conflict_policy: str = "preserve-user",
    ) -> dict[str, Any]:
        return self.transactions.rollback(transaction_id, dry_run=dry_run, conflict_policy=conflict_policy)

    def _image_status(self, key: str) -> str:
        manifest, _warnings = self.analysis._load_manifest(key)
        assets = [item for item in manifest.get("assets", []) if isinstance(item, Mapping)]
        visual = {str(item.get("visualStatus") or "") for item in assets}
        statuses = {str(item.get("status") or "") for item in assets}
        if "visual_verified" in visual:
            return "visual_verified"
        if "pdf_crop_available" in visual:
            return "pdf_crop_available"
        if "referenced" in statuses:
            return "referenced"
        if "unlinked_candidate" in statuses:
            return "candidates_only"
        return "none"


def _render_index(rows: list[dict[str, Any]]) -> str:
    lines = [
        "# Literature Analysis Index",
        "",
        "| Year | Title | Main Note | Analysis | Research Topic | Theory | Method | One-line Positioning | Analysis Status | Evidence Status | Image Status | Pending | Updated |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | ---: | --- |",
    ]
    for row in rows:
        one_line = str(row["oneLinePositioning"])
        if one_line:
            one_line = f"agent_synthesis: {one_line}"
        values = (
            row["year"],
            row["title"],
            row["mainNote"],
            row["analysisNote"],
            row["researchTopic"],
            row["theoreticalFoundation"],
            row["researchMethod"],
            one_line,
            row["analysisStatus"],
            row["evidenceStatus"],
            row["imageStatus"],
            row["uncertaintyCount"],
            row["updatedAt"],
        )
        lines.append("| " + " | ".join(_cell(value) for value in values) + " |")
    return "\n".join(lines)


def _section_digest(body: str, section_id: str, limit: int = 180) -> str:
    text = analysis_section_text(body, _SECTION_TITLE[section_id])
    text = re.sub(r"\[\[(?:evidence|asset):[^\]]+\]\]", "", text)
    text = re.sub(r"(?m)^-[ \t]+\*\*[^*]+\*\*[ \t]+—[ \t]*", "", text)
    text = re.sub(r"(?m)^-[ \t]+Source note:.*$", "", text)
    text = re.sub(r"_[^\n]*No Agent-authored content\._", "", text)
    compact = " ".join(text.split()).strip(" -")
    return compact if len(compact) <= limit else compact[: limit - 1].rstrip() + "…"


def _row_sort_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    year = row.get("year")
    try:
        numeric = int(str(year))
    except (TypeError, ValueError):
        numeric = -1
    return (-numeric, str(row.get("title") or "").casefold(), str(row.get("zoteroKey") or ""))


def _cell(value: Any) -> str:
    return " ".join(str(value or "").replace("|", "\\|").split())
