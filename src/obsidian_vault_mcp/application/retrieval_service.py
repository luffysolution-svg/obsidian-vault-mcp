"""Deterministic metadata and evidence retrieval across local papers."""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

from ..adapters.vault.filesystem import VaultFilesystem
from ..config.loader import load_config
from ..domain.frontmatter import parse_frontmatter
from ..domain.identity import validate_zotero_key
from ..domain.image_assets import ImageAssetValidationError, parse_image_manifest
from ..domain.paths import VaultPaths, normalize_vault_relative
from .coverage_service import CoverageService
from .evidence_service import EvidenceService

_INTENTS = {"enumerate", "verify", "summarize"}
_DEPTHS = {"pool", "metadata", "evidence", "verify"}
_METHODS = {"metadata", "abstract", "exact", "lexical"}
_TOKEN_RE = re.compile(r"[^\W_]+(?:[-'][^\W_]+)*", re.UNICODE)


class RetrievalService:
    """Search the local V2 corpus without embeddings or model calls."""

    def __init__(self, vault_path: str | os.PathLike[str], config: Mapping[str, Any] | None = None) -> None:
        self.vault_path = Path(vault_path).expanduser().resolve()
        self.config = dict(config) if config is not None else load_config(self.vault_path, require_exists=False)
        self.fs = VaultFilesystem(self.vault_path)
        self.paths = VaultPaths(self.vault_path, self.config)
        self.coverage = CoverageService(self.vault_path, self.config)
        self.evidence = EvidenceService(self.vault_path, self.config)

    def retrieve(
        self,
        query: str = "",
        *,
        query_variants: Sequence[str] | None = None,
        scope: Mapping[str, Any] | None = None,
        intent: str = "summarize",
        depth: str = "evidence",
        methods: Sequence[str] | None = None,
        max_candidate_papers: int = 30,
        max_snippet_papers: int = 15,
        per_paper_top_k: int = 3,
        max_total_snippets: int = 40,
        record_coverage: bool = False,
        coverage_dry_run: bool = False,
        coverage_transaction_id: str | None = None,
    ) -> dict[str, Any]:
        """Return ranked papers, source passages, coverage, and an honest frontier."""

        if intent not in _INTENTS:
            raise ValueError(f"intent must be one of: {', '.join(sorted(_INTENTS))}")
        if depth not in _DEPTHS:
            raise ValueError(f"depth must be one of: {', '.join(sorted(_DEPTHS))}")
        selected_methods = tuple(dict.fromkeys(methods or ("metadata", "abstract", "exact", "lexical")))
        unknown_methods = set(selected_methods) - _METHODS
        if unknown_methods:
            raise ValueError(f"unsupported retrieval method(s): {', '.join(sorted(unknown_methods))}")
        _budget(max_candidate_papers, "max_candidate_papers", 1, 500)
        _budget(max_snippet_papers, "max_snippet_papers", 1, 100)
        _budget(per_paper_top_k, "per_paper_top_k", 1, 20)
        _budget(max_total_snippets, "max_total_snippets", 1, 1000)

        normalized_query = " ".join(str(query).split())
        variants = tuple(dict.fromkeys(" ".join(str(value).split()) for value in (query_variants or ()) if str(value).strip()))
        queries = tuple(value for value in (normalized_query, *variants) if value)
        records, warnings = self._paper_records(scope or {})
        pool_total = len(records)
        ranked: list[dict[str, Any]] = []
        exact_match_count = 0
        lexical_match_count = 0
        evidence_cache: dict[str, list[dict[str, Any]]] = {}
        scanned_full_text: set[str] = set()
        search_evidence = bool(
            queries
            and depth in {"evidence", "verify"}
            and {"exact", "lexical"}.intersection(selected_methods)
        )
        for record in records:
            score, reasons, matched_fields, exact_hit, lexical_hit = _score_metadata(record, queries, normalized_query, selected_methods)
            if search_evidence:
                chunks, state_warning = self._evidence_chunks(record["zoteroKey"])
                evidence_cache[record["zoteroKey"]] = chunks
                if state_warning:
                    warnings.append(state_warning)
                if chunks:
                    scanned_full_text.add(record["zoteroKey"])
                chunk_matches = [
                    _score_chunk(chunk, queries, normalized_query, selected_methods)
                    for chunk in chunks
                ]
                evidence_score = max((value[0] for value in chunk_matches), default=0.0)
                evidence_exact = any(value[1] for value in chunk_matches)
                evidence_lexical = any(value[2] for value in chunk_matches)
                if evidence_score > 0:
                    score += evidence_score
                    matched_fields.append("evidence")
                if evidence_exact:
                    reasons.append("exact:evidence")
                if evidence_lexical:
                    reasons.append("lexical:evidence")
                exact_hit = exact_hit or evidence_exact
                lexical_hit = lexical_hit or evidence_lexical
            if queries and score <= 0:
                continue
            exact_match_count += int(exact_hit)
            lexical_match_count += int(lexical_hit)
            ranked.append(
                {
                    **record,
                    "score": round(score, 6),
                    "matchReason": sorted(set(reasons)),
                    "matchedFields": sorted(set(matched_fields)),
                }
            )
        ranked.sort(key=lambda item: (-item["score"], str(item.get("year") or ""), item["title"].casefold(), item["zoteroKey"]))
        candidate_truncated = len(ranked) > max_candidate_papers
        ranked = ranked[:max_candidate_papers]

        snippets: list[dict[str, Any]] = []
        expanded_papers: set[str] = set()
        if depth in {"evidence", "verify"}:
            for paper in ranked[:max_snippet_papers]:
                if paper["zoteroKey"] in evidence_cache:
                    chunks = evidence_cache[paper["zoteroKey"]]
                else:
                    chunks, state_warning = self._evidence_chunks(paper["zoteroKey"])
                    if state_warning:
                        warnings.append(state_warning)
                    if chunks:
                        scanned_full_text.add(paper["zoteroKey"])
                passages = []
                for chunk in chunks:
                    score, exact_hit, lexical_hit = _score_chunk(chunk, queries, normalized_query, selected_methods)
                    if queries and score <= 0:
                        continue
                    passages.append(
                        {
                            "zoteroKey": paper["zoteroKey"],
                            "evidenceId": str(chunk.get("evidenceId") or ""),
                            "text": str(chunk.get("text") or ""),
                            "sectionPath": list(chunk.get("sectionPath") or []),
                            "contentType": str(chunk.get("contentType") or "other"),
                            "page": chunk.get("page"),
                            "sourceLink": str(chunk.get("sourceLink") or ""),
                            "score": round(score, 6),
                            "contentHash": str(chunk.get("contentHash") or ""),
                            "sourceFingerprint": str(chunk.get("sourceFingerprint") or ""),
                            "relatedAssetIds": sorted(set(str(value) for value in chunk.get("relatedAssetIds") or [])),
                            "matchMethods": [name for name, hit in (("exact", exact_hit), ("lexical", lexical_hit)) if hit],
                        }
                    )
                passages.sort(key=lambda item: (-item["score"], item["evidenceId"]))
                selected = passages[:per_paper_top_k]
                if selected:
                    expanded_papers.add(paper["zoteroKey"])
                    snippets.extend(selected)
        snippets.sort(key=lambda item: (-item["score"], item["zoteroKey"], item["evidenceId"]))
        snippet_truncated = len(snippets) > max_total_snippets
        snippets = snippets[:max_total_snippets]

        paper_matches = [_public_paper(record) for record in ranked]
        coverage = {
            "poolTotal": pool_total,
            "metadataChecked": len(records),
            "abstractAvailable": sum(bool(record["abstract"]) for record in records),
            "mineruFullTextAvailable": sum(bool(record["fullTextAvailable"]) for record in records),
            "fullTextScanned": len(scanned_full_text),
            "evidenceExpandedPapers": len(expanded_papers),
            "returnedSnippets": len(snippets),
            "metadataOnlyPapers": [record["zoteroKey"] for record in records if not record["abstract"] and not record["fullTextAvailable"]],
            "abstractOnlyPapers": [record["zoteroKey"] for record in records if record["abstract"] and not record["fullTextAvailable"]],
            "imageAssetsAvailable": sum(bool(record["imageAssetsAvailable"]) for record in records),
            "pdfCropAvailable": sum(bool(record["pdfCropAvailable"]) for record in records),
            "exactMatchPapers": exact_match_count,
            "lexicalMatchPapers": lexical_match_count,
            "candidateTruncated": candidate_truncated,
            "snippetTruncated": snippet_truncated,
            "exhaustive": bool(intent == "enumerate" and not queries and not candidate_truncated and len(ranked) == pool_total),
        }
        frontier = _frontier(records, ranked, expanded_papers, snippets, coverage)
        digest = _digest(snippets, ranked)

        coverage_ledger: list[dict[str, Any]] = []
        if record_coverage:
            coverage_ledger = self._record_coverage(
                ranked,
                snippets,
                normalized_query,
                depth,
                warnings,
                dry_run=coverage_dry_run,
                transaction_id=coverage_transaction_id,
            )
        result = {
            "ok": True,
            "intent": intent,
            "depth": depth,
            "methods": list(selected_methods),
            "query": normalized_query,
            "queryVariants": list(variants),
            "paperMatches": paper_matches,
            "snippets": snippets,
            "paperSynthesisDigest": digest,
            "coverage": coverage,
            "frontier": frontier,
            "warnings": _stable_warnings(warnings),
        }
        if record_coverage:
            result["coverageLedger"] = coverage_ledger
        return result

    def _paper_records(self, scope: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        allowed_scope = {"zotero_keys", "collection_key", "tags"}
        unknown = set(scope) - allowed_scope
        if unknown:
            raise ValueError(f"unknown retrieval scope field(s): {', '.join(sorted(unknown))}")
        keys = {validate_zotero_key(str(value)) for value in scope.get("zotero_keys") or []}
        collection_key = str(scope.get("collection_key") or "").strip()
        required_tags = {str(value).strip().casefold() for value in scope.get("tags") or [] if str(value).strip()}
        root = normalize_vault_relative(str(self.config["literature"]["root"]))
        folder = self.fs.resolve(root)
        records: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        if not folder.is_dir():
            return records, warnings
        for path in sorted(folder.glob("*.md"), key=lambda item: (item.name.casefold(), item.name)):
            relative = self.fs.relative(path)
            if relative == normalize_vault_relative(str(self.config["literature"]["index"])):
                continue
            try:
                document = parse_frontmatter(path.read_text(encoding="utf-8"))
                key = validate_zotero_key(str(document.fields.get("zoteroKey") or ""))
            except Exception as exc:
                warnings.append({"code": "unreadable-paper-metadata", "path": relative, "message": str(exc)})
                continue
            if keys and key not in keys:
                continue
            tags = [str(value) for value in document.fields.get("tags") or []]
            if required_tags and not required_tags <= {value.casefold() for value in tags}:
                continue
            state = self._item_state(key)
            collections = {str(value) for value in state.get("collectionKeys") or state.get("collections") or []}
            if collection_key and collection_key not in collections:
                continue
            manifest = self._manifest(key)
            assets = [item for item in manifest.get("assets", []) if isinstance(item, dict)]
            mineru_path = str(state.get("mineruPath") or "")
            if not mineru_path:
                mineru_path = _link_target(document.fields.get("attachmentMinerULink"), markdown=True)
            full_text = bool(mineru_path and self.fs.exists(mineru_path))
            analysis_path = normalize_vault_relative(f"{self.config['analysis']['folder']}/{key}.md")
            records.append(
                {
                    "zoteroKey": key,
                    "title": str(document.fields.get("title") or key),
                    "year": document.fields.get("year"),
                    "journal": str(document.fields.get("journal") or ""),
                    "doi": str(document.fields.get("doi") or ""),
                    "abstract": str(document.fields.get("abstract") or ""),
                    "tags": tags,
                    "notePath": relative,
                    "fullTextAvailable": full_text,
                    "imageAssetsAvailable": bool(assets),
                    "pdfCropAvailable": any(item.get("pdfCropPath") for item in assets),
                    "analysisAvailable": self.fs.exists(analysis_path),
                    "availableEvidenceLevel": "full_text" if full_text else "abstract" if document.fields.get("abstract") else "metadata",
                    "collections": sorted(collections),
                    "assetCount": len(assets),
                }
            )
        records.sort(key=lambda item: (item["title"].casefold(), item["zoteroKey"]))
        return records, warnings

    def _item_state(self, key: str) -> dict[str, Any]:
        path = normalize_vault_relative(f".obsidian-vault-mcp/state/items/{key}.json")
        if not self.fs.exists(path):
            return {}
        try:
            value = json.loads(self.fs.read_text(path))
            return value if isinstance(value, dict) else {}
        except (OSError, UnicodeError, json.JSONDecodeError):
            return {}

    def _manifest(self, key: str) -> dict[str, Any]:
        root = normalize_vault_relative(str(self.config["mineru"]["candidateCacheFolder"]))
        path = normalize_vault_relative(f"{root}/{key}/manifest.json")
        if not self.fs.exists(path):
            return {}
        try:
            manifest = parse_image_manifest(self.fs.read_text(path))
            if manifest.zotero_key != key:
                return {}
            if not self.fs.exists(manifest.source_markdown):
                return {}
            if self.fs.sha256(manifest.source_markdown) != manifest.source_markdown_sha256:
                return {}
            return manifest.as_dict()
        except (OSError, UnicodeError, ImageAssetValidationError, ValueError):
            return {}

    def _evidence_chunks(self, key: str) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        path = self.paths.evidence_state(key)
        try:
            value = self.evidence.load_verified(key)
            return list(value["chunks"]), None
        except FileNotFoundError:
            return [], None
        except (OSError, UnicodeError, TypeError, ValueError) as exc:
            return [], {"code": "invalid-evidence-state", "path": path, "message": str(exc)}

    def _record_coverage(
        self,
        papers: list[dict[str, Any]],
        snippets: list[dict[str, Any]],
        topic: str,
        depth: str,
        warnings: list[dict[str, Any]],
        *,
        dry_run: bool,
        transaction_id: str | None,
    ) -> list[dict[str, Any]]:
        by_paper: dict[str, list[dict[str, Any]]] = {}
        results: list[dict[str, Any]] = []
        for snippet in snippets:
            by_paper.setdefault(snippet["zoteroKey"], []).append(snippet)
        for index, paper in enumerate(papers):
            selected = by_paper.get(paper["zoteroKey"], [])
            source_kind = "evidence_index" if selected else "abstract" if paper["abstract"] else "zotero_metadata"
            granularity = "passage" if selected else "abstract" if paper["abstract"] else "metadata"
            coverage = "targeted" if selected else "partial" if paper["abstract"] else "listed"
            content_hash = _sha256_json(
                {item["evidenceId"]: item["contentHash"] for item in sorted(selected, key=lambda value: value["evidenceId"])}
                if selected
                else {"title": paper["title"], "abstract": paper["abstract"], "year": paper["year"]}
            )
            evidence_ids = {str(item["evidenceId"]) for item in selected if item.get("evidenceId")}
            asset_ids = {str(asset) for item in selected for asset in item.get("relatedAssetIds", [])}
            try:
                recorded = self.coverage.record(
                    paper["zoteroKey"],
                    source_kind=source_kind,
                    topic=topic,
                    granularity=granularity,
                    coverage=coverage,
                    confidence="high" if selected else "medium",
                    content_hash=content_hash,
                    tool_name="literature_retrieve",
                    evidence_refs=evidence_ids,
                    asset_refs=asset_ids,
                    valid_evidence_ids=evidence_ids,
                    valid_asset_ids=asset_ids,
                    details={"depth": depth},
                    dry_run=dry_run,
                    transaction_id=f"{transaction_id[:120]}-{index + 1:04d}" if transaction_id else None,
                )
                results.append(recorded)
            except Exception as exc:
                warnings.append({"code": "coverage-write-failed", "zoteroKey": paper["zoteroKey"], "message": str(exc)})
        return results


def _score_metadata(
    paper: Mapping[str, Any],
    queries: Sequence[str],
    primary_query: str,
    methods: Sequence[str],
) -> tuple[float, list[str], list[str], bool, bool]:
    if not queries:
        return 0.0, ["explicit-scope-enumeration"], [], False, False
    fields = {
        "title": str(paper.get("title") or ""),
        "abstract": str(paper.get("abstract") or ""),
        "journal": str(paper.get("journal") or ""),
        "doi": str(paper.get("doi") or ""),
        "tags": " ".join(str(value) for value in paper.get("tags") or []),
    }
    weights = {"title": 5.0, "abstract": 3.0, "tags": 3.0, "journal": 1.5, "doi": 1.5}
    score = 0.0
    reasons: list[str] = []
    matched_fields: list[str] = []
    exact_hit = False
    lexical_hit = False
    for name, text in fields.items():
        if name == "abstract" and "abstract" not in methods:
            continue
        if name != "abstract" and "metadata" not in methods:
            continue
        lowered = text.casefold()
        if "exact" in methods and primary_query and primary_query.casefold() in lowered:
            score += weights[name] * 2
            exact_hit = True
            reasons.append(f"exact:{name}")
            matched_fields.append(name)
        if "lexical" in methods:
            lexical = max((_lexical_score(text, value) for value in queries), default=0.0)
            if lexical > 0:
                score += weights[name] * lexical
                lexical_hit = True
                reasons.append(f"lexical:{name}")
                matched_fields.append(name)
    return score, sorted(set(reasons)), sorted(set(matched_fields)), exact_hit, lexical_hit


def _score_chunk(
    chunk: Mapping[str, Any],
    queries: Sequence[str],
    primary_query: str,
    methods: Sequence[str],
) -> tuple[float, bool, bool]:
    if not queries:
        return 1.0, False, False
    text = str(chunk.get("text") or "")
    section = " ".join(str(value) for value in chunk.get("sectionPath") or [])
    haystack = f"{section}\n{text}"
    score = 0.0
    exact_hit = False
    lexical_hit = False
    if "exact" in methods and primary_query and primary_query.casefold() in haystack.casefold():
        score += 8.0
        exact_hit = True
    if "lexical" in methods:
        score += max((_lexical_score(haystack, value) for value in queries), default=0.0) * 5.0
        lexical_hit = score > (8.0 if exact_hit else 0.0)
    if chunk.get("contentType") in {"table", "caption"}:
        score += 0.25
    return score, exact_hit, lexical_hit


def _lexical_score(text: str, query: str) -> float:
    query_tokens = set(_tokens(query))
    if not query_tokens:
        return 0.0
    text_tokens = set(_tokens(text))
    return len(query_tokens & text_tokens) / len(query_tokens)


def _tokens(value: str) -> list[str]:
    return [match.group(0).casefold() for match in _TOKEN_RE.finditer(value)]


def _public_paper(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "zoteroKey": record["zoteroKey"],
        "title": record["title"],
        "year": record["year"],
        "journal": record["journal"],
        "score": record["score"],
        "matchReason": record["matchReason"],
        "matchedFields": record["matchedFields"],
        "availableEvidenceLevel": record["availableEvidenceLevel"],
        "fullTextAvailable": record["fullTextAvailable"],
        "imageAssetsAvailable": record["imageAssetsAvailable"],
        "analysisAvailable": record["analysisAvailable"],
    }


def _frontier(
    records: list[dict[str, Any]],
    ranked: list[dict[str, Any]],
    expanded: set[str],
    snippets: list[dict[str, Any]],
    coverage: Mapping[str, Any],
) -> list[dict[str, Any]]:
    selected = {paper["zoteroKey"] for paper in ranked}
    result: list[dict[str, Any]] = []
    for record in records:
        reasons: list[str] = []
        if record["zoteroKey"] not in selected:
            reasons.append("not-selected-by-query-or-budget")
        if not record["fullTextAvailable"]:
            reasons.append("missing-full-text")
        elif record["zoteroKey"] not in expanded:
            reasons.append("full-text-not-expanded")
        if not record["imageAssetsAvailable"]:
            reasons.append("missing-image-assets")
        if reasons:
            result.append({"zoteroKey": record["zoteroKey"], "reasons": reasons})
    if coverage.get("candidateTruncated") or coverage.get("snippetTruncated"):
        result.append({"kind": "budget-boundary", "candidateTruncated": coverage.get("candidateTruncated"), "snippetTruncated": coverage.get("snippetTruncated")})
    if not coverage.get("exhaustive"):
        result.append({"kind": "claim-boundary", "allowedClaim": "sampled-candidates", "prohibitedClaim": "exhaustive-corpus-conclusion"})
    if not snippets:
        result.append({"kind": "recommended-next-step", "action": "obtain-or-rebuild-evidence-index"})
    return result


def _digest(snippets: list[dict[str, Any]], papers: list[dict[str, Any]]) -> dict[str, Any]:
    section_counts = Counter((item.get("sectionPath") or ["Unsectioned"])[0] for item in snippets)
    content_counts = Counter(item.get("contentType") or "other" for item in snippets)
    return {
        "themes": [{"name": name, "snippetCount": count} for name, count in sorted(section_counts.items())],
        "methods": [item["evidenceId"] for item in snippets if any("method" in part.casefold() for part in item.get("sectionPath") or [])],
        "findings": [item["evidenceId"] for item in snippets if any("result" in part.casefold() or "finding" in part.casefold() for part in item.get("sectionPath") or [])],
        "disagreements": [],
        "evidenceGaps": [paper["zoteroKey"] for paper in papers if paper["availableEvidenceLevel"] != "full_text"],
        "candidateComparisons": [{"contentType": name, "snippetCount": count} for name, count in sorted(content_counts.items())],
        "figureEvidenceAvailability": [paper["zoteroKey"] for paper in papers if paper["imageAssetsAvailable"]],
    }


def _link_target(value: Any, *, markdown: bool) -> str:
    if not isinstance(value, str):
        return ""
    raw = value.strip()
    if raw.startswith("[[") and raw.endswith("]]" ):
        raw = raw[2:-2].split("|", 1)[0].split("#", 1)[0]
    try:
        target = normalize_vault_relative(raw)
    except Exception:
        return ""
    if markdown and PurePosixPath(target).suffix == "":
        target += ".md"
    return target


def _budget(value: int, name: str, minimum: int, maximum: int) -> None:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer from {minimum} to {maximum}")


def _sha256_json(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _stable_warnings(warnings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(warnings, key=lambda item: (str(item.get("code") or ""), str(item.get("zoteroKey") or ""), str(item.get("path") or ""), str(item.get("message") or "")))
