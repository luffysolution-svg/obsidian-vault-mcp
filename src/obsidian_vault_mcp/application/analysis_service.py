"""Evidence-organizing context and transactional structured-analysis writeback."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..adapters.obsidian.markdown_renderer import managed_section_values
from ..adapters.vault.filesystem import VaultFilesystem
from ..config.loader import ConfigLoader
from ..config.schema import validate_config
from ..domain.analysis import (
    ANALYSIS_FIELD_ORDER,
    STRUCTURED_READING_SECTION_IDS,
    STRUCTURED_READING_SECTIONS,
    AnalysisClaim,
    ClaimType,
    UncertaintyItem,
    UncertaintyStatus,
    active_uncertainty_count,
    analysis_status,
    evidence_status,
)
from ..domain.errors import FrontmatterError, IdentityError, TransactionConflictError
from ..domain.frontmatter import compose_frontmatter, merge_frontmatter, parse_frontmatter
from ..domain.identity import validate_zotero_key
from ..domain.image_assets import ImageAssetValidationError, parse_image_manifest
from ..domain.paths import VaultPaths, normalize_vault_relative
from .transaction_service import TransactionService
from .verify_service import scan_unsafe_references

ANALYSIS_BLOCK = "analysis"
UNCERTAINTY_BLOCK = "analysis-uncertainties"
_CONFLICT_POLICIES = {"preserve-user", "overwrite-managed", "fail"}
_IMAGE_EMBED_RE = re.compile(r"!\[\[[^\]]+\]\]|!\[[^\]]*\]\([^)]+\)")
_HTML_IMAGE_RE = re.compile(r"<img\b", re.IGNORECASE)
_MARKDOWN_LINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")
_WIKILINK_RE = re.compile(r"!?\[\[([^\]|#]+)")
_ZOTERO_CHILD_NOTES_START = "<!-- ovm:zotero-child-notes:start -->"
_ZOTERO_CHILD_NOTES_END = "<!-- ovm:zotero-child-notes:end -->"
_ZOTERO_ANNOTATIONS_START = "<!-- ovm:zotero-annotations:start -->"
_ZOTERO_ANNOTATIONS_END = "<!-- ovm:zotero-annotations:end -->"

_SECTION_QUERIES: dict[str, tuple[str, ...]] = {
    "bibliographic-information": ("title author year journal DOI",),
    "research-background": ("background motivation introduction research context", "研究背景 研究动机"),
    "research-question": ("research question objective aim hypothesis", "研究问题 研究目的 假设"),
    "key-concepts": ("definition concept construct terminology", "概念 定义"),
    "theoretical-foundation": ("theory theoretical framework model", "理论基础 理论框架"),
    "mechanisms": ("mechanism relationship pathway explanation", "机制 作用路径 关系"),
    "research-methods": ("methods methodology experimental design sample data analysis", "研究方法 实验设计 样本 数据"),
    "findings": ("results findings conclusion outcome", "研究结果 主要结论"),
    "theoretical-contributions": ("theoretical contribution novelty significance", "理论贡献 创新"),
    "practical-implications": ("practical implication application recommendation", "实践启示 应用"),
    "limitations": ("limitation weakness future work", "研究局限 不足"),
    "review-relevance": ("literature comparison agreement disagreement gap", "文献综述 争议 空白"),
    "further-questions": ("open question uncertainty future research", "后续问题 未来研究"),
}


class AnalysisService:
    """Prepare source-grounded context and persist Agent-authored analysis."""

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
        self.transactions = TransactionService(self.vault_path)

    def context(
        self,
        zotero_key: str,
        *,
        template: str = "structured-reading",
        focus: str = "",
        max_chars: int = 30_000,
        include_existing_analysis: bool = True,
        include_zotero_notes: bool = True,
        include_uncertainties: bool = True,
        include_figures: bool = True,
    ) -> dict[str, Any]:
        """Return a bounded 13-section evidence packet without synthesizing conclusions."""

        key = validate_zotero_key(zotero_key)
        if template != "structured-reading":
            raise ValueError("template must be 'structured-reading'")
        if type(max_chars) is not int or not 1_000 <= max_chars <= 500_000:
            raise ValueError("max_chars must be an integer from 1000 to 500000")
        main_path, main_document = self._main_note(key)
        evidence_state, evidence_warnings = self._load_evidence_state(key)
        chunks = _evidence_chunks(evidence_state, key)
        manifest, manifest_warnings = self._load_manifest(key)
        assets = _manifest_assets(manifest, key)
        asset_by_id = {str(asset["assetId"]): asset for asset in assets}

        mapped = _map_template_sections(chunks, focus=focus)
        selected_ids = {
            evidence_id
            for section in mapped
            for evidence_id in section["evidenceIds"]
        }
        selected_chunks = [chunk for chunk in chunks if str(chunk.get("evidenceId") or "") in selected_ids]
        evidence_budget = max(1_000, int(max_chars * 0.7))
        bounded_chunks, truncated = _bounded_chunks(selected_chunks, max_chars=evidence_budget)
        available_ids = {str(chunk.get("evidenceId") or "") for chunk in bounded_chunks}
        for section in mapped:
            section["evidenceIds"] = [item for item in section["evidenceIds"] if item in available_ids]
            related_assets = {
                str(asset_id)
                for chunk in bounded_chunks
                if str(chunk.get("evidenceId") or "") in section["evidenceIds"]
                for asset_id in _as_string_list(chunk.get("relatedAssetIds", ()))
                if str(asset_id) in asset_by_id
            }
            section_evidence = set(section["evidenceIds"])
            related_assets.update(
                str(asset["assetId"])
                for asset in assets
                if (
                    str(asset.get("captionEvidenceId") or "") in section_evidence
                    or section_evidence.intersection(_as_string_list(asset.get("contextEvidenceIds", ())))
                )
            )
            section["assetIds"] = sorted(related_assets)
            if section["sectionId"] == "bibliographic-information":
                section["evidenceStatus"] = "complete"
                section["missingReason"] = ""
            elif section["evidenceIds"]:
                section["evidenceStatus"] = "partial"
                section["missingReason"] = ""
            else:
                section["evidenceStatus"] = "missing"
                section["missingReason"] = "No matching original-text evidence is available."

        existing_analysis = ""
        analysis_path = self.analysis_path(key)
        if include_existing_analysis and self.fs.exists(analysis_path):
            existing_analysis = self.fs.read_text(analysis_path)
        managed = managed_section_values(main_document.body)
        zotero_content = managed.get("zotero-notes", "") if include_zotero_notes else ""
        zotero_notes, zotero_annotations, zotero_sources_separated = _split_zotero_content(zotero_content)
        used_chars = sum(len(str(chunk.get("text") or "")) for chunk in bounded_chunks)
        remaining_chars = max(0, max_chars - used_chars)
        zotero_notes, notes_truncated = _clip_text(zotero_notes, remaining_chars // 3)
        remaining_chars -= len(zotero_notes)
        zotero_annotations, annotations_truncated = _clip_text(zotero_annotations, remaining_chars // 2)
        remaining_chars -= len(zotero_annotations)
        existing_analysis, analysis_truncated = _clip_text(existing_analysis, remaining_chars)
        truncated = truncated or notes_truncated or annotations_truncated or analysis_truncated
        uncertainty_state = _load_uncertainty_state(self.fs, key) if include_uncertainties else _empty_uncertainty_state(key)
        uncertainty_items = list(uncertainty_state.get("items") or [])
        figures = assets if include_figures else []
        structure = _structure(chunks)
        missing = [section["title"] for section in mapped if section["evidenceStatus"] == "missing"]
        warnings = [
            *evidence_warnings,
            *_as_string_list(evidence_state.get("warnings", ())),
            *manifest_warnings,
        ]
        if evidence_state.get("stale") is True:
            warnings.append("EvidenceChunk state is stale for the current MinerU Markdown")
        if zotero_content and not zotero_sources_separated:
            warnings.append("legacy Zotero notes and annotations remain combined in zoteroNotes")
        if truncated:
            warnings.append("analysis context was truncated to max_chars")
        if not chunks:
            warnings.append("no EvidenceChunk state is available")
        return {
            "ok": True,
            "zoteroKey": key,
            "template": template,
            "focus": focus,
            "metadata": dict(main_document.fields),
            "sourceNote": _note_link(main_path),
            "structure": structure,
            "templateSections": mapped,
            "evidenceChunks": bounded_chunks,
            "zoteroNotes": zotero_notes,
            "zoteroAnnotations": zotero_annotations,
            "existingAnalysis": existing_analysis,
            "uncertainties": uncertainty_items,
            "figures": figures,
            "imageManifest": _manifest_summary(manifest, figures),
            "coverage": {
                "availableEvidenceChunks": len(chunks),
                "returnedEvidenceChunks": len(bounded_chunks),
                "mappedTemplateSections": sum(section["evidenceStatus"] != "missing" for section in mapped),
                "totalTemplateSections": len(mapped),
                "truncated": truncated,
            },
            "budget": {
                "maxChars": max_chars,
                "returnedTextChars": (
                    sum(len(str(chunk.get("text") or "")) for chunk in bounded_chunks)
                    + len(zotero_notes)
                    + len(zotero_annotations)
                    + len(existing_analysis)
                ),
                "truncated": truncated,
            },
            "missingSections": missing,
            "recommendedTargetedQueries": _recommended_queries(mapped),
            "currentContentStatus": "evidence-available" if chunks else "metadata-only",
            "warnings": list(dict.fromkeys(warnings)),
        }

    def write(
        self,
        zotero_key: str,
        sections: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None = None,
        *,
        uncertainties: Sequence[Mapping[str, Any]] | None = None,
        embed_asset_ids: Sequence[str] = (),
        updated_at: str | None = None,
        dry_run: bool = False,
        transaction_id: str | None = None,
        conflict_policy: str = "preserve-user",
    ) -> dict[str, Any]:
        """Validate sources and write one stable Analysis note through a transaction."""

        key = validate_zotero_key(zotero_key)
        _validate_conflict_policy(conflict_policy)
        main_path, main_document = self._main_note(key)
        analysis_path = self.analysis_path(key)
        if analysis_path == main_path:
            raise ValueError("Analysis note path conflicts with the main literature note")
        if analysis_path == self.paths.analysis_index:
            raise ValueError("Analysis note path conflicts with the Analysis index")
        existing_document = None
        if self.fs.exists(analysis_path):
            if conflict_policy == "fail":
                raise TransactionConflictError(f"Analysis note already exists: {analysis_path}", stage="plan")
            try:
                existing_document = parse_frontmatter(self.fs.read_text(analysis_path))
            except (OSError, UnicodeError, FrontmatterError) as exc:
                raise ValueError(f"cannot preserve existing Analysis note: {exc}") from exc

        evidence_state, _warnings = self._load_evidence_state(key, require_persisted_current=True)
        chunks = _evidence_chunks(evidence_state, key)
        evidence_by_id = {str(chunk["evidenceId"]): chunk for chunk in chunks}
        manifest, _manifest_warnings = self._load_manifest(key, require_current=True)
        assets = _manifest_assets(manifest, key)
        asset_by_id = {str(asset["assetId"]): asset for asset in assets}
        normalized_sections = _normalize_analysis_sections(sections)
        claims = [claim for _section_id, section_claims in normalized_sections for claim in section_claims]
        if evidence_state.get("stale") is True and any(claim.evidence_ids for claim in claims):
            raise ValueError("cannot write citations from stale EvidenceChunk state")
        _validate_claims(claims, evidence_by_id, asset_by_id, self.fs)
        embeds = _validate_embed_assets(embed_asset_ids, asset_by_id, self.fs)

        old_uncertainty_state = _load_uncertainty_state(self.fs, key)
        base_timestamp = _validated_timestamp(updated_at) if updated_at is not None else _utc_now()
        uncertainty_state = _merge_uncertainties(
            key,
            old_uncertainty_state,
            uncertainties,
            evidence_by_id=evidence_by_id,
            asset_by_id=asset_by_id,
            created_at=base_timestamp,
        )
        items = [UncertaintyItem.from_mapping(item, zotero_key=key) for item in uncertainty_state["items"]]
        uncertainty_count = active_uncertainty_count(items)
        calculated_evidence_status = evidence_status(claims)
        calculated_analysis_status = analysis_status(claims, uncertainty_count)
        title = str(main_document.fields.get("title") or key)
        analysis_block = render_analysis_block(
            title,
            main_path,
            normalized_sections,
            evidence_by_id=evidence_by_id,
            asset_by_id=asset_by_id,
            embed_asset_ids=embeds,
        )
        uncertainty_block = render_uncertainty_block(items)
        existing_body = existing_document.body if existing_document is not None else ""
        next_body = replace_managed_block(existing_body, ANALYSIS_BLOCK, analysis_block)
        next_body = replace_managed_block(next_body, UNCERTAINTY_BLOCK, uncertainty_block)

        old_fields = existing_document.fields if existing_document is not None else {}
        semantic_fields = {
            "title": title,
            "zoteroKey": key,
            "sourceNote": _note_link(main_path),
            "analysisStatus": calculated_analysis_status,
            "evidenceStatus": calculated_evidence_status,
            "uncertaintyCount": uncertainty_count,
        }
        old_semantic = {name: old_fields.get(name) for name in semantic_fields}
        state_changed = _state_items_changed(old_uncertainty_state, uncertainty_state)
        semantic_changed = next_body != existing_body or semantic_fields != old_semantic or state_changed
        timestamp = (
            _validated_timestamp(updated_at)
            if updated_at is not None
            else str(old_fields.get("updatedAt") or base_timestamp) if not semantic_changed else base_timestamp
        )
        fields = merge_frontmatter(
            old_fields,
            {**semantic_fields, "updatedAt": timestamp},
            omit_empty=False,
            preserve_unknown_fields=True,
            field_order=ANALYSIS_FIELD_ORDER,
        )
        rendered = compose_frontmatter(fields, next_body, omit_empty=False, field_order=ANALYSIS_FIELD_ORDER)
        _validate_analysis_output(rendered)
        uncertainty_state["updatedAt"] = timestamp
        state_text = _json_text(uncertainty_state)

        transaction = self.transactions.begin(item_key=key, transaction_id=transaction_id, dry_run=dry_run)
        transaction.write_text(analysis_path, rendered)
        transaction.write_text(_uncertainty_state_path(key), state_text)
        result = transaction.commit()
        return {
            **result,
            "zoteroKey": key,
            "analysisPath": analysis_path,
            "sourceNote": main_path,
            "analysisStatus": calculated_analysis_status,
            "evidenceStatus": calculated_evidence_status,
            "uncertaintyCount": uncertainty_count,
            "updatedAt": timestamp,
        }

    def rollback(
        self,
        transaction_id: str,
        *,
        dry_run: bool = False,
        conflict_policy: str = "preserve-user",
    ) -> dict[str, Any]:
        return self.transactions.rollback(transaction_id, dry_run=dry_run, conflict_policy=conflict_policy)

    def analysis_path(self, zotero_key: str) -> str:
        return self.paths.analysis_note(zotero_key)

    def _main_note(self, key: str) -> tuple[str, Any]:
        state_path = self.paths.state(key)
        candidates: list[str] = []
        if self.fs.exists(state_path):
            try:
                state = json.loads(self.fs.read_text(state_path))
                if isinstance(state, dict) and state.get("notePath"):
                    candidates.append(normalize_vault_relative(str(state["notePath"])))
            except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
                pass
        try:
            candidates.append(self.paths.note(key, firstAuthor="", year="", shortTitle=key))
        except (IdentityError, ValueError):
            pass
        matches: list[tuple[str, Any]] = []
        for relative in dict.fromkeys(candidates):
            if not self.fs.exists(relative):
                continue
            document = parse_frontmatter(self.fs.read_text(relative))
            if str(document.fields.get("zoteroKey") or "") == key:
                matches.append((relative, document))
        root = self.paths.resolve(str(self.config["literature"]["root"]))
        if root.is_dir():
            for path in sorted(root.glob("*.md"), key=lambda item: (item.name.casefold(), item.name)):
                relative = self.fs.relative(path)
                if any(relative == found[0] for found in matches):
                    continue
                try:
                    document = parse_frontmatter(path.read_text(encoding="utf-8"))
                except (OSError, UnicodeError, FrontmatterError):
                    continue
                if str(document.fields.get("zoteroKey") or "") == key:
                    matches.append((relative, document))
        if not matches:
            raise FileNotFoundError(f"main literature note does not exist for {key}")
        if len(matches) > 1:
            raise IdentityError(f"multiple main literature notes exist for zoteroKey {key}")
        return matches[0]

    def _load_evidence_state(
        self,
        key: str,
        *,
        require_persisted_current: bool = False,
    ) -> tuple[dict[str, Any], list[str]]:
        warnings: list[str] = []
        try:
            from .evidence_service import EvidenceService

            try:
                service = EvidenceService(self.vault_path, self.config)
            except TypeError:
                service = EvidenceService(self.vault_path)
            try:
                state = service.load_verified(key)
            except FileNotFoundError:
                if require_persisted_current:
                    raise
                state = service.build(key)
                warnings.append("EvidenceChunk state is not persisted; context used an in-memory rebuild")
            except ValueError as exc:
                if require_persisted_current:
                    raise
                state = service.build(key)
                warnings.append(f"persisted EvidenceChunk state is invalid or stale; context rebuilt it in memory: {exc}")
            if isinstance(state, dict):
                return state, warnings
            warnings.append("EvidenceService returned a non-object state")
        except (ImportError, AttributeError, FileNotFoundError) as exc:
            if require_persisted_current:
                raise ValueError(f"persisted current EvidenceChunk state is required: {exc}") from exc
        except Exception as exc:
            if require_persisted_current:
                raise ValueError(f"persisted current EvidenceChunk state is required: {exc}") from exc
            warnings.append(f"could not load EvidenceChunk state: {exc}")
        return {"schemaVersion": 1, "zoteroKey": key, "chunks": [], "warnings": []}, warnings

    def _load_manifest(
        self,
        key: str,
        *,
        require_current: bool = False,
    ) -> tuple[dict[str, Any], list[str]]:
        relative = self.paths.image_manifest(key)
        if not self.fs.exists(relative):
            return {"schemaVersion": 1, "zoteroKey": key, "assets": [], "warnings": []}, []
        try:
            manifest = parse_image_manifest(self.fs.read_text(relative))
            if manifest.zotero_key != key:
                raise ValueError("image manifest identity mismatch")
            warnings = [str(value.get("code") or value) for value in manifest.warnings]
            integrity_warnings: list[str] = []
            if not self.fs.exists(manifest.source_markdown):
                integrity_warnings.append("image manifest source Markdown is missing")
            elif self.fs.sha256(manifest.source_markdown) != manifest.source_markdown_sha256:
                integrity_warnings.append("image manifest source Markdown hash is stale")
            if require_current and integrity_warnings:
                raise ValueError(integrity_warnings[0])
            return manifest.as_dict(), [*warnings, *integrity_warnings]
        except (OSError, UnicodeError, ImageAssetValidationError, TypeError, ValueError) as exc:
            if require_current:
                raise ValueError(f"valid current image manifest is required: {exc}") from exc
            return {"schemaVersion": 1, "zoteroKey": key, "assets": []}, [f"could not read image manifest: {exc}"]


def render_analysis_block(
    title: str,
    main_note_path: str,
    sections: Sequence[tuple[str, Sequence[AnalysisClaim]]],
    *,
    evidence_by_id: Mapping[str, Mapping[str, Any]],
    asset_by_id: Mapping[str, Mapping[str, Any]],
    embed_asset_ids: Sequence[str],
) -> str:
    section_claims = {section_id: list(claims) for section_id, claims in sections}
    lines = [f"# {title.strip() or 'Untitled'}"]
    used_evidence: list[str] = []
    used_assets: list[str] = []
    for section_id, heading in STRUCTURED_READING_SECTIONS:
        lines.extend(["", f"## {heading}", ""])
        if section_id == "bibliographic-information":
            lines.append(f"- Source note: {_note_link(main_note_path)}")
        claims = section_claims.get(section_id, [])
        if not claims and section_id != "bibliographic-information":
            lines.append("_No Agent-authored content._")
        for claim in claims:
            anchors = [*(f"[[evidence:{item}]]" for item in claim.evidence_ids), *(f"[[asset:{item}]]" for item in claim.asset_ids)]
            suffix = f" {' '.join(anchors)}" if anchors else ""
            content = claim.content.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\n  ")
            lines.append(
                f"- **{claim.claim_type.value} · {claim.verification_status.value}** — {content}{suffix}"
            )
            for evidence_id in claim.evidence_ids:
                if evidence_id not in used_evidence:
                    used_evidence.append(evidence_id)
            for asset_id in claim.asset_ids:
                if asset_id not in used_assets:
                    used_assets.append(asset_id)

    lines.extend(["", "## Evidence", ""])
    if not used_evidence:
        lines.append("_No original-text evidence cited._")
    for evidence_id in used_evidence:
        chunk = evidence_by_id[evidence_id]
        section_path = " > ".join(_as_string_list(chunk.get("sectionPath", ()))) or "Unsectioned"
        source_link = str(chunk.get("sourceLink") or "")
        lines.append(f"- [[evidence:{evidence_id}]] — {section_path}" + (f" — {source_link}" if source_link else ""))

    lines.extend(["", "## Figures", ""])
    figure_ids = list(dict.fromkeys([*used_assets, *embed_asset_ids]))
    if not figure_ids:
        lines.append("_No image assets cited._")
    for asset_id in figure_ids:
        asset = asset_by_id[asset_id]
        status = str(asset.get("status") or "unknown")
        visual = str(asset.get("visualStatus") or "unavailable")
        lines.append(f"- [[asset:{asset_id}]] — status: `{status}`; visualStatus: `{visual}`")
        if asset_id in embed_asset_ids:
            lines.append(f"  ![[{asset['normalizedPath']}]]")
    return "\n".join(lines).rstrip()


def render_uncertainty_block(items: Sequence[UncertaintyItem | Mapping[str, Any]]) -> str:
    normalized = [
        item if isinstance(item, UncertaintyItem) else UncertaintyItem.from_mapping(item)
        for item in items
    ]
    active = [item for item in normalized if item.status.value in {"pending", "unresolved"}]
    lines = ["## 待复核内容", ""]
    if not active:
        lines.append("_No pending review items._")
    for item in sorted(active, key=lambda value: value.uncertainty_id):
        anchors = [*(f"[[evidence:{value}]]" for value in item.evidence_ids), *(f"[[asset:{value}]]" for value in item.asset_ids)]
        suffix = f" {' '.join(anchors)}" if anchors else ""
        lines.append(f"- [ ] **{item.uncertainty_id}** — {item.claim}{suffix}")
        lines.append(f"  - Reason: {item.reason}")
        if item.status is UncertaintyStatus.UNRESOLVED and item.resolution_note:
            lines.append(f"  - Resolution: {item.resolution_note}")
    return "\n".join(lines).rstrip()


def replace_managed_block(body: str, name: str, content: str) -> str:
    start = f"<!-- ovm:{name}:start -->"
    end = f"<!-- ovm:{name}:end -->"
    normalized = body.replace("\r\n", "\n").replace("\r", "\n")
    starts = [match.start() for match in re.finditer(re.escape(start), normalized)]
    ends = [match.start() for match in re.finditer(re.escape(end), normalized)]
    if len(starts) != len(ends) or len(starts) > 1 or (starts and starts[0] >= ends[0]):
        raise ValueError(f"invalid or duplicate managed block markers: {name}")
    rendered = f"{start}\n{content.rstrip()}\n{end}"
    if starts:
        finish = ends[0] + len(end)
        result = normalized[: starts[0]] + rendered + normalized[finish:]
    else:
        result = f"{normalized.rstrip()}\n\n{rendered}" if normalized.strip() else rendered
    return result.strip() + "\n"


def analysis_section_text(body: str, heading: str) -> str:
    pattern = re.compile(
        rf"(?ms)^##[ \t]+{re.escape(heading)}[ \t]*\n+(.*?)(?=^##[ \t]+|<!--[ \t]*ovm:analysis:end|\Z)"
    )
    match = pattern.search(body.replace("\r\n", "\n").replace("\r", "\n"))
    return match.group(1).strip() if match else ""


def _normalize_analysis_sections(
    value: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None,
) -> list[tuple[str, list[AnalysisClaim]]]:
    by_id: dict[str, list[AnalysisClaim]] = {section_id: [] for section_id, _title in STRUCTURED_READING_SECTIONS}
    if value is None:
        return list(by_id.items())
    entries: list[tuple[str, Any]] = []
    if isinstance(value, Mapping):
        entries = [(str(section_id), payload) for section_id, payload in value.items()]
    elif not isinstance(value, (str, bytes)) and isinstance(value, Sequence):
        for item in value:
            if not isinstance(item, Mapping):
                raise TypeError("analysis sections must contain objects")
            entries.append((str(item.get("sectionId") or ""), item.get("claims", ())))
    else:
        raise TypeError("sections must be an object or array")
    for section_id, payload in entries:
        if section_id not in STRUCTURED_READING_SECTION_IDS:
            raise ValueError(f"unknown structured-reading sectionId: {section_id}")
        if isinstance(payload, str):
            claims = [AnalysisClaim.from_mapping({"content": payload, "claimType": "agent_inference"})]
        elif isinstance(payload, Mapping):
            if "claims" in payload:
                raw_claims = payload["claims"]
                if isinstance(raw_claims, (str, bytes)) or not isinstance(raw_claims, Sequence):
                    raise TypeError("section claims must be an array")
                claims = [AnalysisClaim.from_mapping(claim) for claim in raw_claims]
            else:
                claims = [AnalysisClaim.from_mapping(payload)]
        elif not isinstance(payload, (str, bytes)) and isinstance(payload, Sequence):
            claims = [AnalysisClaim.from_mapping(claim) for claim in payload]
        else:
            raise TypeError(f"invalid analysis section payload: {section_id}")
        by_id[section_id] = claims
    return list(by_id.items())


def _validate_claims(
    claims: Sequence[AnalysisClaim],
    evidence_by_id: Mapping[str, Mapping[str, Any]],
    asset_by_id: Mapping[str, Mapping[str, Any]],
    fs: VaultFilesystem,
) -> None:
    for claim in claims:
        unsafe = scan_unsafe_references(claim.content)
        if unsafe:
            raise ValueError(f"analysis content contains forbidden {unsafe[0]['kind']}")
        if _IMAGE_EMBED_RE.search(claim.content) or _HTML_IMAGE_RE.search(claim.content):
            raise ValueError("analysis claims must use embed_asset_ids instead of raw image embeds")
        for raw_target in _MARKDOWN_LINK_RE.findall(claim.content):
            target = raw_target.strip().strip("<>").split(maxsplit=1)[0]
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            fs.resolve(normalize_vault_relative(target))
        for target in _WIKILINK_RE.findall(claim.content):
            if target.startswith("evidence:"):
                evidence_id = target.removeprefix("evidence:")
                if evidence_id not in evidence_by_id:
                    raise ValueError(f"unknown evidenceId: {evidence_id}")
                if evidence_id not in claim.evidence_ids:
                    raise ValueError("evidence anchors in content must also be declared in evidenceIds")
                continue
            if target.startswith("asset:"):
                asset_id = target.removeprefix("asset:")
                if asset_id not in asset_by_id:
                    raise ValueError(f"unknown assetId: {asset_id}")
                if asset_id not in claim.asset_ids:
                    raise ValueError("asset anchors in content must also be declared in assetIds")
                continue
            fs.resolve(normalize_vault_relative(target))
        missing_evidence = [item for item in claim.evidence_ids if item not in evidence_by_id]
        if missing_evidence:
            raise ValueError(f"unknown evidenceId: {missing_evidence[0]}")
        missing_assets = [item for item in claim.asset_ids if item not in asset_by_id]
        if missing_assets:
            raise ValueError(f"unknown assetId: {missing_assets[0]}")
        if (
            claim.claim_type is not ClaimType.USER_NOTE
            and claim.verification_status.value == "verified"
            and not claim.evidence_ids
        ):
            raise ValueError("verified evidence-bearing claims require evidenceIds")
        for asset_id in claim.asset_ids:
            _validate_asset_paths(asset_by_id[asset_id])


def _validate_embed_assets(
    values: Sequence[str],
    asset_by_id: Mapping[str, Mapping[str, Any]],
    fs: VaultFilesystem,
) -> list[str]:
    ids = _as_string_list(values)
    result: list[str] = []
    for asset_id in ids:
        if asset_id not in asset_by_id:
            raise ValueError(f"unknown assetId: {asset_id}")
        asset = asset_by_id[asset_id]
        if str(asset.get("status") or "") == "unlinked_candidate":
            raise ValueError("unlinked_candidate assets cannot be embedded automatically")
        normalized = _validate_asset_paths(asset)
        if not normalized:
            raise ValueError(f"asset has no formal normalizedPath: {asset_id}")
        if not fs.exists(normalized):
            raise FileNotFoundError(f"formal image asset does not exist: {normalized}")
        if asset_id not in result:
            result.append(asset_id)
    return result


def _validate_asset_paths(asset: Mapping[str, Any]) -> str:
    normalized = str(asset.get("normalizedPath") or "")
    if normalized:
        normalized = normalize_vault_relative(normalized)
        if normalized.casefold().startswith(".obsidian-vault-mcp/staging/"):
            raise ValueError("staging image paths cannot be written to Analysis notes")
    cache = str(asset.get("cachePath") or "")
    if cache:
        normalize_vault_relative(cache)
    return normalized


def _merge_uncertainties(
    key: str,
    existing: Mapping[str, Any],
    incoming: Sequence[Mapping[str, Any]] | None,
    *,
    evidence_by_id: Mapping[str, Mapping[str, Any]],
    asset_by_id: Mapping[str, Mapping[str, Any]],
    created_at: str,
) -> dict[str, Any]:
    old_items = [UncertaintyItem.from_mapping(item, zotero_key=key) for item in existing.get("items", [])]
    by_id = {item.uncertainty_id: item for item in old_items}
    if incoming is not None:
        if isinstance(incoming, (str, bytes)) or not isinstance(incoming, Sequence):
            raise TypeError("uncertainties must be an array")
        for raw in incoming:
            item = UncertaintyItem.from_mapping(raw, zotero_key=key)
            if item.status is not UncertaintyStatus.PENDING:
                raise ValueError("Analysis write may create only pending uncertainty items")
            for evidence_id in item.evidence_ids:
                if evidence_id not in evidence_by_id:
                    raise ValueError(f"unknown evidenceId: {evidence_id}")
            for asset_id in item.asset_ids:
                if asset_id not in asset_by_id:
                    raise ValueError(f"unknown assetId: {asset_id}")
            previous = by_id.get(item.uncertainty_id)
            if previous is not None and previous.status is not UncertaintyStatus.PENDING:
                continue
            data = item.as_dict()
            data["createdAt"] = previous.created_at if previous and previous.created_at else item.created_at or created_at
            by_id[item.uncertainty_id] = UncertaintyItem.from_mapping(data, zotero_key=key)
    return {
        "schemaVersion": 1,
        "zoteroKey": key,
        "items": [by_id[item_id].as_dict() for item_id in sorted(by_id)],
        "history": list(existing.get("history") or []),
        "updatedAt": str(existing.get("updatedAt") or ""),
    }


def _evidence_chunks(state: Mapping[str, Any], key: str) -> list[dict[str, Any]]:
    raw = state.get("chunks", state.get("evidenceChunks", []))
    if not isinstance(raw, list):
        return []
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        evidence_id = str(item.get("evidenceId") or "")
        if not evidence_id or evidence_id in seen:
            continue
        item_key = str(item.get("zoteroKey") or key)
        if item_key != key:
            continue
        normalized = dict(item)
        normalized["zoteroKey"] = key
        normalized["sectionPath"] = _as_string_list(item.get("sectionPath", ()))
        normalized["relatedAssetIds"] = _as_string_list(item.get("relatedAssetIds", ()))
        normalized["text"] = str(item.get("text") or "")
        seen.add(evidence_id)
        result.append(normalized)
    return result


def _manifest_assets(manifest: Mapping[str, Any], key: str) -> list[dict[str, Any]]:
    raw = manifest.get("assets", [])
    if not isinstance(raw, list):
        return []
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        asset_id = str(item.get("assetId") or "")
        if not asset_id or asset_id in seen:
            continue
        normalized = dict(item)
        normalized.setdefault("zoteroKey", key)
        normalized.setdefault("visualStatus", "unavailable")
        normalized.setdefault("captionEvidenceId", None)
        normalized.setdefault("contextEvidenceIds", [])
        normalized.setdefault("figureLabel", None)
        normalized.setdefault("page", None)
        normalized.setdefault("pdfCropPath", None)
        result.append(normalized)
        seen.add(asset_id)
    result.sort(key=lambda item: str(item["assetId"]))
    return result


def _map_template_sections(chunks: Sequence[Mapping[str, Any]], *, focus: str) -> list[dict[str, Any]]:
    mapped: list[dict[str, Any]] = []
    for section_id, title in STRUCTURED_READING_SECTIONS:
        scoring_queries = list(_SECTION_QUERIES[section_id])
        queries = (
            [f"{focus.strip()} {query}" for query in scoring_queries]
            if focus.strip()
            else scoring_queries
        )
        scored: list[tuple[int, int, str]] = []
        for index, chunk in enumerate(chunks):
            score = _chunk_score(chunk, scoring_queries)
            if score > 0:
                scored.append((-score, index, str(chunk.get("evidenceId") or "")))
        evidence_ids = [evidence_id for _score, _index, evidence_id in sorted(scored)[:8]]
        mapped.append(
            {
                "sectionId": section_id,
                "title": title,
                "evidenceStatus": "partial" if evidence_ids else "missing",
                "evidenceIds": evidence_ids,
                "assetIds": [],
                "missingReason": "" if evidence_ids else "No matching original-text evidence is available.",
                "recommendedQueries": queries,
            }
        )
    return mapped


def _chunk_score(chunk: Mapping[str, Any], queries: Sequence[str]) -> int:
    path = " ".join(_as_string_list(chunk.get("sectionPath", ()))).casefold()
    text = str(chunk.get("text") or "").casefold()
    score = 0
    for query in queries:
        tokens = {token for token in re.findall(r"[^\W_]+", query.casefold()) if len(token) > 1}
        score += sum(8 for token in tokens if token in path)
        score += sum(1 for token in tokens if token in text)
    return score


def _bounded_chunks(chunks: Sequence[Mapping[str, Any]], *, max_chars: int) -> tuple[list[dict[str, Any]], bool]:
    remaining = max_chars
    result: list[dict[str, Any]] = []
    truncated = False
    for chunk in chunks:
        text = str(chunk.get("text") or "")
        if remaining <= 0:
            truncated = True
            break
        value = dict(chunk)
        if len(text) > remaining:
            value["text"] = text[: max(0, remaining - 1)].rstrip() + "…"
            value["truncated"] = True
            truncated = True
        remaining -= len(str(value.get("text") or ""))
        result.append(value)
    return result, truncated


def _split_zotero_content(value: str) -> tuple[str, str, bool]:
    if not value:
        return "", "", True
    notes = _marked_content(value, _ZOTERO_CHILD_NOTES_START, _ZOTERO_CHILD_NOTES_END)
    annotations = _marked_content(value, _ZOTERO_ANNOTATIONS_START, _ZOTERO_ANNOTATIONS_END)
    if notes is None or annotations is None:
        return value, "", False
    return notes, annotations, True


def _marked_content(value: str, start_marker: str, end_marker: str) -> str | None:
    if value.count(start_marker) != 1 or value.count(end_marker) != 1:
        return None
    start = value.index(start_marker) + len(start_marker)
    end = value.index(end_marker, start)
    return value[start:end].strip()


def _clip_text(value: str, limit: int) -> tuple[str, bool]:
    if len(value) <= limit:
        return value, False
    if limit <= 0:
        return "", bool(value)
    return value[: max(0, limit - 1)].rstrip() + "…", True


def _structure(chunks: Sequence[Mapping[str, Any]]) -> list[list[str]]:
    paths = {
        tuple(_as_string_list(chunk.get("sectionPath", ())))
        for chunk in chunks
        if _as_string_list(chunk.get("sectionPath", ()))
    }
    return [list(path) for path in sorted(paths, key=lambda value: tuple(item.casefold() for item in value))]


def _recommended_queries(sections: Sequence[Mapping[str, Any]]) -> list[str]:
    result: list[str] = []
    for section in sections:
        if section.get("evidenceStatus") != "missing":
            continue
        for query in _as_string_list(section.get("recommendedQueries", ())):
            if query not in result:
                result.append(query)
    return result


def _manifest_summary(manifest: Mapping[str, Any], assets: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    counts = manifest.get("counts")
    if not isinstance(counts, Mapping):
        counts = {
            "total": len(assets),
            "referenced": sum(str(asset.get("status") or "") == "referenced" for asset in assets),
            "unlinkedCandidates": sum(str(asset.get("status") or "") == "unlinked_candidate" for asset in assets),
            "invalid": sum(str(asset.get("status") or "") == "invalid" for asset in assets),
        }
    return {
        "available": bool(assets),
        "schemaVersion": manifest.get("schemaVersion"),
        "counts": dict(counts),
        "warnings": _as_string_list(manifest.get("warnings", ())),
    }


def _load_uncertainty_state(fs: VaultFilesystem, key: str) -> dict[str, Any]:
    relative = _uncertainty_state_path(key)
    if not fs.exists(relative):
        return _empty_uncertainty_state(key)
    try:
        value = json.loads(fs.read_text(relative))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read uncertainty state for {key}: {exc}") from exc
    if not isinstance(value, dict) or value.get("zoteroKey") != key:
        raise ValueError(f"uncertainty state identity mismatch for {key}")
    if not isinstance(value.get("items", []), list) or not isinstance(value.get("history", []), list):
        raise ValueError(f"invalid uncertainty state structure for {key}")
    ids: list[str] = []
    for raw in value.get("items", []):
        item = UncertaintyItem.from_mapping(raw, zotero_key=key)
        if item.uncertainty_id in ids:
            raise ValueError(f"duplicate uncertaintyId in state: {item.uncertainty_id}")
        ids.append(item.uncertainty_id)
    return value


def _empty_uncertainty_state(key: str) -> dict[str, Any]:
    return {"schemaVersion": 1, "zoteroKey": key, "items": [], "history": [], "updatedAt": ""}


def _uncertainty_state_path(key: str) -> str:
    return f".obsidian-vault-mcp/state/uncertainties/{validate_zotero_key(key)}.json"


def _state_items_changed(before: Mapping[str, Any], after: Mapping[str, Any]) -> bool:
    return before.get("items", []) != after.get("items", []) or before.get("history", []) != after.get("history", [])


def _validate_analysis_output(text: str) -> None:
    unsafe = scan_unsafe_references(text)
    if unsafe:
        raise ValueError(f"rendered Analysis note contains forbidden {unsafe[0]['kind']}")


def _validate_conflict_policy(value: str) -> None:
    if value == "rename":
        raise ValueError("Analysis notes use stable zoteroKey paths and cannot be renamed")
    if value not in _CONFLICT_POLICIES:
        raise ValueError(f"conflict_policy must be one of: {', '.join(sorted(_CONFLICT_POLICIES))}")


def _validated_timestamp(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("updated_at must be an ISO-8601 timestamp")
    normalized = value.strip()
    try:
        datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("updated_at must be an ISO-8601 timestamp") from exc
    return normalized


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _note_link(path: str) -> str:
    normalized = normalize_vault_relative(path)
    target = normalized[:-3] if normalized.lower().endswith(".md") else normalized
    return f"[[{target}]]"


def _json_text(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def _as_string_list(value: Any) -> list[str]:
    if isinstance(value, (str, bytes)):
        return [str(value)] if str(value) else []
    if not isinstance(value, Sequence):
        return []
    return [str(item) for item in value if isinstance(item, str) and item]
