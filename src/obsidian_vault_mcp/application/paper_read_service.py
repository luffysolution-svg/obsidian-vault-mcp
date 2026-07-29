"""Deterministic, model-neutral reading views over one paper's evidence."""

from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

from ..adapters.vault.filesystem import VaultFilesystem
from ..config.loader import load_config
from ..domain.errors import IdentityError, PathValidationError
from ..domain.evidence import EvidenceChunk
from ..domain.frontmatter import parse_frontmatter
from ..domain.identity import validate_zotero_key
from ..domain.image_assets import ImageAssetValidationError, parse_image_manifest
from ..domain.paths import VaultPaths, normalize_vault_relative
from .coverage_service import CoverageService
from .evidence_service import EvidenceService

_MODES = {"overview", "targeted", "sections", "full", "figures"}
_OVERVIEW_SECTIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("abstract", ("abstract", "summary", "摘要")),
    ("introduction", ("introduction", "background", "related work", "引言", "绪论", "背景", "研究背景", "相关工作")),
    (
        "methods",
        (
            "methods",
            "methodology",
            "experimental",
            "materials and methods",
            "method",
            "方法",
            "研究方法",
            "实验方法",
            "材料与方法",
        ),
    ),
    ("results", ("results", "findings", "结果", "研究结果", "实验结果", "主要发现")),
    ("discussion", ("discussion", "讨论", "结果与讨论", "分析与讨论")),
    ("limitations", ("limitations", "limitation", "局限", "局限性", "研究限制")),
    ("conclusion", ("conclusion", "conclusions", "结论", "结语", "总结")),
)
_FIGURE_LABEL_RE = re.compile(
    r"^\s*(?P<label>(?:(?:figure|fig\.?|table)\s*(?:s?\d+|[ivxlcdm]+)|(?:图|表)\s*[零〇一二三四五六七八九十百\d]+))\b",
    re.IGNORECASE,
)
_VISUAL_STATUSES = {
    "mineru_candidate",
    "referenced",
    "caption_only",
    "pdf_crop_available",
    "visual_verified",
    "unavailable",
}


class PaperReadService:
    """Return bounded evidence views without generating conclusions."""

    def __init__(
        self,
        vault_path: str | os.PathLike[str],
        config: Mapping[str, Any] | None = None,
        *,
        evidence_service: EvidenceService | None = None,
    ) -> None:
        self.vault_path = Path(vault_path).expanduser().resolve()
        self.config = dict(config) if config is not None else load_config(self.vault_path, require_exists=False)
        self.fs = VaultFilesystem(self.vault_path)
        self.paths = VaultPaths(self.vault_path, self.config)
        self.evidence = evidence_service or EvidenceService(self.vault_path, self.config)

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
        record_coverage: bool = False,
        coverage_dry_run: bool = False,
        coverage_transaction_id: str | None = None,
    ) -> dict[str, Any]:
        key = validate_zotero_key(zotero_key)
        normalized_mode = str(mode).strip().casefold()
        if normalized_mode not in _MODES:
            raise ValueError(f"mode must be one of: {', '.join(sorted(_MODES))}")
        if type(max_chars) is not int or not 1 <= max_chars <= 1_000_000:
            raise ValueError("max_chars must be an integer from 1 to 1000000")
        if type(top_k) is not int or not 1 <= top_k <= 500:
            raise ValueError("top_k must be an integer from 1 to 500")
        variants = _string_sequence(query_variants, "query_variants")
        requested_sections = _string_sequence(sections, "sections")

        warnings: list[dict[str, Any]] = []
        missing: list[str] = []
        evidence_state: dict[str, Any] | None = None
        chunks: list[EvidenceChunk] = []
        try:
            evidence_state = self.evidence.build(key)
            chunks = [EvidenceChunk.from_dict(value) for value in evidence_state["chunks"]]
            warnings.extend(evidence_state.get("warnings", []))
        except FileNotFoundError as exc:
            missing.append("mineru")
            warnings.append({"code": "mineru-markdown-missing", "message": str(exc)})

        source_path = str(evidence_state.get("sourcePath") or "") if evidence_state else ""
        metadata, status, metadata_warnings, metadata_missing = self._metadata(key, source_path)
        warnings.extend(metadata_warnings)
        missing.extend(metadata_missing)
        structure = _structure(chunks)
        manifest, manifest_warnings = self._manifest(key, source_path=source_path)
        warnings.extend(manifest_warnings)
        result: dict[str, Any] = {
            "ok": True,
            "zoteroKey": key,
            "mode": normalized_mode,
            "metadata": metadata,
            "structure": structure,
            "passages": [],
            "figures": [],
            "coverage": {},
            "missing": [],
            "warnings": [],
            "budget": {"maxChars": max_chars, "usedChars": 0, "truncated": False, "scope": "passageText"},
            "contentStatus": status,
        }
        status["evidenceAvailable"] = bool(chunks)
        status["evidenceChunkCount"] = len(chunks)
        status["imageManifestAvailable"] = manifest is not None

        if normalized_mode == "overview":
            selected, categories, overview_missing = _overview_passages(chunks)
            passages, budget = _apply_budget([_passage(chunk) for chunk in selected], max_chars)
            by_id = {passage["evidenceId"]: passage for passage in passages}
            result["passages"] = passages
            result["overview"] = {
                category: [by_id[evidence_id] for evidence_id in evidence_ids if evidence_id in by_id]
                for category, evidence_ids in categories.items()
            }
            if metadata.get("abstract"):
                overview_missing = [name for name in overview_missing if name != "abstract"]
                result["overviewAbstract"] = {
                    "text": metadata["abstract"],
                    "source": "zotero-metadata",
                    "isEvidenceChunk": False,
                }
            missing.extend(f"section:{name}" for name in overview_missing)
            result["coverage"] = _coverage("overview", passages, chunks, budget["truncated"], complete=False)
            result["budget"] = budget
        elif normalized_mode == "targeted":
            if not isinstance(query, str):
                raise TypeError("query must be a string")
            if not query.strip():
                warnings.append({"code": "empty-query", "message": "targeted mode requires a non-empty query"})
                passages = []
            else:
                ranked = _targeted(chunks, query, variants)[:top_k]
                passages = [_passage(chunk, score=score) for score, chunk in ranked]
            passages, budget = _apply_budget(passages, max_chars)
            result["passages"] = passages
            result["query"] = query
            result["queryVariantsUsedForRecall"] = variants
            result["coverage"] = _coverage("targeted", passages, chunks, budget["truncated"], complete=False)
            result["budget"] = budget
        elif normalized_mode == "sections":
            matched, unmatched = _section_passages(chunks, requested_sections)
            passages, budget = _apply_budget([_passage(chunk) for chunk in matched], max_chars)
            result["passages"] = passages
            result["requestedSections"] = requested_sections
            result["unmatchedSections"] = unmatched
            missing.extend(f"section:{name}" for name in unmatched)
            result["coverage"] = _coverage("sections", passages, chunks, budget["truncated"], complete=False)
            result["budget"] = budget
        elif normalized_mode == "full":
            passages, budget = _apply_budget([_passage(chunk) for chunk in chunks], max_chars)
            result["passages"] = passages
            complete = bool(chunks) and not budget["truncated"] and len(passages) == len(chunks)
            state = "complete" if complete else ("partial" if passages else "unreadable")
            result["coverage"] = _coverage(state, passages, chunks, budget["truncated"], complete=complete)
            result["budget"] = budget
        else:
            figures, figure_chunks, tables, figure_warnings = self._figures(chunks, manifest)
            warnings.extend(figure_warnings)
            selected = _unique_chunks([*figure_chunks, *tables])
            passages, budget = _apply_budget([_passage(chunk) for chunk in selected], max_chars)
            passage_by_id = {passage["evidenceId"]: passage for passage in passages}
            text_by_id = {evidence_id: passage["text"] for evidence_id, passage in passage_by_id.items()}
            for figure in figures:
                caption_id = figure.get("captionEvidenceId")
                if caption_id:
                    figure["caption"] = text_by_id.get(caption_id)
                    if caption_id not in text_by_id:
                        figure["warnings"].append("caption-excluded-by-budget")
            result["passages"] = passages
            result["figures"] = figures
            result["tables"] = [passage_by_id[chunk.evidence_id] for chunk in tables if chunk.evidence_id in passage_by_id]
            result["coverage"] = _coverage("figures", passages, chunks, budget["truncated"], complete=False)
            result["budget"] = budget
            if manifest is None:
                missing.append("image-manifest")

        if include_images and normalized_mode != "figures":
            figures, _figure_chunks, _tables, figure_warnings = self._figures(chunks, manifest)
            warnings.extend(figure_warnings)
            result["figures"] = figures
        result["includeImages"] = bool(include_images)
        result["binaryImagesEmbedded"] = False
        result["missing"] = sorted(set(missing), key=lambda value: (value.casefold(), value))
        result["warnings"] = _dedupe_warnings(warnings)
        if record_coverage:
            try:
                result["coverageLedger"] = self._record_coverage(
                    result,
                    dry_run=coverage_dry_run,
                    transaction_id=coverage_transaction_id,
                )
            except Exception as exc:
                result["warnings"] = _dedupe_warnings(
                    [*result["warnings"], {"code": "coverage-write-failed", "message": str(exc)}]
                )
        return result

    paper_read = read

    def _record_coverage(
        self,
        result: Mapping[str, Any],
        *,
        dry_run: bool,
        transaction_id: str | None,
    ) -> dict[str, Any]:
        passages = [item for item in result.get("passages", []) if isinstance(item, Mapping)]
        evidence_ids = {str(item.get("evidenceId")) for item in passages if item.get("evidenceId")}
        content_hashes = {
            str(item.get("evidenceId")): str(item.get("contentHash") or "")
            for item in passages
            if item.get("evidenceId")
        }
        figures = [item for item in result.get("figures", []) if isinstance(item, Mapping)]
        asset_ids = {str(item.get("assetId")) for item in figures if item.get("assetId")}
        mode = str(result["mode"])
        budget = result.get("budget", {})
        truncated = bool(budget.get("truncated")) if isinstance(budget, Mapping) else False
        coverage_state = str(result.get("coverage", {}).get("status") or "") if isinstance(result.get("coverage"), Mapping) else ""
        if mode == "targeted":
            granularity, level = "passage", "targeted"
        elif mode == "sections":
            granularity, level = "section", "partial" if truncated else "broad"
        elif mode == "full":
            granularity, level = "full", "complete" if coverage_state == "complete" else "partial"
        elif mode == "figures":
            granularity, level = "figure", "targeted"
        else:
            granularity, level = "overview", "partial" if truncated else "broad"
        metadata = result.get("metadata", {}) if isinstance(result.get("metadata"), Mapping) else {}
        payload: Any = content_hashes or {
            "title": metadata.get("title"),
            "abstract": metadata.get("abstract"),
            "year": metadata.get("year"),
        }
        source_kind = "mineru_image" if mode == "figures" else "evidence_index" if passages else "abstract" if metadata.get("abstract") else "zotero_metadata"
        if not passages and granularity not in {"metadata", "abstract"}:
            granularity = "abstract" if metadata.get("abstract") else "metadata"
            level = "partial" if metadata.get("abstract") else "listed"
        topic = str(result.get("query") or "")
        if not topic and mode == "sections":
            topic = ", ".join(str(value) for value in result.get("requestedSections", []))
        return CoverageService(self.vault_path, self.config).record(
            str(result["zoteroKey"]),
            source_kind=source_kind,
            topic=topic,
            granularity=granularity,
            coverage=level,
            confidence="high" if passages else "medium",
            content_hash=_canonical_hash(payload),
            tool_name="literature_paper_read",
            evidence_refs=evidence_ids,
            asset_refs=asset_ids,
            valid_evidence_ids=evidence_ids,
            valid_asset_ids=asset_ids,
            details={"mode": mode, "truncated": truncated},
            dry_run=dry_run,
            transaction_id=transaction_id,
        )

    def _metadata(
        self,
        key: str,
        source_path: str,
    ) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], list[str]]:
        warnings: list[dict[str, Any]] = []
        missing: list[str] = []
        note = self._main_note(key)
        fields: dict[str, Any] = dict(note["fields"]) if note else {}
        if note is None:
            warnings.append({"code": "main-note-missing", "message": f"main literature note does not exist for {key}"})
        if source_path and self.fs.exists(source_path):
            source_fields = parse_frontmatter(self.fs.read_text(source_path)).fields
            for name in ("title", "zoteroKey", "abstract", "year", "journal"):
                if not fields.get(name) and source_fields.get(name) not in (None, ""):
                    fields[name] = source_fields[name]
        fields.setdefault("zoteroKey", key)
        metadata_names = (
            "title",
            "itemType",
            "year",
            "journal",
            "tags",
            "doi",
            "url",
            "abstract",
            "zoteroKey",
            "zoteroPdfLink",
            "attachmentPdfLink",
            "attachmentMinerULink",
        )
        metadata = {name: fields.get(name) for name in metadata_names if fields.get(name) not in (None, "", [])}
        if not metadata.get("title"):
            metadata["title"] = key
            warnings.append({"code": "metadata-title-fallback", "message": "title is unavailable; zoteroKey is used as display fallback"})
        if not metadata.get("abstract"):
            missing.append("abstract")

        item_state = self._item_state(key)
        pdf_path = str(item_state.get("pdfPath") or "")
        if not pdf_path:
            pdf_path = _wikilink_target(fields.get("attachmentPdfLink"), markdown=False)
        pdf_available = bool(pdf_path and self.fs.exists(pdf_path) and self.paths.resolve(pdf_path).is_file())
        if not pdf_available:
            missing.append("pdf")
        status = {
            "mainNoteAvailable": note is not None,
            "pdfAvailable": pdf_available,
            "mineruAvailable": bool(source_path and self.fs.exists(source_path)),
            "evidenceAvailable": bool(source_path),
            "pdfPath": pdf_path or None,
            "mineruPath": source_path or None,
        }
        return metadata, status, warnings, missing

    def _main_note(self, key: str) -> dict[str, Any] | None:
        root = self.paths.resolve(str(self.config["literature"]["root"]))
        index_path = normalize_vault_relative(str(self.config["literature"]["index"]))
        matches: list[dict[str, Any]] = []
        if root.is_dir():
            for path in sorted(root.glob("*.md"), key=lambda value: (value.name.casefold(), value.name)):
                relative = self.fs.relative(path)
                if relative == index_path:
                    continue
                document = parse_frontmatter(path.read_text(encoding="utf-8-sig"))
                if str(document.fields.get("zoteroKey") or "") == key:
                    matches.append({"path": relative, "fields": document.fields, "body": document.body})
        if len(matches) > 1:
            raise IdentityError(f"multiple main literature notes exist for zoteroKey {key}")
        return matches[0] if matches else None

    def _item_state(self, key: str) -> dict[str, Any]:
        path = self.paths.state(key)
        if not self.fs.exists(path):
            return {}
        try:
            value = json.loads(self.fs.read_text(path))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) and value.get("zoteroKey") == key else {}

    def _manifest(self, key: str, *, source_path: str = "") -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        path = self.evidence.image_manifest_path(key)
        if not self.fs.exists(path):
            return None, [{"code": "image-manifest-missing", "message": f"image manifest does not exist for {key}"}]
        try:
            value = parse_image_manifest(self.fs.read_text(path)).as_dict()
        except (OSError, UnicodeError, ImageAssetValidationError) as exc:
            return None, [{"code": "invalid-image-manifest", "message": str(exc)}]
        if value.get("zoteroKey") != key:
            return None, [{"code": "invalid-image-manifest", "message": "manifest identity or assets are invalid"}]
        warnings: list[dict[str, Any]] = []
        if source_path and value.get("sourceMarkdown") != source_path:
            warnings.append({"code": "stale-image-manifest", "message": "manifest sourceMarkdown does not match MinerU Markdown"})
        if source_path and self.fs.exists(source_path):
            actual_sha256 = hashlib.sha256(self.fs.read_bytes(source_path)).hexdigest()
            if value.get("sourceMarkdownSha256") != actual_sha256:
                warnings.append({"code": "stale-image-manifest", "message": "manifest source Markdown hash is stale"})
        return value, warnings

    def _figures(
        self,
        chunks: Sequence[EvidenceChunk],
        manifest: Mapping[str, Any] | None,
    ) -> tuple[list[dict[str, Any]], list[EvidenceChunk], list[EvidenceChunk], list[dict[str, Any]]]:
        warnings: list[dict[str, Any]] = []
        tables = [chunk for chunk in chunks if chunk.content_type == "table"]
        if manifest is None:
            return [], [], tables, warnings
        by_asset: dict[str, list[EvidenceChunk]] = {}
        for chunk in chunks:
            for asset_id in chunk.related_asset_ids:
                by_asset.setdefault(asset_id, []).append(chunk)
        figures: list[dict[str, Any]] = []
        figure_chunks: list[EvidenceChunk] = []
        assets = [value for value in manifest.get("assets", []) if isinstance(value, Mapping)]
        assets.sort(key=lambda value: (str(value.get("assetId") or "").casefold(), str(value.get("assetId") or "")))
        for asset in assets:
            asset_id = str(asset.get("assetId") or "")
            status = str(asset.get("status") or "unlinked_candidate")
            related = by_asset.get(asset_id, [])
            manifest_caption_id = str(asset.get("captionEvidenceId") or "")
            manifest_context_ids = {
                str(value) for value in asset.get("contextEvidenceIds", []) if isinstance(value, str) and value
            }
            by_evidence_id = {chunk.evidence_id: chunk for chunk in chunks}
            if manifest_caption_id in by_evidence_id and by_evidence_id[manifest_caption_id] not in related:
                related = [*related, by_evidence_id[manifest_caption_id]]
            for evidence_id in sorted(manifest_context_ids):
                if evidence_id in by_evidence_id and by_evidence_id[evidence_id] not in related:
                    related.append(by_evidence_id[evidence_id])
            captions = [chunk for chunk in related if chunk.content_type == "caption"]
            contexts = [chunk for chunk in related if chunk.content_type != "caption"]
            caption = captions[0] if captions else None
            figure_chunks.extend(related)
            item_warnings: list[str] = []
            normalized_path = _safe_manifest_path(asset.get("normalizedPath"), item_warnings, "normalizedPath")
            cache_path = _safe_manifest_path(asset.get("cachePath"), item_warnings, "cachePath")
            pdf_crop_path = _safe_manifest_path(asset.get("pdfCropPath"), item_warnings, "pdfCropPath")
            if normalized_path and not self.fs.exists(normalized_path):
                item_warnings.append("missing-normalizedPath")
            if cache_path and not self.fs.exists(cache_path):
                item_warnings.append("missing-cachePath")
            if pdf_crop_path and not self.fs.exists(pdf_crop_path):
                item_warnings.append("missing-pdfCropPath")
                pdf_crop_path = None
            visual_status = str(asset.get("visualStatus") or "")
            if visual_status not in _VISUAL_STATUSES:
                visual_status = ""
            if visual_status == "visual_verified":
                item_warnings.append("visual-verification-not-established-by-manifest")
                visual_status = "pdf_crop_available" if pdf_crop_path else ("referenced" if status == "referenced" else "mineru_candidate")
            if not visual_status:
                if pdf_crop_path:
                    visual_status = "pdf_crop_available"
                elif status == "referenced":
                    visual_status = "referenced"
                elif status == "invalid":
                    visual_status = "unavailable"
                else:
                    visual_status = "mineru_candidate"
            if visual_status == "pdf_crop_available" and not pdf_crop_path:
                item_warnings.append("pdf-crop-unavailable")
                visual_status = "referenced" if status == "referenced" else "mineru_candidate"
            page = asset.get("page")
            if type(page) is not int or page < 1:
                page = caption.page if caption is not None else None
            figure_label = str(asset.get("figureLabel") or "").strip() or (_figure_label(caption.text) if caption is not None else None)
            figures.append(
                {
                    "assetId": asset_id,
                    "status": status,
                    "visualStatus": visual_status,
                    "figureLabel": figure_label,
                    "caption": caption.text if caption is not None else None,
                    "captionEvidenceId": caption.evidence_id if caption is not None else None,
                    "contextEvidenceIds": [chunk.evidence_id for chunk in contexts],
                    "page": page,
                    "normalizedPath": normalized_path,
                    "cachePath": cache_path,
                    "pdfCropPath": pdf_crop_path,
                    "warnings": item_warnings,
                }
            )
        return figures, figure_chunks, tables, warnings


def _overview_passages(
    chunks: Sequence[EvidenceChunk],
) -> tuple[list[EvidenceChunk], dict[str, list[str]], list[str]]:
    selected: list[EvidenceChunk] = []
    categories: dict[str, list[str]] = {}
    missing: list[str] = []
    for category, aliases in _OVERVIEW_SECTIONS:
        matches = [
            chunk
            for chunk in chunks
            if chunk.content_type != "heading" and any(_heading_alias_match(component, aliases) for component in chunk.section_path)
        ][:3]
        categories[category] = [chunk.evidence_id for chunk in matches]
        if not matches:
            missing.append(category)
        selected.extend(matches)
    return _unique_chunks(selected), categories, missing


def _targeted(chunks: Sequence[EvidenceChunk], query: str, variants: Sequence[str]) -> list[tuple[int, EvidenceChunk]]:
    main = _normalize(query)
    variant_values = [_normalize(value) for value in variants if _normalize(value)]
    ranked: list[tuple[int, EvidenceChunk]] = []
    for chunk in chunks:
        text = _normalize(chunk.text)
        section = _normalize(" / ".join(chunk.section_path))
        score = _score_query(main, text, section, phrase_weight=24, token_weight=4, section_weight=7)
        for variant in variant_values:
            score += _score_query(variant, text, section, phrase_weight=8, token_weight=1, section_weight=2)
        if score > 0:
            if chunk.content_type in {"table", "caption"}:
                score += 2
            ranked.append((score, chunk))
    ranked.sort(key=lambda item: (-item[0], item[1].evidence_id.casefold(), item[1].evidence_id))
    return ranked


def _score_query(query: str, text: str, section: str, *, phrase_weight: int, token_weight: int, section_weight: int) -> int:
    if not query:
        return 0
    score = phrase_weight if query in text else 0
    score += section_weight * 2 if query in section else 0
    tokens = sorted({token for token in re.findall(r"[^\W_]+", query, flags=re.UNICODE) if len(token) > 1})
    score += sum(token_weight for token in tokens if token in text)
    score += sum(section_weight for token in tokens if token in section)
    return score


def _section_passages(chunks: Sequence[EvidenceChunk], sections: Sequence[str]) -> tuple[list[EvidenceChunk], list[str]]:
    if not sections:
        return [], []
    matched: list[EvidenceChunk] = []
    unmatched: list[str] = []
    for requested in sections:
        candidates = [chunk for chunk in chunks if _section_matches(chunk.section_path, requested)]
        if candidates:
            matched.extend(candidates)
        else:
            unmatched.append(requested)
    return _unique_chunks(matched), unmatched


def _section_matches(section_path: Sequence[str], requested: str) -> bool:
    needle = _normalize(requested)
    if not needle:
        return False
    components = [_normalize(value) for value in section_path]
    joined = " / ".join(components)
    return any(needle == value or needle in value or value in needle for value in components) or joined.startswith(needle)


def _heading_alias_match(value: str, aliases: Sequence[str]) -> bool:
    normalized = _normalize(value)
    return any(normalized == alias or normalized.startswith(f"{alias} ") or alias in normalized for alias in aliases)


def _passage(chunk: EvidenceChunk, *, score: int | None = None) -> dict[str, Any]:
    value = {
        "evidenceId": chunk.evidence_id,
        "text": chunk.text,
        "sectionPath": list(chunk.section_path),
        "contentType": chunk.content_type,
        "page": chunk.page,
        "sourceLink": chunk.source_link,
        "contentHash": chunk.content_hash,
        "sourceFingerprint": chunk.source_fingerprint,
        "relatedAssetIds": list(chunk.related_asset_ids),
    }
    if score is not None:
        value["score"] = score
    return value


def _apply_budget(passages: Sequence[dict[str, Any]], max_chars: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    used = 0
    truncated = False
    for passage in passages:
        text = str(passage.get("text") or "")
        remaining = max_chars - used
        if remaining <= 0:
            truncated = True
            break
        value = dict(passage)
        if len(text) > remaining:
            value["text"] = text[:remaining]
            value["textTruncated"] = True
            selected.append(value)
            used += remaining
            truncated = True
            break
        selected.append(value)
        used += len(text)
    if len(selected) < len(passages):
        truncated = True
    return selected, {"maxChars": max_chars, "usedChars": used, "truncated": truncated, "scope": "passageText"}


def _coverage(
    status: str,
    passages: Sequence[Mapping[str, Any]],
    chunks: Sequence[EvidenceChunk],
    truncated: bool,
    *,
    complete: bool,
) -> dict[str, Any]:
    read_ids = [str(passage.get("evidenceId") or "") for passage in passages]
    read_set = set(read_ids)
    read_sections = _unique_section_paths(
        tuple(str(value) for value in passage.get("sectionPath", []))
        for passage in passages
        if isinstance(passage.get("sectionPath"), list)
    )
    unread_sections = _unique_section_paths(chunk.section_path for chunk in chunks if chunk.evidence_id not in read_set)
    return {
        "status": status,
        "complete": bool(complete),
        "truncated": bool(truncated),
        "evidenceRead": read_ids,
        "readSections": [list(path) for path in read_sections],
        "unreadSections": [list(path) for path in unread_sections],
        "totalEvidenceChunks": len(chunks),
        "returnedEvidenceChunks": len(passages),
    }


def _structure(chunks: Sequence[EvidenceChunk]) -> list[dict[str, Any]]:
    return [
        {"title": chunk.text, "sectionPath": list(chunk.section_path), "evidenceId": chunk.evidence_id}
        for chunk in chunks
        if chunk.content_type == "heading"
    ]


def _unique_chunks(chunks: Sequence[EvidenceChunk]) -> list[EvidenceChunk]:
    seen: set[str] = set()
    result: list[EvidenceChunk] = []
    for chunk in chunks:
        if chunk.evidence_id in seen:
            continue
        seen.add(chunk.evidence_id)
        result.append(chunk)
    return result


def _unique_section_paths(paths: Sequence[Sequence[str]] | Any) -> list[tuple[str, ...]]:
    seen: set[tuple[str, ...]] = set()
    result: list[tuple[str, ...]] = []
    for value in paths:
        path = tuple(value)
        if not path or path in seen:
            continue
        seen.add(path)
        result.append(path)
    return result


def _safe_manifest_path(value: Any, warnings: list[str], field: str) -> str | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        warnings.append(f"invalid-{field}")
        return None
    try:
        return normalize_vault_relative(value)
    except PathValidationError:
        warnings.append(f"invalid-{field}")
        return None


def _figure_label(text: str) -> str | None:
    match = _FIGURE_LABEL_RE.match(text)
    return match.group("label").strip() if match else None


def _wikilink_target(value: Any, *, markdown: bool) -> str:
    if not isinstance(value, str) or not value.strip():
        return ""
    raw = value.strip().strip("\"'")
    if raw.startswith("[[") and raw.endswith("]]" ):
        raw = raw[2:-2].split("|", 1)[0].split("#", 1)[0].strip()
    try:
        target = normalize_vault_relative(raw)
    except PathValidationError:
        return ""
    if markdown and PurePosixPath(target).suffix == "":
        target = f"{target}.md"
    return target


def _string_sequence(value: Sequence[str], name: str) -> list[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError(f"{name} must be an array of strings")
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            raise TypeError(f"{name} must be an array of strings")
        text = item.strip()
        marker = _normalize(text)
        if text and marker not in seen:
            seen.add(marker)
            result.append(text)
    return result


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value).casefold()).strip()


def _canonical_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _dedupe_warnings(values: Sequence[Any]) -> list[dict[str, Any]]:
    by_payload: dict[str, dict[str, Any]] = {}
    for value in values:
        warning = dict(value) if isinstance(value, Mapping) else {"code": "warning", "message": str(value)}
        marker = json.dumps(warning, ensure_ascii=False, sort_keys=True, default=str)
        by_payload.setdefault(marker, warning)
    return [by_payload[key] for key in sorted(by_payload)]
