"""Read-only integrity checks for user-visible V2 Vault assets."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from ..adapters.vault.filesystem import VaultFilesystem
from ..config.loader import ConfigLoader
from ..config.schema import validate_config
from ..domain.errors import FrontmatterError, IdentityError, PathValidationError
from ..domain.frontmatter import parse_frontmatter
from ..domain.identity import validate_zotero_key
from ..domain.paths import VaultPaths, normalize_vault_relative

_WIKILINK_RE = re.compile(r"^\[\[([^\]|#]+)")
_UNSAFE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("file-url", re.compile(r"file:(?://|\\\\)", re.IGNORECASE)),
    ("windows-absolute-path", re.compile(r"(?<![A-Za-z0-9])(?:[A-Za-z]:[\\/])")),
    ("unc-absolute-path", re.compile(r"\\\\[A-Za-z0-9._$ -]+[\\/]")),
    (
        "posix-absolute-path",
        re.compile(r"(?<![A-Za-z0-9.])/(?:Users|home|tmp|var|private|mnt|Volumes)/[^\s\])}\"']+"),
    ),
    ("staging-reference", re.compile(r"\.obsidian-vault-mcp[\\/]staging(?:[\\/]|\b)", re.IGNORECASE)),
)
def scan_unsafe_references(text: str) -> list[dict[str, Any]]:
    """Locate forbidden local paths, file URLs, and staging references."""

    findings: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for kind, pattern in _UNSAFE_PATTERNS:
        for match in pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            marker = (kind, line)
            if marker in seen:
                continue
            seen.add(marker)
            findings.append({"kind": kind, "line": line, "value": match.group(0)})
    return sorted(findings, key=lambda item: (item["line"], item["kind"]))


class VerifyService:
    """Audit identity, links, locations, and portability without writing."""

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

    def verify(self) -> dict[str, Any]:
        issues: list[dict[str, Any]] = []
        visible_files = self._visible_files()
        parsed_markdown: dict[str, tuple[dict[str, Any], str]] = {}

        for relative, path in visible_files:
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                issues.append(_issue("unreadable-visible-file", "error", relative, f"Cannot read UTF-8 file: {exc}"))
                continue
            for finding in scan_unsafe_references(text):
                issues.append(
                    _issue(
                        finding["kind"],
                        "error",
                        relative,
                        f"User-visible file contains forbidden reference: {finding['value']}",
                        line=finding["line"],
                    )
                )
            if path.suffix.lower() != ".md":
                continue
            try:
                document = parse_frontmatter(text)
            except FrontmatterError as exc:
                issues.append(_issue("invalid-frontmatter", "error", relative, str(exc)))
                continue
            parsed_markdown[relative] = (document.fields, document.body)

        records = self._main_note_records(parsed_markdown, issues)
        self._check_duplicate_identity(records, issues)
        for record in records:
            self._check_attachment(record, "attachmentPdfLink", "pdf", issues)
            self._check_attachment(record, "attachmentMinerULink", "mineru", issues)

        issues.sort(
            key=lambda item: (
                item.get("path", "").casefold(),
                item["code"],
                str(item.get("zoteroKey", "")),
                int(item.get("line", 0)),
            )
        )
        by_code = dict(sorted(Counter(issue["code"] for issue in issues).items()))
        error_count = sum(issue["severity"] == "error" for issue in issues)
        warning_count = sum(issue["severity"] == "warning" for issue in issues)
        return {
            "ok": not issues,
            "issueCount": len(issues),
            "counts": {
                "errors": error_count,
                "warnings": warning_count,
                "filesScanned": len(visible_files),
                "mainNotes": len(records),
                "byCode": by_code,
            },
            "issues": issues,
        }

    run = verify

    def _visible_files(self) -> list[tuple[str, Path]]:
        files: list[tuple[str, Path]] = []
        for path in self.vault_path.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".md", ".base"}:
                continue
            relative_path = path.relative_to(self.vault_path)
            if len(relative_path.parts) > 1 and relative_path.parts[0].startswith("."):
                continue
            relative = normalize_vault_relative(relative_path.as_posix())
            files.append((relative, path))
        return sorted(files, key=lambda item: (item[0].casefold(), item[0]))

    def _main_note_records(
        self,
        parsed_markdown: Mapping[str, tuple[dict[str, Any], str]],
        issues: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        literature_root = normalize_vault_relative(str(self.config["literature"]["root"]))
        index_path = normalize_vault_relative(str(self.config["literature"]["index"]))
        wiki_folder = normalize_vault_relative(str(self.config["literature"]["wikiFolder"]))
        mineru_folder = normalize_vault_relative(str(self.config["mineru"]["markdownFolder"]))
        records: list[dict[str, Any]] = []

        for relative, (fields, _body) in parsed_markdown.items():
            path = PurePosixPath(relative)
            is_top_level_note = path.parent.as_posix() == literature_root and relative != index_path
            in_wiki = relative == wiki_folder or relative.startswith(f"{wiki_folder}/")
            in_mineru = relative == mineru_folder or relative.startswith(f"{mineru_folder}/")
            raw_key = fields.get("zoteroKey")
            looks_like_main = bool(
                raw_key
                and not in_wiki
                and not in_mineru
                and (
                    is_top_level_note
                    or "itemType" in fields
                    or "attachmentPdfLink" in fields
                    or "attachmentMinerULink" in fields
                )
            )

            if is_top_level_note and not raw_key:
                issues.append(
                    _issue(
                        "missing-zotero-key",
                        "error",
                        relative,
                        "A top-level literature note must have a zoteroKey",
                    )
                )
                continue
            if not looks_like_main:
                continue
            key = str(raw_key).strip()
            try:
                key = validate_zotero_key(key)
            except IdentityError as exc:
                issues.append(_issue("invalid-zotero-key", "error", relative, str(exc), zoteroKey=key))
                continue

            if not is_top_level_note or key.casefold() not in path.name.casefold():
                issues.append(
                    _issue(
                        "illegal-main-note-location",
                        "error",
                        relative,
                        f"Main note for {key} must be directly under {literature_root} with its key in the filename",
                        zoteroKey=key,
                    )
                )
            records.append({"path": relative, "zoteroKey": key, "fields": fields})
        return records

    @staticmethod
    def _check_duplicate_identity(records: list[dict[str, Any]], issues: list[dict[str, Any]]) -> None:
        by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
        by_doi: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for record in records:
            by_key[record["zoteroKey"].casefold()].append(record)
            doi = _normalize_doi(record["fields"].get("doi"))
            if doi:
                by_doi[doi].append(record)
        for duplicates in by_key.values():
            if len(duplicates) < 2:
                continue
            paths = sorted((record["path"] for record in duplicates), key=str.casefold)
            key = duplicates[0]["zoteroKey"]
            issues.append(
                _issue(
                    "duplicate-zotero-key",
                    "error",
                    paths[0],
                    f"zoteroKey {key} appears in multiple main notes",
                    zoteroKey=key,
                    paths=paths,
                )
            )
        for doi, duplicates in by_doi.items():
            if len(duplicates) < 2:
                continue
            paths = sorted((record["path"] for record in duplicates), key=str.casefold)
            issues.append(
                _issue(
                    "duplicate-doi",
                    "error",
                    paths[0],
                    f"DOI {doi} appears in multiple main notes",
                    doi=doi,
                    paths=paths,
                )
            )

    def _check_attachment(
        self,
        record: Mapping[str, Any],
        field: str,
        asset: str,
        issues: list[dict[str, Any]],
    ) -> None:
        value = record["fields"].get(field)
        if not value:
            issues.append(
                _issue(
                    f"missing-{asset}-link",
                    "warning",
                    record["path"],
                    f"Main note has no {field}",
                    zoteroKey=record["zoteroKey"],
                )
            )
            return
        try:
            target = _vault_link_target(value, markdown=asset == "mineru")
            full = self.paths.resolve(target)
        except (PathValidationError, TypeError, ValueError) as exc:
            issues.append(
                _issue(
                    f"invalid-{asset}-link",
                    "error",
                    record["path"],
                    f"Invalid {field}: {exc}",
                    zoteroKey=record["zoteroKey"],
                    target=str(value),
                )
            )
            return
        if not full.is_file():
            issues.append(
                _issue(
                    f"broken-{asset}-link",
                    "error",
                    record["path"],
                    f"Linked {asset} file does not exist: {target}",
                    zoteroKey=record["zoteroKey"],
                    target=target,
                )
            )


def _vault_link_target(value: Any, *, markdown: bool) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TypeError("link must be a non-empty string")
    raw = value.strip().strip('"\'')
    match = _WIKILINK_RE.match(raw)
    if match:
        raw = match.group(1).strip()
    elif raw.startswith("[["):
        raise ValueError("malformed Wikilink")
    target = normalize_vault_relative(raw)
    if markdown and PurePosixPath(target).suffix == "":
        target = f"{target}.md"
    return target


def _normalize_doi(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    doi = value.strip().casefold()
    doi = re.sub(r"^(?:doi:\s*|https?://(?:dx\.)?doi\.org/)", "", doi)
    return doi.rstrip(". ")


def _issue(code: str, severity: str, path: str, message: str, **details: Any) -> dict[str, Any]:
    return {"code": code, "severity": severity, "path": path, "message": message, **details}
