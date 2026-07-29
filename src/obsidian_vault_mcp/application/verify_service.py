"""Read-only integrity checks for user-visible V2 Vault assets."""

from __future__ import annotations

import hashlib
import json
import posixpath
import re
from collections import Counter, defaultdict
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from ..adapters.mineru.normalizer import (
    find_unsupported_image_syntax,
    parse_image_destination,
    parse_image_references,
)
from ..adapters.vault.filesystem import VaultFilesystem
from ..config.loader import ConfigLoader
from ..config.schema import validate_config
from ..domain.coverage import CoverageRecord
from ..domain.errors import FrontmatterError, IdentityError, PathValidationError
from ..domain.evidence import (
    EVIDENCE_SCHEMA_VERSION,
    EvidenceChunk,
    evidence_block_id_counts,
    parse_evidence_markdown,
)
from ..domain.frontmatter import parse_frontmatter
from ..domain.identity import validate_zotero_key
from ..domain.image_assets import (
    SUPPORTED_IMAGE_EXTENSIONS,
    ImageAssetManifest,
    ImageAssetValidationError,
)
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
        known_formal_images: set[str] = set()
        for record in records:
            self._check_attachment(record, "attachmentPdfLink", "pdf", issues)
            self._check_attachment(record, "attachmentMinerULink", "mineru", issues)
            self._check_mineru_images(record, issues, known_formal_images)
            evidence_hashes, evidence_state_stale = self._check_evidence_state(record, issues)
            self._check_coverage_state(record, evidence_hashes, evidence_state_stale, issues)
        self._check_orphan_mineru_images(known_formal_images, issues)

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

    def _check_mineru_images(
        self,
        record: Mapping[str, Any],
        issues: list[dict[str, Any]],
        known_formal_images: set[str],
    ) -> None:
        value = record["fields"].get("attachmentMinerULink")
        if not value:
            return
        try:
            mineru_path = _vault_link_target(value, markdown=True)
            markdown_file = self.paths.resolve(mineru_path)
        except (PathValidationError, TypeError, ValueError):
            return
        if not markdown_file.is_file():
            return
        try:
            markdown_bytes = markdown_file.read_bytes()
            markdown = markdown_bytes.decode("utf-8")
        except (OSError, UnicodeError):
            return

        inline_targets: set[str] = set()
        for finding in find_unsupported_image_syntax(markdown):
            issues.append(
                _issue(
                    "unsupported-image-syntax",
                    "warning",
                    mineru_path,
                    f"Unsupported {finding['syntax']} image syntax",
                    zoteroKey=record["zoteroKey"],
                    line=markdown.count("\n", 0, int(finding["sourceOffset"])) + 1,
                    syntax=finding["syntax"],
                )
            )
        for reference in parse_image_references(markdown):
            raw_path, _suffix = parse_image_destination(reference.destination)
            try:
                target = _resolve_inline_image_target(mineru_path, raw_path)
                full = self.paths.resolve(target)
            except (PathValidationError, ValueError) as exc:
                issues.append(
                    _issue(
                        "invalid-mineru-image-link",
                        "error",
                        mineru_path,
                        f"Invalid inline MinerU image path: {exc}",
                        zoteroKey=record["zoteroKey"],
                        line=markdown.count("\n", 0, reference.start) + 1,
                        target=raw_path,
                    )
                )
                continue
            inline_targets.add(target)
            known_formal_images.add(target)
            if not full.is_file():
                issues.append(
                    _issue(
                        "broken-mineru-image-link",
                        "error",
                        mineru_path,
                        f"Inline MinerU image does not exist: {target}",
                        zoteroKey=record["zoteroKey"],
                        line=markdown.count("\n", 0, reference.start) + 1,
                        target=target,
                    )
                )

        if not bool(self.config["mineru"]["imageManifestEnabled"]):
            return
        manifest_relative = self.paths.image_manifest(record["zoteroKey"])
        manifest_path = self.paths.resolve(manifest_relative)
        if not manifest_path.is_file():
            issues.append(
                _issue(
                    "missing-image-manifest",
                    "warning",
                    manifest_relative,
                    f"MinerU image manifest is missing for {record['zoteroKey']}",
                    zoteroKey=record["zoteroKey"],
                )
            )
            return
        try:
            raw_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            issues.append(
                _issue(
                    "invalid-image-manifest",
                    "error",
                    manifest_relative,
                    f"Cannot read image manifest JSON: {exc}",
                    zoteroKey=record["zoteroKey"],
                )
            )
            return
        self._check_raw_manifest(raw_manifest, record["zoteroKey"], manifest_relative, issues)
        try:
            manifest = ImageAssetManifest.from_dict(raw_manifest)
        except (ImageAssetValidationError, TypeError, ValueError) as exc:
            issues.append(
                _issue(
                    "invalid-image-manifest",
                    "error",
                    manifest_relative,
                    str(exc),
                    zoteroKey=record["zoteroKey"],
                )
            )
            return

        if manifest.source_markdown != mineru_path:
            issues.append(
                _issue(
                    "asset-status-mismatch",
                    "error",
                    manifest_relative,
                    "Image manifest sourceMarkdown does not match the linked MinerU Markdown",
                    zoteroKey=record["zoteroKey"],
                    expected=mineru_path,
                    actual=manifest.source_markdown,
                )
            )
        markdown_sha = hashlib.sha256(markdown_bytes).hexdigest()
        if manifest.source_markdown_sha256 != markdown_sha:
            issues.append(
                _issue(
                    "stale-image-hash",
                    "error",
                    mineru_path,
                    "MinerU Markdown hash does not match its image manifest",
                    zoteroKey=record["zoteroKey"],
                    expectedSha256=manifest.source_markdown_sha256,
                    actualSha256=markdown_sha,
                )
            )

        manifest_referenced: set[str] = set()
        for asset in manifest.assets:
            asset_path = asset.normalized_path or asset.cache_path
            if asset.normalized_path:
                known_formal_images.add(asset.normalized_path)
            if asset.status == "referenced":
                if asset.normalized_path is None:
                    continue
                manifest_referenced.add(asset.normalized_path)
                if asset.normalized_path not in inline_targets:
                    issues.append(
                        _issue(
                            "asset-status-mismatch",
                            "error",
                            manifest_relative,
                            f"Referenced manifest asset is not linked by Markdown: {asset.asset_id}",
                            zoteroKey=record["zoteroKey"],
                            assetId=asset.asset_id,
                        )
                    )
            if asset_path is None:
                continue
            try:
                full_asset = self.paths.resolve(asset_path)
            except PathValidationError:
                continue
            if not full_asset.is_file():
                code = "missing-candidate-cache" if asset.status == "unlinked_candidate" else "missing-image-asset"
                severity = "warning" if asset.status == "unlinked_candidate" else "error"
                issues.append(
                    _issue(
                        code,
                        severity,
                        asset_path,
                        f"Image asset file is missing: {asset.asset_id}",
                        zoteroKey=record["zoteroKey"],
                        assetId=asset.asset_id,
                    )
                )
                continue
            if asset.sha256:
                actual_sha = _hash_file(full_asset)
                if actual_sha != asset.sha256:
                    issues.append(
                        _issue(
                            "stale-image-hash",
                            "error",
                            asset_path,
                            f"Image asset hash is stale: {asset.asset_id}",
                            zoteroKey=record["zoteroKey"],
                            assetId=asset.asset_id,
                            expectedSha256=asset.sha256,
                            actualSha256=actual_sha,
                        )
                    )
        for target in sorted(inline_targets - manifest_referenced, key=str.casefold):
            issues.append(
                _issue(
                    "missing-image-manifest-entry",
                    "error",
                    mineru_path,
                    f"Inline image has no referenced manifest entry: {target}",
                    zoteroKey=record["zoteroKey"],
                    target=target,
                )
            )

    def _check_raw_manifest(
        self,
        value: Any,
        key: str,
        manifest_path: str,
        issues: list[dict[str, Any]],
    ) -> None:
        if not isinstance(value, Mapping):
            return
        assets = value.get("assets")
        if not isinstance(assets, list):
            return
        image_folder = normalize_vault_relative(str(self.config["mineru"]["imageFolder"]))
        candidate_folder = self.paths.image_candidate_cache(key)
        identities: Counter[str] = Counter()
        digests: Counter[str] = Counter()
        destinations: Counter[str] = Counter()
        for asset in assets:
            if not isinstance(asset, Mapping):
                continue
            asset_id = asset.get("assetId")
            digest = asset.get("sha256")
            if isinstance(asset_id, str):
                identities[asset_id] += 1
            if isinstance(digest, str):
                digests[digest.casefold()] += 1
            for field, expected_folder in (("normalizedPath", image_folder), ("cachePath", candidate_folder)):
                raw_path = asset.get(field)
                if raw_path is None:
                    continue
                try:
                    relative = normalize_vault_relative(raw_path)
                except (PathValidationError, TypeError, ValueError) as exc:
                    issues.append(
                        _issue(
                            "invalid-asset-path",
                            "error",
                            manifest_path,
                            f"Invalid {field}: {exc}",
                            zoteroKey=key,
                            assetId=str(asset_id or ""),
                            target=str(raw_path),
                        )
                    )
                    continue
                destinations[relative.casefold()] += 1
                if not _inside_folder(relative, expected_folder):
                    issues.append(
                        _issue(
                            "invalid-asset-path",
                            "error",
                            manifest_path,
                            f"{field} is outside its managed folder: {relative}",
                            zoteroKey=key,
                            assetId=str(asset_id or ""),
                            target=relative,
                        )
                    )
                try:
                    self.paths.resolve(relative)
                except PathValidationError as exc:
                    issues.append(
                        _issue(
                            "asset-outside-vault",
                            "error",
                            manifest_path,
                            str(exc),
                            zoteroKey=key,
                            assetId=str(asset_id or ""),
                            target=relative,
                        )
                    )
        duplicates = sorted(
            {identity for identity, count in identities.items() if count > 1}
            | {digest for digest, count in digests.items() if count > 1}
            | {path for path, count in destinations.items() if count > 1},
            key=str.casefold,
        )
        for duplicate in duplicates:
            issues.append(
                _issue(
                    "duplicate-mineru-image",
                    "error",
                    manifest_path,
                    f"Duplicate image identity or content in manifest: {duplicate}",
                    zoteroKey=key,
                    duplicate=duplicate,
                )
            )

    def _check_orphan_mineru_images(
        self,
        known_formal_images: set[str],
        issues: list[dict[str, Any]],
    ) -> None:
        image_folder = normalize_vault_relative(str(self.config["mineru"]["imageFolder"]))
        known = {path.casefold() for path in known_formal_images}
        try:
            files = self.fs.list_files(image_folder)
        except (OSError, PathValidationError, ValueError):
            return
        for path in files:
            if PurePosixPath(path).suffix.lower().lstrip(".") not in SUPPORTED_IMAGE_EXTENSIONS:
                continue
            if path.casefold() in known:
                continue
            issues.append(
                _issue(
                    "orphan-mineru-image",
                    "warning",
                    path,
                    "Formal MinerU image is referenced by neither Markdown nor a manifest",
                )
            )

    def _check_evidence_state(
        self,
        record: Mapping[str, Any],
        issues: list[dict[str, Any]],
    ) -> tuple[dict[str, str], bool]:
        key = str(record["zoteroKey"])
        mineru_link = record["fields"].get("attachmentMinerULink")
        if not mineru_link:
            return {}, False
        state_path = self.paths.evidence_state(key)
        if not self.fs.exists(state_path):
            issues.append(
                _issue(
                    "stale-evidence-index",
                    "warning",
                    state_path,
                    "Evidence state is missing for an available MinerU document",
                    zoteroKey=key,
                )
            )
            return {}, True
        try:
            state = json.loads(self.fs.read_text(state_path))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            issues.append(_issue("stale-evidence-index", "error", state_path, f"Cannot read evidence state: {exc}", zoteroKey=key))
            return {}, True
        if not isinstance(state, Mapping) or state.get("schemaVersion") != EVIDENCE_SCHEMA_VERSION or state.get("zoteroKey") != key:
            issues.append(_issue("stale-evidence-index", "error", state_path, "Evidence state schema or identity is invalid", zoteroKey=key))
            return {}, True
        try:
            source_path = normalize_vault_relative(str(state.get("sourcePath") or ""))
        except PathValidationError as exc:
            issues.append(_issue("broken-evidence-source-link", "error", state_path, str(exc), zoteroKey=key))
            return {}, True
        if not self.fs.exists(source_path):
            issues.append(
                _issue(
                    "broken-evidence-source-link",
                    "error",
                    state_path,
                    f"Evidence source Markdown does not exist: {source_path}",
                    zoteroKey=key,
                    target=source_path,
                )
            )
            return {}, True
        source_text = self.fs.read_text(source_path)
        actual_source_hash = self.fs.sha256(source_path)
        state_stale = False
        if str(state.get("sourceMarkdownSha256") or "") != actual_source_hash:
            state_stale = True
            issues.append(
                _issue(
                    "stale-evidence-index",
                    "error",
                    state_path,
                    "Evidence source Markdown hash is stale",
                    zoteroKey=key,
                    expectedSha256=state.get("sourceMarkdownSha256"),
                    actualSha256=actual_source_hash,
                )
            )
        chunks = state.get("chunks")
        if not isinstance(chunks, list):
            issues.append(_issue("stale-evidence-index", "error", state_path, "Evidence chunks must be an array", zoteroKey=key))
            return {}, True
        hashes: dict[str, str] = {}
        duplicate_ids: set[str] = set()
        block_id_counts = evidence_block_id_counts(source_text)
        reported_block_ids: set[str] = set()
        for raw_chunk in chunks:
            try:
                chunk = EvidenceChunk.from_dict(raw_chunk)
            except (TypeError, ValueError, IdentityError, PathValidationError) as exc:
                state_stale = True
                issues.append(_issue("stale-evidence-index", "error", state_path, f"Invalid EvidenceChunk: {exc}", zoteroKey=key))
                continue
            if chunk.evidence_id in hashes:
                duplicate_ids.add(chunk.evidence_id)
            hashes[chunk.evidence_id] = chunk.content_hash
            if chunk.source_path != source_path or chunk.source_link != f"[[{source_path}#^{chunk.block_id}]]":
                issues.append(
                    _issue(
                        "broken-evidence-source-link",
                        "error",
                        state_path,
                        f"Evidence source link is inconsistent: {chunk.evidence_id}",
                        zoteroKey=key,
                        evidenceId=chunk.evidence_id,
                    )
                )
                state_stale = True
            block_count = block_id_counts.get(chunk.block_id, 0)
            if block_count != 1 and chunk.block_id not in reported_block_ids:
                reported_block_ids.add(chunk.block_id)
                issues.append(
                    _issue(
                        "broken-evidence-source-link",
                        "error",
                        source_path,
                        (
                            f"Evidence block ID is missing from source Markdown: {chunk.block_id}"
                            if block_count == 0
                            else f"Evidence block ID is ambiguous in source Markdown: {chunk.block_id}"
                        ),
                        zoteroKey=key,
                        evidenceId=chunk.evidence_id,
                        blockId=chunk.block_id,
                        occurrences=block_count,
                    )
                )
                state_stale = True
        for evidence_id in sorted(duplicate_ids):
            state_stale = True
            issues.append(
                _issue(
                    "duplicate-evidence-id",
                    "error",
                    state_path,
                    f"Duplicate evidenceId: {evidence_id}",
                    zoteroKey=key,
                    evidenceId=evidence_id,
                )
            )
        if bool(self.config.get("evidence", {}).get("enabled", True)):
            manifest_value: Mapping[str, Any] | None = None
            manifest_path = self.paths.image_manifest(key)
            if self.fs.exists(manifest_path):
                try:
                    manifest_value = ImageAssetManifest.from_dict(json.loads(self.fs.read_text(manifest_path))).as_dict()
                except (OSError, UnicodeError, json.JSONDecodeError, ImageAssetValidationError, TypeError, ValueError):
                    manifest_value = None
            try:
                evidence_config = self.config.get("evidence", {})
                rebuilt = parse_evidence_markdown(
                    source_text,
                    zotero_key=key,
                    source_path=source_path,
                    asset_manifest=manifest_value,
                    block_id_prefix=str(evidence_config.get("blockIdPrefix") or "ev"),
                    max_chunk_chars=int(evidence_config.get("maxChunkChars") or 2500),
                    overlap_chars=int(evidence_config.get("overlapChars") or 0),
                )
                rebuilt_chunks = [chunk.as_dict() for chunk in rebuilt.chunks]
            except (TypeError, ValueError, IdentityError, PathValidationError) as exc:
                state_stale = True
                issues.append(
                    _issue(
                        "stale-evidence-index",
                        "error",
                        state_path,
                        f"Cannot rebuild EvidenceChunk state from source Markdown: {exc}",
                        zoteroKey=key,
                    )
                )
            else:
                if rebuilt_chunks != chunks:
                    state_stale = True
                    issues.append(
                        _issue(
                            "stale-evidence-index",
                            "error",
                            state_path,
                            "Evidence chunks do not match a deterministic rebuild from source Markdown",
                            zoteroKey=key,
                        )
                    )
        return hashes, state_stale

    def _check_coverage_state(
        self,
        record: Mapping[str, Any],
        evidence_hashes: Mapping[str, str],
        evidence_state_stale: bool,
        issues: list[dict[str, Any]],
    ) -> None:
        key = str(record["zoteroKey"])
        state_path = self.paths.coverage_state(key)
        if not self.fs.exists(state_path):
            return
        try:
            state = json.loads(self.fs.read_text(state_path))
            if not isinstance(state, Mapping) or state.get("schemaVersion") != 1 or state.get("zoteroKey") != key:
                raise ValueError("coverage state schema or identity mismatch")
            raw_records = state.get("records")
            if not isinstance(raw_records, list):
                raise ValueError("coverage records must be an array")
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            issues.append(_issue("stale-coverage-record", "warning", state_path, str(exc), zoteroKey=key))
            return
        asset_ids = self._manifest_asset_ids(key)
        for raw_record in raw_records:
            try:
                coverage = CoverageRecord.from_dict(raw_record)
            except (TypeError, ValueError) as exc:
                issues.append(_issue("stale-coverage-record", "warning", state_path, f"Invalid coverage record: {exc}", zoteroKey=key))
                continue
            missing_evidence = sorted(set(coverage.evidence_refs) - set(evidence_hashes))
            missing_assets = sorted(set(coverage.asset_refs) - asset_ids)
            expected_hash = ""
            if coverage.evidence_refs and not missing_evidence:
                expected_hash = _canonical_sha256(
                    {evidence_id: evidence_hashes[evidence_id] for evidence_id in coverage.evidence_refs}
                )
            if (
                coverage.stale
                or missing_evidence
                or missing_assets
                or (evidence_state_stale and coverage.evidence_refs)
                or (expected_hash and coverage.content_hash != expected_hash)
            ):
                issues.append(
                    _issue(
                        "stale-coverage-record",
                        "warning",
                        state_path,
                        "Coverage record no longer matches current evidence or assets",
                        zoteroKey=key,
                        missingEvidenceIds=missing_evidence,
                        missingAssetIds=missing_assets,
                        expectedContentHash=expected_hash or None,
                        actualContentHash=coverage.content_hash,
                    )
                )

    def _manifest_asset_ids(self, key: str) -> set[str]:
        path = self.paths.image_manifest(key)
        if not self.fs.exists(path):
            return set()
        try:
            manifest = ImageAssetManifest.from_dict(json.loads(self.fs.read_text(path)))
        except (OSError, UnicodeError, json.JSONDecodeError, ImageAssetValidationError, TypeError, ValueError):
            return set()
        return {asset.asset_id for asset in manifest.assets}

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


def _resolve_inline_image_target(markdown_path: str, raw_path: str) -> str:
    value = raw_path.strip().replace("\\", "/")
    if (
        not value
        or value.startswith("/")
        or re.match(r"^[A-Za-z]:/", value)
        or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", value)
    ):
        raise ValueError(f"image target must be a Vault-relative path: {raw_path}")
    extension = PurePosixPath(value).suffix.lower().lstrip(".")
    if extension not in SUPPORTED_IMAGE_EXTENSIONS:
        raise ValueError(f"unsupported image extension: {PurePosixPath(value).suffix}")
    parent = PurePosixPath(markdown_path).parent.as_posix()
    target = posixpath.normpath(posixpath.join(parent, value))
    if target in {"", ".", ".."} or target.startswith("../"):
        raise ValueError(f"image target escapes the Vault: {raw_path}")
    return normalize_vault_relative(target)


def _inside_folder(path: str, folder: str) -> bool:
    return path == folder or path.startswith(f"{folder}/")


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _normalize_doi(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    doi = value.strip().casefold()
    doi = re.sub(r"^(?:doi:\s*|https?://(?:dx\.)?doi\.org/)", "", doi)
    return doi.rstrip(". ")


def _issue(code: str, severity: str, path: str, message: str, **details: Any) -> dict[str, Any]:
    return {"code": code, "severity": severity, "path": path, "message": message, **details}
