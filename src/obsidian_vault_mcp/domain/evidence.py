"""Deterministic text evidence extracted from normalized MinerU Markdown."""

from __future__ import annotations

import hashlib
import json
import posixpath
import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import PurePosixPath
from typing import Any

from .errors import IdentityError, PathValidationError
from .frontmatter import parse_frontmatter
from .identity import validate_zotero_key
from .paths import normalize_vault_relative

EVIDENCE_SCHEMA_VERSION = 1
EVIDENCE_CONTENT_TYPES = (
    "heading",
    "paragraph",
    "list",
    "table",
    "caption",
    "equation",
    "reference",
    "other",
)

_CONTENT_TYPE_SET = set(EVIDENCE_CONTENT_TYPES)
_BLOCK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
_EVIDENCE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,191}$")
_ASSET_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,191}$")
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_ATX_HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")
_SETEXT_HEADING_RE = re.compile(r"^[ \t]*(=+|-+)[ \t]*$")
_LIST_RE = re.compile(r"^[ \t]*(?:[-+*]|\d+[.)])[ \t]+\S")
_FENCE_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})[ \t]*([^\s`]*)")
_TABLE_SEPARATOR_RE = re.compile(
    r"^[ \t]*\|?[ \t]*:?-{3,}:?[ \t]*(?:\|[ \t]*:?-{3,}:?[ \t]*)+\|?[ \t]*$"
)
_CAPTION_RE = re.compile(
    r"^(?:(?:figure|fig\.?|table)[ \t]*(?:s?\d+|[ivxlcdm]+)|(?:图|表)[ \t]*[零〇一二三四五六七八九十百\d]+)(?:\b|[ \t]*[:：.\-–—])",
    re.IGNORECASE,
)
_MARKDOWN_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)\n]+)\)")
_WIKI_IMAGE_RE = re.compile(r"!\[\[([^\]\n|#]+)(?:\|[^\]]*)?\]\]")
_HTML_IMAGE_RE = re.compile(r"<img\b[^>]*\bsrc\s*=\s*([\"'])(.*?)\1[^>]*>", re.IGNORECASE)
_REFERENCE_HEADINGS = {
    "bibliography",
    "citations",
    "literature cited",
    "references",
    "参考文献",
    "引用文献",
    "参考资料",
}


@dataclass(frozen=True)
class EvidenceChunk:
    """One source-grounded Markdown block with stable provenance."""

    evidence_id: str
    zotero_key: str
    section_path: tuple[str, ...]
    content_type: str
    text: str
    source_path: str
    source_link: str
    page: int | None
    content_hash: str
    source_fingerprint: str
    block_id: str
    related_asset_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        key = validate_zotero_key(self.zotero_key)
        source_path = normalize_vault_relative(self.source_path)
        if not source_path.lower().endswith(".md"):
            raise PathValidationError("Evidence sourcePath must be a Vault-relative Markdown file")
        if not _EVIDENCE_ID_RE.fullmatch(self.evidence_id):
            raise IdentityError("evidenceId must be a portable, non-empty identifier")
        if self.content_type not in _CONTENT_TYPE_SET:
            raise ValueError(f"unsupported evidence contentType: {self.content_type}")
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError("EvidenceChunk text must be non-empty")
        if not _BLOCK_ID_RE.fullmatch(self.block_id):
            raise IdentityError("blockId must be a legal Obsidian block identifier")
        if self.page is not None and (type(self.page) is not int or self.page < 1):
            raise ValueError("EvidenceChunk page must be null or a positive integer")
        if not _HASH_RE.fullmatch(self.content_hash):
            raise ValueError("contentHash must be a lowercase SHA-256 digest")
        if not _HASH_RE.fullmatch(self.source_fingerprint):
            raise ValueError("sourceFingerprint must be a lowercase SHA-256 digest")
        section_path = tuple(_clean_text(value) for value in self.section_path if _clean_text(value))
        asset_ids = tuple(sorted(set(self.related_asset_ids), key=lambda value: (value.casefold(), value)))
        if any(not _ASSET_ID_RE.fullmatch(value) for value in asset_ids):
            raise IdentityError("relatedAssetIds must contain portable asset identifiers")
        object.__setattr__(self, "zotero_key", key)
        object.__setattr__(self, "source_path", source_path)
        object.__setattr__(self, "section_path", section_path)
        object.__setattr__(self, "related_asset_ids", asset_ids)
        expected_link = f"[[{source_path}#^{self.block_id}]]"
        if self.source_link != expected_link:
            raise ValueError("sourceLink must target sourcePath and blockId")

    def as_dict(self) -> dict[str, Any]:
        return {
            "evidenceId": self.evidence_id,
            "zoteroKey": self.zotero_key,
            "sectionPath": list(self.section_path),
            "contentType": self.content_type,
            "text": self.text,
            "sourcePath": self.source_path,
            "sourceLink": self.source_link,
            "page": self.page,
            "contentHash": self.content_hash,
            "sourceFingerprint": self.source_fingerprint,
            "blockId": self.block_id,
            "relatedAssetIds": list(self.related_asset_ids),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "EvidenceChunk":
        if not isinstance(value, Mapping):
            raise TypeError("EvidenceChunk must be loaded from a mapping")
        section_path = value.get("sectionPath", [])
        related_assets = value.get("relatedAssetIds", [])
        if isinstance(section_path, (str, bytes)) or not isinstance(section_path, Sequence):
            raise TypeError("sectionPath must be an array of strings")
        if isinstance(related_assets, (str, bytes)) or not isinstance(related_assets, Sequence):
            raise TypeError("relatedAssetIds must be an array of strings")
        return cls(
            evidence_id=str(value.get("evidenceId") or ""),
            zotero_key=str(value.get("zoteroKey") or ""),
            section_path=tuple(str(item) for item in section_path),
            content_type=str(value.get("contentType") or ""),
            text=str(value.get("text") or ""),
            source_path=str(value.get("sourcePath") or ""),
            source_link=str(value.get("sourceLink") or ""),
            page=value.get("page"),
            content_hash=str(value.get("contentHash") or ""),
            source_fingerprint=str(value.get("sourceFingerprint") or ""),
            block_id=str(value.get("blockId") or ""),
            related_asset_ids=tuple(str(item) for item in related_assets),
        )


@dataclass(frozen=True)
class EvidenceParseResult:
    chunks: tuple[EvidenceChunk, ...]
    warnings: tuple[dict[str, Any], ...]
    source_markdown_sha256: str


@dataclass(frozen=True)
class _RawBlock:
    content_type: str
    text: str
    section_path: tuple[str, ...]
    block_id_candidate: str
    block_id_valid: bool
    image_paths: tuple[str, ...]
    image_alts: tuple[str, ...]
    source_index: int = 0
    piece_index: int = 0
    source_start: int = -1
    source_end: int = -1


class _AssetResolver:
    def __init__(self, source_path: str, assets: Iterable[Mapping[str, Any]]) -> None:
        self.source_path = source_path
        self.by_path: dict[str, set[str]] = {}
        self.by_alt: dict[str, set[str]] = {}
        for asset in assets:
            if not isinstance(asset, Mapping):
                continue
            asset_id = str(asset.get("assetId") or "")
            if not _ASSET_ID_RE.fullmatch(asset_id):
                continue
            normalized_path = asset.get("normalizedPath")
            if isinstance(normalized_path, str) and normalized_path:
                try:
                    portable = normalize_vault_relative(normalized_path)
                except PathValidationError:
                    pass
                else:
                    self.by_path.setdefault(portable, set()).add(asset_id)
            references = asset.get("references", [])
            if isinstance(references, list):
                for reference in references:
                    if not isinstance(reference, Mapping):
                        continue
                    alt = _normalized_match_text(reference.get("alt"))
                    if alt:
                        self.by_alt.setdefault(alt, set()).add(asset_id)

    def resolve(self, image_paths: Iterable[str], image_alts: Iterable[str], text: str) -> tuple[str, ...]:
        matches: set[str] = set()
        for raw_path in image_paths:
            target = self._target(raw_path)
            if target:
                matches.update(self.by_path.get(target, ()))
        if matches:
            return tuple(sorted(matches, key=lambda value: (value.casefold(), value)))
        for alt in image_alts:
            matches.update(self.by_alt.get(_normalized_match_text(alt), ()))
        matches.update(self.by_alt.get(_normalized_match_text(text), ()))
        return tuple(sorted(matches, key=lambda value: (value.casefold(), value)))

    def _target(self, raw_path: str) -> str:
        value = raw_path.strip().strip("<>\"'")
        if not value or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", value) or value.startswith(("/", "\\")):
            return ""
        value = value.replace("\\", "/").split("#", 1)[0]
        parent = PurePosixPath(self.source_path).parent.as_posix()
        candidates = (value, posixpath.normpath(posixpath.join(parent, value)))
        for candidate in candidates:
            try:
                portable = normalize_vault_relative(candidate)
            except PathValidationError:
                continue
            if portable in self.by_path:
                return portable
        return ""


def parse_evidence_markdown(
    markdown: str,
    *,
    zotero_key: str,
    source_path: str,
    asset_manifest: Mapping[str, Any] | None = None,
    block_id_prefix: str = "ev",
    max_chunk_chars: int = 2500,
    overlap_chars: int = 200,
) -> EvidenceParseResult:
    """Parse Markdown blocks without inventing page numbers or source facts."""

    if not isinstance(markdown, str):
        raise TypeError("MinerU Markdown must be text")
    key = validate_zotero_key(zotero_key)
    if not isinstance(block_id_prefix, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,31}", block_id_prefix):
        raise IdentityError("block_id_prefix must be a portable identifier of at most 32 characters")
    if type(max_chunk_chars) is not int or not 256 <= max_chunk_chars <= 100_000:
        raise ValueError("max_chunk_chars must be an integer from 256 to 100000")
    if type(overlap_chars) is not int or not 0 <= overlap_chars < max_chunk_chars:
        raise ValueError("overlap_chars must be a non-negative integer smaller than max_chunk_chars")
    portable_source = normalize_vault_relative(source_path)
    if not portable_source.lower().endswith(".md"):
        raise PathValidationError("Evidence sourcePath must end with .md")
    document = parse_frontmatter(markdown)
    source_key = document.fields.get("zoteroKey")
    if source_key not in (None, "") and str(source_key) != key:
        raise IdentityError(f"MinerU Markdown zoteroKey does not match {key}")

    source_blocks, block_id_warnings = _assign_block_ids(
        _parse_blocks(document.body),
        zotero_key=key,
        source_path=portable_source,
        block_id_prefix=block_id_prefix,
    )
    raw_blocks, size_warnings = _bounded_raw_blocks(
        source_blocks,
        max_chunk_chars=max_chunk_chars,
        overlap_chars=overlap_chars,
    )
    assets = asset_manifest.get("assets", []) if isinstance(asset_manifest, Mapping) else []
    resolver = _AssetResolver(portable_source, assets if isinstance(assets, list) else [])
    source_sha = _sha256(markdown.encode("utf-8"))
    warnings: list[dict[str, Any]] = [*block_id_warnings, *size_warnings]
    chunks: list[EvidenceChunk] = []

    for block in raw_blocks:
        content_hash = _sha256(block.text.encode("utf-8"))
        block_id = block.block_id_candidate
        identity_seed = _canonical_hash(
            {
                "zoteroKey": key,
                "sourcePath": portable_source,
                "blockId": block_id,
                "pieceIndex": block.piece_index,
            }
        )
        section_slug = _section_slug(block.section_path)
        evidence_id = f"{key}-{section_slug}-{identity_seed[:12]}"
        fingerprint = _canonical_hash(
            {
                "zoteroKey": key,
                "sourcePath": portable_source,
                "sectionPath": list(block.section_path),
                "contentType": block.content_type,
                "blockId": block_id,
                "pieceIndex": block.piece_index,
            }
        )
        related_assets = resolver.resolve(block.image_paths, block.image_alts, block.text)
        chunks.append(
            EvidenceChunk(
                evidence_id=evidence_id,
                zotero_key=key,
                section_path=block.section_path,
                content_type=block.content_type,
                text=block.text,
                source_path=portable_source,
                source_link=f"[[{portable_source}#^{block_id}]]",
                page=None,
                content_hash=content_hash,
                source_fingerprint=fingerprint,
                block_id=block_id,
                related_asset_ids=related_assets,
            )
        )

    linked_chunks: list[EvidenceChunk] = []
    for chunk in chunks:
        if (
            chunk.content_type == "caption"
            and not chunk.related_asset_ids
            and linked_chunks
            and linked_chunks[-1].content_type == "other"
            and linked_chunks[-1].section_path == chunk.section_path
            and linked_chunks[-1].related_asset_ids
        ):
            chunk = replace(chunk, related_asset_ids=linked_chunks[-1].related_asset_ids)
        linked_chunks.append(chunk)
    return EvidenceParseResult(tuple(linked_chunks), tuple(warnings), source_sha)


def materialize_evidence_block_ids(
    markdown: str,
    *,
    zotero_key: str,
    source_path: str,
    block_id_prefix: str = "ev",
) -> tuple[str, tuple[dict[str, Any], ...]]:
    """Insert or repair deterministic Obsidian block IDs without rewriting content."""

    if not isinstance(markdown, str):
        raise TypeError("MinerU Markdown must be text")
    key = validate_zotero_key(zotero_key)
    portable_source = normalize_vault_relative(source_path)
    if not portable_source.lower().endswith(".md"):
        raise PathValidationError("Evidence sourcePath must end with .md")
    if not isinstance(block_id_prefix, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,31}", block_id_prefix):
        raise IdentityError("block_id_prefix must be a portable identifier of at most 32 characters")
    document = parse_frontmatter(markdown)
    source_key = document.fields.get("zoteroKey")
    if source_key not in (None, "") and str(source_key) != key:
        raise IdentityError(f"MinerU Markdown zoteroKey does not match {key}")

    blocks = _parse_blocks(document.body)
    assigned, warnings = _assign_block_ids(
        blocks,
        zotero_key=key,
        source_path=portable_source,
        block_id_prefix=block_id_prefix,
    )
    if not assigned:
        return markdown, tuple(warnings)

    prefix, body = _raw_document_parts(markdown)
    lines = body.splitlines(keepends=True)
    newline = "\r\n" if "\r\n" in body and body.count("\r\n") >= body.count("\n") - body.count("\r\n") else "\n"
    insertions: list[tuple[int, str]] = []
    for original, updated in zip(blocks, assigned):
        if original.block_id_candidate == updated.block_id_candidate and original.block_id_valid:
            continue
        if original.block_id_candidate and _replace_existing_block_id(
            lines,
            original,
            original.block_id_candidate,
            updated.block_id_candidate,
        ):
            continue
        insertions.append((original.source_end, updated.block_id_candidate))

    for index, block_id in sorted(insertions, reverse=True):
        bounded_index = max(0, min(index, len(lines)))
        if bounded_index > 0 and not lines[bounded_index - 1].endswith(("\n", "\r")):
            lines[bounded_index - 1] += newline
        lines.insert(bounded_index, f"^{block_id}{newline}")
    return prefix + "".join(lines), tuple(warnings)


def evidence_block_id_counts(markdown: str) -> dict[str, int]:
    """Count valid block IDs physically present in Markdown source blocks."""

    document = parse_frontmatter(markdown)
    counts: dict[str, int] = {}
    for block in _parse_blocks(document.body):
        if block.block_id_candidate and block.block_id_valid:
            counts[block.block_id_candidate] = counts.get(block.block_id_candidate, 0) + 1
    return counts


def _assign_block_ids(
    blocks: Sequence[_RawBlock],
    *,
    zotero_key: str,
    source_path: str,
    block_id_prefix: str,
) -> tuple[list[_RawBlock], list[dict[str, Any]]]:
    seen: set[str] = set()
    generated_counts: dict[str, int] = {}
    assigned: list[_RawBlock] = []
    warnings: list[dict[str, Any]] = []
    for block_index, block in enumerate(blocks):
        candidate = block.block_id_candidate
        if candidate and not block.block_id_valid:
            warnings.append({"code": "invalid-block-id", "blockId": candidate, "blockIndex": block_index})
            candidate = ""
        if candidate and candidate in seen:
            warnings.append({"code": "duplicate-block-id", "blockId": candidate, "blockIndex": block_index})
            candidate = ""
        if not candidate:
            locator_base = _canonical_hash(
                {
                    "zoteroKey": zotero_key,
                    "sourcePath": source_path,
                    "sectionPath": list(block.section_path),
                    "contentType": block.content_type,
                    "contentHash": _sha256(block.text.encode("utf-8")),
                }
            )
            occurrence = generated_counts.get(locator_base, 0) + 1
            generated_counts[locator_base] = occurrence
            candidate = f"{block_id_prefix}-{locator_base[:12]}" + (f"-{occurrence}" if occurrence > 1 else "")
            while candidate in seen:
                occurrence += 1
                generated_counts[locator_base] = occurrence
                candidate = f"{block_id_prefix}-{locator_base[:12]}-{occurrence}"
        seen.add(candidate)
        assigned.append(replace(block, block_id_candidate=candidate, block_id_valid=True))
    return assigned, warnings


def _bounded_raw_blocks(
    blocks: Sequence[_RawBlock],
    *,
    max_chunk_chars: int,
    overlap_chars: int,
) -> tuple[list[_RawBlock], list[dict[str, Any]]]:
    result: list[_RawBlock] = []
    warnings: list[dict[str, Any]] = []
    for block_index, block in enumerate(blocks):
        if len(block.text) <= max_chunk_chars:
            result.append(block)
            continue
        if block.content_type in {"heading", "table", "equation"}:
            result.append(block)
            warnings.append(
                {
                    "code": "oversized-structured-evidence",
                    "blockIndex": block_index,
                    "contentType": block.content_type,
                    "chars": len(block.text),
                }
            )
            continue
        pieces = _overlapping_text_slices(block.text, max_chunk_chars, overlap_chars)
        for piece_index, text in enumerate(pieces):
            paths, alts = _image_references(text)
            result.append(
                _RawBlock(
                    content_type=block.content_type,
                    text=text,
                    section_path=block.section_path,
                    block_id_candidate=block.block_id_candidate,
                    block_id_valid=block.block_id_valid,
                    image_paths=paths,
                    image_alts=alts,
                    source_index=block.source_index,
                    piece_index=piece_index,
                    source_start=block.source_start,
                    source_end=block.source_end,
                )
            )
        warnings.append(
            {
                "code": "evidence-block-split",
                "blockIndex": block_index,
                "contentType": block.content_type,
                "chunks": len(pieces),
                "chars": len(block.text),
            }
        )
    return result, warnings


def _overlapping_text_slices(text: str, limit: int, overlap: int) -> list[str]:
    pieces: list[str] = []
    start = 0
    while start < len(text):
        maximum = min(len(text), start + limit)
        end = maximum
        if maximum < len(text):
            boundary = max(
                text.rfind("\n", start + limit // 2, maximum),
                text.rfind(" ", start + limit // 2, maximum),
            )
            if boundary > start:
                end = boundary
        piece = text[start:end].strip()
        if piece:
            pieces.append(piece)
        if end >= len(text):
            break
        next_start = max(start + 1, end - overlap)
        while next_start < end and not text[next_start].isspace():
            next_start += 1
        start = next_start if next_start < end else end
    return pieces


def _parse_blocks(body: str) -> list[_RawBlock]:
    lines = body.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    blocks: list[_RawBlock] = []
    headings: list[str] = []
    index = 0
    while index < len(lines):
        if not lines[index].strip():
            index += 1
            continue
        line = lines[index]
        atx = _ATX_HEADING_RE.match(line)
        if atx:
            end = _include_following_block_id(lines, index + 1)
            heading_lines = [atx.group(2).strip()]
            if end > index + 1:
                heading_lines.append(lines[index + 1])
            raw_lines, candidate, valid = _strip_block_id(heading_lines)
            title = _clean_text(raw_lines[0] if raw_lines else atx.group(2))
            level = len(atx.group(1))
            headings = headings[: level - 1]
            headings.append(title)
            blocks.append(
                replace(
                    _raw_block("heading", title, headings, candidate, valid),
                    source_index=len(blocks),
                    source_start=index,
                    source_end=end,
                )
            )
            index = end
            continue
        if index + 1 < len(lines) and line.strip() and _SETEXT_HEADING_RE.match(lines[index + 1]):
            end = _include_following_block_id(lines, index + 2)
            heading_lines = [line.strip()]
            if end > index + 2:
                heading_lines.append(lines[index + 2])
            raw_lines, candidate, valid = _strip_block_id(heading_lines)
            title = _clean_text(raw_lines[0] if raw_lines else line)
            level = 1 if lines[index + 1].lstrip().startswith("=") else 2
            headings = headings[: level - 1]
            headings.append(title)
            blocks.append(
                replace(
                    _raw_block("heading", title, headings, candidate, valid),
                    source_index=len(blocks),
                    source_start=index,
                    source_end=end,
                )
            )
            index = end
            continue

        fence = _FENCE_RE.match(line)
        if fence:
            end = index + 1
            marker = fence.group(1)[0]
            minimum = len(fence.group(1))
            while end < len(lines):
                if re.match(rf"^[ \t]*{re.escape(marker)}{{{minimum},}}[ \t]*$", lines[end]):
                    end += 1
                    break
                end += 1
            end = _include_following_block_id(lines, end)
            block_lines = lines[index:end]
            language = fence.group(2).casefold()
            content_type = "equation" if language in {"math", "latex", "tex"} else "other"
            blocks.append(
                replace(
                    _block_from_lines(content_type, block_lines, headings),
                    source_index=len(blocks),
                    source_start=index,
                    source_end=end,
                )
            )
            index = end
            continue

        if line.lstrip().startswith("$$") or line.lstrip().startswith("\\["):
            closing = "$$" if line.lstrip().startswith("$$") else "\\]"
            end = index + 1
            if line.strip() != closing or line.strip().count(closing) < 2:
                while end < len(lines):
                    if closing in lines[end]:
                        end += 1
                        break
                    end += 1
            end = _include_following_block_id(lines, end)
            blocks.append(
                replace(
                    _block_from_lines("equation", lines[index:end], headings),
                    source_index=len(blocks),
                    source_start=index,
                    source_end=end,
                )
            )
            index = end
            continue

        if index + 1 < len(lines) and "|" in line and _TABLE_SEPARATOR_RE.match(lines[index + 1]):
            end = index + 2
            while end < len(lines) and lines[end].strip() and "|" in lines[end]:
                end += 1
            end = _include_following_block_id(lines, end)
            blocks.append(
                replace(
                    _block_from_lines("table", lines[index:end], headings),
                    source_index=len(blocks),
                    source_start=index,
                    source_end=end,
                )
            )
            index = end
            continue

        if _LIST_RE.match(line):
            end = index + 1
            while end < len(lines) and lines[end].strip() and not _starts_non_list_block(lines, end):
                end += 1
            content_type = "reference" if _in_reference_section(headings) else "list"
            blocks.append(
                replace(
                    _block_from_lines(content_type, lines[index:end], headings),
                    source_index=len(blocks),
                    source_start=index,
                    source_end=end,
                )
            )
            index = end
            continue

        end = index + 1
        while end < len(lines) and lines[end].strip() and not _starts_distinct_block(lines, end):
            end += 1
        block_lines = lines[index:end]
        content_lines, _candidate, _valid = _strip_block_id(block_lines)
        raw_text = "\n".join(content_lines).strip()
        image_paths, image_alts = _image_references(raw_text)
        caption_text = _caption_text(raw_text, image_alts)
        if _in_reference_section(headings):
            content_type = "reference"
        elif caption_text:
            content_type = "caption"
        elif image_paths and not re.sub(r"!\[[^\]]*\]\([^)]+\)|!\[\[[^\]]+\]\]|<img\b[^>]*>", "", raw_text, flags=re.IGNORECASE).strip():
            content_type = "other"
        else:
            content_type = "paragraph"
        block = replace(
            _block_from_lines(content_type, block_lines, headings, text_override=caption_text or None),
            source_index=len(blocks),
            source_start=index,
            source_end=end,
        )
        blocks.append(block)
        index = end
    return [block for block in blocks if block.text.strip()]


def _include_following_block_id(lines: list[str], end: int) -> int:
    if end < len(lines) and re.fullmatch(r"[ \t]*\^[^\s]+[ \t]*", lines[end]):
        return end + 1
    return end


def _starts_distinct_block(lines: list[str], index: int) -> bool:
    line = lines[index]
    if _ATX_HEADING_RE.match(line) or _FENCE_RE.match(line) or _LIST_RE.match(line):
        return True
    if line.lstrip().startswith(("$$", "\\[")):
        return True
    return index + 1 < len(lines) and "|" in line and bool(_TABLE_SEPARATOR_RE.match(lines[index + 1]))


def _starts_non_list_block(lines: list[str], index: int) -> bool:
    line = lines[index]
    if _ATX_HEADING_RE.match(line) or _FENCE_RE.match(line):
        return True
    if line.lstrip().startswith(("$$", "\\[")):
        return True
    return index + 1 < len(lines) and "|" in line and bool(_TABLE_SEPARATOR_RE.match(lines[index + 1]))


def _block_from_lines(
    content_type: str,
    lines: list[str],
    headings: Sequence[str],
    *,
    text_override: str | None = None,
) -> _RawBlock:
    stripped, candidate, valid = _strip_block_id(lines)
    raw_text = "\n".join(stripped).strip()
    image_paths, image_alts = _image_references(raw_text)
    text = _clean_text(text_override) if text_override is not None else raw_text
    return _RawBlock(content_type, text, tuple(headings), candidate, valid, image_paths, image_alts)


def _raw_block(
    content_type: str,
    text: str,
    headings: Sequence[str],
    candidate: str = "",
    valid: bool = True,
) -> _RawBlock:
    paths, alts = _image_references(text)
    return _RawBlock(content_type, text, tuple(headings), candidate, valid, paths, alts)


def _strip_block_id(lines: list[str]) -> tuple[list[str], str, bool]:
    result = list(lines)
    if not result:
        return result, "", True
    standalone = re.fullmatch(r"[ \t]*\^([^\s]+)[ \t]*", result[-1])
    if standalone:
        candidate = standalone.group(1)
        return result[:-1], candidate, bool(_BLOCK_ID_RE.fullmatch(candidate))
    suffix = re.search(r"[ \t]+\^([^\s]+)[ \t]*$", result[-1])
    if suffix:
        candidate = suffix.group(1)
        result[-1] = result[-1][: suffix.start()].rstrip()
        return result, candidate, bool(_BLOCK_ID_RE.fullmatch(candidate))
    return result, "", True


def _raw_document_parts(markdown: str) -> tuple[str, str]:
    text = markdown
    bom = ""
    if text.startswith("\ufeff"):
        bom, text = "\ufeff", text[1:]
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return bom, text
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return bom + "".join(lines[: index + 1]), "".join(lines[index + 1 :])
    return bom, text


def _replace_existing_block_id(
    lines: list[str],
    block: _RawBlock,
    old_block_id: str,
    new_block_id: str,
) -> bool:
    start = max(0, block.source_start)
    end = min(len(lines), block.source_end)
    for index in range(end - 1, start - 1, -1):
        line = lines[index]
        content = line.rstrip("\r\n")
        ending = line[len(content) :]
        standalone = re.fullmatch(r"(?P<indent>[ \t]*)\^(?P<id>[^\s]+)(?P<trailing>[ \t]*)", content)
        if standalone and standalone.group("id") == old_block_id:
            lines[index] = f"{standalone.group('indent')}^{new_block_id}{standalone.group('trailing')}{ending}"
            return True
        suffix = re.search(r"(?P<space>[ \t]+)\^(?P<id>[^\s]+)(?P<trailing>[ \t]*)$", content)
        if suffix and suffix.group("id") == old_block_id:
            lines[index] = f"{content[:suffix.start()]}{suffix.group('space')}^{new_block_id}{suffix.group('trailing')}{ending}"
            return True
    return False


def _image_references(text: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    paths: list[str] = []
    alts: list[str] = []
    for match in _MARKDOWN_IMAGE_RE.finditer(text):
        destination = match.group(2).strip()
        if destination.startswith("<") and ">" in destination:
            destination = destination[1 : destination.index(">")]
        else:
            destination = destination.split()[0] if destination else ""
        if destination:
            paths.append(destination)
        if match.group(1).strip():
            alts.append(match.group(1).strip())
    paths.extend(match.group(1).strip() for match in _WIKI_IMAGE_RE.finditer(text) if match.group(1).strip())
    paths.extend(match.group(2).strip() for match in _HTML_IMAGE_RE.finditer(text) if match.group(2).strip())
    return tuple(paths), tuple(alts)


def _caption_text(text: str, image_alts: Sequence[str]) -> str:
    candidates = [*image_alts, text]
    for candidate in candidates:
        normalized = re.sub(r"^[ \t>*_`#]+", "", candidate.strip())
        if _CAPTION_RE.match(normalized):
            return _clean_text(candidate)
    return ""


def _in_reference_section(headings: Sequence[str]) -> bool:
    for heading in headings:
        normalized = _normalized_match_text(heading).rstrip(":：")
        if normalized in _REFERENCE_HEADINGS:
            return True
    return False


def _section_slug(section_path: Sequence[str]) -> str:
    value = section_path[-1] if section_path else "root"
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").casefold()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_value).strip("-")
    if not slug:
        slug = f"section-{_sha256(value.encode('utf-8'))[:8]}" if value else "root"
    return slug[:40]


def _canonical_hash(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return _sha256(encoded)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _clean_text(value: Any) -> str:
    return str(value).strip().replace("\r\n", "\n").replace("\r", "\n")


def _normalized_match_text(value: Any) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(value or "")).casefold()).strip()
