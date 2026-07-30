"""On-demand, model-neutral reading views over one MinerU Markdown file."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

from ..adapters.mineru.normalizer import (
    MinerUNormalizationError,
    parse_image_references,
    resolve_image_reference,
)
from ..adapters.vault.filesystem import VaultFilesystem, VaultPathSafetyError
from ..config.loader import load_config
from ..domain.frontmatter import parse_frontmatter
from ..domain.identity import validate_zotero_key
from ..domain.paths import (
    VaultPaths,
    naming_metadata_from_fields,
    normalize_vault_relative,
)

_MODES = {"overview", "full", "sections", "targeted", "figures"}
_TOKEN_RE = re.compile(r"[^\W_]+(?:[-'][^\W_]+)*", re.UNICODE)
_HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")
_PAGE_MARKER_RE = re.compile(
    r"^\s*(?:<!--\s*)?(?:page|p\.)\s*[:#]?\s*(\d+)(?:\s*-->)?\s*$",
    re.IGNORECASE,
)
_FIGURE_LABEL_RE = re.compile(
    r"\b(?P<kind>figure|fig\.?|table|scheme|equation|eq\.?)\s*[-:#]?\s*"
    r"[\(\[]?(?P<number>S?\d+|[IVXLCDM]+)[\)\]]?"
    r"(?P<panel>[a-z](?:\s*[-‐-―−]\s*[a-z])?)?\b"
    r"|(?P<cjk_kind>图|表|方案|方程|公式)\s*"
    r"(?P<cjk_number>[零〇一二三四五六七八九十百\d]+)",
    re.IGNORECASE,
)
_PANEL_RE = re.compile(r"(?:^|[\s,;])\(([a-z])\)", re.IGNORECASE)
_PAGE_IN_TEXT_RE = re.compile(r"\b(?:page|p\.)\s*(\d+)\b", re.IGNORECASE)
_EQUATION_TAG_RE = re.compile(r"\\tag\s*\{\s*(?:eq(?:uation)?\.?\s*)?(\d+)\s*\}", re.IGNORECASE)
_MATH_ENV_RE = re.compile(r"\\begin\{(?:equation|align|gather|multline)\*?\}", re.IGNORECASE)
_MATH_FENCE_RE = re.compile(r"^(?:```|~~~)\s*(?:math|latex|tex)\b", re.IGNORECASE)
_OVERVIEW_HEADINGS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("abstract", ("abstract", "summary", "摘要")),
    ("introduction", ("introduction", "background", "引言", "背景")),
    ("methods", ("methods", "methodology", "experimental", "方法", "实验")),
    ("results", ("results", "findings", "结果", "发现")),
    ("discussion", ("discussion", "讨论")),
    ("limitations", ("limitations", "limitation", "局限")),
    ("conclusion", ("conclusion", "conclusions", "结论", "总结")),
)


def parse_mineru_passages(markdown: str, source_path: str) -> list[dict[str, Any]]:
    """Parse Markdown paragraphs into transient, 1-based source passages."""

    portable_source = normalize_vault_relative(source_path)
    document = parse_frontmatter(markdown)
    lines = document.body.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    headings: list[str] = []
    current_page: int | None = None
    passages: list[dict[str, Any]] = []
    buffer: list[str] = []
    in_fence = False

    def flush() -> None:
        nonlocal buffer
        text = "\n".join(buffer).strip()
        buffer = []
        if not text:
            return
        section_path = list(headings)
        passage: dict[str, Any] = {
            "text": text,
            "sectionPath": section_path,
            "paragraphIndex": len(passages) + 1,
            "sourceLink": _source_link(portable_source, headings[-1] if headings else ""),
        }
        content_type = _content_type(text)
        if content_type != "paragraph":
            passage["contentType"] = content_type
        if current_page is not None:
            passage["page"] = current_page
        if headings:
            passage["heading"] = headings[-1]
        passages.append(passage)

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            if not in_fence and buffer:
                flush()
            buffer.append(line)
            in_fence = not in_fence
            if not in_fence:
                flush()
            continue
        if in_fence:
            buffer.append(line)
            continue
        heading = _HEADING_RE.match(line)
        if heading:
            flush()
            level = len(heading.group(1))
            value = _plain_text(heading.group(2))
            headings[level - 1 :] = [value]
            continue
        page_marker = _PAGE_MARKER_RE.match(stripped)
        if page_marker:
            flush()
            current_page = int(page_marker.group(1))
            continue
        if not stripped:
            flush()
            continue
        if buffer and _starts_new_block(buffer, line):
            flush()
        buffer.append(line)
    flush()
    return passages


class PaperReadService:
    """Return bounded passages and figures without reading or writing hidden evidence state."""

    def __init__(
        self,
        vault_path: str | os.PathLike[str],
        config: Mapping[str, Any] | None = None,
    ) -> None:
        self.vault_path = Path(vault_path).expanduser().resolve()
        self.config = dict(config) if config is not None else load_config(self.vault_path, require_exists=False)
        self.fs = VaultFilesystem(self.vault_path)
        self.paths = VaultPaths(self.vault_path, self.config)

    def read(
        self,
        zotero_key: str,
        *,
        mode: str = "overview",
        query: str = "",
        query_variants: Sequence[str] = (),
        sections: Sequence[str] = (),
        max_chars: int = 12_000,
        top_k: int = 8,
        include_images: bool = False,
    ) -> dict[str, Any]:
        key = validate_zotero_key(zotero_key)
        normalized_mode = str(mode).strip().casefold()
        if normalized_mode not in _MODES:
            raise ValueError(f"mode must be one of: {', '.join(sorted(_MODES))}")
        _integer_budget(max_chars, "max_chars", 1, 1_000_000)
        _integer_budget(top_k, "top_k", 1, 500)
        variants = _string_sequence(query_variants, "query_variants")
        requested_sections = _string_sequence(sections, "sections")

        metadata, source_fields, note_warnings = self._metadata(key)
        warnings = list(note_warnings)
        missing: list[str] = []
        source_path = self.paths.mineru_markdown(
            key,
            **naming_metadata_from_fields(source_fields),
        )
        passages: list[dict[str, Any]] = []
        raw_markdown = ""
        try:
            source = self.fs.owned_path(source_path)
        except VaultPathSafetyError as exc:
            missing.append("mineru")
            warnings.append(
                {
                    "code": "unsafe-vault-path",
                    "path": source_path,
                    "message": str(exc),
                }
            )
        else:
            try:
                if source.is_file():
                    raw_markdown = self.fs.read_text_owned(source_path)
                    passages = parse_mineru_passages(raw_markdown, source_path)
                elif source.exists():
                    raise OSError("MinerU Markdown path is not a regular file")
                else:
                    missing.append("mineru")
                    warnings.append(
                        {
                            "code": "mineru-markdown-missing",
                            "path": source_path,
                            "message": f"MinerU Markdown does not exist for {key}",
                        }
                    )
            except (OSError, UnicodeError, TypeError, ValueError) as exc:
                warnings.append(
                    {
                        "code": "mineru-markdown-unreadable",
                        "path": source_path,
                        "message": str(exc),
                    }
                )

        selected: list[dict[str, Any]]
        if normalized_mode == "full":
            selected = list(passages)
        elif normalized_mode == "targeted":
            normalized_query = " ".join(str(query).split())
            if not normalized_query:
                selected = []
                warnings.append(
                    {
                        "code": "empty-query",
                        "message": "targeted mode requires a non-empty query",
                    }
                )
            else:
                selected = _targeted(
                    passages,
                    (normalized_query, *variants),
                    normalized_query,
                )[:top_k]
        elif normalized_mode == "sections":
            if not requested_sections:
                selected = []
                warnings.append(
                    {
                        "code": "empty-sections",
                        "message": "sections mode requires at least one section",
                    }
                )
            else:
                wanted = [value.casefold() for value in requested_sections]
                selected = [
                    passage for passage in passages if any(requested in heading.casefold() for requested in wanted for heading in passage["sectionPath"])
                ]
        elif normalized_mode == "figures":
            selected = [passage for passage in passages if _is_target_passage(passage)]
        else:
            selected = _overview(passages, top_k)

        bounded, budget = _apply_budget(selected, max_chars)
        figures = self._figures(raw_markdown, source_path, passages) if raw_markdown and (normalized_mode == "figures" or include_images) else []
        available_sections = _unique(heading for passage in passages for heading in passage["sectionPath"])
        selected_sections = _unique(heading for passage in bounded for heading in passage["sectionPath"])
        result = {
            "ok": True,
            "zoteroKey": key,
            "mode": normalized_mode,
            "metadata": metadata,
            "passages": bounded,
            "figures": figures,
            "basicCoverage": {
                "fullTextAvailable": bool(raw_markdown),
                "totalPassages": len(passages),
                "selectedPassages": len(bounded),
                "sectionsAvailable": available_sections,
                "sectionsRead": selected_sections,
                "truncated": budget["truncated"],
            },
            "budget": budget,
            "missing": sorted(set(missing)),
            "warnings": _stable_warnings(warnings),
        }
        if normalized_mode == "targeted":
            result["query"] = " ".join(str(query).split())
            result["queryVariants"] = list(variants)
        if normalized_mode == "sections":
            result["requestedSections"] = list(requested_sections)
            result["unmatchedSections"] = [
                value for value in requested_sections if not any(value.casefold() in heading.casefold() for heading in available_sections)
            ]
        return result

    paper_read = read

    def _metadata(
        self,
        key: str,
    ) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
        literature_root = normalize_vault_relative(str(self.config["literature"]["root"]))
        warnings: list[dict[str, Any]] = []
        matches: list[tuple[str, dict[str, Any]]] = []
        try:
            candidates, rejected = self.fs.scan_owned_files(
                literature_root,
                recursive=False,
            )
        except VaultPathSafetyError as exc:
            candidates = []
            rejected = [exc.relative_path]
        for relative in rejected:
            if PurePosixPath(relative).suffix.lower() == ".md" or relative == literature_root:
                warnings.append(
                    {
                        "code": "unsafe-vault-path",
                        "path": relative,
                        "message": "Main-note candidate has a linked or reparse path",
                    }
                )
        for relative in candidates:
            if PurePosixPath(relative).suffix.lower() != ".md":
                continue
            try:
                fields = parse_frontmatter(self.fs.read_text_owned(relative)).fields
            except VaultPathSafetyError as exc:
                warnings.append(
                    {
                        "code": "unsafe-vault-path",
                        "path": exc.relative_path,
                        "message": str(exc),
                    }
                )
                continue
            except (OSError, UnicodeError, TypeError, ValueError):
                continue
            if str(fields.get("zoteroKey") or "") == key:
                matches.append((relative, fields))
        if len(matches) > 1:
            raise ValueError(f"multiple main literature notes exist for zoteroKey {key}")
        if not matches:
            warnings.append(
                {
                    "code": "main-note-missing",
                    "message": f"main literature note does not exist for {key}",
                }
            )
            fallback = {"title": key, "zoteroKey": key}
            return fallback, fallback, warnings
        path, fields = matches[0]
        names = (
            "title",
            "itemType",
            "year",
            "journal",
            "tags",
            "doi",
            "url",
            "abstract",
            "zoteroKey",
        )
        metadata = {name: fields[name] for name in names if fields.get(name) not in (None, "", [])}
        metadata.setdefault("title", key)
        metadata["notePath"] = path
        return metadata, fields, warnings

    def _figures(
        self,
        markdown: str,
        source_path: str,
        passages: Sequence[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        body = parse_frontmatter(markdown).body
        candidates: list[tuple[int, int, dict[str, Any]]] = []
        blocks = _text_blocks(body)
        sequence = 0
        for reference in parse_image_references(body):
            raw_reference = body[reference.start : reference.end]
            source_passage = _passage_containing(passages, raw_reference)
            alt = _plain_text(reference.alt)
            caption = _caption_for_reference(body, reference.end, blocks, alt)
            descriptive = " ".join(value for value in (alt, caption) if value)
            label, target_type, inline_panel = _figure_label(descriptive)
            if label is None and source_passage is not None:
                heading_label, heading_type, heading_panel = _figure_label(str(source_passage.get("heading") or ""))
                if heading_label is not None:
                    label = heading_label
                    target_type = heading_type
                    inline_panel = heading_panel
                    caption = caption or str(source_passage.get("heading") or "")
            panel_match = _PANEL_RE.search(descriptive)
            panel = inline_panel or (panel_match.group(1).casefold() if panel_match else None)
            page_match = _PAGE_IN_TEXT_RE.search(descriptive)
            page = int(page_match.group(1)) if page_match else source_passage.get("page") if source_passage is not None else None
            try:
                image_path = resolve_image_reference(
                    source_path,
                    reference.destination,
                )
            except MinerUNormalizationError:
                image_path = None
            try:
                image_exists = bool(image_path and self.fs.is_file_owned(image_path))
            except VaultPathSafetyError:
                image_exists = False
            context = caption or _nearest_context(passages, descriptive)
            sequence += 1
            candidates.append(
                (
                    int(source_passage.get("paragraphIndex") or len(passages) + sequence) if source_passage is not None else len(passages) + sequence,
                    sequence,
                    {
                        "targetType": target_type,
                        "targetLabel": label,
                        "targetPanel": panel,
                        "page": page,
                        "caption": caption or None,
                        "sourceLink": (source_passage.get("sourceLink") if source_passage is not None else _source_link(source_path, "")),
                        "imagePath": image_path,
                        "imageExists": image_exists,
                        "visualMode": "image" if image_exists else "caption_context",
                        "contentType": "image",
                        "content": raw_reference,
                        "context": context,
                    },
                )
            )

        for index, passage in enumerate(passages):
            content_type = str(passage.get("contentType") or "paragraph")
            if content_type not in {"table", "equation"}:
                continue
            sequence += 1
            candidates.append(
                (
                    int(passage.get("paragraphIndex") or index + 1),
                    sequence,
                    _structured_target(passages, index, content_type),
                )
            )
        return _coalesce_targets(candidates)


def _overview(
    passages: Sequence[dict[str, Any]],
    top_k: int,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen: set[int] = set()
    for _category, aliases in _OVERVIEW_HEADINGS:
        match = next(
            (passage for passage in passages if any(alias in heading.casefold() for alias in aliases for heading in passage["sectionPath"])),
            None,
        )
        if match is not None and match["paragraphIndex"] not in seen:
            selected.append(match)
            seen.add(match["paragraphIndex"])
    for passage in passages:
        if len(selected) >= top_k:
            break
        if passage["paragraphIndex"] not in seen:
            selected.append(passage)
            seen.add(passage["paragraphIndex"])
    return selected[:top_k]


def _targeted(
    passages: Sequence[dict[str, Any]],
    queries: Sequence[str],
    primary_query: str,
) -> list[dict[str, Any]]:
    ranked: list[tuple[float, int, dict[str, Any]]] = []
    for passage in passages:
        haystack = f"{' '.join(passage['sectionPath'])}\n{passage['text']}"
        exact = primary_query.casefold() in haystack.casefold()
        lexical = max((_lexical_score(haystack, query) for query in queries), default=0.0)
        score = (8.0 if exact else 0.0) + lexical * 5.0
        if score <= 0:
            continue
        value = dict(passage)
        value["score"] = round(score, 6)
        value["matchMethods"] = [name for name, matched in (("exact", exact), ("lexical", lexical > 0)) if matched]
        ranked.append((-score, passage["paragraphIndex"], value))
    ranked.sort(key=lambda value: (value[0], value[1]))
    return [value[2] for value in ranked]


def _apply_budget(
    passages: Sequence[dict[str, Any]],
    max_chars: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    used = 0
    truncated = False
    for passage in passages:
        remaining = max_chars - used
        if remaining <= 0:
            truncated = True
            break
        text = str(passage["text"])
        value = dict(passage)
        if len(text) > remaining:
            value["text"] = text[:remaining]
            value["truncated"] = True
            truncated = True
        selected.append(value)
        used += len(value["text"])
        if value.get("truncated"):
            break
    if len(selected) < len(passages):
        truncated = True
    return selected, {
        "maxChars": max_chars,
        "usedChars": used,
        "truncated": truncated,
        "scope": "passageText",
    }


def _text_blocks(text: str) -> list[tuple[int, int, str]]:
    blocks: list[tuple[int, int, str]] = []
    for match in re.finditer(r"(?ms)(?:^|\n\s*\n)([^\n].*?)(?=\n\s*\n|\Z)", text):
        value = match.group(1).strip()
        if value and not _HEADING_RE.match(value):
            blocks.append((match.start(1), match.end(1), _plain_text(value)))
    return blocks


def _caption_for_reference(
    body: str,
    reference_end: int,
    blocks: Sequence[tuple[int, int, str]],
    alt: str,
) -> str:
    next_block = next(
        (value for start, _end, value in blocks if start >= reference_end),
        "",
    )
    if next_block and not parse_image_references(next_block):
        return next_block
    return alt


def _passage_containing(
    passages: Sequence[Mapping[str, Any]],
    text: str,
) -> Mapping[str, Any] | None:
    if not text:
        return None
    return next(
        (passage for passage in passages if text in str(passage.get("text") or "")),
        None,
    )


def _structured_target(
    passages: Sequence[Mapping[str, Any]],
    index: int,
    content_type: str,
) -> dict[str, Any]:
    passage = passages[index]
    content = str(passage.get("text") or "")
    label, target_type, panel, caption = _target_details_for_passage(
        passages,
        index,
        content_type,
    )
    page_match = _PAGE_IN_TEXT_RE.search(caption or content)
    page = int(page_match.group(1)) if page_match else passage.get("page")
    return {
        "targetType": target_type,
        "targetLabel": label,
        "targetPanel": panel,
        "page": page,
        "caption": caption,
        "sourceLink": passage.get("sourceLink"),
        "imagePath": None,
        "imageExists": False,
        "visualMode": "table_text" if content_type == "table" else "equation_text",
        "contentType": content_type,
        "content": content,
        "context": _structured_context(passages, index, caption),
    }


def _target_details_for_passage(
    passages: Sequence[Mapping[str, Any]],
    index: int,
    expected_type: str,
) -> tuple[str | None, str, str | None, str | None]:
    passage = passages[index]
    candidate_texts = [
        str(passage.get("heading") or ""),
        str(passage.get("text") or ""),
    ]
    if index > 0:
        candidate_texts.append(str(passages[index - 1].get("text") or ""))
    if index + 1 < len(passages):
        candidate_texts.append(str(passages[index + 1].get("text") or ""))
    for candidate in candidate_texts:
        label, target_type, inline_panel = _figure_label(candidate)
        if label is None or target_type != expected_type:
            continue
        panel_match = _PANEL_RE.search(candidate)
        panel = inline_panel or (panel_match.group(1).casefold() if panel_match else None)
        return label, target_type, panel, _plain_text(candidate)
    if expected_type == "equation":
        tag = _EQUATION_TAG_RE.search(str(passage.get("text") or ""))
        if tag:
            return f"Equation {tag.group(1)}", "equation", None, None
    return None, expected_type, None, None


def _structured_context(
    passages: Sequence[Mapping[str, Any]],
    index: int,
    caption: str | None,
) -> str:
    values: list[str] = []

    def add(value: str) -> None:
        if value and value not in values:
            values.append(value)

    add(caption or "")
    add(str(passages[index].get("text") or ""))
    for neighbor_index in (index - 1, index + 1):
        if not 0 <= neighbor_index < len(passages):
            continue
        neighbor = passages[neighbor_index]
        if neighbor.get("contentType") in {"image", "table", "equation"}:
            continue
        add(str(neighbor.get("text") or ""))
    return "\n\n".join(values)


def _coalesce_targets(
    candidates: Sequence[tuple[int, int, dict[str, Any]]],
) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    for _order, _sequence, candidate in sorted(candidates, key=lambda value: (value[0], value[1])):
        label = candidate.get("targetLabel")
        if not isinstance(label, str) or not label:
            targets.append(candidate)
            continue
        match_index: int | None = None
        for index, existing in enumerate(targets):
            if existing.get("targetType") != candidate.get("targetType") or str(existing.get("targetLabel") or "").casefold() != label.casefold():
                continue
            if existing.get("contentType") == "image" and candidate.get("contentType") == "image" and existing.get("imagePath") != candidate.get("imagePath"):
                continue
            match_index = index
            break
        if match_index is None:
            targets.append(candidate)
        else:
            targets[match_index] = _merge_target_records(targets[match_index], candidate)
    return targets


def _merge_target_records(
    existing: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> dict[str, Any]:
    priority = {
        "caption_context": 1,
        "image": 2,
        "table_text": 3,
        "equation_text": 3,
    }
    existing_priority = priority.get(str(existing.get("visualMode") or ""), 0)
    candidate_priority = priority.get(str(candidate.get("visualMode") or ""), 0)
    primary, secondary = (candidate, existing) if candidate_priority > existing_priority else (existing, candidate)
    merged = dict(primary)
    for name in ("targetPanel", "page", "caption", "sourceLink", "content", "context"):
        if merged.get(name) in (None, "") and secondary.get(name) not in (None, ""):
            merged[name] = secondary[name]
    if secondary.get("imageExists") and not merged.get("imageExists"):
        merged["imagePath"] = secondary.get("imagePath")
        merged["imageExists"] = True
    return merged


def _figure_label(text: str) -> tuple[str | None, str, str | None]:
    match = _FIGURE_LABEL_RE.search(text)
    if match is None:
        return None, "figure", None
    if match.group("cjk_kind"):
        raw_kind = match.group("cjk_kind")
        number = match.group("cjk_number")
        kind, target_type = {
            "图": ("Figure", "figure"),
            "表": ("Table", "table"),
            "方案": ("Scheme", "scheme"),
            "方程": ("Equation", "equation"),
            "公式": ("Equation", "equation"),
        }[raw_kind]
        return f"{kind} {number}", target_type, None
    raw_kind = match.group("kind") or "Figure"
    folded_kind = raw_kind.casefold()
    if folded_kind.startswith("table"):
        kind, target_type = "Table", "table"
    elif folded_kind.startswith("scheme"):
        kind, target_type = "Scheme", "scheme"
    elif folded_kind.startswith(("eq", "equation")):
        kind, target_type = "Equation", "equation"
    else:
        kind, target_type = "Figure", "figure"
    number = match.group("number")
    panel = _normalized_panel(match.group("panel"))
    return (
        f"{kind} {number}",
        target_type,
        panel,
    )


def _normalized_panel(value: str | None) -> str | None:
    if not value:
        return None
    return re.sub(r"\s*[-‐-―−]\s*", "-", value).casefold()


def _nearest_context(
    passages: Sequence[Mapping[str, Any]],
    descriptive: str,
) -> str:
    if descriptive:
        folded = descriptive.casefold()
        for passage in passages:
            text = str(passage.get("text") or "")
            if folded in text.casefold() or text.casefold() in folded:
                return text
    return ""


def _is_target_passage(passage: Mapping[str, Any]) -> bool:
    if passage.get("contentType") in {"image", "table", "equation"}:
        return True
    descriptive = "\n".join(
        (
            str(passage.get("heading") or ""),
            str(passage.get("text") or ""),
        )
    )
    label, _target_type, _panel = _figure_label(descriptive)
    return label is not None


def _content_type(text: str) -> str:
    stripped = text.strip()
    if parse_image_references(stripped):
        return "image"
    if _is_equation_block(stripped):
        return "equation"
    lines = stripped.splitlines()
    if stripped.startswith(("```", "~~~")):
        return "code"
    if _is_markdown_table(lines):
        return "table"
    if all(re.match(r"^\s*(?:[-*+]|\d+[.)])\s+", line) for line in lines):
        return "list"
    if all(line.lstrip().startswith(">") for line in lines):
        return "quote"
    return "paragraph"


def _starts_new_block(buffer: Sequence[str], line: str) -> bool:
    previous_type = _content_type("\n".join(buffer))
    current_type = _content_type(line)
    if previous_type == "table" and _looks_like_table_row(line):
        return False
    if previous_type == "equation" and _equation_block_is_open("\n".join(buffer)):
        return False
    return (
        previous_type in {"image", "code", "table", "equation"}
        or current_type in {"image", "code", "equation"}
        or (previous_type == "table") != (current_type == "table")
    )


def _is_equation_block(text: str) -> bool:
    stripped = text.strip()
    return bool(stripped.startswith("$$") or stripped.startswith(r"\[") or _MATH_ENV_RE.search(stripped) or _MATH_FENCE_RE.match(stripped))


def _equation_block_is_open(text: str) -> bool:
    stripped = text.strip()
    if stripped.startswith("$$"):
        return stripped.count("$$") % 2 == 1
    if stripped.startswith(r"\["):
        return r"\]" not in stripped
    if _MATH_ENV_RE.search(stripped):
        return not re.search(
            r"\\end\{(?:equation|align|gather|multline)\*?\}",
            stripped,
            re.IGNORECASE,
        )
    return False


def _is_markdown_table(lines: Sequence[str]) -> bool:
    values = [line.strip() for line in lines if line.strip()]
    if len(values) < 2:
        return False
    if all(value.startswith("|") for value in values):
        return True
    if "|" not in values[0]:
        return False
    cells = values[1].strip("|").split("|")
    return bool(cells) and all(re.fullmatch(r"\s*:?-{3,}:?\s*", cell) for cell in cells)


def _looks_like_table_row(line: str) -> bool:
    return "|" in line


def _source_link(path: str, heading: str) -> str:
    return f"[[{path}#{heading}]]" if heading else f"[[{path}]]"


def _plain_text(value: str) -> str:
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", value)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"[*_`~]", "", text)
    return " ".join(text.split())


def _lexical_score(text: str, query: str) -> float:
    query_tokens = set(_tokens(query))
    if not query_tokens:
        return 0.0
    return len(query_tokens & set(_tokens(text))) / len(query_tokens)


def _tokens(value: str) -> list[str]:
    return [match.group(0).casefold() for match in _TOKEN_RE.finditer(value)]


def _string_sequence(values: Sequence[str], name: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise TypeError(f"{name} must be an array of strings")
    result: list[str] = []
    for value in values:
        if not isinstance(value, str):
            raise TypeError(f"{name} must be an array of strings")
        normalized = " ".join(value.split())
        if normalized and normalized not in result:
            result.append(normalized)
    return tuple(result)


def _integer_budget(value: int, name: str, minimum: int, maximum: int) -> None:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer from {minimum} to {maximum}")


def _unique(values: Sequence[str] | Any) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def _stable_warnings(
    warnings: Sequence[dict[str, Any] | None],
) -> list[dict[str, Any]]:
    values = [warning for warning in warnings if warning]
    return sorted(
        values,
        key=lambda item: (
            str(item.get("code") or ""),
            str(item.get("path") or ""),
            str(item.get("message") or ""),
        ),
    )
