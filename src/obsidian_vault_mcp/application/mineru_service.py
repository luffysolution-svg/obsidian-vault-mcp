from __future__ import annotations

import hashlib
import json
import os
import posixpath
import stat
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path, PurePosixPath
from typing import Any

from ..adapters.mineru.client import MinerUClient
from ..adapters.mineru.normalizer import normalize_mineru_output, relative_source_pdf
from ..adapters.obsidian.markdown_renderer import replace_managed_section
from ..adapters.vault.filesystem import VaultFilesystem
from ..adapters.vault.lock import GlobalLock
from ..config.loader import load_config
from ..domain.frontmatter import compose_frontmatter, merge_frontmatter, parse_frontmatter
from ..domain.identity import validate_zotero_key
from ..domain.models import ItemState
from ..domain.paths import (
    VaultPaths,
    naming_metadata_from_fields,
    normalize_vault_relative,
)
from .index_service import IndexService
from .transaction_service import Transaction, TransactionService

_STATE_FIELD_ORDER = (
    "schemaVersion",
    "zoteroKey",
    "zoteroVersion",
    "notePath",
    "pdfPath",
    "mineruPath",
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
        metadata = naming_metadata_from_fields(document.fields)
        mineru_path = str(
            state.get("mineruPath")
            or self.paths.mineru_markdown(key, **metadata)
        )
        transaction = self.transactions.begin(item_key=key, transaction_id=transaction_id, dry_run=dry_run)
        staging_rel = self.paths.staging(transaction.transaction_id, "mineru")
        if dry_run:
            preview = transaction.commit()
            return {
                **preview,
                "zoteroKey": key,
                "pdfPath": pdf_path,
                "mineruPath": mineru_path,
                "stagingPath": staging_rel,
                "planned": True,
            }

        stage = "extract"
        try:
            staging, _ = _scan_owned_directory(self.paths, staging_rel, "MinerU extraction staging")
            self.client.parse(
                self.paths.resolve(pdf_path),
                staging,
                mode=str(self.config["mineru"]["mode"]),
            )
            _scan_owned_directory(self.paths, staging_rel, "MinerU extraction staging")
            stage = "normalize"

            image_folder = self.paths.mineru_image_folder(key)
            markdown_folder = PurePosixPath(mineru_path.replace("\\", "/")).parent.as_posix()
            normalized = normalize_mineru_output(
                staging,
                zotero_key=key,
                title=title,
                source_pdf_path=relative_source_pdf(mineru_path, pdf_path),
                image_link_prefix=posixpath.relpath(image_folder, start=markdown_folder),
            )
            desired_images: set[str] = set()
            transaction.write_text(mineru_path, normalized.markdown)
            for image in normalized.images:
                image_path = f"{image_folder.rstrip('/')}/{image.filename}"
                desired_images.add(image_path)
                transaction.write_bytes(image_path, image.content)
            transaction.guard(
                lambda: _list_owned_files(
                    self.paths,
                    image_folder,
                    "MinerU item image folder",
                )
            )
            for old_path in _list_owned_files(self.paths, image_folder, "MinerU item image folder"):
                if old_path not in desired_images:
                    transaction.delete(old_path)

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

            stage = "cleanup"
            _remove_mineru_staging(self.paths, transaction.transaction_id)
            stage = "commit"
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
            }
        except Exception as exc:
            cleanup_error = _try_remove_staging(self.paths, transaction.transaction_id)
            return self._record_failure(transaction, key, state, stage, exc, cleanup_error=cleanup_error)

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
        document = (
            parse_frontmatter(self.fs.read_text(note_path))
            if note_path and self.fs.exists(note_path)
            else None
        )
        mineru_path = str(
            state.get("mineruPath")
            or self.paths.mineru_markdown(
                key,
                **naming_metadata_from_fields(
                    document.fields if document is not None else {"title": key}
                ),
            )
        )
        image_folder = self.paths.mineru_image_folder(key)
        old_images = _list_owned_files(self.paths, image_folder, "MinerU item image folder")
        transaction = self.transactions.begin(item_key=key, transaction_id=transaction_id, dry_run=dry_run)
        transaction.guard(
            lambda: _list_owned_files(
                self.paths,
                image_folder,
                "MinerU item image folder",
            )
        )
        if self.fs.exists(mineru_path):
            transaction.delete(mineru_path)
        for old_path in old_images:
            transaction.delete(old_path)

        overlay: dict[str, Any] | None = None
        if document is not None:
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
        next_state.update(mineruPath=None, mineruSourceSha256=None, lastMineruAt=None, lastTransactionId=transaction.transaction_id, status="ready", errors=[])
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
        return {**result, "zoteroKey": key, "mineruPath": mineru_path}

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

    def _record_failure(
        self,
        transaction: Transaction,
        key: str,
        state: dict[str, Any],
        stage: str,
        exc: Exception,
        *,
        cleanup_error: str | None = None,
    ) -> dict[str, Any]:
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
        result = {
            "ok": False,
            "status": "failed",
            "transactionId": transaction.transaction_id,
            "zoteroKey": key,
            "stage": stage,
            "error": str(exc),
            "stateTransaction": state_result,
        }
        if cleanup_error:
            result["cleanupError"] = cleanup_error
        return result


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _without_md(path: str) -> str:
    return path[:-3] if path.lower().endswith(".md") else path


def _remove_staging(paths: VaultPaths, transaction_id: str) -> None:
    staging_root = _lexical_vault_path(paths, f"{paths.internal_root}/staging", "MinerU staging root")
    relative = paths.staging(transaction_id)
    target = _lexical_vault_path(paths, relative, "MinerU transaction staging")
    if target.parent != staging_root:
        raise RuntimeError("refusing to clean a MinerU staging path without lexical transaction ownership")
    _remove_owned_directory(paths, relative, "MinerU transaction staging")


def _remove_mineru_staging(paths: VaultPaths, transaction_id: str) -> None:
    transaction_root = _lexical_vault_path(paths, paths.staging(transaction_id), "MinerU transaction staging")
    relative = paths.staging(transaction_id, "mineru")
    target = _lexical_vault_path(paths, relative, "MinerU extraction staging")
    if target.parent != transaction_root:
        raise RuntimeError("refusing to clean a MinerU extraction path without lexical transaction ownership")
    _remove_owned_directory(paths, relative, "MinerU extraction staging")


def _try_remove_staging(paths: VaultPaths, transaction_id: str) -> str | None:
    try:
        _remove_staging(paths, transaction_id)
    except Exception as exc:
        return str(exc)
    return None


def _list_owned_files(paths: VaultPaths, relative_path: str, label: str) -> list[str]:
    _, files = _scan_owned_directory(paths, relative_path, label)
    return sorted(
        normalize_vault_relative(path.relative_to(paths.root).as_posix())
        for path in files
    )


def _remove_owned_directory(paths: VaultPaths, relative_path: str, label: str) -> None:
    target, files, directories = _scan_owned_tree(paths, relative_path, label)
    if not target.exists():
        return
    filesystem = VaultFilesystem(paths.root)
    for file in files:
        filesystem.unlink_owned(
            normalize_vault_relative(file.relative_to(paths.root).as_posix()),
            missing_ok=True,
        )
    for directory in sorted(
        directories,
        key=lambda path: (
            -len(path.parts),
            path.as_posix().casefold(),
            path.as_posix(),
        ),
    ):
        filesystem.rmdir_owned(
            normalize_vault_relative(directory.relative_to(paths.root).as_posix()),
            missing_ok=True,
        )


def _scan_owned_directory(paths: VaultPaths, relative_path: str, label: str) -> tuple[Path, list[Path]]:
    target, files, _ = _scan_owned_tree(paths, relative_path, label)
    return target, files


def _scan_owned_tree(
    paths: VaultPaths,
    relative_path: str,
    label: str,
) -> tuple[Path, list[Path], list[Path]]:
    target = _lexical_vault_path(paths, relative_path, label)
    try:
        metadata = target.lstat()
    except FileNotFoundError:
        return target, [], []
    if _is_link_or_reparse(metadata):
        raise RuntimeError(f"refusing to use {label} with a linked or reparse root")
    if not stat.S_ISDIR(metadata.st_mode):
        raise RuntimeError(f"refusing to use {label} because it is not a directory")

    files: list[Path] = []
    directories = [target]
    pending = [target]
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                child_metadata = entry.stat(follow_symlinks=False)
                if _is_link_or_reparse(child_metadata):
                    raise RuntimeError(f"refusing to use {label} with a linked or reparse component: {entry.path}")
                child = Path(entry.path)
                if stat.S_ISDIR(child_metadata.st_mode):
                    directories.append(child)
                    pending.append(child)
                else:
                    files.append(child)
    return target, files, directories


def _lexical_vault_path(paths: VaultPaths, relative_path: str, label: str) -> Path:
    relative = normalize_vault_relative(relative_path)
    target = paths.root.joinpath(*PurePosixPath(relative).parts)
    try:
        parts = target.relative_to(paths.root).parts
    except ValueError as exc:
        raise RuntimeError(f"refusing to use {label} outside the Vault") from exc

    current = paths.root
    for index, part in enumerate(parts):
        current /= part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            continue
        if _is_link_or_reparse(metadata):
            raise RuntimeError(f"refusing to use {label} with a linked or reparse path component: {current}")
        if index < len(parts) - 1 and not stat.S_ISDIR(metadata.st_mode):
            raise RuntimeError(f"refusing to use {label} through a non-directory path component: {current}")
    return target


def _is_link_or_reparse(metadata: os.stat_result) -> bool:
    return stat.S_ISLNK(metadata.st_mode) or bool(
        getattr(metadata, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )
