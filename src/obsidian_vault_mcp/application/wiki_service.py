"""Traceable Wiki context retrieval and safe transactional write-back."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from ..adapters.obsidian.markdown_renderer import managed_section_values
from ..adapters.vault.filesystem import VaultFilesystem
from ..config.loader import ConfigLoader
from ..config.schema import validate_config
from ..domain.errors import FrontmatterError, IdentityError, PathValidationError, TransactionConflictError
from ..domain.frontmatter import compose_frontmatter, parse_frontmatter
from ..domain.identity import sanitize_filename, validate_zotero_key
from ..domain.paths import (
    VaultPaths,
    naming_metadata_from_fields,
    normalize_vault_relative,
)
from .transaction_service import TransactionService
from .verify_service import _vault_link_target, scan_unsafe_references

_CONFLICT_POLICIES = {"preserve-user", "overwrite-managed", "fail", "rename"}


class WikiService:
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

    def context(self, topic: str, *, limit: int = 20, excerpt_chars: int = 2_000) -> dict[str, Any]:
        """Return deterministic, source-linked literature context for a topic."""

        display_topic, relative = self._topic_path(topic)
        if type(limit) is not int or limit < 1 or limit > 500:
            raise ValueError("limit must be an integer from 1 to 500")
        if type(excerpt_chars) is not int or excerpt_chars < 100 or excerpt_chars > 20_000:
            raise ValueError("excerpt_chars must be an integer from 100 to 20000")

        candidates: list[dict[str, Any]] = []
        for note in self._main_notes(excerpt_chars=excerpt_chars):
            score = _topic_score(display_topic, note)
            if score <= 0:
                continue
            candidates.append({**note, "relevance": score})
        candidates.sort(
            key=lambda item: (
                -item["relevance"],
                str(item.get("title", "")).casefold(),
                item["zoteroKey"],
            )
        )
        related = candidates[:limit]
        wiki_path = self.paths.resolve(relative)
        wiki_exists = wiki_path.is_file()
        existing_content = wiki_path.read_text(encoding="utf-8") if wiki_exists else ""
        return {
            "ok": True,
            "topic": display_topic,
            "wikiPath": relative,
            "existingWikiPage": {
                "exists": wiki_exists,
                "path": relative,
                "content": existing_content,
            },
            "wikiPages": self.list(),
            "relatedLiterature": related,
            "sourceNoteLinks": [item["noteLink"] for item in related],
            "count": len(related),
        }

    def write(
        self,
        topic: str,
        content: str,
        zotero_keys: Sequence[str],
        *,
        updated_at: str | None = None,
        dry_run: bool = False,
        transaction_id: str | None = None,
        conflict_policy: str = "preserve-user",
    ) -> dict[str, Any]:
        """Write a Wiki page with validated sources through a Vault transaction."""

        display_topic, relative = self._topic_path(topic)
        if conflict_policy not in _CONFLICT_POLICIES:
            raise ValueError(f"conflict_policy must be one of: {', '.join(sorted(_CONFLICT_POLICIES))}")
        if not isinstance(content, str):
            raise TypeError("Wiki content must be a string")
        unsafe = scan_unsafe_references(content)
        if unsafe:
            finding = unsafe[0]
            raise ValueError(
                f"Wiki content contains forbidden {finding['kind']} on line {finding['line']}: {finding['value']}"
            )
        keys = _validated_keys(zotero_keys)
        if not keys:
            raise IdentityError("at least one zoteroKey is required for a traceable Wiki page")

        notes_by_key: dict[str, list[dict[str, Any]]] = {}
        for note in self._main_notes(excerpt_chars=200):
            notes_by_key.setdefault(note["zoteroKey"], []).append(note)
        selected: list[dict[str, Any]] = []
        for key in keys:
            matches = notes_by_key.get(key, [])
            if not matches:
                raise IdentityError(f"no main literature note exists for zoteroKey {key}")
            if len(matches) > 1:
                raise IdentityError(f"multiple main literature notes exist for zoteroKey {key}")
            selected.append(matches[0])

        destination = self.paths.resolve(relative)
        if destination.exists() and not destination.is_file():
            raise TransactionConflictError(f"Wiki destination is not a file: {relative}", stage="plan")
        if destination.is_file() and conflict_policy == "fail":
            raise TransactionConflictError(f"Wiki page already exists: {relative}", stage="plan")
        if destination.exists() and conflict_policy == "rename":
            relative = self._renamed_path(display_topic)
            destination = self.paths.resolve(relative)

        existing_fields: dict[str, Any] = {}
        if destination.is_file() and conflict_policy == "preserve-user":
            try:
                existing_fields = parse_frontmatter(destination.read_text(encoding="utf-8")).fields
            except (OSError, UnicodeError, FrontmatterError) as exc:
                raise ValueError(f"cannot preserve existing Wiki frontmatter: {exc}") from exc

        submitted = parse_frontmatter(content)
        body = submitted.body if submitted.has_frontmatter else content
        body = _ensure_source_links(body, selected)
        timestamp = _validated_timestamp(updated_at)
        fields: dict[str, Any] = {
            "title": display_topic,
            "zoteroKeys": keys,
            "updatedAt": timestamp,
        }
        for source_fields in (existing_fields, submitted.fields):
            for name, value in source_fields.items():
                if name not in fields:
                    fields[name] = value
        rendered = compose_frontmatter(fields, body.rstrip() + "\n")
        unsafe_rendered = scan_unsafe_references(rendered)
        if unsafe_rendered:
            raise ValueError("rendered Wiki page contains a forbidden local or staging reference")

        transaction = TransactionService(self.vault_path).begin(
            transaction_id=transaction_id,
            dry_run=dry_run,
        )
        transaction.write_text(relative, rendered)
        result = transaction.commit()
        return {
            **result,
            "topic": display_topic,
            "path": relative,
            "zoteroKeys": keys,
            "sourceNoteLinks": [note["noteLink"] for note in selected],
            "updatedAt": timestamp,
        }

    def list(self) -> list[dict[str, Any]]:
        """List direct Wiki topic pages in deterministic path order."""

        folder_relative = normalize_vault_relative(str(self.config["literature"]["wikiFolder"]))
        folder = self.paths.resolve(folder_relative)
        if not folder.is_dir():
            return []
        pages: list[dict[str, Any]] = []
        for path in sorted(folder.glob("*.md"), key=lambda item: (item.name.casefold(), item.name)):
            relative = self.fs.relative(path)
            try:
                document = parse_frontmatter(path.read_text(encoding="utf-8"))
                keys = document.fields.get("zoteroKeys", [])
                if not isinstance(keys, list):
                    keys = []
                pages.append(
                    {
                        "path": relative,
                        "title": str(document.fields.get("title") or path.stem),
                        "zoteroKeys": [str(key) for key in keys],
                        "updatedAt": str(document.fields.get("updatedAt") or ""),
                    }
                )
            except (OSError, UnicodeError, FrontmatterError):
                pages.append({"path": relative, "title": path.stem, "zoteroKeys": [], "updatedAt": ""})
        return pages

    list_pages = list

    def _main_notes(self, *, excerpt_chars: int) -> list[dict[str, Any]]:
        literature_root = normalize_vault_relative(str(self.config["literature"]["root"]))
        index_path = normalize_vault_relative(str(self.config["literature"]["index"]))
        folder = self.paths.resolve(literature_root)
        if not folder.is_dir():
            return []
        notes: list[dict[str, Any]] = []
        for path in sorted(folder.glob("*.md"), key=lambda item: (item.name.casefold(), item.name)):
            relative = self.fs.relative(path)
            if relative == index_path:
                continue
            try:
                document = parse_frontmatter(path.read_text(encoding="utf-8"))
                key = validate_zotero_key(str(document.fields.get("zoteroKey") or ""))
            except (OSError, UnicodeError, FrontmatterError, IdentityError):
                continue
            managed = managed_section_values(document.body)
            mineru_excerpt = self._mineru_excerpt(key, document.fields, excerpt_chars)
            title = str(document.fields.get("title") or path.stem)
            tags = document.fields.get("tags", [])
            if not isinstance(tags, list):
                tags = [str(tags)] if tags else []
            notes.append(
                {
                    "zoteroKey": key,
                    "title": title,
                    "abstract": _excerpt(str(document.fields.get("abstract") or ""), excerpt_chars),
                    "tags": [str(tag) for tag in tags],
                    "zoteroNotes": _excerpt(managed.get("zotero-notes", ""), excerpt_chars),
                    "mineruExcerpt": mineru_excerpt,
                    "notePath": relative,
                    "noteLink": _note_link(relative, title),
                }
            )
        return notes

    def _mineru_excerpt(self, key: str, fields: Mapping[str, Any], excerpt_chars: int) -> str:
        candidates: list[str] = []
        link = fields.get("attachmentMinerULink")
        if link:
            try:
                candidates.append(_vault_link_target(link, markdown=True))
            except (PathValidationError, TypeError, ValueError):
                pass
        try:
            candidates.append(
                self.paths.mineru_markdown(
                    key,
                    **naming_metadata_from_fields(fields),
                )
            )
        except (IdentityError, PathValidationError):
            pass
        for relative in dict.fromkeys(candidates):
            path = self.paths.resolve(relative)
            if not path.is_file():
                continue
            try:
                document = parse_frontmatter(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, FrontmatterError):
                continue
            return _excerpt(document.body, excerpt_chars)
        return ""

    def _topic_path(self, topic: str) -> tuple[str, str]:
        if not isinstance(topic, str):
            raise TypeError("topic must be a string")
        display = unicodedata.normalize("NFC", topic).strip()
        if display.lower().endswith(".md"):
            display = display[:-3].rstrip()
        if not display or display in {".", ".."} or "/" in display or "\\" in display or "\x00" in display:
            raise ValueError("topic must be one safe filename component")
        filename = sanitize_filename(display)
        if filename.startswith("."):
            raise ValueError("topic cannot create a hidden Wiki page")
        folder = normalize_vault_relative(str(self.config["literature"]["wikiFolder"]))
        return display, normalize_vault_relative(f"{folder}/{filename}.md")

    def _renamed_path(self, topic: str) -> str:
        _display, original = self._topic_path(topic)
        base = PurePosixPath(original)
        for index in range(2, 10_002):
            candidate = (base.parent / f"{base.stem}-{index}.md").as_posix()
            if not self.paths.resolve(candidate).exists():
                return candidate
        raise TransactionConflictError("could not find an unused Wiki filename", stage="plan")


def _validated_keys(values: Sequence[str]) -> list[str]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise TypeError("zotero_keys must be a sequence of strings")
    by_folded: dict[str, str] = {}
    for value in values:
        key = validate_zotero_key(value)
        by_folded.setdefault(key.casefold(), key)
    return sorted(by_folded.values(), key=lambda key: (key.casefold(), key))


def _validated_timestamp(value: str | None) -> str:
    if value is None:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("updated_at must be an ISO-8601 timestamp")
    normalized = value.strip()
    try:
        datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("updated_at must be an ISO-8601 timestamp") from exc
    return normalized


def _ensure_source_links(body: str, notes: Sequence[Mapping[str, Any]]) -> str:
    result = body.rstrip()
    missing = [note for note in notes if not _body_links_to(result, str(note["notePath"]))]
    if not missing:
        return result + "\n"
    lines = ["## Sources", ""]
    lines.extend(f"- {note['noteLink']}" for note in missing)
    sources = "\n".join(lines) + "\n"
    return f"{result}\n\n{sources}" if result else sources


def _body_links_to(body: str, note_path: str) -> bool:
    target = note_path[:-3] if note_path.lower().endswith(".md") else note_path
    pattern = re.compile(r"\[\[" + re.escape(target) + r"(?:\.md)?(?:[|#\]])")
    return bool(pattern.search(body.replace("\\", "/")))


def _note_link(note_path: str, title: str) -> str:
    target = note_path[:-3] if note_path.lower().endswith(".md") else note_path
    safe_title = title.replace("|", "-").replace("]", "").strip() or PurePosixPath(target).name
    return f"[[{target}|{safe_title}]]"


def _topic_score(topic: str, note: Mapping[str, Any]) -> int:
    phrase = topic.casefold()
    tokens = {token for token in re.findall(r"[^\W_]+", phrase) if len(token) > 1}
    title = str(note.get("title", "")).casefold()
    tags = " ".join(str(tag) for tag in note.get("tags", [])).casefold()
    abstract = str(note.get("abstract", "")).casefold()
    zotero_notes = str(note.get("zoteroNotes", "")).casefold()
    mineru = str(note.get("mineruExcerpt", "")).casefold()
    score = 0
    for text, weight in ((title, 12), (tags, 10), (abstract, 4), (zotero_notes, 3), (mineru, 1)):
        if phrase and phrase in text:
            score += weight * 2
        score += sum(weight for token in tokens if token in text)
    return score


def _excerpt(value: str, limit: int) -> str:
    compact = re.sub(r"\s+", " ", value).strip()
    return compact if len(compact) <= limit else compact[: max(0, limit - 1)].rstrip() + "…"
