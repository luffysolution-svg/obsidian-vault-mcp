from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Sequence
from contextlib import ExitStack
from pathlib import Path, PurePosixPath
from typing import Any

from ..adapters.obsidian.markdown_renderer import render_note_body
from ..adapters.vault.filesystem import VaultFilesystem
from ..adapters.vault.lock import GlobalLock
from ..adapters.zotero.client import ZoteroClient
from ..config.loader import load_config
from ..domain.errors import TransactionConflictError
from ..domain.frontmatter import compose_frontmatter, merge_frontmatter, parse_frontmatter
from ..domain.identity import validate_zotero_key
from ..domain.models import ItemState, ZoteroItem
from ..domain.paths import VaultPaths
from .base_service import BaseService
from .index_service import IndexService
from .transaction_service import TransactionService

_CONFLICT_POLICIES = {"preserve-user", "overwrite-managed", "fail", "rename"}
_ZOTERO_CHILD_NOTES_START = "<!-- ovm:zotero-child-notes:start -->"
_ZOTERO_CHILD_NOTES_END = "<!-- ovm:zotero-child-notes:end -->"
_ZOTERO_ANNOTATIONS_START = "<!-- ovm:zotero-annotations:start -->"
_ZOTERO_ANNOTATIONS_END = "<!-- ovm:zotero-annotations:end -->"


class ImportService:
    def __init__(
        self,
        vault_path: str | os.PathLike[str],
        *,
        zotero_client: ZoteroClient | Any | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        self.vault_path = Path(vault_path).expanduser().resolve()
        self.config = config or load_config(self.vault_path, require_exists=False)
        self.fs = VaultFilesystem(self.vault_path)
        self.paths = VaultPaths(self.vault_path, self.config)
        self.transactions = TransactionService(self.vault_path)
        self.client = zotero_client or ZoteroClient(
            api_base=os.environ.get("ZOTERO_LOCAL_API") or str(self.config["zotero"]["apiBase"]),
            page_size=int(self.config["zotero"]["paginationSize"]),
            linked_attachment_base_dir=str(self.config["zotero"]["linkedAttachmentBaseDir"]),
        )

    def import_item(
        self,
        zotero_key: str,
        *,
        collection_keys: Sequence[str] = (),
        dry_run: bool = False,
        transaction_id: str | None = None,
        conflict_policy: str = "preserve-user",
        require_existing: bool = False,
    ) -> dict[str, Any]:
        key = validate_zotero_key(zotero_key)
        if isinstance(collection_keys, (str, bytes)):
            raise TypeError("collection_keys must be an array of strings")
        if conflict_policy not in _CONFLICT_POLICIES:
            raise ValueError(f"unsupported conflict policy: {conflict_policy}")
        tree = self.client.get_item_tree(key)
        parent = dict(tree["parent"])
        children = dict(tree["children"])
        if str(parent.get("key") or key) != key:
            raise ValueError(f"Zotero returned the wrong item for {key}")

        state = self._load_state(key)
        existing_note = self._find_note(key, state.get("notePath") or "")
        if require_existing and not state and not existing_note:
            raise FileNotFoundError(f"literature item has not been imported: {key}")

        metadata = self._filename_metadata(parent)
        note_path = existing_note or self.paths.note(key, **metadata)
        note_path = self._resolve_note_collision(note_path, key, conflict_policy)
        existing_text = self.fs.read_text(note_path) if self.fs.exists(note_path) else ""
        existing_document = parse_frontmatter(existing_text)

        attachments = [
            attachment
            for attachment in children.get("attachments", [])
            if str(attachment.get("contentType") or "").lower() == "application/pdf"
            or str(attachment.get("filename") or "").lower().endswith(".pdf")
        ]
        pdf_attachment = attachments[0] if attachments else None
        source_pdf = self.client.resolve_attachment_source(pdf_attachment) if pdf_attachment else None
        source_pdf = source_pdf if source_pdf is not None and source_pdf.is_file() else None
        copy_pdf_enabled = bool(self.config["attachments"]["copyPdf"])
        previous_pdf_path = str(state.get("pdfPath") or "")
        previous_pdf_exists = bool(previous_pdf_path and self.fs.exists(previous_pdf_path))
        pdf_path = previous_pdf_path if copy_pdf_enabled and previous_pdf_exists else ""
        if copy_pdf_enabled and source_pdf is not None:
            pdf_path = previous_pdf_path or self.paths.pdf(key, **metadata)
        overwrite_policy = str(self.config["attachments"]["overwritePolicy"])
        should_copy_pdf = bool(
            source_pdf is not None
            and pdf_path
            and (not self.fs.exists(pdf_path) or overwrite_policy != "never")
        )

        mineru_path = str(state.get("mineruPath") or "")
        if mineru_path and not self.fs.exists(mineru_path):
            mineru_path = ""

        item = ZoteroItem(
            zotero_key=key,
            title=str(parent.get("title") or "Untitled Reference"),
            item_type=str(parent.get("itemType") or ""),
            year=_year(parent.get("year") or parent.get("date")),
            journal=str(parent.get("journal") or parent.get("publicationTitle") or ""),
            tags=tuple(parent.get("tags") or ()) if self.config["zotero"]["syncTags"] else (),
            doi=str(parent.get("doi") or ""),
            url=str(parent.get("url") or ""),
            abstract=str(parent.get("abstract") or ""),
            zotero_pdf_link=str(pdf_attachment.get("zoteroPdfLink") or "") if pdf_attachment else "",
        )
        managed = item.managed_frontmatter()
        managed["attachmentPdfLink"] = f"[[{pdf_path}]]" if pdf_path else ""
        managed["attachmentMinerULink"] = f"[[{_without_md(mineru_path)}]]" if mineru_path else ""
        merged = merge_frontmatter(
            existing_document.fields,
            managed,
            omit_empty=bool(self.config["frontmatter"]["omitEmpty"]),
            preserve_unknown_fields=bool(self.config["frontmatter"]["preserveUnknownFields"]),
            field_order=self.config["frontmatter"]["fieldOrder"],
        )

        bibtex = ""
        bibtex_provider = "disabled"
        bibtex_errors: list[dict[str, Any]] = []
        if self.config["bibtex"]["enabled"]:
            result = self.client.get_bibtex(
                key,
                item=parent,
                provider=str(self.config["bibtex"]["provider"]),
                fallback=str(self.config["bibtex"].get("fallback") or "") == "builtin",
            )
            bibtex = str(result["bibtex"])
            bibtex_provider = str(result["provider"])
            bibtex_errors = list(result["errors"])

        body = render_note_body(
            item.title,
            abstract=item.abstract,
            pdf_path=pdf_path,
            mineru_path=mineru_path,
            zotero_notes=_render_zotero_notes(children),
            bibtex=bibtex,
            existing_body=existing_document.body,
            reading_notes_heading=str(self.config["note"]["readingNotesHeading"]),
            embed_pdf=bool(self.config["note"]["embedPdf"]),
            embed_mineru=bool(self.config["note"]["embedMineruMarkdown"]),
            omit_empty=bool(self.config["note"]["omitEmptySections"]),
        )
        note_text = compose_frontmatter(
            merged,
            body,
            omit_empty=bool(self.config["frontmatter"]["omitEmpty"]),
            field_order=self.config["frontmatter"]["fieldOrder"],
        )

        transaction = self.transactions.begin(item_key=key, transaction_id=transaction_id, dry_run=dry_run)
        transaction.write_text(note_path, note_text)
        if should_copy_pdf and source_pdf is not None:
            transaction.copy(source_pdf, pdf_path)
        elif not copy_pdf_enabled and previous_pdf_exists:
            transaction.delete(str(state["pdfPath"]))

        core_changed = bool(transaction.preview()["changed"])
        source_sha = _hash_file(source_pdf) if source_pdf else str(state.get("sourcePdfSha256") or "")
        if should_copy_pdf:
            copied_pdf_sha = source_sha
        elif pdf_path and self.fs.exists(pdf_path):
            copied_pdf_sha = _hash_file(self.paths.resolve(pdf_path))
        else:
            copied_pdf_sha = ""
        version = _integer_or_none(parent.get("version"))
        state_changed = not state or state.get("zoteroVersion") != version or core_changed
        imported_at = ItemState.utc_now() if state_changed else str(state.get("lastImportedAt") or "")
        parent_collections = parent.get("collections")
        if isinstance(parent_collections, Sequence) and not isinstance(parent_collections, (str, bytes)):
            saved_collections = {str(value) for value in parent_collections if str(value)}
            saved_collections.update(str(value) for value in collection_keys if str(value))
        else:
            saved_collections = {
                *(str(value) for value in state.get("collectionKeys") or ()),
                *(str(value) for value in collection_keys if str(value)),
            }
        state_model = ItemState(
            zotero_key=key,
            zotero_version=version,
            note_path=note_path,
            pdf_path=pdf_path,
            mineru_path=mineru_path,
            mineru_asset_root=str(state.get("mineruAssetRoot") or ""),
            collection_keys=sorted(saved_collections),
            source_pdf_path=str(source_pdf) if source_pdf else str(state.get("sourcePdfPath") or ""),
            source_pdf_sha256=source_sha,
            copied_pdf_sha256=copied_pdf_sha,
            mineru_source_sha256=str(state.get("mineruSourceSha256") or ""),
            last_imported_at=imported_at,
            last_mineru_at=str(state.get("lastMineruAt") or ""),
            last_transaction_id=transaction.transaction_id if state_changed else str(state.get("lastTransactionId") or ""),
            status="ready",
            errors=[],
        )
        state_payload = _clean_state(state_model.as_dict())
        state_text = json.dumps(state_payload, ensure_ascii=False, indent=2) + "\n"
        state_path = self.paths.state(key)
        if not self.fs.exists(state_path) or self.fs.read_text(state_path) != state_text:
            transaction.write_text(state_path, state_text)

        overlay = dict(merged)
        overlay.update(notePath=note_path, lastImportedAt=imported_at)
        index_service = IndexService(self.vault_path, self.config)
        base_service = BaseService(self.vault_path, self.config)
        if self.config["index"]["autoRebuild"]:
            transaction.write_text(index_service.index_path, index_service.render([overlay]))
        if self.config["base"]["autoRebuild"]:
            transaction.write_text(base_service.base_path, base_service.render())

        if dry_run:
            committed = transaction.commit()
        else:
            with ExitStack() as stack:
                if self.config["index"]["autoRebuild"]:
                    stack.enter_context(GlobalLock(self.vault_path, "index"))
                if self.config["base"]["autoRebuild"]:
                    stack.enter_context(GlobalLock(self.vault_path, "base"))
                committed = transaction.commit()
        return {
            **committed,
            "zoteroKey": key,
            "title": item.title,
            "notePath": note_path,
            "pdfPath": pdf_path or None,
            "mineruPath": mineru_path or None,
            "bibtexProvider": bibtex_provider,
            "bibtexErrors": bibtex_errors,
        }

    def import_collection(
        self,
        collection_key: str,
        *,
        dry_run: bool = False,
        transaction_id: str | None = None,
        conflict_policy: str = "preserve-user",
        require_existing: bool = False,
        result_limit: int = 20,
    ) -> dict[str, Any]:
        items = self.client.list_collection_items(collection_key)
        parent_items = [item for item in items if item.get("itemType") not in {"attachment", "note", "annotation"}]
        summaries: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        succeeded = 0
        for index, item in enumerate(parent_items):
            key = str(item.get("key") or "")
            child_transaction = _child_transaction_id(transaction_id, index) if transaction_id else None
            try:
                result = self.import_item(
                    key,
                    collection_keys=(collection_key,),
                    dry_run=dry_run,
                    transaction_id=child_transaction,
                    conflict_policy=conflict_policy,
                    require_existing=require_existing,
                )
                succeeded += 1
                if len(summaries) < max(0, result_limit):
                    summaries.append({"zoteroKey": key, "status": result["status"], "notePath": result["notePath"]})
            except Exception as exc:
                failure = {"zoteroKey": key, "stage": "import", "error": str(exc)}
                failures.append(failure)
                if len(summaries) < max(0, result_limit):
                    summaries.append({**failure, "status": "failed"})
        return {
            "ok": not failures,
            "collectionKey": collection_key,
            "dryRun": dry_run,
            "total": len(parent_items),
            "succeeded": succeeded,
            "failed": len(failures),
            "results": summaries,
            "truncated": len(parent_items) > len(summaries),
            "nextCursor": str(len(summaries)) if len(parent_items) > len(summaries) else None,
            "errors": failures[: max(0, result_limit)],
        }

    def _load_state(self, key: str) -> dict[str, Any]:
        path = self.paths.state(key)
        if not self.fs.exists(path):
            return {}
        try:
            value = json.loads(self.fs.read_text(path))
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid item state for {key}: {exc}") from exc
        if not isinstance(value, dict) or value.get("zoteroKey") != key:
            raise ValueError(f"item state identity mismatch for {key}")
        return value

    def _find_note(self, key: str, state_path: str) -> str:
        if state_path and self.fs.exists(state_path):
            document = parse_frontmatter(self.fs.read_text(state_path))
            if document.fields.get("zoteroKey") == key:
                return state_path
        root = self.paths.resolve(str(self.config["literature"]["root"]))
        matches: list[str] = []
        if root.is_dir():
            for path in root.glob("*.md"):
                document = parse_frontmatter(path.read_text(encoding="utf-8-sig"))
                if document.fields.get("zoteroKey") == key:
                    matches.append(self.fs.relative(path))
        if len(matches) > 1:
            raise TransactionConflictError(f"multiple main notes have zoteroKey {key}: {matches}", stage="identity")
        return matches[0] if matches else ""

    def _resolve_note_collision(self, note_path: str, key: str, conflict_policy: str) -> str:
        if not self.fs.exists(note_path):
            return note_path
        document = parse_frontmatter(self.fs.read_text(note_path))
        existing_key = str(document.fields.get("zoteroKey") or "")
        if existing_key == key:
            return note_path
        if conflict_policy == "rename":
            original = PurePosixPath(note_path)
            for suffix in range(2, 10_002):
                candidate = original.with_name(f"{original.stem}-{suffix}{original.suffix}").as_posix()
                if not self.fs.exists(candidate):
                    return candidate
                candidate_document = parse_frontmatter(self.fs.read_text(candidate))
                if str(candidate_document.fields.get("zoteroKey") or "") == key:
                    return candidate
            raise TransactionConflictError(
                f"could not allocate a renamed note path for {key}",
                stage="identity",
                details={"conflictPolicy": conflict_policy},
            )
        owner = existing_key or "an unowned user note"
        raise TransactionConflictError(
            f"note path collision: {note_path} belongs to {owner}",
            stage="identity",
            details={"conflictPolicy": conflict_policy},
        )

    @staticmethod
    def _filename_metadata(parent: dict[str, Any]) -> dict[str, Any]:
        creators = parent.get("creators") or []
        first = creators[0] if creators else {}
        author = first.get("lastName") or first.get("name") or "Unknown" if isinstance(first, dict) else str(first)
        title = str(parent.get("title") or "Untitled")
        words = re.findall(r"[\w]+", title, flags=re.UNICODE)[:10]
        return {"firstAuthor": str(author), "year": str(parent.get("year") or "n.d."), "shortTitle": "-".join(words) or "Untitled"}


def _render_zotero_notes(children: dict[str, Any]) -> str:
    notes: list[str] = []
    for note in children.get("notes", []):
        text = str(note.get("note") or "").strip()
        if text:
            notes.append(text)
    annotations: list[str] = []
    for annotation in children.get("annotations", []):
        text = str(annotation.get("annotationText") or "").strip()
        comment = str(annotation.get("annotationComment") or "").strip()
        page = str(annotation.get("annotationPageLabel") or "").strip()
        if text or comment:
            prefix = f"- p. {page}: " if page else "- "
            annotations.append(prefix + (text or comment))
            if text and comment:
                annotations.append(f"  - {comment}")
    if not notes and not annotations:
        return ""
    return "\n".join(
        (
            _ZOTERO_CHILD_NOTES_START,
            "\n\n".join(notes),
            _ZOTERO_CHILD_NOTES_END,
            "",
            _ZOTERO_ANNOTATIONS_START,
            "\n\n".join(annotations),
            _ZOTERO_ANNOTATIONS_END,
        )
    )


def _year(value: Any) -> int | None:
    match = re.search(r"(?<!\d)(\d{4})(?!\d)", str(value or ""))
    return int(match.group(1)) if match else None


def _integer_or_none(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _without_md(path: str) -> str:
    return path[:-3] if path.lower().endswith(".md") else path


def _clean_state(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if item is not None}


def _child_transaction_id(base: str | None, index: int) -> str | None:
    if not base:
        return None
    return f"{base[:120]}-{index + 1:04d}"
