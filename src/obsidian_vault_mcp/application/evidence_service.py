"""Build and transactionally persist deterministic MinerU text evidence."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..adapters.vault.filesystem import VaultFilesystem
from ..config.loader import load_config
from ..domain.errors import IdentityError, PathValidationError
from ..domain.evidence import (
    EVIDENCE_SCHEMA_VERSION,
    EvidenceChunk,
    evidence_block_id_counts,
    materialize_evidence_block_ids,
    parse_evidence_markdown,
)
from ..domain.frontmatter import parse_frontmatter
from ..domain.identity import validate_zotero_key
from ..domain.image_assets import (
    ImageAssetManifest,
    ImageAssetValidationError,
    parse_image_manifest,
    render_image_manifest,
)
from ..domain.paths import VaultPaths, normalize_vault_relative
from .transaction_service import TransactionService


class EvidenceService:
    """Rebuild and load hidden EvidenceChunk state for one stable item."""

    def __init__(
        self,
        vault_path: str | os.PathLike[str],
        config: Mapping[str, Any] | None = None,
    ) -> None:
        self.vault_path = Path(vault_path).expanduser().resolve()
        self.config = dict(config) if config is not None else load_config(self.vault_path, require_exists=False)
        self.fs = VaultFilesystem(self.vault_path)
        self.paths = VaultPaths(self.vault_path, self.config)
        self.transactions = TransactionService(self.vault_path)

    def evidence_state_path(self, zotero_key: str) -> str:
        return self.paths.evidence_state(zotero_key)

    def image_manifest_path(self, zotero_key: str) -> str:
        key = validate_zotero_key(zotero_key)
        return self.paths.image_manifest(key)

    def build(self, zotero_key: str, *, generated_at: str | None = None) -> dict[str, Any]:
        """Build current evidence in memory without writing the Vault."""

        key = validate_zotero_key(zotero_key)
        source_path = self._source_path(key)
        source_text = self.fs.read_text(source_path)
        source_bytes = self.fs.read_bytes(source_path)
        source_sha256 = hashlib.sha256(source_bytes).hexdigest()
        manifest, manifest_warnings = self._manifest(key, source_path=source_path, source_sha256=source_sha256)
        materialized_text, block_warnings = self.materialize_source_text(
            key,
            source_path=source_path,
            source_text=source_text,
        )
        if materialized_text != source_text:
            block_warnings.append(
                {
                    "code": "unmaterialized-evidence-block-ids",
                    "message": "Evidence block IDs are not yet persisted in the MinerU Markdown",
                }
            )
        return self.build_from_text(
            key,
            source_path=source_path,
            source_text=materialized_text,
            source_bytes=source_bytes,
            asset_manifest=manifest,
            warnings=[*manifest_warnings, *block_warnings],
            generated_at=generated_at,
        )

    def materialize_source_text(
        self,
        zotero_key: str,
        *,
        source_path: str,
        source_text: str,
    ) -> tuple[str, list[dict[str, Any]]]:
        """Return Markdown with physical deterministic anchors, without writing it."""

        evidence_config = self.config.get("evidence", {})
        if not bool(evidence_config.get("enabled", True)):
            return source_text, []
        materialized, warnings = materialize_evidence_block_ids(
            source_text,
            zotero_key=zotero_key,
            source_path=source_path,
            block_id_prefix=str(evidence_config.get("blockIdPrefix") or "ev"),
        )
        return materialized, list(warnings)

    def build_from_text(
        self,
        zotero_key: str,
        *,
        source_path: str,
        source_text: str,
        source_bytes: bytes | None = None,
        asset_manifest: Mapping[str, Any] | None = None,
        warnings: list[dict[str, Any]] | None = None,
        generated_at: str | None = None,
    ) -> dict[str, Any]:
        """Build state from already-normalized text for inclusion in a parent transaction."""

        key = validate_zotero_key(zotero_key)
        source_path = normalize_vault_relative(source_path)
        evidence_config = self.config.get("evidence", {})
        enabled = bool(evidence_config.get("enabled", True))
        parsed = parse_evidence_markdown(
            source_text,
            zotero_key=key,
            source_path=source_path,
            asset_manifest=asset_manifest,
            block_id_prefix=str(evidence_config.get("blockIdPrefix") or "ev"),
            max_chunk_chars=int(evidence_config.get("maxChunkChars") or 2500),
            overlap_chars=int(evidence_config.get("overlapChars") or 0),
        )
        state_warnings = [*(warnings or []), *parsed.warnings]
        chunks = parsed.chunks if enabled else ()
        if not enabled:
            state_warnings.append({"code": "evidence-disabled", "message": "Evidence indexing is disabled by configuration"})
        relationships = _asset_relationships(chunks)
        state: dict[str, Any] = {
            "schemaVersion": EVIDENCE_SCHEMA_VERSION,
            "zoteroKey": key,
            "sourcePath": source_path,
            # Hash the persisted bytes, not the text-mode newline view. This
            # keeps stale detection correct on Windows without changing chunk
            # normalization or user-visible Markdown.
            "sourceMarkdownSha256": hashlib.sha256(source_bytes if source_bytes is not None else source_text.encode("utf-8")).hexdigest(),
            "generatedAt": _validated_timestamp(generated_at) if generated_at is not None else _utc_now(),
            "chunks": [chunk.as_dict() for chunk in chunks],
            "assetRelationships": relationships,
            "warnings": state_warnings,
        }
        existing = self._load_optional(key)
        if existing is not None and _semantic_state(existing) == _semantic_state(state):
            old_generated_at = existing.get("generatedAt")
            if isinstance(old_generated_at, str) and old_generated_at:
                state["generatedAt"] = old_generated_at
        _validate_state(state, key)
        return state

    def rebuild(
        self,
        zotero_key: str,
        *,
        dry_run: bool = False,
        transaction_id: str | None = None,
        conflict_policy: str = "preserve-user",
        generated_at: str | None = None,
    ) -> dict[str, Any]:
        """Persist evidence state through the existing transaction engine."""

        del conflict_policy
        key = validate_zotero_key(zotero_key)
        source_path = self._source_path(key)
        source_text = self.fs.read_text(source_path)
        source_bytes = self.fs.read_bytes(source_path)
        source_sha256 = hashlib.sha256(source_bytes).hexdigest()
        manifest, manifest_warnings = self._manifest(key, source_path=source_path, source_sha256=source_sha256)
        materialized_text, block_warnings = self.materialize_source_text(
            key,
            source_path=source_path,
            source_text=source_text,
        )
        materialized_bytes = materialized_text.encode("utf-8")
        materialized_sha256 = hashlib.sha256(materialized_bytes).hexdigest()
        if manifest is not None:
            manifest = {
                **manifest,
                "sourceMarkdown": source_path,
                "sourceMarkdownSha256": materialized_sha256,
            }
            manifest = ImageAssetManifest.from_dict(manifest).as_dict()
            manifest_warnings = [
                warning
                for warning in manifest_warnings
                if warning.get("code") != "stale-image-manifest"
            ]
        state = self.build_from_text(
            key,
            source_path=source_path,
            source_text=materialized_text,
            source_bytes=materialized_bytes,
            asset_manifest=manifest,
            warnings=[*manifest_warnings, *block_warnings],
            generated_at=generated_at,
        )
        state_path = self.evidence_state_path(key)
        text = json.dumps(state, ensure_ascii=False, indent=2) + "\n"
        transaction = self.transactions.begin(item_key=key, transaction_id=transaction_id, dry_run=dry_run)
        transaction.write_text(source_path, materialized_text)
        if manifest is not None:
            transaction.write_text(self.image_manifest_path(key), render_image_manifest(ImageAssetManifest.from_dict(manifest)))
        transaction.write_text(state_path, text)
        result = transaction.commit()
        return {
            **result,
            "zoteroKey": key,
            "path": state_path,
            "sourcePath": state["sourcePath"],
            "chunkCount": len(state["chunks"]),
            "warnings": state["warnings"],
        }

    def load(self, zotero_key: str) -> dict[str, Any]:
        """Load validated state and report staleness without rebuilding it."""

        key = validate_zotero_key(zotero_key)
        state = self._load_required(key)
        source_path = str(state["sourcePath"])
        stale = True
        if self.fs.exists(source_path):
            source = self.fs.read_bytes(source_path)
            stale = hashlib.sha256(source).hexdigest() != state["sourceMarkdownSha256"]
        result = dict(state)
        result["stale"] = stale
        return result

    def load_chunks(self, zotero_key: str) -> list[EvidenceChunk]:
        return [EvidenceChunk.from_dict(chunk) for chunk in self.load(zotero_key)["chunks"]]

    def load_verified(self, zotero_key: str) -> dict[str, Any]:
        """Load persisted evidence only when it matches a current deterministic rebuild."""

        key = validate_zotero_key(zotero_key)
        state = self.load(key)
        if state["stale"]:
            raise ValueError("EvidenceChunk state is stale for the current MinerU Markdown")
        rebuilt = self.build(key, generated_at=str(state["generatedAt"]))
        if state["sourcePath"] != rebuilt["sourcePath"] or state["chunks"] != rebuilt["chunks"]:
            raise ValueError("EvidenceChunk state does not match a deterministic source rebuild")
        source_text = self.fs.read_text(str(state["sourcePath"]))
        counts = evidence_block_id_counts(source_text)
        missing = sorted(
            {
                str(chunk["blockId"])
                for chunk in state["chunks"]
                if counts.get(str(chunk["blockId"]), 0) != 1
            }
        )
        if missing:
            raise ValueError(f"EvidenceChunk source block ID is missing or ambiguous: {missing[0]}")
        return state

    def rollback(
        self,
        transaction_id: str,
        *,
        dry_run: bool = False,
        conflict_policy: str = "preserve-user",
    ) -> dict[str, Any]:
        return self.transactions.rollback(transaction_id, dry_run=dry_run, conflict_policy=conflict_policy)

    def _source_path(self, key: str) -> str:
        candidates: list[str] = []
        item_state = self._item_state(key)
        state_path = item_state.get("mineruPath")
        if isinstance(state_path, str) and state_path:
            candidates.append(state_path)

        note = self._main_note(key)
        if note is not None:
            link = note["fields"].get("attachmentMinerULink")
            target = _wikilink_target(link)
            if target:
                candidates.append(target)
        try:
            candidates.append(self.paths.mineru_markdown(key))
        except (IdentityError, PathValidationError):
            pass

        for candidate in dict.fromkeys(candidates):
            try:
                normalized = normalize_vault_relative(candidate)
            except PathValidationError:
                continue
            if not normalized.lower().endswith(".md"):
                normalized = f"{normalized}.md"
            if self.fs.exists(normalized) and self.paths.resolve(normalized).is_file():
                return normalized
        raise FileNotFoundError(f"MinerU Markdown does not exist for {key}")

    def _item_state(self, key: str) -> dict[str, Any]:
        path = self.paths.state(key)
        if not self.fs.exists(path):
            return {}
        try:
            value = json.loads(self.fs.read_text(path))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid item state for {key}: {exc}") from exc
        if not isinstance(value, dict) or value.get("zoteroKey") != key:
            raise ValueError(f"item state identity mismatch for {key}")
        return value

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

    def _manifest(
        self,
        key: str,
        *,
        source_path: str = "",
        source_sha256: str = "",
    ) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        path = self.image_manifest_path(key)
        if not self.fs.exists(path):
            return None, []
        try:
            value = parse_image_manifest(self.fs.read_text(path)).as_dict()
        except (OSError, UnicodeError, ImageAssetValidationError) as exc:
            return None, [{"code": "invalid-image-manifest", "message": str(exc)}]
        if value.get("zoteroKey") != key:
            return None, [{"code": "invalid-image-manifest", "message": "manifest identity or assets are invalid"}]
        warnings: list[dict[str, Any]] = []
        if source_path and value.get("sourceMarkdown") != source_path:
            warnings.append({"code": "stale-image-manifest", "message": "manifest sourceMarkdown does not match evidence sourcePath"})
        if source_sha256 and value.get("sourceMarkdownSha256") != source_sha256:
            warnings.append({"code": "stale-image-manifest", "message": "manifest source Markdown hash is stale"})
        return value, warnings

    def _load_optional(self, key: str) -> dict[str, Any] | None:
        path = self.evidence_state_path(key)
        if not self.fs.exists(path):
            return None
        try:
            return self._load_required(key)
        except (OSError, UnicodeError, ValueError, TypeError, IdentityError, PathValidationError):
            return None

    def _load_required(self, key: str) -> dict[str, Any]:
        path = self.evidence_state_path(key)
        if not self.fs.exists(path):
            raise FileNotFoundError(f"evidence state does not exist for {key}")
        try:
            value = json.loads(self.fs.read_text(path))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid evidence state for {key}: {exc}") from exc
        _validate_state(value, key)
        return value


def _validate_state(value: Any, key: str) -> None:
    if not isinstance(value, dict):
        raise ValueError("evidence state must be a JSON object")
    if value.get("schemaVersion") != EVIDENCE_SCHEMA_VERSION:
        raise ValueError(f"evidence state schemaVersion must be {EVIDENCE_SCHEMA_VERSION}")
    if value.get("zoteroKey") != key:
        raise ValueError(f"evidence state identity mismatch for {key}")
    source_path = normalize_vault_relative(str(value.get("sourcePath") or ""))
    if not source_path.lower().endswith(".md"):
        raise ValueError("evidence state sourcePath must be a Markdown file")
    if not re_full_hash(value.get("sourceMarkdownSha256")):
        raise ValueError("evidence sourceMarkdownSha256 must be a SHA-256 digest")
    _validated_timestamp(value.get("generatedAt"))
    chunks = value.get("chunks")
    if not isinstance(chunks, list):
        raise ValueError("evidence state chunks must be an array")
    seen: set[str] = set()
    for raw_chunk in chunks:
        chunk = EvidenceChunk.from_dict(raw_chunk)
        if chunk.zotero_key != key:
            raise ValueError("EvidenceChunk identity does not match evidence state")
        if chunk.source_path != source_path:
            raise ValueError("EvidenceChunk sourcePath does not match evidence state")
        if chunk.evidence_id in seen:
            raise ValueError(f"duplicate evidenceId in state: {chunk.evidence_id}")
        seen.add(chunk.evidence_id)
    if not isinstance(value.get("warnings", []), list):
        raise ValueError("evidence state warnings must be an array")
    if not isinstance(value.get("assetRelationships", {}), dict):
        raise ValueError("evidence state assetRelationships must be an object")


def _asset_relationships(chunks: tuple[EvidenceChunk, ...]) -> dict[str, dict[str, Any]]:
    relationships: dict[str, dict[str, list[str]]] = {}
    for chunk in chunks:
        for asset_id in chunk.related_asset_ids:
            relation = relationships.setdefault(asset_id, {"captionEvidenceIds": [], "contextEvidenceIds": []})
            name = "captionEvidenceIds" if chunk.content_type == "caption" else "contextEvidenceIds"
            relation[name].append(chunk.evidence_id)
    return {
        asset_id: {
            "captionEvidenceIds": sorted(set(value["captionEvidenceIds"])),
            "contextEvidenceIds": sorted(set(value["contextEvidenceIds"])),
        }
        for asset_id, value in sorted(relationships.items(), key=lambda item: (item[0].casefold(), item[0]))
    }


def _semantic_state(value: Mapping[str, Any]) -> dict[str, Any]:
    return {name: item for name, item in value.items() if name not in {"generatedAt", "stale"}}


def _wikilink_target(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        return ""
    raw = value.strip().strip("\"'")
    if raw.startswith("[[") and raw.endswith("]]" ):
        raw = raw[2:-2].split("|", 1)[0].split("#", 1)[0].strip()
    if not raw:
        return ""
    try:
        target = normalize_vault_relative(raw)
    except PathValidationError:
        return ""
    return target if target.lower().endswith(".md") else f"{target}.md"


def _validated_timestamp(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("generated_at must be an ISO-8601 timestamp")
    normalized = value.strip()
    try:
        datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("generated_at must be an ISO-8601 timestamp") from exc
    return normalized


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def re_full_hash(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value)
