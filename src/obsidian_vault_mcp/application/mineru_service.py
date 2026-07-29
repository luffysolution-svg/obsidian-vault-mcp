from __future__ import annotations

import hashlib
import json
import os
import posixpath
import re
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from pathlib import Path, PurePosixPath
from typing import Any

from ..adapters.mineru.client import MinerUClient
from ..adapters.mineru.normalizer import (
    normalize_mineru_output,
    parse_image_destination,
    parse_image_references,
    relative_source_pdf,
)
from ..adapters.obsidian.markdown_renderer import replace_managed_section
from ..adapters.vault.filesystem import VaultFilesystem
from ..adapters.vault.lock import GlobalLock
from ..config.loader import load_config
from ..domain.frontmatter import compose_frontmatter, merge_frontmatter, parse_frontmatter
from ..domain.identity import validate_zotero_key
from ..domain.image_assets import ImageAssetManifest, parse_image_manifest, render_image_manifest
from ..domain.models import ItemState
from ..domain.paths import VaultPaths, normalize_vault_relative
from .evidence_service import EvidenceService
from .index_service import IndexService
from .transaction_service import Transaction, TransactionService

_STATE_FIELD_ORDER = (
    "schemaVersion",
    "zoteroKey",
    "zoteroVersion",
    "notePath",
    "pdfPath",
    "mineruPath",
    "mineruAssetRoot",
    "collectionKeys",
    "sourcePdfPath",
    "sourcePdfSha256",
    "copiedPdfSha256",
    "mineruSourceSha256",
    "lastImportedAt",
    "lastMineruAt",
    "lastTransactionId",
    "status",
    "errors",
)


class MinerUService:
    def __init__(
        self,
        vault_path: str | os.PathLike[str],
        *,
        mineru_client: MinerUClient | Any | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        self.vault_path = Path(vault_path).expanduser().resolve()
        self.config = config or load_config(self.vault_path, require_exists=False)
        self.fs = VaultFilesystem(self.vault_path)
        self.paths = VaultPaths(self.vault_path, self.config)
        self.transactions = TransactionService(self.vault_path)
        self.client = mineru_client or MinerUClient()

    def parse(
        self,
        zotero_key: str,
        *,
        dry_run: bool = False,
        transaction_id: str | None = None,
        conflict_policy: str = "preserve-user",
    ) -> dict[str, Any]:
        del conflict_policy
        key = validate_zotero_key(zotero_key)
        state = self._state(key)
        note_path = str(state.get("notePath") or "")
        pdf_path = str(state.get("pdfPath") or "")
        if not note_path or not self.fs.exists(note_path):
            raise FileNotFoundError(f"main literature note does not exist for {key}")
        if not pdf_path or not self.fs.exists(pdf_path):
            raise FileNotFoundError(f"Vault PDF copy does not exist for {key}")

        document = parse_frontmatter(self.fs.read_text(note_path))
        title = str(document.fields.get("title") or key)
        metadata = {"firstAuthor": "", "year": document.fields.get("year") or "", "shortTitle": title}
        mineru_path = str(state.get("mineruPath") or self.paths.mineru_markdown(key, **metadata))
        transaction = self.transactions.begin(item_key=key, transaction_id=transaction_id, dry_run=dry_run)
        staging_rel = self.paths.staging(transaction.transaction_id, "mineru")
        if dry_run:
            preview = transaction.commit()
            return {
                **preview,
                "zoteroKey": key,
                "pdfPath": pdf_path,
                "mineruPath": mineru_path,
                "manifestPath": self.paths.image_manifest(key),
                "evidencePath": self.paths.evidence_state(key),
                "stagingPath": staging_rel,
                "planned": True,
            }

        staging = self.paths.resolve(staging_rel)
        stage = "extract"
        try:
            self.client.parse(
                self.paths.resolve(pdf_path),
                staging,
                mode=str(self.config["mineru"]["mode"]),
            )
            stage = "normalize"

            def image_namer(index: int, extension: str) -> str:
                return PurePosixPath(self.paths.mineru_image(key, index, extension, **metadata)).name

            image_folder = str(self.config["mineru"]["imageFolder"]).replace("\\", "/")
            markdown_folder = PurePosixPath(mineru_path.replace("\\", "/")).parent.as_posix()
            manifest_path = self.paths.image_manifest(key)
            candidate_folder = self.paths.image_candidate_cache(key)
            asset_root = PurePosixPath(manifest_path).parent.as_posix()
            previous_asset_root = self._previous_asset_root(state, key, asset_root)
            previous_manifest_path = f"{previous_asset_root}/manifest.json"
            existing_manifest = self._image_manifest_path(manifest_path)
            if existing_manifest is None and previous_manifest_path != manifest_path:
                existing_manifest = self._image_manifest_path(previous_manifest_path)
            manifest_enabled = bool(self.config["mineru"]["imageManifestEnabled"])
            preserve_candidates = bool(self.config["mineru"]["preserveUnlinkedImageCandidates"])
            old_formal_images = self._owned_formal_images(key, mineru_path, existing_manifest)
            normalized = normalize_mineru_output(
                staging,
                zotero_key=key,
                title=title,
                source_pdf_path=relative_source_pdf(mineru_path, pdf_path),
                image_namer=image_namer,
                image_link_prefix=posixpath.relpath(image_folder, start=markdown_folder),
                output_markdown_path=mineru_path,
                normalized_image_folder=image_folder,
                candidate_cache_folder=candidate_folder,
            )
            manifest = _apply_candidate_policy(
                _merge_manifest_relationships(normalized.manifest, existing_manifest),
                preserve=preserve_candidates,
            )
            evidence = EvidenceService(self.vault_path, self.config)
            materialized_markdown, block_warnings = evidence.materialize_source_text(
                key,
                source_path=mineru_path,
                source_text=normalized.markdown,
            )
            materialized_bytes = materialized_markdown.encode("utf-8")
            manifest = replace(
                manifest,
                source_markdown_sha256=hashlib.sha256(materialized_bytes).hexdigest(),
            )
            evidence_state = evidence.build_from_text(
                key,
                source_path=mineru_path,
                source_text=materialized_markdown,
                source_bytes=materialized_bytes,
                asset_manifest=manifest.as_dict(),
                warnings=block_warnings,
            )
            manifest = _finalize_manifest(
                _apply_evidence_relationships(manifest, evidence_state.get("assetRelationships", {})),
                existing_manifest,
            )
            desired_images: set[str] = set()
            desired_candidates: set[str] = set()
            transaction.write_text(mineru_path, materialized_markdown)
            for image in normalized.images:
                image_path = f"{image_folder.rstrip('/')}/{image.filename}"
                desired_images.add(image_path)
                transaction.write_bytes(image_path, image.content)
            for candidate in normalized.candidate_images if preserve_candidates else ():
                candidate_path = self.paths.image_candidate_cache(
                    key,
                    candidate.asset_id,
                    PurePosixPath(candidate.filename).suffix,
                )
                desired_candidates.add(candidate_path)
                transaction.write_bytes(candidate_path, candidate.content)
            for old_path in sorted(old_formal_images):
                if old_path not in desired_images and self.fs.exists(old_path):
                    transaction.delete(old_path)
            for old_path in self.fs.list_files(candidate_folder):
                if old_path not in desired_candidates:
                    transaction.delete(old_path)
            if previous_asset_root != asset_root:
                protected_asset_paths = set(desired_candidates)
                if manifest_enabled:
                    protected_asset_paths.add(manifest_path)
                for old_path in self.fs.list_files(previous_asset_root):
                    if old_path not in protected_asset_paths:
                        transaction.delete(old_path)
            if manifest_enabled:
                transaction.write_text(manifest_path, render_image_manifest(manifest))
            elif self.fs.exists(manifest_path):
                transaction.delete(manifest_path)
            transaction.write_text(
                self.paths.evidence_state(key),
                json.dumps(evidence_state, ensure_ascii=False, indent=2) + "\n",
            )

            mineru_link = f"[[{_without_md(mineru_path)}]]"
            merged = merge_frontmatter(
                document.fields,
                {"attachmentMinerULink": mineru_link},
                omit_empty=bool(self.config["frontmatter"]["omitEmpty"]),
                preserve_unknown_fields=bool(self.config["frontmatter"]["preserveUnknownFields"]),
                field_order=self.config["frontmatter"]["fieldOrder"],
            )
            block = f"- Full text: [[{_without_md(mineru_path)}]]"
            if self.config["note"]["embedMineruMarkdown"]:
                block += f"\n\n![[{_without_md(mineru_path)}]]"
            updated_body = replace_managed_section(document.body, "mineru", "MinerU", block)
            transaction.write_text(
                note_path,
                compose_frontmatter(merged, updated_body, omit_empty=True, field_order=self.config["frontmatter"]["fieldOrder"]),
            )

            output_changed = bool(transaction.preview()["changed"])
            source_sha = _hash_file(self.paths.resolve(pdf_path))
            last_mineru_at = ItemState.utc_now() if output_changed or state.get("status") != "ready" else str(state.get("lastMineruAt") or "")
            next_state = dict(state)
            next_state.update(
                schemaVersion=2,
                zoteroKey=key,
                mineruPath=mineru_path,
                mineruAssetRoot=asset_root,
                mineruSourceSha256=source_sha,
                lastMineruAt=last_mineru_at,
                lastTransactionId=transaction.transaction_id if output_changed else state.get("lastTransactionId"),
                status="ready",
                errors=[],
            )
            self._add_state_if_changed(transaction, key, next_state)

            overlay = dict(merged)
            overlay.update(notePath=note_path, lastImportedAt=state.get("lastImportedAt") or "")
            if self.config["index"]["autoRebuild"]:
                index = IndexService(self.vault_path, self.config)
                transaction.write_text(index.index_path, index.render([overlay]))

            if self.config["index"]["autoRebuild"]:
                with GlobalLock(self.vault_path, "index"):
                    committed = transaction.commit()
            else:
                committed = transaction.commit()
            return {
                **committed,
                "zoteroKey": key,
                "mineruPath": mineru_path,
                "images": sorted(desired_images),
                "manifestPath": manifest_path,
                "evidencePath": self.paths.evidence_state(key),
                "evidenceCount": len(evidence_state["chunks"]),
                "assets": manifest.as_dict()["assets"],
                "counts": manifest.counts,
            }
        except Exception as exc:
            _remove_staging(self.paths, transaction.transaction_id)
            return self._record_failure(transaction, key, state, stage, exc)

    def parse_batch(
        self,
        zotero_keys: list[str],
        *,
        dry_run: bool = False,
        transaction_id: str | None = None,
        conflict_policy: str = "preserve-user",
    ) -> dict[str, Any]:
        keys = list(dict.fromkeys(validate_zotero_key(key) for key in zotero_keys))
        results: list[dict[str, Any]] = []
        workers = min(max(1, int(self.config["mineru"]["maxConcurrentJobs"])), max(1, len(keys)))

        def run(index: int, key: str) -> dict[str, Any]:
            child_id = f"{transaction_id[:120]}-{index + 1:04d}" if transaction_id else None
            return self.parse(key, dry_run=dry_run, transaction_id=child_id, conflict_policy=conflict_policy)

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(run, index, key): key for index, key in enumerate(keys)}
            for future in as_completed(futures):
                key = futures[future]
                try:
                    results.append(future.result())
                except Exception as exc:
                    results.append({"ok": False, "zoteroKey": key, "error": str(exc)})
        results.sort(key=lambda result: keys.index(str(result.get("zoteroKey") or "")))
        return {
            "ok": all(result.get("ok") for result in results),
            "total": len(keys),
            "succeeded": sum(bool(result.get("ok")) for result in results),
            "failed": sum(not bool(result.get("ok")) for result in results),
            "results": results[:20],
            "truncated": len(results) > 20,
            "nextCursor": "20" if len(results) > 20 else None,
        }

    def remove_output(
        self,
        zotero_key: str,
        *,
        dry_run: bool = False,
        transaction_id: str | None = None,
        conflict_policy: str = "preserve-user",
    ) -> dict[str, Any]:
        del conflict_policy
        key = validate_zotero_key(zotero_key)
        state = self._state(key)
        note_path = str(state.get("notePath") or "")
        mineru_path = str(state.get("mineruPath") or self.paths.mineru_markdown(key, firstAuthor="", year="", shortTitle=key))
        manifest = self._image_manifest(key)
        owned_images = self._owned_formal_images(key, mineru_path, manifest)
        transaction = self.transactions.begin(item_key=key, transaction_id=transaction_id, dry_run=dry_run)
        if self.fs.exists(mineru_path):
            transaction.delete(mineru_path)
        for old_path in sorted(owned_images):
            if self.fs.exists(old_path):
                transaction.delete(old_path)
        manifest_path = self.paths.image_manifest(key)
        current_asset_root = PurePosixPath(manifest_path).parent.as_posix()
        asset_roots = {
            current_asset_root,
            self._previous_asset_root(state, key, current_asset_root),
        }
        owned_asset_files = {
            old_path
            for asset_root in asset_roots
            for old_path in self.fs.list_files(asset_root)
        }
        for old_path in sorted(owned_asset_files):
            transaction.delete(old_path)
        evidence_path = self.paths.evidence_state(key)
        if self.fs.exists(evidence_path):
            transaction.delete(evidence_path)

        overlay: dict[str, Any] | None = None
        if note_path and self.fs.exists(note_path):
            document = parse_frontmatter(self.fs.read_text(note_path))
            merged = merge_frontmatter(
                document.fields,
                {"attachmentMinerULink": ""},
                omit_empty=True,
                preserve_unknown_fields=True,
                field_order=self.config["frontmatter"]["fieldOrder"],
            )
            body = replace_managed_section(document.body, "mineru", "MinerU", "")
            transaction.write_text(note_path, compose_frontmatter(merged, body, field_order=self.config["frontmatter"]["fieldOrder"]))
            overlay = dict(merged)
            overlay.update(notePath=note_path, lastImportedAt=state.get("lastImportedAt") or "")
        next_state = dict(state)
        next_state.update(
            mineruPath=None,
            mineruAssetRoot=None,
            mineruSourceSha256=None,
            lastMineruAt=None,
            lastTransactionId=transaction.transaction_id,
            status="ready",
            errors=[],
        )
        self._add_state_if_changed(transaction, key, next_state)
        if overlay is not None and self.config["index"]["autoRebuild"]:
            index = IndexService(self.vault_path, self.config)
            transaction.write_text(index.index_path, index.render([overlay]))
        if dry_run:
            result = transaction.commit()
        elif overlay is not None and self.config["index"]["autoRebuild"]:
            with GlobalLock(self.vault_path, "index"):
                result = transaction.commit()
        else:
            result = transaction.commit()
        return {
            **result,
            "zoteroKey": key,
            "mineruPath": mineru_path,
            "manifestPath": manifest_path,
            "evidencePath": evidence_path,
        }

    def _state(self, key: str) -> dict[str, Any]:
        path = self.paths.state(key)
        if not self.fs.exists(path):
            raise FileNotFoundError(f"item state does not exist for {key}")
        value = json.loads(self.fs.read_text(path))
        if not isinstance(value, dict) or value.get("zoteroKey") != key:
            raise ValueError(f"item state identity mismatch for {key}")
        return value

    def _add_state_if_changed(self, transaction: Transaction, key: str, state: dict[str, Any]) -> None:
        path = self.paths.state(key)
        ordered = {
            name: state[name]
            for name in _STATE_FIELD_ORDER
            if name in state and state[name] is not None
        }
        ordered.update(
            (name, value)
            for name, value in state.items()
            if name not in ordered and value is not None
        )
        text = json.dumps(ordered, ensure_ascii=False, indent=2) + "\n"
        if not self.fs.exists(path) or self.fs.read_text(path) != text:
            transaction.write_text(path, text)

    def _image_manifest(self, key: str) -> ImageAssetManifest | None:
        return self._image_manifest_path(self.paths.image_manifest(key))

    def _image_manifest_path(self, path: str) -> ImageAssetManifest | None:
        if not self.fs.exists(path):
            return None
        try:
            return parse_image_manifest(self.fs.read_text(path))
        except (OSError, UnicodeError, ValueError):
            return None

    def _previous_asset_root(self, state: dict[str, Any], key: str, current_root: str) -> str:
        raw = state.get("mineruAssetRoot")
        if isinstance(raw, str) and raw:
            previous = normalize_vault_relative(raw)
            if PurePosixPath(previous).name != key:
                raise ValueError("item state mineruAssetRoot identity mismatch")
            return previous
        legacy = f".obsidian-vault-mcp/cache/mineru-assets/{key}"
        if legacy != current_root and self.fs.list_files(legacy):
            return legacy
        return current_root

    def _owned_formal_images(
        self,
        key: str,
        mineru_path: str,
        manifest: ImageAssetManifest | None,
    ) -> set[str]:
        del key
        image_folder = normalize_vault_relative(str(self.config["mineru"]["imageFolder"]))
        owned: set[str] = set()
        if manifest is not None:
            for asset in manifest.assets:
                if asset.status == "referenced" and asset.normalized_path and _inside_folder(asset.normalized_path, image_folder):
                    owned.add(asset.normalized_path)
        if self.fs.exists(mineru_path):
            try:
                markdown = self.fs.read_text(mineru_path)
            except (OSError, UnicodeError):
                return owned
            for reference in parse_image_references(markdown):
                raw_path, _suffix = parse_image_destination(reference.destination)
                target = _resolve_markdown_image_path(mineru_path, raw_path)
                if target and _inside_folder(target, image_folder):
                    owned.add(target)
        return owned

    def _record_failure(self, transaction: Transaction, key: str, state: dict[str, Any], stage: str, exc: Exception) -> dict[str, Any]:
        failed = dict(state)
        errors = list(failed.get("errors") or [])
        errors.append({"stage": stage, "message": str(exc), "at": ItemState.utc_now()})
        failed.update(status="error", errors=errors[-20:], lastTransactionId=transaction.transaction_id)
        # Never reuse a transaction that may already contain formal output.
        # A fresh transaction records only the failure state, so partial MinerU
        # files cannot leak from an unsuccessful attempt.
        failure_transaction = self.transactions.begin(item_key=key)
        self._add_state_if_changed(failure_transaction, key, failed)
        state_result = failure_transaction.commit()
        return {
            "ok": False,
            "status": "failed",
            "transactionId": transaction.transaction_id,
            "zoteroKey": key,
            "stage": stage,
            "error": str(exc),
            "stateTransaction": state_result,
        }


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _finalize_manifest(
    manifest: ImageAssetManifest,
    previous: ImageAssetManifest | None,
) -> ImageAssetManifest:
    if previous is not None:
        current_value = manifest.as_dict()
        previous_value = previous.as_dict()
        current_value["generatedAt"] = ""
        previous_value["generatedAt"] = ""
        if current_value == previous_value:
            return manifest.with_generated_at(previous.generated_at)
    return manifest.with_generated_at(ItemState.utc_now())


def _merge_manifest_relationships(
    manifest: ImageAssetManifest,
    previous: ImageAssetManifest | None,
) -> ImageAssetManifest:
    if previous is None:
        return manifest
    previous_by_id = {asset.asset_id: asset for asset in previous.assets}
    assets = []
    for asset in manifest.assets:
        old = previous_by_id.get(asset.asset_id)
        if old is None:
            assets.append(asset)
            continue
        visual_status = old.visual_status if old.visual_status in {"pdf_crop_available", "visual_verified"} else asset.visual_status
        assets.append(
            replace(
                asset,
                figure_label=old.figure_label,
                page=old.page,
                visual_status=visual_status,
                pdf_crop_path=old.pdf_crop_path,
            )
        )
    return replace(manifest, assets=tuple(assets))


def _apply_candidate_policy(manifest: ImageAssetManifest, *, preserve: bool) -> ImageAssetManifest:
    if preserve:
        return manifest
    return replace(manifest, assets=tuple(asset for asset in manifest.assets if asset.status != "unlinked_candidate"))


def _apply_evidence_relationships(
    manifest: ImageAssetManifest,
    relationships: Any,
) -> ImageAssetManifest:
    values = relationships if isinstance(relationships, dict) else {}
    assets = []
    for asset in manifest.assets:
        relation = values.get(asset.asset_id, {})
        captions = sorted(set(str(value) for value in relation.get("captionEvidenceIds", []))) if isinstance(relation, dict) else []
        contexts = sorted(set(str(value) for value in relation.get("contextEvidenceIds", []))) if isinstance(relation, dict) else []
        assets.append(
            replace(
                asset,
                caption_evidence_id=captions[0] if captions else None,
                context_evidence_ids=tuple(contexts),
            )
        )
    return replace(manifest, assets=tuple(assets))


def _resolve_markdown_image_path(markdown_path: str, raw_path: str) -> str | None:
    value = raw_path.strip().replace("\\", "/")
    if (
        not value
        or value.startswith("/")
        or re.match(r"^[A-Za-z]:/", value)
        or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", value)
    ):
        return None
    parent = PurePosixPath(markdown_path.replace("\\", "/")).parent.as_posix()
    candidate = posixpath.normpath(posixpath.join(parent, value))
    if candidate in {"", ".", ".."} or candidate.startswith("../"):
        return None
    try:
        return normalize_vault_relative(candidate)
    except ValueError:
        return None


def _inside_folder(path: str, folder: str) -> bool:
    return path == folder or path.startswith(f"{folder}/")


def _without_md(path: str) -> str:
    return path[:-3] if path.lower().endswith(".md") else path


def _remove_staging(paths: VaultPaths, transaction_id: str) -> None:
    target = paths.resolve(paths.staging(transaction_id))
    staging_root = paths.resolve(f"{paths.internal_root}/staging")
    try:
        target.relative_to(staging_root)
    except ValueError as exc:
        raise RuntimeError("refusing to clean an invalid MinerU staging path") from exc
    if target.is_dir():
        shutil.rmtree(target)
