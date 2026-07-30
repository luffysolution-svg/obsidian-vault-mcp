"""Staged, backed-up, atomic Vault transactions with rollback."""

from __future__ import annotations

import difflib
import hashlib
import json
import os
import stat
import uuid
from collections.abc import Callable, Iterator, Sequence
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from ..adapters.vault.filesystem import VaultFilesystem, VaultPathSafetyError
from ..adapters.vault.lock import ItemLock, TargetLock
from ..domain.errors import TransactionConflictError, TransactionError, TransactionRollbackError
from ..domain.identity import validate_zotero_key
from ..domain.models import ChangeAction, FileChange
from ..domain.paths import VaultPaths, normalize_vault_relative, validate_transaction_id

OperationKind = Literal["write", "copy", "delete"]


@dataclass(frozen=True)
class _Operation:
    kind: OperationKind
    path: str
    data: bytes | None = None
    source: Path | None = None
    source_relative: str | None = None
    source_sha256: str | None = None
    source_size: int = 0
    before_sha256: str | None = None
    before_size: int = 0
    text: bool = False


class Transaction:
    """A mutable transaction plan; formal files change only at ``commit``."""

    def __init__(
        self,
        service: "TransactionService",
        transaction_id: str,
        *,
        item_key: str | None,
        dry_run: bool,
    ) -> None:
        self.service = service
        self.transaction_id = transaction_id
        self.item_key = item_key
        self.dry_run = dry_run
        self._operations: list[_Operation] = []
        self._destinations: set[str] = set()
        self._guards: list[Callable[[], None]] = []
        self._finished = False

    def write_text(self, path: str, text: str) -> "Transaction":
        if not isinstance(text, str):
            raise TypeError("transaction text must be a string")
        return self.write_bytes(path, text.encode("utf-8"), _text=True)

    def write_bytes(self, path: str, data: bytes, *, _text: bool = False) -> "Transaction":
        if not isinstance(data, bytes):
            raise TypeError("transaction bytes must be bytes")
        self._add(_Operation("write", normalize_vault_relative(path), data=data, text=_text))
        return self

    def copy(self, source: str | os.PathLike[str], path: str) -> "Transaction":
        (
            source_path,
            source_relative,
            source_sha256,
            source_size,
        ) = self.service._plan_copy_source(source, identifier=self.transaction_id)
        self._add(
            _Operation(
                "copy",
                normalize_vault_relative(path),
                source=source_path,
                source_relative=source_relative,
                source_sha256=source_sha256,
                source_size=source_size,
            )
        )
        return self

    def delete(self, path: str) -> "Transaction":
        self._add(_Operation("delete", normalize_vault_relative(path)))
        return self

    stage_text = write_text
    stage_bytes = write_bytes
    stage_copy = copy
    stage_delete = delete
    add_text = write_text
    add_bytes = write_bytes
    add_copy = copy
    add_delete = delete

    def guard(self, callback: Callable[[], None]) -> "Transaction":
        """Register a last-moment check executed with all coordination locks held."""

        if self._finished:
            raise TransactionConflictError(
                "cannot add a guard to a finished transaction",
                transaction_id=self.transaction_id,
                stage="plan",
            )
        if not callable(callback):
            raise TypeError("transaction guard must be callable")
        self._guards.append(callback)
        return self

    def preview(self) -> dict[str, Any]:
        return self.service._preview(self)

    def commit(self) -> dict[str, Any]:
        if self._finished:
            raise TransactionConflictError(
                "transaction object has already finished",
                transaction_id=self.transaction_id,
                stage="commit",
            )
        result = self.service._commit(self)
        self._finished = True
        return result

    def _add(self, operation: _Operation) -> None:
        if self._finished:
            raise TransactionConflictError(
                "cannot add an operation to a finished transaction",
                transaction_id=self.transaction_id,
                stage="plan",
            )
        destination_key = operation.path.casefold()
        if destination_key in self._destinations:
            raise TransactionConflictError(
                f"duplicate transaction destination: {operation.path}",
                transaction_id=self.transaction_id,
                stage="plan",
            )
        protected = (
            f"{self.service.paths.internal_root}/staging",
            f"{self.service.paths.internal_root}/backups",
            f"{self.service.paths.internal_root}/locks",
        )
        if any(operation.path == root or operation.path.startswith(f"{root}/") for root in protected):
            raise TransactionConflictError(
                f"transaction destination is reserved for internal coordination: {operation.path}",
                transaction_id=self.transaction_id,
                stage="plan",
            )
        operation = self.service._bind_destination_baseline(
            operation,
            identifier=self.transaction_id,
        )
        self._destinations.add(destination_key)
        self._operations.append(operation)


class TransactionService:
    def __init__(self, vault_root: str | os.PathLike[str], *, lock_timeout: float = 10.0) -> None:
        self.paths = VaultPaths(vault_root)
        if not self.paths.root.is_dir():
            raise NotADirectoryError(f"Vault root is not a directory: {self.paths.root}")
        self.fs = VaultFilesystem(self.paths.root)
        self.lock_timeout = lock_timeout

    def begin(
        self,
        *,
        item_key: str | None = None,
        transaction_id: str | None = None,
        dry_run: bool = False,
    ) -> Transaction:
        identifier = validate_transaction_id(transaction_id) if transaction_id else _new_transaction_id()
        validated_key = validate_zotero_key(item_key) if item_key is not None else None
        return Transaction(self, identifier, item_key=validated_key, dry_run=dry_run)

    transaction = begin

    def _plan_copy_source(
        self,
        source: str | os.PathLike[str],
        *,
        identifier: str,
    ) -> tuple[Path, str | None, str, int]:
        """Bind a copy source without resolving a Vault-internal link."""

        requested = Path(source).expanduser()
        lexical = Path(os.path.abspath(os.fspath(requested)))
        try:
            owned_relative = self._owned_source_relative(lexical)
        except (TypeError, ValueError):
            owned_relative = None
        if owned_relative is not None:
            try:
                snapshot = _owned_file_snapshot(self.fs, owned_relative)
            except (OSError, VaultPathSafetyError) as exc:
                raise TransactionConflictError(
                    f"transaction copy source is unsafe: {owned_relative}",
                    transaction_id=identifier,
                    stage="plan",
                ) from exc
            if snapshot is None:
                raise FileNotFoundError(
                    f"transaction copy source is not a file: {lexical}"
                )
            return lexical, owned_relative, snapshot[0], snapshot[1]

        try:
            resolved = lexical.resolve(strict=True)
            source_sha256, source_size = _path_file_snapshot(resolved)
        except (OSError, ValueError) as exc:
            raise FileNotFoundError(
                f"transaction copy source is not a file: {lexical}"
            ) from exc
        return resolved, None, source_sha256, source_size

    def _bind_destination_baseline(
        self,
        operation: _Operation,
        *,
        identifier: str,
    ) -> _Operation:
        """Capture the destination state that this operation may replace."""

        self._operation_target(
            operation.path,
            identifier=identifier,
            stage="plan",
        )
        try:
            snapshot = _owned_file_snapshot(self.fs, operation.path)
        except (OSError, VaultPathSafetyError) as exc:
            raise TransactionConflictError(
                f"transaction destination is not a file: {operation.path}",
                transaction_id=identifier,
                stage="plan",
            ) from exc
        return replace(
            operation,
            before_sha256=snapshot[0] if snapshot is not None else None,
            before_size=snapshot[1] if snapshot is not None else 0,
        )

    def _copy_source_snapshot(
        self,
        operation: _Operation,
    ) -> tuple[str, int]:
        source = operation.source
        if source is None:
            raise TransactionError(
                f"copy operation has no source: {operation.path}",
                stage="staging",
            )
        if operation.source_relative is not None:
            snapshot = _owned_file_snapshot(
                self.fs,
                operation.source_relative,
            )
            if snapshot is None:
                raise FileNotFoundError(
                    f"transaction copy source is missing: {operation.source_relative}"
                )
            return snapshot[0], snapshot[1]
        return _path_file_snapshot(source)

    def preview(self, transaction: Transaction) -> dict[str, Any]:
        return self._preview(transaction)

    def preview_committed(self, transaction_id: str) -> dict[str, Any]:
        """Return the safe manifest for a committed transaction."""

        identifier = validate_transaction_id(transaction_id)
        manifest_relative = self.paths.manifest(identifier)
        manifest_path = self._internal_path(
            manifest_relative,
            identifier=identifier,
            stage="preview",
        )
        if not manifest_path.is_file():
            raise FileNotFoundError(f"transaction manifest does not exist: {identifier}")
        try:
            manifest = json.loads(self.fs.read_text_owned(manifest_relative))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise TransactionError(
                f"could not read transaction manifest: {exc}",
                transaction_id=identifier,
                stage="preview",
            ) from exc
        if not isinstance(manifest, dict) or manifest.get("transactionId") != identifier:
            raise TransactionError(
                "transaction manifest identity mismatch",
                transaction_id=identifier,
                stage="preview",
            )
        return {
            "ok": True,
            "manifestPath": self.paths.manifest(identifier),
            "transaction": manifest,
        }

    def commit(self, transaction: Transaction) -> dict[str, Any]:
        return transaction.commit()

    def rollback(
        self,
        transaction_id: str,
        *,
        dry_run: bool = False,
        conflict_policy: str = "preserve-user",
    ) -> dict[str, Any]:
        identifier = validate_transaction_id(transaction_id)
        if conflict_policy not in {"preserve-user", "overwrite-managed", "fail", "rename"}:
            raise ValueError(f"unsupported conflict policy: {conflict_policy}")
        manifest_relative = self.paths.manifest(identifier)
        manifest_path = self._internal_path(
            manifest_relative,
            identifier=identifier,
            stage="rollback",
            rollback=True,
        )
        if not manifest_path.is_file():
            raise TransactionRollbackError(
                f"transaction manifest does not exist: {identifier}",
                transaction_id=identifier,
                stage="rollback",
            )
        try:
            manifest = json.loads(self.fs.read_text_owned(manifest_relative))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise TransactionRollbackError(
                f"could not read transaction manifest: {exc}",
                transaction_id=identifier,
                stage="rollback",
            ) from exc
        if manifest.get("transactionId") != identifier:
            raise TransactionRollbackError(
                "transaction manifest identity mismatch",
                transaction_id=identifier,
                stage="rollback",
            )
        if manifest.get("status") == "rolled-back":
            return {"ok": True, "transactionId": identifier, "status": "already-rolled-back", "changes": []}

        entries = manifest.get("operations", [])
        if not isinstance(entries, list):
            raise TransactionRollbackError(
                "transaction manifest operations must be an array",
                transaction_id=identifier,
                stage="rollback",
            )
        entries = self._validated_rollback_entries(identifier, entries)
        if dry_run:
            conflicts = self._rollback_conflicts(entries)
            return {
                "ok": not conflicts or conflict_policy == "overwrite-managed",
                "transactionId": identifier,
                "status": "conflict" if conflicts and conflict_policy != "overwrite-managed" else "dry-run",
                "dryRun": True,
                "conflictPolicy": conflict_policy,
                "conflicts": conflicts,
                "changeCount": len(entries),
            }

        item_key = manifest.get("itemKey")
        try:
            with self._operation_locks(
                item_key=item_key,
                target_paths=[entry["path"] for entry in entries],
            ):
                conflicts = self._rollback_conflicts(entries)
                if conflicts and conflict_policy != "overwrite-managed":
                    raise TransactionConflictError(
                        "rollback would overwrite files changed after the transaction",
                        transaction_id=identifier,
                        stage="rollback-conflict",
                        details={
                            "conflictPolicy": conflict_policy,
                            "conflicts": conflicts,
                        },
                    )
                changes = self._restore_entries(
                    identifier,
                    entries,
                    overwrite_changed=conflict_policy == "overwrite-managed",
                )
                manifest["status"] = "rolled-back"
                manifest["rolledBackAt"] = _utc_now()
                self._write_manifest(identifier, manifest)
            return {"ok": True, "transactionId": identifier, "status": "rolled-back", "changes": changes}
        except Exception as exc:
            if isinstance(exc, (TransactionConflictError, TransactionRollbackError)):
                raise
            raise TransactionRollbackError(
                f"rollback failed: {exc}",
                transaction_id=identifier,
                stage="rollback",
            ) from exc

    rollback_transaction = rollback

    def _validated_rollback_entries(
        self,
        identifier: str,
        entries: list[Any],
    ) -> list[dict[str, Any]]:
        """Validate every manifest path before rollback can read or write files."""

        validated: list[dict[str, Any]] = []
        seen: set[str] = set()
        for entry in entries:
            if not isinstance(entry, dict):
                raise TransactionRollbackError(
                    "transaction manifest contains a non-object operation",
                    transaction_id=identifier,
                    stage="rollback",
                )
            raw_path = entry.get("path")
            try:
                path = normalize_vault_relative(raw_path)
            except (TypeError, ValueError) as exc:
                raise TransactionRollbackError(
                    "transaction manifest contains an invalid operation path",
                    transaction_id=identifier,
                    stage="rollback",
                ) from exc
            if raw_path != path or path.casefold() in seen:
                raise TransactionRollbackError(
                    "transaction manifest contains a non-canonical or duplicate operation path",
                    transaction_id=identifier,
                    stage="rollback",
                )
            seen.add(path.casefold())

            kind = entry.get("kind")
            if kind not in {"write", "copy", "delete"} or type(entry.get("existed")) is not bool:
                raise TransactionRollbackError(
                    f"transaction manifest operation is invalid: {path}",
                    transaction_id=identifier,
                    stage="rollback",
                )
            expected_backup = f"files/{path}" if entry["existed"] else None
            if entry.get("backupPath") != expected_backup:
                raise TransactionRollbackError(
                    f"transaction manifest backup path is invalid: {path}",
                    transaction_id=identifier,
                    stage="rollback",
                )
            expected_staged = f"transaction-files/{path}" if kind != "delete" else None
            if entry.get("stagedPath") != expected_staged:
                raise TransactionRollbackError(
                    f"transaction manifest staging path is invalid: {path}",
                    transaction_id=identifier,
                    stage="rollback",
                )
            self._operation_target(
                path,
                identifier=identifier,
                stage="rollback",
                rollback=True,
            )
            validated_entry = dict(entry)
            if validated_entry["existed"]:
                self._validated_backup_file(identifier, validated_entry)
            validated.append(validated_entry)
        return validated

    def _validated_backup_file(
        self,
        identifier: str,
        entry: dict[str, Any],
    ) -> str:
        backup_relative = entry.get("backupPath")
        if not isinstance(backup_relative, str):
            raise TransactionRollbackError(
                "manifest is missing a backup path",
                transaction_id=identifier,
            )
        owned_backup = normalize_vault_relative(
            f"{self.paths.backup(identifier)}/{backup_relative}"
        )
        try:
            backup = self.fs.owned_path(owned_backup)
        except (VaultPathSafetyError, OSError, ValueError) as exc:
            raise TransactionRollbackError(
                f"backup path escapes its transaction: {entry['path']}",
                transaction_id=identifier,
            ) from exc
        if not backup.is_file():
            raise TransactionRollbackError(
                f"backup file is missing: {entry['path']}",
                transaction_id=identifier,
            )
        expected = entry.get("beforeSha256")
        try:
            actual = self.fs.sha256_owned(owned_backup)
        except (FileNotFoundError, VaultPathSafetyError, OSError) as exc:
            raise TransactionRollbackError(
                f"backup file is unsafe or unreadable: {entry['path']}",
                transaction_id=identifier,
            ) from exc
        if not isinstance(expected, str) or actual != expected:
            raise TransactionRollbackError(
                f"backup checksum mismatch: {entry['path']}",
                transaction_id=identifier,
            )
        return owned_backup

    def _rollback_conflicts(self, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        conflicts: list[dict[str, Any]] = []
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
                conflicts.append({"path": "", "reason": "invalid-manifest-entry"})
                continue
            self._operation_target(
                entry["path"],
                identifier=None,
                stage="rollback-conflict",
                rollback=True,
            )
            expected_after = entry.get("afterSha256")
            expected_before = (
                entry.get("beforeSha256")
                if entry.get("existed")
                else None
            )
            try:
                snapshot = _owned_file_snapshot(self.fs, entry["path"])
            except (OSError, VaultPathSafetyError):
                conflicts.append(
                    {
                        "path": entry["path"],
                        "reason": "destination-is-not-a-file",
                    }
                )
                continue
            actual = snapshot[0] if snapshot is not None else None
            if actual != expected_before and actual != expected_after:
                conflicts.append(
                    {
                        "path": entry["path"],
                        "reason": "changed-after-commit",
                        "expectedSha256": expected_after,
                        "beforeSha256": expected_before,
                        "actualSha256": actual,
                    }
                )
        return conflicts

    def _preview(self, transaction: Transaction) -> dict[str, Any]:
        changes = [
            self._preview_operation(
                operation,
                identifier=transaction.transaction_id,
            )
            for operation in transaction._operations
        ]
        changed = [change for change in changes if change.action is not ChangeAction.NOOP]
        return {
            "ok": True,
            "transactionId": transaction.transaction_id,
            "dryRun": transaction.dry_run,
            "changed": bool(changed),
            "changeCount": len(changed),
            "operations": [change.as_dict() for change in changes],
        }

    def _preview_operation(
        self,
        operation: _Operation,
        *,
        identifier: str,
    ) -> FileChange:
        self._operation_target(
            operation.path,
            identifier=None,
            stage="preview",
        )
        try:
            snapshot = _owned_file_snapshot(
                self.fs,
                operation.path,
                include_data=operation.text,
            )
        except (OSError, VaultPathSafetyError) as exc:
            raise TransactionConflictError(
                f"transaction destination is not a file: {operation.path}",
                stage="preview",
            ) from exc
        before_sha = snapshot[0] if snapshot is not None else None
        before_size = snapshot[1] if snapshot is not None else 0
        before = snapshot[2] if snapshot is not None else None
        if (
            before_sha != operation.before_sha256
            or before_size != operation.before_size
        ):
            raise TransactionConflictError(
                f"transaction destination changed after planning: {operation.path}",
                transaction_id=identifier,
                stage="preview",
            )
        if operation.kind == "copy" and operation.source is not None:
            try:
                source_sha256, source_size = self._copy_source_snapshot(
                    operation
                )
            except (OSError, VaultPathSafetyError) as exc:
                raise TransactionConflictError(
                    f"transaction copy source became unsafe: {operation.path}",
                    transaction_id=identifier,
                    stage="preview",
                ) from exc
            if (
                source_sha256 != operation.source_sha256
                or source_size != operation.source_size
            ):
                raise TransactionConflictError(
                    f"transaction copy source changed after planning: {operation.path}",
                    transaction_id=identifier,
                    stage="preview",
                )
            after_sha = operation.source_sha256
            after_size = operation.source_size
            before = after = None
        elif operation.kind == "write":
            after = operation.data or b""
            after_sha = _sha256(after)
            after_size = len(after)
        else:
            after = None
            after_sha = None
            after_size = 0
        if before_sha == after_sha and before_size == after_size:
            action = ChangeAction.NOOP
        elif operation.kind == "delete":
            action = ChangeAction.DELETE if before_sha is not None else ChangeAction.NOOP
        elif before_sha is None:
            action = ChangeAction.CREATE
        else:
            action = ChangeAction.REPLACE
        diff = _text_diff(before, after, operation.path) if operation.text and action is not ChangeAction.NOOP else None
        return FileChange(operation.path, action, before_sha, after_sha, after_size, diff)

    def _commit(self, transaction: Transaction) -> dict[str, Any]:
        if transaction.dry_run:
            preview = self._preview(transaction)
            return {**preview, "status": "dry-run"}
        identifier = transaction.transaction_id
        self._internal_path(
            f"{self.paths.internal_root}/locks",
            identifier=identifier,
            stage="prepare",
        )
        try:
            with self._operation_locks(
                item_key=transaction.item_key,
                target_paths=[operation.path for operation in transaction._operations],
            ):
                return self._commit_locked(transaction)
        except (TransactionConflictError, TransactionError):
            raise
        except Exception as exc:
            raise TransactionError(
                f"transaction failed before staging: {exc}",
                transaction_id=identifier,
                stage="prepare",
            ) from exc

    def _commit_locked(self, transaction: Transaction) -> dict[str, Any]:
        identifier = transaction.transaction_id
        staging_root = self._owned_staging_path(identifier, stage="prepare")
        transaction_files_root = staging_root / "transaction-files"
        backup_root = self._internal_path(
            self.paths.backup(identifier),
            identifier=identifier,
            stage="prepare",
        )
        self._internal_path(
            self.paths.manifest(identifier),
            identifier=identifier,
            stage="prepare",
        )
        if backup_root.exists() or transaction_files_root.exists():
            raise TransactionConflictError(
                f"transaction id already exists: {identifier}",
                transaction_id=identifier,
                stage="prepare",
            )
        for guard in transaction._guards:
            guard()

        # Preview and no-op selection happen while holding item and target locks
        # so another Agent cannot change a destination before backup.
        preview = self._preview(transaction)
        changed_paths = {
            entry["path"] for entry in preview["operations"] if entry["action"] != ChangeAction.NOOP.value
        }
        operations = [operation for operation in transaction._operations if operation.path in changed_paths]
        staged_paths = [
            self.paths.staging(
                identifier,
                f"transaction-files/{operation.path}",
            )
            for operation in operations
            if operation.kind != "delete"
        ]
        if not operations:
            cleanup_error = self._try_remove_owned_staging(
                identifier,
                staging_root,
                staged_paths,
            )
            result = {**preview, "status": "noop"}
            if cleanup_error:
                result["cleanupError"] = cleanup_error
            return result

        stage = "staging"
        manifest: dict[str, Any] | None = None
        owns_staging = False
        touched_entries: list[dict[str, Any]] = []
        try:
            # MinerU may already have raw output under this transaction's
            # staging root. Formal transaction files use a private child.
            owns_staging = True
            entries: list[dict[str, Any]] = []
            for operation in operations:
                self._operation_target(
                    operation.path,
                    identifier=identifier,
                    stage="staging",
                )
                staged_relative = f"transaction-files/{operation.path}"
                owned_staged = self.paths.staging(identifier, staged_relative)
                if operation.kind == "write":
                    self.fs.atomic_write_bytes_owned(
                        owned_staged,
                        operation.data or b"",
                    )
                elif operation.kind == "copy":
                    source = operation.source
                    if source is None:
                        raise TransactionError(
                            f"copy operation has no source: {operation.path}",
                            transaction_id=identifier,
                            stage="staging",
                        )
                    if operation.source_relative is not None:
                        with self.fs.open_binary_owned(
                            operation.source_relative
                        ) as stream:
                            self.fs.atomic_copy_stream_owned(owned_staged, stream)
                    else:
                        with source.open("rb") as stream:
                            self.fs.atomic_copy_stream_owned(owned_staged, stream)
                staged_snapshot = (
                    _owned_file_snapshot(self.fs, owned_staged)
                    if operation.kind != "delete"
                    else None
                )
                if operation.kind != "delete" and staged_snapshot is None:
                    raise TransactionError(
                        f"transaction staged file is missing: {operation.path}",
                        transaction_id=identifier,
                        stage="staging",
                    )
                if (
                    operation.kind == "copy"
                    and staged_snapshot is not None
                    and (
                        staged_snapshot[0] != operation.source_sha256
                        or staged_snapshot[1] != operation.source_size
                    )
                ):
                    raise TransactionConflictError(
                        f"transaction copy source changed after planning: {operation.path}",
                        transaction_id=identifier,
                        stage="staging",
                    )
                try:
                    snapshot = _owned_file_snapshot(self.fs, operation.path)
                except (OSError, VaultPathSafetyError) as exc:
                    raise TransactionConflictError(
                        f"transaction destination is not a file: {operation.path}",
                        transaction_id=identifier,
                        stage="staging",
                    ) from exc
                before_sha256 = snapshot[0] if snapshot is not None else None
                before_size = snapshot[1] if snapshot is not None else 0
                if (
                    before_sha256 != operation.before_sha256
                    or before_size != operation.before_size
                ):
                    raise TransactionConflictError(
                        f"transaction destination changed after planning: {operation.path}",
                        transaction_id=identifier,
                        stage="staging",
                    )
                existed = operation.before_sha256 is not None
                entries.append(
                    {
                        "kind": operation.kind,
                        "path": operation.path,
                        "existed": existed,
                        "beforeSha256": operation.before_sha256,
                        "afterSha256": (
                            staged_snapshot[0]
                            if staged_snapshot is not None
                            else None
                        ),
                        "stagedPath": staged_relative if operation.kind != "delete" else None,
                        "backupPath": f"files/{operation.path}" if existed else None,
                    }
                )

            stage = "backup"
            for entry in entries:
                if entry["existed"]:
                    self._operation_target(
                        entry["path"],
                        identifier=identifier,
                        stage="backup",
                    )
                    backup = normalize_vault_relative(
                        f"{self.paths.backup(identifier)}/{entry['backupPath']}"
                    )
                    self.fs.atomic_copy_owned(entry["path"], backup)
                    if self.fs.sha256_owned(backup) != entry["beforeSha256"]:
                        raise TransactionConflictError(
                            f"transaction backup changed while copying: {entry['path']}",
                            transaction_id=identifier,
                            stage="backup",
                        )

            stage = "manifest"
            manifest = {
                "schemaVersion": 2,
                "transactionId": identifier,
                "itemKey": transaction.item_key,
                "status": "prepared",
                "createdAt": _utc_now(),
                "operations": entries,
            }
            self._write_manifest(identifier, manifest)

            stage = "commit"
            for entry in entries:
                self._operation_target(
                    entry["path"],
                    identifier=identifier,
                    stage="commit",
                )
                if not self._matches_before_state(entry):
                    raise TransactionConflictError(
                        f"transaction destination changed before commit: {entry['path']}",
                        transaction_id=identifier,
                        stage="commit",
                    )
                # A failed atomic operation may still have changed its
                # destination, so include the current entry before attempting
                # the formal write.
                touched_entries.append(entry)
                if entry["kind"] == "delete":
                    self.fs.unlink_owned(entry["path"], missing_ok=True)
                else:
                    staged = self.paths.staging(identifier, entry["stagedPath"])
                    _replace_owned(self.fs, staged, entry["path"])
            manifest["status"] = "committed"
            manifest["committedAt"] = _utc_now()
            self._write_manifest(identifier, manifest)
        except BaseException as exc:
            recovery_changes: list[dict[str, str]] = []
            recovery_errors: list[dict[str, str]] = []
            manifest_error: str | None = None
            if manifest is not None:
                try:
                    recovery_changes = self._restore_entries(
                        identifier,
                        touched_entries,
                    )
                except TransactionRollbackError as restore_exc:
                    raw_failures = restore_exc.details.get("failures", [])
                    if isinstance(raw_failures, list):
                        recovery_errors = [
                            failure
                            for failure in raw_failures
                            if isinstance(failure, dict)
                            and all(
                                isinstance(failure.get(field), str)
                                for field in ("path", "errorType", "error")
                            )
                        ]
                    raw_changes = restore_exc.details.get("changes", [])
                    if isinstance(raw_changes, list):
                        recovery_changes = [
                            change
                            for change in raw_changes
                            if isinstance(change, dict)
                            and isinstance(change.get("path"), str)
                            and isinstance(change.get("action"), str)
                        ]
                    if not recovery_errors:
                        recovery_errors = [
                            {
                                "path": "",
                                "errorType": type(restore_exc).__name__,
                                "error": str(restore_exc),
                            }
                        ]
                except Exception as restore_exc:
                    recovery_errors = [
                        {
                            "path": "",
                            "errorType": type(restore_exc).__name__,
                            "error": str(restore_exc),
                        }
                    ]

                manifest["status"] = (
                    "failed-restore-incomplete"
                    if recovery_errors
                    else "failed-restored"
                )
                manifest["failedAt"] = _utc_now()
                manifest["failureStage"] = stage
                manifest["error"] = str(exc)
                manifest["touchedPaths"] = [
                    entry["path"] for entry in touched_entries
                ]
                if recovery_errors:
                    manifest["recoveryErrors"] = recovery_errors
                try:
                    self._write_manifest(identifier, manifest)
                except Exception as write_exc:
                    manifest_error = str(write_exc)
            cleanup_error = (
                self._try_remove_owned_staging(
                    identifier,
                    staging_root,
                    staged_paths,
                )
                if owns_staging
                else None
            )
            recovery_error = (
                "; ".join(
                    f"{failure['path']}: {failure['error']}"
                    for failure in recovery_errors
                )
                if recovery_errors
                else None
            )
            if (
                isinstance(exc, (KeyboardInterrupt, SystemExit))
                and not recovery_errors
                and manifest_error is None
            ):
                raise
            raise TransactionError(
                f"transaction failed during {stage}: {exc}",
                transaction_id=identifier,
                stage=stage,
                details={
                    "restored": manifest is None or not recovery_errors,
                    "recoveryError": recovery_error,
                    "recoveryErrors": recovery_errors,
                    "recoveryChanges": recovery_changes,
                    "touchedPaths": [
                        entry["path"] for entry in touched_entries
                    ],
                    "manifestError": manifest_error,
                    "cleanupError": cleanup_error,
                },
            ) from exc

        cleanup_error = self._try_remove_owned_staging(
            identifier,
            staging_root,
            staged_paths,
        )
        result = {
            "ok": True,
            "transactionId": identifier,
            "status": "committed",
            "changed": True,
            "changeCount": len(entries),
            "operations": [entry for entry in preview["operations"] if entry["path"] in changed_paths],
            "manifestPath": self.paths.manifest(identifier),
        }
        if cleanup_error:
            result["cleanupError"] = cleanup_error
        return result

    def _restore_entries(
        self,
        identifier: str,
        entries: list[dict[str, Any]],
        *,
        overwrite_changed: bool = False,
    ) -> list[dict[str, str]]:
        changes: list[dict[str, str]] = []
        failures: list[dict[str, str]] = []
        for entry in reversed(entries):
            try:
                self._operation_target(
                    entry["path"],
                    identifier=identifier,
                    stage="restore",
                    rollback=True,
                )
                action = "restored" if entry.get("existed") else "removed"
                actual_sha256 = self._current_state_sha256(entry["path"])
                before_sha256 = (
                    entry.get("beforeSha256")
                    if entry.get("existed")
                    else None
                )
                if actual_sha256 == before_sha256:
                    changes.append({"path": entry["path"], "action": action})
                    continue
                if (
                    actual_sha256 != entry.get("afterSha256")
                    and not overwrite_changed
                ):
                    raise TransactionRollbackError(
                        f"transaction destination changed after its write: {entry['path']}",
                        transaction_id=identifier,
                        stage="restore-conflict",
                    )
                if entry.get("existed"):
                    backup = self._validated_backup_file(identifier, entry)
                    self.fs.atomic_copy_owned(backup, entry["path"])
                else:
                    self.fs.unlink_owned(entry["path"], missing_ok=True)
                if not self._matches_before_state(entry):
                    raise TransactionRollbackError(
                        f"rollback verification failed: {entry['path']}",
                        transaction_id=identifier,
                        stage="restore",
                    )
                changes.append({"path": entry["path"], "action": action})
            except Exception as exc:
                failures.append(
                    {
                        "path": entry["path"],
                        "errorType": type(exc).__name__,
                        "error": str(exc),
                    }
                )
        if failures:
            summary = "; ".join(
                f"{failure['path']}: {failure['error']}"
                for failure in failures
            )
            raise TransactionRollbackError(
                f"rollback could not restore {len(failures)} path(s): {summary}",
                transaction_id=identifier,
                stage="restore",
                details={
                    "failures": failures,
                    "changes": changes,
                },
            )
        return changes

    def _matches_before_state(self, entry: dict[str, Any]) -> bool:
        actual_sha = self._current_state_sha256(entry["path"])
        expected_sha = entry.get("beforeSha256") if entry.get("existed") else None
        return actual_sha == expected_sha

    def _current_state_sha256(self, path: str) -> str | None:
        snapshot = _owned_file_snapshot(self.fs, path)
        return snapshot[0] if snapshot is not None else None

    def _owned_source_relative(self, source: Path) -> str | None:
        try:
            lexical = source.expanduser().absolute()
            relative = lexical.relative_to(self.paths.root).as_posix()
            return normalize_vault_relative(relative)
        except (OSError, TypeError, ValueError):
            return None

    def _write_manifest(self, identifier: str, value: dict[str, Any]) -> None:
        payload = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
        self.fs.atomic_write_bytes_owned(
            self.paths.manifest(identifier),
            payload.encode("utf-8"),
        )

    def _remove_staging(
        self,
        identifier: str,
        path: Path,
        staged_paths: Sequence[str],
    ) -> None:
        """Remove only the exact, validated staging directory for this id."""

        expected = self._owned_staging_path(identifier, stage="cleanup")
        if path != expected:
            raise TransactionError(
                "refusing to remove an unexpected staging path",
                transaction_id=identifier,
                stage="cleanup",
            )
        root_relative = self.paths.staging(identifier)
        directories = {
            normalize_vault_relative(
                f"{root_relative}/transaction-files"
            ),
            root_relative,
        }
        root_parts = Path(root_relative).parts
        for staged in staged_paths:
            self.fs.unlink_owned(staged, missing_ok=True)
            parent = Path(staged).parent
            while len(parent.parts) >= len(root_parts):
                directories.add(
                    normalize_vault_relative(parent.as_posix())
                )
                if len(parent.parts) == len(root_parts):
                    break
                parent = parent.parent
        for directory in sorted(
            directories,
            key=lambda value: (-len(Path(value).parts), value.casefold(), value),
        ):
            self.fs.rmdir_owned(directory, missing_ok=True)

    def _owned_staging_path(self, identifier: str, *, stage: str) -> Path:
        """Return the lexical transaction staging path without following links."""

        validated = validate_transaction_id(identifier)
        lexical_parent = self.paths.root / self.paths.internal_root / "staging"
        resolved_parent = self.paths.resolve(f"{self.paths.internal_root}/staging")
        expected = lexical_parent / validated
        if (
            resolved_parent != lexical_parent
            or _is_link_or_reparse_point(lexical_parent)
            or _is_link_or_reparse_point(expected)
        ):
            raise TransactionError(
                "refusing to use a linked transaction staging path",
                transaction_id=validated,
                stage=stage,
            )
        return expected

    def _try_remove_owned_staging(
        self,
        identifier: str,
        path: Path,
        staged_paths: Sequence[str],
    ) -> str | None:
        try:
            self._remove_staging(identifier, path, staged_paths)
        except Exception as exc:
            return str(exc)
        return None

    def _operation_target(
        self,
        relative_path: str,
        *,
        identifier: str | None,
        stage: str,
        rollback: bool = False,
    ) -> Path:
        """Return a lexical formal destination after rejecting linked components."""

        try:
            return self.fs.owned_path(relative_path)
        except (VaultPathSafetyError, OSError, ValueError) as exc:
            error_type = (
                TransactionRollbackError if rollback else TransactionConflictError
            )
            raise error_type(
                (
                    "transaction destination contains an unsafe linked path "
                    f"(linked or reparse component): {relative_path}"
                ),
                transaction_id=identifier,
                stage=stage,
            ) from exc

    @contextmanager
    def _operation_locks(
        self,
        *,
        item_key: str | None,
        target_paths: Sequence[str],
    ) -> Iterator[None]:
        """Acquire item coordination first, then deterministic target locks."""

        targets: dict[str, str] = {}
        for path in target_paths:
            normalized = normalize_vault_relative(path)
            targets[normalized.casefold()] = normalized
        ordered_targets = sorted(
            targets.values(),
            key=lambda path: (path.casefold(), path),
        )
        with ExitStack() as locks:
            if item_key is not None:
                locks.enter_context(
                    ItemLock(
                        self.paths.root,
                        item_key,
                        timeout=self.lock_timeout,
                    )
                )
            for path in ordered_targets:
                locks.enter_context(
                    TargetLock(
                        self.paths.root,
                        path,
                        timeout=self.lock_timeout,
                    )
                )
            yield

    def _internal_path(
        self,
        relative_path: str,
        *,
        identifier: str,
        stage: str,
        rollback: bool = False,
    ) -> Path:
        """Return a lexical internal path after rejecting linked components."""

        try:
            return self.fs.owned_path(relative_path)
        except (VaultPathSafetyError, OSError, ValueError) as exc:
            error_type = TransactionRollbackError if rollback else TransactionError
            raise error_type(
                f"transaction internal path is unsafe: {relative_path}",
                transaction_id=identifier,
                stage=stage,
            ) from exc


def _new_transaction_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return f"{timestamp}-{uuid.uuid4().hex[:12]}"


def _is_link_or_reparse_point(path: Path) -> bool:
    """Detect POSIX symlinks and Windows junction/reparse-point directories."""

    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISLNK(metadata.st_mode) or bool(
        getattr(metadata, "st_file_attributes", 0) & 0x400
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256(data: bytes | None) -> str | None:
    return hashlib.sha256(data).hexdigest() if data is not None else None


def _path_file_snapshot(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _replace_owned(
    filesystem: VaultFilesystem,
    source_relative: str,
    destination_relative: str,
) -> Path:
    """Small fault-injection seam around the secure handle-relative replace."""

    return filesystem.atomic_replace_owned(source_relative, destination_relative)


def _owned_file_snapshot(
    filesystem: VaultFilesystem,
    relative_path: str,
    *,
    include_data: bool = False,
) -> tuple[str, int, bytes | None] | None:
    try:
        stream_context = filesystem.open_binary_owned(relative_path)
        with stream_context as stream:
            digest = hashlib.sha256()
            size = 0
            content = bytearray() if include_data else None
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
                size += len(chunk)
                if content is not None:
                    content.extend(chunk)
            return (
                digest.hexdigest(),
                size,
                bytes(content) if content is not None else None,
            )
    except FileNotFoundError:
        return None


def _text_diff(before: bytes | None, after: bytes | None, path: str) -> str | None:
    try:
        old = (before or b"").decode("utf-8")
        new = (after or b"").decode("utf-8")
    except UnicodeDecodeError:
        return None
    return "".join(
        difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
    )
