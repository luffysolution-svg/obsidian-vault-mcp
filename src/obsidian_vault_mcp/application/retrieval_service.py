"""Deterministic retrieval over metadata and transient MinerU passages."""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from ..adapters.vault.filesystem import VaultFilesystem, VaultPathSafetyError
from ..config.loader import load_config
from ..domain.frontmatter import parse_frontmatter
from ..domain.identity import validate_zotero_key
from ..domain.paths import (
    VaultPaths,
    naming_metadata_from_fields,
    normalize_vault_relative,
)
from .paper_read_service import PaperReadService

_INTENTS = {"compare", "enumerate", "verify", "summarize"}
_DEPTHS = {"pool", "metadata", "evidence", "verify"}
_METHODS = {"metadata", "abstract", "exact", "lexical"}
_TOKEN_RE = re.compile(r"[^\W_]+(?:[-'][^\W_]+)*", re.UNICODE)
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


class RetrievalService:
    """Search the local corpus without embeddings, manifests, or persistent coverage."""

    def __init__(
        self,
        vault_path: str | os.PathLike[str],
        config: Mapping[str, Any] | None = None,
    ) -> None:
        self.vault_path = Path(vault_path).expanduser().resolve()
        self.config = dict(config) if config is not None else load_config(self.vault_path, require_exists=False)
        self.fs = VaultFilesystem(self.vault_path)
        self.paths = VaultPaths(self.vault_path, self.config)
        self.reader = PaperReadService(self.vault_path, self.config)

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
    ) -> dict[str, Any]:
        if not isinstance(query, str):
            raise TypeError("query must be a string")
        if intent not in _INTENTS:
            raise ValueError(f"intent must be one of: {', '.join(sorted(_INTENTS))}")
        if depth not in _DEPTHS:
            raise ValueError(f"depth must be one of: {', '.join(sorted(_DEPTHS))}")
        if isinstance(methods, (str, bytes)) or (methods is not None and not isinstance(methods, Sequence)):
            raise TypeError("methods must be an array of strings")
        selected_methods = tuple(dict.fromkeys(methods or ("metadata", "abstract", "exact", "lexical")))
        if not all(isinstance(value, str) for value in selected_methods):
            raise TypeError("methods must be an array of strings")
        unknown_methods = set(selected_methods) - _METHODS
        if unknown_methods:
            raise ValueError(f"unsupported retrieval method(s): {', '.join(sorted(unknown_methods))}")
        _budget(max_candidate_papers, "max_candidate_papers", 1, 500)
        _budget(max_snippet_papers, "max_snippet_papers", 1, 100)
        _budget(per_paper_top_k, "per_paper_top_k", 1, 20)
        _budget(max_total_snippets, "max_total_snippets", 1, 1000)

        normalized_query = " ".join(query.split())
        variants = _string_sequence(query_variants or (), "query_variants")
        queries = tuple(value for value in (normalized_query, *variants) if value)
        records, warnings = self._paper_records(scope or {})
        pool_total = len(records)
        full_text_scanned: set[str] = set()
        passage_cache: dict[str, list[dict[str, Any]]] = {}
        ranked: list[dict[str, Any]] = []
        exact_match_papers = 0
        lexical_match_papers = 0

        for record in records:
            score, reasons, fields, exact, lexical = _score_metadata(
                record,
                queries,
                normalized_query,
                selected_methods,
            )
            if queries and depth in {"evidence", "verify"} and {"exact", "lexical"}.intersection(selected_methods) and record["fullTextAvailable"]:
                passages = self._passages(record["zoteroKey"], warnings)
                passage_cache[record["zoteroKey"]] = passages
                full_text_scanned.add(record["zoteroKey"])
                passage_scores = [
                    _score_passage(
                        passage,
                        queries,
                        normalized_query,
                        selected_methods,
                    )
                    for passage in passages
                ]
                best = max((value[0] for value in passage_scores), default=0.0)
                evidence_exact = any(value[1] for value in passage_scores)
                evidence_lexical = any(value[2] for value in passage_scores)
                if best > 0:
                    score += best
                    fields.append("fullText")
                if evidence_exact:
                    reasons.append("exact:fullText")
                if evidence_lexical:
                    reasons.append("lexical:fullText")
                exact = exact or evidence_exact
                lexical = lexical or evidence_lexical
            if queries and score <= 0:
                continue
            exact_match_papers += int(exact)
            lexical_match_papers += int(lexical)
            ranked.append(
                {
                    **record,
                    "score": round(score, 6),
                    "matchReason": sorted(set(reasons)),
                    "matchedFields": sorted(set(fields)),
                }
            )

        ranked.sort(
            key=lambda item: (
                -item["score"],
                str(item.get("year") or ""),
                item["title"].casefold(),
                item["zoteroKey"],
            )
        )
        candidate_truncated = len(ranked) > max_candidate_papers
        ranked = ranked[:max_candidate_papers]

        snippets: list[dict[str, Any]] = []
        expanded: set[str] = set()
        if depth in {"evidence", "verify"}:
            for paper in ranked[:max_snippet_papers]:
                passages = passage_cache.get(paper["zoteroKey"])
                if passages is None:
                    passages = self._passages(paper["zoteroKey"], warnings)
                    passage_cache[paper["zoteroKey"]] = passages
                    if paper["fullTextAvailable"]:
                        full_text_scanned.add(paper["zoteroKey"])
                selected: list[dict[str, Any]] = []
                for passage in passages:
                    score, exact, lexical = _score_passage(
                        passage,
                        queries,
                        normalized_query,
                        selected_methods,
                    )
                    if queries and score <= 0:
                        continue
                    value = {
                        "zoteroKey": paper["zoteroKey"],
                        "title": paper["title"],
                        **passage,
                        "score": round(score if queries else 1.0, 6),
                        "matchMethods": [
                            name
                            for name, matched in (
                                ("exact", exact),
                                ("lexical", lexical),
                            )
                            if matched
                        ],
                    }
                    selected.append(value)
                selected.sort(
                    key=lambda item: (
                        -item["score"],
                        item["paragraphIndex"],
                    )
                )
                selected = selected[:per_paper_top_k]
                if selected:
                    expanded.add(paper["zoteroKey"])
                    snippets.extend(selected)
        snippets.sort(
            key=lambda item: (
                -item["score"],
                item["zoteroKey"],
                item["paragraphIndex"],
            )
        )
        snippet_truncated = len(snippets) > max_total_snippets
        snippets = snippets[:max_total_snippets]

        basic_coverage = {
            "poolTotal": pool_total,
            "metadataChecked": len(records),
            "abstractAvailable": sum(bool(record["abstract"]) for record in records),
            "mineruFullTextAvailable": sum(bool(record["fullTextAvailable"]) for record in records),
            "fullTextScanned": len(full_text_scanned),
            "expandedPapers": len(expanded),
            "returnedSnippets": len(snippets),
            "exactMatchPapers": exact_match_papers,
            "lexicalMatchPapers": lexical_match_papers,
            "candidateTruncated": candidate_truncated,
            "snippetTruncated": snippet_truncated,
            "exhaustive": bool(intent == "enumerate" and not queries and not candidate_truncated and len(ranked) == pool_total),
        }
        return {
            "ok": True,
            "intent": intent,
            "depth": depth,
            "methods": list(selected_methods),
            "query": normalized_query,
            "queryVariants": list(variants),
            "paperMatches": [_public_paper(record) for record in ranked],
            "snippets": snippets,
            "basicCoverage": basic_coverage,
            "frontier": _frontier(records, ranked, expanded, basic_coverage),
            "paperSynthesisDigest": _digest(snippets, ranked),
            "warnings": _stable_warnings(warnings),
        }

    def _passages(
        self,
        key: str,
        warnings: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        result = self.reader.read(
            key,
            mode="full",
            max_chars=1_000_000,
            top_k=500,
        )
        warnings.extend(result["warnings"])
        return list(result["passages"])

    def _paper_records(
        self,
        scope: Mapping[str, Any],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        if not isinstance(scope, Mapping):
            raise TypeError("scope must be an object")
        allowed_scope = {"zotero_keys", "collection_key", "tags"}
        unknown = set(scope) - allowed_scope
        if unknown:
            raise ValueError(f"unknown retrieval scope field(s): {', '.join(sorted(unknown))}")
        keys = {validate_zotero_key(value) for value in _string_sequence(scope.get("zotero_keys") or (), "scope.zotero_keys")}
        required_tags = {value.casefold() for value in _string_sequence(scope.get("tags") or (), "scope.tags")}
        collection_key = " ".join(str(scope.get("collection_key") or "").split())
        literature_root = normalize_vault_relative(str(self.config["literature"]["root"]))
        index_path = normalize_vault_relative(str(self.config["literature"]["index"]))
        records: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        try:
            candidates, rejected = self.fs.scan_owned_files(
                literature_root,
                recursive=False,
            )
        except VaultPathSafetyError as exc:
            _append_unsafe_warning(warnings, exc.relative_path, str(exc))
            return records, warnings
        for relative in rejected:
            _append_unsafe_warning(
                warnings,
                relative,
                "Paper metadata scan skipped a linked, reparse, or non-regular path",
            )
        image_root = str(self.config["mineru"]["imageFolder"]).replace("\\", "/").rstrip("/")
        for relative in candidates:
            if Path(relative).suffix.lower() != ".md":
                continue
            if relative == index_path:
                continue
            try:
                document = parse_frontmatter(self.fs.read_text_owned(relative))
                key = validate_zotero_key(str(document.fields.get("zoteroKey") or ""))
            except VaultPathSafetyError as exc:
                _append_unsafe_warning(warnings, exc.relative_path, str(exc))
                continue
            except Exception as exc:
                warnings.append(
                    {
                        "code": "unreadable-paper-metadata",
                        "path": relative,
                        "message": str(exc),
                    }
                )
                continue
            if keys and key not in keys:
                continue
            tags = _field_strings(document.fields.get("tags"))
            if required_tags and not required_tags <= {value.casefold() for value in tags}:
                continue
            collections = set(_field_strings(document.fields.get("collectionKeys") or document.fields.get("collections")))
            collections.update(self._state_collections(key, warnings))
            if collection_key and collection_key not in collections:
                continue
            mineru_path = self.paths.mineru_markdown(
                key,
                **naming_metadata_from_fields(document.fields),
            )
            full_text_available = self._is_file_available(mineru_path, warnings)
            images = self._image_files(f"{image_root}/{key}", warnings)
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
                    "fullTextAvailable": full_text_available,
                    "imageAvailable": bool(images),
                    "imageCount": len(images),
                    "availableEvidenceLevel": ("full_text" if full_text_available else "abstract" if document.fields.get("abstract") else "metadata"),
                    "collections": sorted(collections),
                }
            )
        records.sort(key=lambda item: (item["title"].casefold(), item["zoteroKey"]))
        return records, warnings

    def _is_file_available(
        self,
        relative: str,
        warnings: list[dict[str, Any]],
    ) -> bool:
        try:
            return self.fs.is_file_owned(relative)
        except VaultPathSafetyError as exc:
            _append_unsafe_warning(warnings, exc.relative_path, str(exc))
            return False

    def _image_files(
        self,
        folder: str,
        warnings: list[dict[str, Any]],
    ) -> list[str]:
        try:
            candidates, rejected = self.fs.scan_owned_files(folder, recursive=True)
        except VaultPathSafetyError as exc:
            _append_unsafe_warning(warnings, exc.relative_path, str(exc))
            return []
        for relative in rejected:
            _append_unsafe_warning(
                warnings,
                relative,
                "Image scan skipped a linked, reparse, or non-regular path",
            )
        return [relative for relative in candidates if Path(relative).suffix.lower() in _IMAGE_EXTENSIONS]

    def _state_collections(
        self,
        key: str,
        warnings: list[dict[str, Any]],
    ) -> list[str]:
        state_path = self.paths.state(key)
        try:
            if not self.fs.is_file_owned(state_path):
                return []
            state = json.loads(self.fs.read_text_owned(state_path))
        except VaultPathSafetyError as exc:
            _append_unsafe_warning(warnings, exc.relative_path, str(exc))
            return []
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            warnings.append(
                {
                    "code": "unreadable-item-state",
                    "path": state_path,
                    "message": str(exc),
                }
            )
            return []
        if not isinstance(state, Mapping) or state.get("zoteroKey") != key:
            warnings.append(
                {
                    "code": "invalid-item-state",
                    "path": state_path,
                    "message": f"Item state identity does not match {key}",
                }
            )
            return []
        raw_collections = state.get("collectionKeys")
        if raw_collections is None:
            return []
        if (
            isinstance(raw_collections, (str, bytes))
            or not isinstance(raw_collections, Sequence)
            or not all(isinstance(value, str) for value in raw_collections)
        ):
            warnings.append(
                {
                    "code": "invalid-item-state",
                    "path": state_path,
                    "message": "Item state collectionKeys must be an array of strings",
                }
            )
            return []
        return _field_strings(raw_collections)


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
        if "exact" in methods and primary_query and primary_query.casefold() in text.casefold():
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
    return score, reasons, matched_fields, exact_hit, lexical_hit


def _score_passage(
    passage: Mapping[str, Any],
    queries: Sequence[str],
    primary_query: str,
    methods: Sequence[str],
) -> tuple[float, bool, bool]:
    if not queries:
        return 1.0, False, False
    haystack = f"{' '.join(str(value) for value in passage.get('sectionPath') or [])}\n{passage.get('text') or ''}"
    exact = bool("exact" in methods and primary_query and primary_query.casefold() in haystack.casefold())
    lexical_score = max((_lexical_score(haystack, value) for value in queries), default=0.0) if "lexical" in methods else 0.0
    return (8.0 if exact else 0.0) + lexical_score * 5.0, exact, lexical_score > 0


def _lexical_score(text: str, query: str) -> float:
    query_tokens = set(_tokens(query))
    if not query_tokens:
        return 0.0
    return len(query_tokens & set(_tokens(text))) / len(query_tokens)


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
        "imageAvailable": record["imageAvailable"],
        "imageCount": record["imageCount"],
    }


def _frontier(
    records: Sequence[Mapping[str, Any]],
    ranked: Sequence[Mapping[str, Any]],
    expanded: set[str],
    coverage: Mapping[str, Any],
) -> list[dict[str, Any]]:
    selected = {str(paper["zoteroKey"]) for paper in ranked}
    result: list[dict[str, Any]] = []
    for record in records:
        reasons: list[str] = []
        key = str(record["zoteroKey"])
        if key not in selected:
            reasons.append("not-selected-by-query-or-budget")
        if not record["fullTextAvailable"]:
            reasons.append("missing-full-text")
        elif key not in expanded:
            reasons.append("full-text-not-returned")
        if reasons:
            result.append({"zoteroKey": key, "reasons": reasons})
    if coverage["candidateTruncated"] or coverage["snippetTruncated"]:
        result.append(
            {
                "kind": "budget-boundary",
                "candidateTruncated": coverage["candidateTruncated"],
                "snippetTruncated": coverage["snippetTruncated"],
            }
        )
    if not coverage["exhaustive"]:
        result.append(
            {
                "kind": "claim-boundary",
                "allowedClaim": "returned-candidates",
                "prohibitedClaim": "exhaustive-corpus-conclusion",
            }
        )
    return result


def _digest(
    snippets: Sequence[Mapping[str, Any]],
    papers: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    section_counts = Counter((item.get("sectionPath") or ["Unsectioned"])[-1] for item in snippets)
    return {
        "sections": [{"name": name, "snippetCount": count} for name, count in sorted(section_counts.items())],
        "papersWithoutFullText": [paper["zoteroKey"] for paper in papers if not paper["fullTextAvailable"]],
    }


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


def _field_strings(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [str(item) for item in value if str(item)]
    return []


def _budget(value: int, name: str, minimum: int, maximum: int) -> None:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer from {minimum} to {maximum}")


def _append_unsafe_warning(
    warnings: list[dict[str, Any]],
    path: str,
    message: str,
) -> None:
    warnings.append(
        {
            "code": "unsafe-vault-path",
            "path": path,
            "message": message,
        }
    )


def _stable_warnings(warnings: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[tuple[str, str, str], dict[str, Any]] = {}
    for warning in warnings:
        marker = (
            str(warning.get("code") or ""),
            str(warning.get("path") or ""),
            str(warning.get("message") or ""),
        )
        unique[marker] = warning
    return [unique[key] for key in sorted(unique)]
