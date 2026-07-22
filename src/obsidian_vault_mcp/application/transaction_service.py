"""Staged, backed-up, atomic Vault transactions with rollback."""

from __future__ import annotations

import difflib
import hashlib
import json
import os
import shutil
import uuid
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from ..adapters.vault import atomic_writer
from ..adapters.vault.lock import ItemLock
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
        source_path = Path(source).expanduser().resolve()
        if not source_path.is_file():
            raise FileNotFoundError(f"transaction copy source is not a file: {source_path}")
        self._add(_Operation("copy", normalize_vault_relative(path), source=source_path))
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
            self.service.paths.staging(self.transaction_id),
            self.service.paths.backup(self.transaction_id),
            f"{self.service.paths.internal_root}/locks",
        )
        if any(operation.path == root or operation.path.startswith(f"{root}/") for root in protected):
            raise TransactionConflictError(
                f"transaction destination is reserved for internal coordination: {operation.path}",
                transaction_id=self.transaction_id,
                stage="plan",
            )
        self._destinations.add(destination_key)
        self._operations.append(operation)


class TransactionService:
    def __init__(self, vault_root: str | os.PathLike[str], *, lock_timeout: float = 10.0) -> None:
        self.paths = VaultPaths(vault_root)
        if not self.paths.root.is_dir():
            raise NotADirectoryError(f"Vault root is not a directory: {self.paths.root}")
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

    def preview(self, transaction: Transaction) -> dict[str, Any]:
        return self._preview(transaction)

    def preview_committed(self, transaction_id: str) -> dict[str, Any]:
        """Return the safe manifest for a committed transaction."""

        identifier = validate_transaction_id(transaction_id)
        manifest_path = self.paths.resolve(self.paths.manifest(identifier))
        if not manifest_path.is_file():
            raise FileNotFoundError(f"transaction manifest does not exist: {identifier}")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
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
        manifest_path = self.paths.resolve(self.paths.manifest(identifier))
        if not manifest_path.is_file():
            raise TransactionRollbackError(
                f"transaction manifest does not exist: {identifier}",
                transaction_id=identifier,
                stage="rollback",
            )
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
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
        conflicts = self._rollback_conflicts(entries)
        if dry_run:
            return {
                "ok": not conflicts or conflict_policy == "overwrite-managed",
                "transactionId": identifier,
                "status": "conflict" if conflicts and conflict_policy != "overwrite-managed" else "dry-run",
                "dryRun": True,
                "conflictPolicy": conflict_policy,
                "conflicts": conflicts,
                "changeCount": len(entries),
            }
        if conflicts and conflict_policy != "overwrite-managed":
            raise TransactionConflictError(
                "rollback would overwrite files changed after the transaction",
                transaction_id=identifier,
                stage="rollback-conflict",
                details={"conflictPolicy": conflict_policy, "conflicts": conflicts},
            )

        item_key = manifest.get("itemKey")
        lock = ItemLock(self.paths.root, item_key, timeout=self.lock_timeout) if item_key else nullcontext()
        try:
            with lock:
                changes = self._restore_entries(identifier, entries)
                manifest["status"] = "rolled-back"
                manifest["rolledBackAt"] = _utc_now()
                _write_json(manifest_path, manifest)
            return {"ok": True, "transactionId": identifier, "status": "rolled-back", "changes": changes}
        except Exception as exc:
            if isinstance(exc, TransactionRollbackError):
                raise
            raise TransactionRollbackError(
                f"rollback failed: {exc}",
                transaction_id=identifier,
                stage="rollback",
            ) from exc

    rollback_transaction = rollback

    def _rollback_conflicts(self, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        conflicts: list[dict[str, Any]] = []
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
                conflicts.append({"path": "", "reason": "invalid-manifest-entry"})
                continue
            target = self.paths.resolve(entry["path"])
            expected = entry.get("afterSha256")
            if target.exists() and not target.is_file():
                conflicts.append({"path": entry["path"], "reason": "destination-is-not-a-file"})
                continue
            actual = _hash_file(target) if target.is_file() else None
            if actual != expected:
                conflicts.append(
                    {
                        "path": entry["path"],
                        "reason": "changed-after-commit",
                        "expectedSha256": expected,
                        "actualSha256": actual,
                    }
                )
        return conflicts

    def _preview(self, transaction: Transaction) -> dict[str, Any]:
        changes = [self._preview_operation(operation) for operation in transaction._operations]
        changed = [change for change in changes if change.action is not ChangeAction.NOOP]
        return {
            "ok": True,
            "transactionId": transaction.transaction_id,
            "dryRun": transaction.dry_run,
            "changed": bool(changed),
            "changeCount": len(changed),
            "operations": [change.as_dict() for change in changes],
        }

    def _preview_operation(self, operation: _Operation) -> FileChange:
        target = self.paths.resolve(operation.path)
        if target.exists() and not target.is_file():
            raise TransactionConflictError(f"transaction destination is not a file: {operation.path}", stage="preview")
        before_sha = _hash_file(target) if target.is_file() else None
        before_size = target.stat().st_size if target.is_file() else 0
        if operation.kind == "copy" and operation.source is not None:
            after_sha = _hash_file(operation.source)
            after_size = operation.source.stat().st_size
            before = after = None
        elif operation.kind == "write":
            after = operation.data or b""
            after_sha = _sha256(after)
            after_size = len(after)
            before = target.read_bytes() if target.is_file() and operation.text else None
        else:
            after = None
            after_sha = None
            after_size = 0
            before = target.read_bytes() if target.is_file() and operation.text else None
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
        lock = ItemLock(self.paths.root, transaction.item_key, timeout=self.lock_timeout) if transaction.item_key else nullcontext()
        try:
            with lock:
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
        staging_root = self.paths.resolve(self.paths.staging(identifier))
        transaction_files_root = staging_root / "transaction-files"
        backup_root = self.paths.resolve(self.paths.backup(identifier))
        manifest_path = self.paths.resolve(self.paths.manifest(identifier))
        if backup_root.exists() or transaction_files_root.exists():
            raise TransactionConflictError(
                f"transaction id already exists: {identifier}",
                transaction_id=identifier,
                stage="prepare",
            )

        # Preview and no-op selection happen while holding the per-item lock so
        # another Agent cannot change the target between comparison and backup.
        preview = self._preview(transaction)
        changed_paths = {
            entry["path"] for entry in preview["operations"] if entry["action"] != ChangeAction.NOOP.value
        }
        operations = [operation for operation in transaction._operations if operation.path in changed_paths]
        if not operations:
            cleanup_error = self._try_remove_owned_staging(identifier, staging_root)
            result = {**preview, "status": "noop"}
            if cleanup_error:
                result["cleanupError"] = cleanup_error
            return result

        stage = "staging"
        manifest: dict[str, Any] | None = None
        owns_staging = False
        try:
            # MinerU may already have raw output under this transaction's
            # staging root. Formal transaction files use a private child.
            staging_root.mkdir(parents=True, exist_ok=True)
            transaction_files_root.mkdir()
            owns_staging = True
            entries: list[dict[str, Any]] = []
            for operation in operations:
                target = self.paths.resolve(operation.path)
                staged_relative = f"transaction-files/{operation.path}"
                staged = staging_root.joinpath(*Path(staged_relative).parts)
                if operation.kind == "write":
                    atomic_writer.atomic_write_bytes(staged, operation.data or b"")
                elif operation.kind == "copy":
                    atomic_writer.atomic_copy(operation.source or "", staged)
                existed = target.is_file()
                entries.append(
                    {
                        "kind": operation.kind,
                        "path": operation.path,
                        "existed": existed,
                        "beforeSha256": _hash_file(target) if existed else None,
                        "afterSha256": _hash_file(staged) if operation.kind != "delete" else None,
                        "stagedPath": staged_relative if operation.kind != "delete" else None,
                        "backupPath": f"files/{operation.path}" if existed else None,
                    }
                )

            stage = "backup"
            backup_root.mkdir(parents=True)
            for entry in entries:
                if entry["existed"]:
                    source = self.paths.resolve(entry["path"])
                    backup = backup_root.joinpath(*Path(entry["backupPath"]).parts)
                    atomic_writer.atomic_copy(source, backup)

            stage = "manifest"
            manifest = {
                "schemaVersion": 2,
                "transactionId": identifier,
                "itemKey": transaction.item_key,
                "status": "prepared",
                "createdAt": _utc_now(),
                "operations": entries,
            }
            _write_json(manifest_path, manifest)

            stage = "commit"
            for entry in entries:
                target = self.paths.resolve(entry["path"])
                if entry["kind"] == "delete":
                    target.unlink(missing_ok=True)
                else:
                    staged = staging_root.joinpath(*Path(entry["stagedPath"]).parts)
                    atomic_writer.atomic_replace(staged, target)
            manifest["status"] = "committed"
            manifest["committedAt"] = _utc_now()
            _write_json(manifest_path, manifest)
        except Exception as exc:
            recovery_error: str | None = None
            if manifest is not None:
                try:
                    self._restore_entries(identifier, manifest["operations"])
                    manifest["status"] = "failed-restored"
                    manifest["failedAt"] = _utc_now()
                    manifest["failureStage"] = stage
                    manifest["error"] = str(exc)
                    _write_json(manifest_path, manifest)
                except Exception as restore_exc:
                    recovery_error = str(restore_exc)
            cleanup_error = self._try_remove_owned_staging(identifier, staging_root) if owns_staging else None
            raise TransactionError(
                f"transaction failed during {stage}: {exc}",
                transaction_id=identifier,
                stage=stage,
                details={
                    "restored": manifest is None or recovery_error is None,
                    "recoveryError": recovery_error,
                    "cleanupError": cleanup_error,
                },
            ) from exc

        cleanup_error = self._try_remove_owned_staging(identifier, staging_root)
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

    def _restore_entries(self, identifier: str, entries: list[dict[str, Any]]) -> list[dict[str, str]]:
        backup_root = self.paths.resolve(self.paths.backup(identifier))
        changes: list[dict[str, str]] = []
        for entry in reversed(entries):
            target = self.paths.resolve(entry["path"])
            if entry.get("existed"):
                backup_relative = entry.get("backupPath")
                if not isinstance(backup_relative, str):
                    raise TransactionRollbackError("manifest is missing a backup path", transaction_id=identifier)
                backup = backup_root.joinpath(*Path(backup_relative).parts)
                if not backup.is_file():
                    raise TransactionRollbackError(f"backup file is missing: {entry['path']}", transaction_id=identifier)
                atomic_writer.atomic_copy(backup, target)
                changes.append({"path": entry["path"], "action": "restored"})
            else:
                if target.is_dir():
                    raise TransactionRollbackError(f"cannot remove directory during rollback: {entry['path']}")
                target.unlink(missing_ok=True)
                changes.append({"path": entry["path"], "action": "removed"})
        return changes

    def _remove_staging(self, identifier: str, path: Path) -> None:
        """Remove only the exact, validated staging directory for this id."""

        expected = self.paths.resolve(self.paths.staging(validate_transaction_id(identifier)))
        staging_parent = self.paths.resolve(f"{self.paths.internal_root}/staging")
        if path.resolve(strict=False) != expected or expected.parent != staging_parent:
            raise TransactionError(
                "refusing to remove an unexpected staging path",
                transaction_id=identifier,
                stage="cleanup",
            )
        if expected.exists():
            shutil.rmtree(expected)

    def _try_remove_owned_staging(self, identifier: str, path: Path) -> str | None:
        try:
            self._remove_staging(identifier, path)
        except Exception as exc:
            return str(exc)
        return None


def _new_transaction_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return f"{timestamp}-{uuid.uuid4().hex[:12]}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256(data: bytes | None) -> str | None:
    return hashlib.sha256(data).hexdigest() if data is not None else None


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def _write_json(path: Path, value: dict[str, Any]) -> None:
    atomic_writer.atomic_write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")
