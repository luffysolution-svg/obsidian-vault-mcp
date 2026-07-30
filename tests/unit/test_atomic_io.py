from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

import obsidian_vault_mcp.application.transaction_service as transaction_module
from obsidian_vault_mcp.adapters.vault import atomic_writer
from obsidian_vault_mcp.adapters.vault import filesystem as filesystem_module
from obsidian_vault_mcp.adapters.vault.atomic_writer import atomic_write_text
from obsidian_vault_mcp.adapters.vault.lock import ItemLock, TargetLock
from obsidian_vault_mcp.application.transaction_service import (
    Transaction,
    TransactionService,
)
from obsidian_vault_mcp.domain.errors import (
    AtomicWriteError,
    LockError,
    LockTimeoutError,
    TransactionConflictError,
    TransactionError,
    TransactionRollbackError,
)


def _create_directory_link(link: Path, target: Path) -> None:
    if os.name == "nt":
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            raise unittest.SkipTest(f"could not create a Windows junction: {result.stderr or result.stdout}")
        return
    link.symlink_to(target, target_is_directory=True)


def _remove_directory_link(link: Path) -> None:
    if os.name == "nt":
        os.rmdir(link)
    else:
        link.unlink(missing_ok=True)


class AtomicIoTests(unittest.TestCase):
    def test_item_lock_rejects_linked_lock_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            vault = Path(directory)
            target = vault / "private-locks"
            target.mkdir()
            linked = vault / ".obsidian-vault-mcp" / "locks"
            linked.parent.mkdir()
            _create_directory_link(linked, target)
            try:
                with self.assertRaisesRegex(
                    LockError,
                    "linked or reparse component",
                ):
                    ItemLock(vault, "ABCD1234", timeout=0).acquire()
                self.assertEqual(list(target.iterdir()), [])
            finally:
                _remove_directory_link(linked)

    def test_item_lock_parent_swap_after_validation_cannot_escape_vault(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            vault = root / "vault"
            locks = vault / ".obsidian-vault-mcp" / "locks"
            locks.mkdir(parents=True)
            saved_locks = vault / "saved-locks"
            outside = root / "outside"
            outside.mkdir()
            lock = ItemLock(vault, "ABCD1234", timeout=0)
            original_validate = lock._validate_safe_path
            validations = 0

            def validate_then_swap() -> None:
                nonlocal validations
                original_validate()
                validations += 1
                if validations == 2:
                    locks.rename(saved_locks)
                    _create_directory_link(locks, outside)

            try:
                with mock.patch.object(
                    lock,
                    "_validate_safe_path",
                    side_effect=validate_then_swap,
                ):
                    with self.assertRaisesRegex(
                        LockError,
                        "could not acquire lock",
                    ):
                        lock.acquire()
                self.assertFalse(lock.acquired)
                self.assertEqual(list(outside.iterdir()), [])
                self.assertEqual(list(saved_locks.iterdir()), [])
            finally:
                if locks.exists():
                    _remove_directory_link(locks)
                if saved_locks.exists():
                    saved_locks.rename(locks)

    def test_transaction_rejects_linked_formal_destination(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            vault = Path(directory)
            victim = vault / "Literature" / "victim"
            victim.mkdir(parents=True)
            marker = victim / "marker.md"
            marker.write_text("keep", encoding="utf-8")
            linked = vault / "Literature" / "alias"
            _create_directory_link(linked, victim)
            try:
                transaction = TransactionService(vault).begin(
                    transaction_id="linked-formal-target"
                )
                with self.assertRaisesRegex(
                    TransactionConflictError,
                    "unsafe linked path",
                ):
                    transaction.delete("Literature/alias/marker.md")
                    transaction.commit()
                self.assertEqual(marker.read_text(encoding="utf-8"), "keep")
            finally:
                _remove_directory_link(linked)

    @unittest.skipUnless(os.name == "nt", "Windows junction race regression")
    def test_commit_parent_swap_cannot_escape_vault(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            vault = root / "vault"
            literature = vault / "Literature"
            literature.mkdir(parents=True)
            note = literature / "note.md"
            note.write_text("before", encoding="utf-8")
            outside = root / "outside"
            outside.mkdir()
            outside_note = outside / "note.md"
            outside_note.write_text("outside-before", encoding="utf-8")
            saved = vault / "saved-Literature"
            service = TransactionService(vault)
            transaction = service.begin(transaction_id="junction-race")
            transaction.write_text("Literature/note.md", "managed")
            original_rename = filesystem_module._WindowsNative.rename
            injected = False

            def swap_parent_then_rename(
                native: object,
                handle: int,
                destination_parent: int,
                destination_name: str,
                *,
                expected_parent: Path,
                relative: str,
            ) -> None:
                nonlocal injected
                if relative == "Literature/note.md" and not injected:
                    injected = True
                    literature.rename(saved)
                    _create_directory_link(literature, outside)
                original_rename(
                    native,
                    handle,
                    destination_parent,
                    destination_name,
                    expected_parent=expected_parent,
                    relative=relative,
                )

            try:
                with mock.patch.object(
                    filesystem_module._WindowsNative,
                    "rename",
                    new=swap_parent_then_rename,
                ):
                    with self.assertRaisesRegex(
                        TransactionError,
                        "owned Vault parent moved",
                    ):
                        transaction.commit()
                self.assertTrue(injected)
                self.assertEqual(outside_note.read_text(encoding="utf-8"), "outside-before")
                self.assertEqual(
                    (saved / "note.md").read_text(encoding="utf-8"),
                    "before",
                )
            finally:
                if literature.exists():
                    _remove_directory_link(literature)

    @unittest.skipUnless(os.name == "nt", "Windows handle leak regression")
    def test_rejected_root_junction_does_not_leak_handles(self) -> None:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        get_current_process = kernel32.GetCurrentProcess
        get_current_process.restype = wintypes.HANDLE
        get_process_handle_count = kernel32.GetProcessHandleCount
        get_process_handle_count.argtypes = (
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.DWORD),
        )
        get_process_handle_count.restype = wintypes.BOOL

        def handle_count() -> int:
            count = wintypes.DWORD()
            self.assertTrue(
                get_process_handle_count(
                    get_current_process(),
                    ctypes.byref(count),
                )
            )
            return int(count.value)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            vault = root / "vault"
            vault.mkdir()
            service = TransactionService(vault)
            saved = root / "saved-vault"
            vault.rename(saved)
            outside = root / "outside"
            outside.mkdir()
            _create_directory_link(vault, outside)
            try:
                before = handle_count()
                for _ in range(50):
                    with self.assertRaisesRegex(
                        filesystem_module.VaultPathSafetyError,
                        "linked or non-directory",
                    ):
                        service.fs.read_bytes_owned("note.md")
                after = handle_count()
                self.assertLessEqual(after, before + 1)
            finally:
                _remove_directory_link(vault)

    def test_rollback_rejects_link_inserted_after_commit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            vault = Path(directory)
            item = vault / "Literature" / "item"
            item.mkdir(parents=True)
            note = item / "note.md"
            note.write_text("before", encoding="utf-8")
            service = TransactionService(vault)
            transaction = service.begin(transaction_id="linked-rollback-target")
            transaction.write_text("Literature/item/note.md", "managed")
            transaction.commit()

            saved = item.with_name("saved-item")
            item.rename(saved)
            victim = item.with_name("victim")
            victim.mkdir()
            victim_note = victim / "note.md"
            victim_note.write_text("managed", encoding="utf-8")
            _create_directory_link(item, victim)
            try:
                with self.assertRaisesRegex(
                    TransactionRollbackError,
                    "unsafe linked path",
                ):
                    service.rollback(
                        "linked-rollback-target",
                        conflict_policy="overwrite-managed",
                    )
                self.assertEqual(
                    victim_note.read_text(encoding="utf-8"),
                    "managed",
                )
            finally:
                _remove_directory_link(item)

    def test_keyboard_interrupt_restores_all_formal_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            vault = Path(directory)
            folder = vault / "Literature"
            folder.mkdir()
            first = folder / "first.md"
            second = folder / "second.md"
            first.write_text("before-first", encoding="utf-8")
            second.write_text("before-second", encoding="utf-8")
            service = TransactionService(vault)
            transaction = service.begin(transaction_id="cancelled-commit")
            transaction.write_text("Literature/first.md", "managed-first")
            transaction.write_text("Literature/second.md", "managed-second")
            original_replace = transaction_module._replace_owned
            calls = 0

            def interrupt_second(
                filesystem: object,
                source: str,
                destination: str,
            ) -> Path:
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise KeyboardInterrupt
                return original_replace(filesystem, source, destination)

            with mock.patch.object(
                transaction_module,
                "_replace_owned",
                side_effect=interrupt_second,
            ):
                with self.assertRaises(KeyboardInterrupt):
                    transaction.commit()

            self.assertEqual(first.read_text(encoding="utf-8"), "before-first")
            self.assertEqual(second.read_text(encoding="utf-8"), "before-second")
            manifest = json.loads(
                (
                    vault
                    / ".obsidian-vault-mcp"
                    / "backups"
                    / "cancelled-commit"
                    / "manifest.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["status"], "failed-restored")
            self.assertFalse(
                (
                    vault
                    / ".obsidian-vault-mcp"
                    / "staging"
                    / "cancelled-commit"
                ).exists()
            )

    def test_transactions_reserve_every_coordination_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            service = TransactionService(directory)
            for path in (
                ".obsidian-vault-mcp/backups/other/manifest.json",
                ".obsidian-vault-mcp/staging/other/file",
                ".obsidian-vault-mcp/locks/other.lock",
            ):
                with self.subTest(path=path):
                    transaction = service.begin()
                    with self.assertRaisesRegex(
                        TransactionConflictError,
                        "reserved for internal coordination",
                    ):
                        transaction.write_text(path, "unsafe")

    def test_transaction_staging_link_cannot_delete_another_transaction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            vault = Path(directory)
            staging = vault / ".obsidian-vault-mcp" / "staging"
            victim = staging / "tx-b"
            victim.mkdir(parents=True)
            marker = victim / "marker.txt"
            marker.write_text("other transaction", encoding="utf-8")
            linked = staging / "tx-a"
            _create_directory_link(linked, victim)
            try:
                with self.assertRaisesRegex(TransactionError, "linked transaction staging path"):
                    TransactionService(vault).begin(transaction_id="tx-a").commit()
                self.assertEqual(marker.read_text(encoding="utf-8"), "other transaction")
            finally:
                _remove_directory_link(linked)

    def test_atomic_write_replaces_utf8_and_cleans_temp_on_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "中文.md"
            target.write_text("old", encoding="utf-8")
            atomic_write_text(target, "新内容")
            self.assertEqual(target.read_text(encoding="utf-8"), "新内容")
            with mock.patch.object(atomic_writer.os, "replace", side_effect=OSError("boom")):
                with self.assertRaises(AtomicWriteError):
                    atomic_write_text(target, "broken")
            self.assertEqual(target.read_text(encoding="utf-8"), "新内容")
            self.assertEqual(list(target.parent.glob(f".{target.name}.*.tmp")), [])

    def test_transaction_preview_commit_noop_and_rollback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            vault = Path(directory)
            source = vault / "source.pdf"
            source.write_bytes(b"PDF")
            old = vault / "Literature" / "old.md"
            old.parent.mkdir(parents=True)
            old.write_text("old", encoding="utf-8")
            service = TransactionService(vault)
            tx = service.begin(item_key="ABCD1234", transaction_id="tx-1")
            tx.write_text("Literature/old.md", "new")
            tx.write_bytes("Literature/data.bin", b"data")
            tx.copy(source, "Literature/attachment/ABCD1234.pdf")
            preview = tx.preview()
            self.assertEqual(preview["changeCount"], 3)
            self.assertIn("-old", preview["operations"][0]["diff"])
            self.assertEqual(tx.commit()["status"], "committed")
            self.assertEqual(old.read_text(encoding="utf-8"), "new")
            self.assertEqual(service.rollback("tx-1")["status"], "rolled-back")
            self.assertEqual(old.read_text(encoding="utf-8"), "old")
            self.assertFalse((vault / "Literature" / "data.bin").exists())
            self.assertFalse((vault / "Literature" / "attachment" / "ABCD1234.pdf").exists())

            noop = service.begin(item_key="ABCD1234", transaction_id="tx-noop")
            noop.write_text("Literature/old.md", "old")
            self.assertEqual(noop.commit()["status"], "noop")
            self.assertFalse((vault / ".obsidian-vault-mcp" / "backups" / "tx-noop").exists())

    def test_dry_run_does_not_touch_vault(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            vault = Path(directory)
            tx = TransactionService(vault).begin(transaction_id="dry", dry_run=True)
            tx.write_text("Literature/new.md", "preview")
            result = tx.commit()
            self.assertEqual(result["status"], "dry-run")
            self.assertFalse((vault / "Literature" / "new.md").exists())
            self.assertFalse((vault / ".obsidian-vault-mcp").exists())

    def test_transaction_guard_fails_before_any_formal_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            vault = Path(directory)
            note = vault / "Literature" / "note.md"
            note.parent.mkdir()
            note.write_text("before", encoding="utf-8")
            transaction = TransactionService(vault).begin(
                item_key="ABCD1234",
                transaction_id="guard-before-write",
            )
            transaction.write_text("Literature/note.md", "managed")

            def reject() -> None:
                raise RuntimeError("unsafe path changed before commit")

            transaction.guard(reject)
            with self.assertRaisesRegex(TransactionError, "unsafe path changed"):
                transaction.commit()
            self.assertEqual(note.read_text(encoding="utf-8"), "before")
            self.assertFalse(
                (
                    vault
                    / ".obsidian-vault-mcp"
                    / "backups"
                    / "guard-before-write"
                ).exists()
            )

    def test_commit_failure_automatically_restores_old_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            vault = Path(directory)
            folder = vault / "Literature"
            folder.mkdir()
            (folder / "a.md").write_text("old-a", encoding="utf-8")
            (folder / "b.md").write_text("old-b", encoding="utf-8")
            service = TransactionService(vault)
            tx = service.begin(item_key="ABCD1234", transaction_id="failing")
            tx.write_text("Literature/a.md", "new-a")
            tx.write_text("Literature/b.md", "new-b")
            original_replace = transaction_module._replace_owned
            calls = 0

            def fail_second(
                filesystem: object,
                source: str,
                destination: str,
            ) -> Path:
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise AtomicWriteError("injected failure")
                return original_replace(filesystem, source, destination)

            with mock.patch.object(
                transaction_module,
                "_replace_owned",
                side_effect=fail_second,
            ):
                with self.assertRaises(TransactionError) as caught:
                    tx.commit()
            self.assertTrue(caught.exception.details["restored"])
            self.assertEqual((folder / "a.md").read_text(encoding="utf-8"), "old-a")
            self.assertEqual((folder / "b.md").read_text(encoding="utf-8"), "old-b")
            self.assertFalse((vault / ".obsidian-vault-mcp" / "staging" / "failing").exists())

    @unittest.skipUnless(os.name == "nt", "Windows read-only replacement regression")
    def test_later_read_only_destination_does_not_leave_an_earlier_commit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            vault = Path(directory)
            folder = vault / "Literature"
            folder.mkdir()
            first = folder / "a.md"
            read_only = folder / "b.md"
            first.write_text("old-a", encoding="utf-8")
            read_only.write_text("old-b", encoding="utf-8")
            os.chmod(read_only, stat.S_IREAD)
            try:
                service = TransactionService(vault)
                transaction = service.begin(transaction_id="read-only-later")
                transaction.write_text("Literature/a.md", "new-a")
                transaction.write_text("Literature/b.md", "new-b")

                with self.assertRaises(TransactionError) as caught:
                    transaction.commit()

                self.assertEqual(first.read_text(encoding="utf-8"), "old-a")
                self.assertEqual(read_only.read_text(encoding="utf-8"), "old-b")
                self.assertEqual(caught.exception.transaction_id, "read-only-later")
                self.assertEqual(caught.exception.stage, "commit")
                self.assertTrue(caught.exception.details["restored"])
                self.assertEqual(caught.exception.details["recoveryErrors"], [])
                self.assertIsNone(caught.exception.details["recoveryError"])
                manifest = json.loads(
                    (
                        vault
                        / ".obsidian-vault-mcp"
                        / "backups"
                        / "read-only-later"
                        / "manifest.json"
                    ).read_text(encoding="utf-8")
                )
                self.assertEqual(manifest["status"], "failed-restored")
            finally:
                os.chmod(read_only, stat.S_IREAD | stat.S_IWRITE)

    def test_commit_recovery_continues_after_one_restore_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            vault = Path(directory)
            folder = vault / "Literature"
            folder.mkdir()
            first = folder / "a.md"
            failed_restore = folder / "b.md"
            later_failure = folder / "c.md"
            first.write_text("old-a", encoding="utf-8")
            failed_restore.write_text("old-b", encoding="utf-8")
            later_failure.write_text("old-c", encoding="utf-8")
            service = TransactionService(vault)
            transaction = service.begin(transaction_id="best-effort-restore")
            transaction.write_text("Literature/a.md", "new-a")
            transaction.write_text("Literature/b.md", "new-b")
            transaction.write_text("Literature/c.md", "new-c")
            original_replace = transaction_module._replace_owned
            original_copy = service.fs.atomic_copy_owned
            replace_calls = 0

            def fail_third_replace(
                filesystem: object,
                source: str,
                destination: str,
            ) -> Path:
                nonlocal replace_calls
                replace_calls += 1
                if replace_calls == 3:
                    raise AtomicWriteError("injected later replacement failure")
                return original_replace(filesystem, source, destination)

            def fail_one_restore(source: str, destination: str) -> Path:
                if (
                    source.endswith(
                        "backups/best-effort-restore/files/Literature/b.md"
                    )
                    and destination == "Literature/b.md"
                ):
                    raise AtomicWriteError("injected b.md restore failure")
                return original_copy(source, destination)

            with (
                mock.patch.object(
                    transaction_module,
                    "_replace_owned",
                    side_effect=fail_third_replace,
                ),
                mock.patch.object(
                    service.fs,
                    "atomic_copy_owned",
                    side_effect=fail_one_restore,
                ),
                self.assertRaises(TransactionError) as caught,
            ):
                transaction.commit()

            self.assertEqual(first.read_text(encoding="utf-8"), "old-a")
            self.assertEqual(failed_restore.read_text(encoding="utf-8"), "new-b")
            self.assertEqual(later_failure.read_text(encoding="utf-8"), "old-c")
            self.assertEqual(caught.exception.transaction_id, "best-effort-restore")
            self.assertEqual(caught.exception.stage, "commit")
            self.assertFalse(caught.exception.details["restored"])
            self.assertEqual(
                caught.exception.details["touchedPaths"],
                [
                    "Literature/a.md",
                    "Literature/b.md",
                    "Literature/c.md",
                ],
            )
            self.assertEqual(
                caught.exception.details["recoveryErrors"],
                [
                    {
                        "path": "Literature/b.md",
                        "errorType": "AtomicWriteError",
                        "error": "injected b.md restore failure",
                    }
                ],
            )
            self.assertIn(
                "Literature/b.md: injected b.md restore failure",
                caught.exception.details["recoveryError"],
            )
            manifest = json.loads(
                (
                    vault
                    / ".obsidian-vault-mcp"
                    / "backups"
                    / "best-effort-restore"
                    / "manifest.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["status"], "failed-restore-incomplete")
            self.assertEqual(
                manifest["recoveryErrors"],
                caught.exception.details["recoveryErrors"],
            )

    def test_item_lock_is_exclusive(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first = ItemLock(directory, "ABCD1234", timeout=0)
            second = ItemLock(directory, "ABCD1234", timeout=0)
            with first:
                with self.assertRaises(LockTimeoutError):
                    second.acquire()
            with second:
                self.assertTrue(second.acquired)

    def test_target_lock_is_deterministic_and_case_insensitive(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first = TargetLock(
                directory,
                "Literature/Analysis/full-reads/FR-QZBLIATR.md",
                timeout=0,
            )
            second = TargetLock(
                directory,
                "literature/analysis/FULL-READS/fr-qzbliatr.MD",
                timeout=0,
            )

            self.assertEqual(first.path, second.path)
            with first:
                with self.assertRaises(LockTimeoutError):
                    second.acquire()
            with second:
                self.assertTrue(second.acquired)

    def test_same_analysis_target_serializes_different_item_keys(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            vault = Path(directory)
            service = TransactionService(vault)
            relative = "Literature/Analysis/full-reads/FR-QZBLIATR.md"
            target = vault.joinpath(*relative.split("/"))
            first = service.begin(
                item_key="QZBLIATR",
                transaction_id="analysis-source-a",
            )
            second = service.begin(
                item_key="ABCD1234",
                transaction_id="analysis-source-b",
            )
            first.write_text(relative, "from source A")
            second.write_text(relative, "from source B")

            def require_missing() -> None:
                if target.exists():
                    raise TransactionConflictError(
                        "Analysis target appeared after planning",
                        stage="guard",
                    )

            first.guard(require_missing)
            second.guard(require_missing)
            ready = threading.Barrier(2)
            committed: list[str] = []
            errors: list[BaseException] = []

            def commit(transaction: Transaction, content: str) -> None:
                try:
                    ready.wait(timeout=5)
                    transaction.commit()
                    committed.append(content)
                except BaseException as exc:
                    errors.append(exc)

            threads = [
                threading.Thread(
                    target=commit,
                    args=(first, "from source A"),
                ),
                threading.Thread(
                    target=commit,
                    args=(second, "from source B"),
                ),
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)

            self.assertTrue(all(not thread.is_alive() for thread in threads))
            self.assertEqual(len(committed), 1)
            self.assertEqual(len(errors), 1)
            self.assertIsInstance(errors[0], TransactionConflictError)
            self.assertEqual(target.read_text(encoding="utf-8"), committed[0])

    def test_rollback_preserves_post_commit_user_edits_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            vault = Path(directory)
            note = vault / "Literature" / "note.md"
            note.parent.mkdir()
            note.write_text("before", encoding="utf-8")
            service = TransactionService(vault)
            transaction = service.begin(transaction_id="guarded-rollback")
            transaction.write_text("Literature/note.md", "managed")
            transaction.commit()
            note.write_text("user edit", encoding="utf-8")

            preview = service.rollback("guarded-rollback", dry_run=True)
            self.assertEqual(preview["status"], "conflict")
            with self.assertRaises(TransactionConflictError):
                service.rollback("guarded-rollback")
            self.assertEqual(note.read_text(encoding="utf-8"), "user edit")

            forced = service.rollback("guarded-rollback", conflict_policy="overwrite-managed")
            self.assertEqual(forced["status"], "rolled-back")
            self.assertEqual(note.read_text(encoding="utf-8"), "before")

    def test_rollback_rechecks_conflicts_after_acquiring_the_item_lock(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            vault = Path(directory)
            note = vault / "Literature" / "note.md"
            note.parent.mkdir()
            note.write_text("before", encoding="utf-8")
            service = TransactionService(vault)
            transaction = service.begin(
                item_key="ABCD1234",
                transaction_id="locked-rollback-conflict",
            )
            transaction.write_text("Literature/note.md", "managed")
            transaction.commit()

            class EditingLock:
                def __init__(self, *_args: object, **_kwargs: object) -> None:
                    pass

                def __enter__(self) -> EditingLock:
                    note.write_text("concurrent edit", encoding="utf-8")
                    return self

                def __exit__(self, *_args: object) -> None:
                    return None

            with (
                mock.patch.object(transaction_module, "ItemLock", EditingLock),
                self.assertRaises(TransactionConflictError),
            ):
                service.rollback("locked-rollback-conflict")

            self.assertEqual(note.read_text(encoding="utf-8"), "concurrent edit")

    def test_itemless_rollback_holds_target_lock_through_restore(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            vault = Path(directory)
            note = vault / "Literature" / "note.md"
            note.parent.mkdir()
            note.write_text("before", encoding="utf-8")
            service = TransactionService(vault)
            transaction = service.begin(transaction_id="itemless-rollback")
            transaction.write_text("Literature/note.md", "managed")
            transaction.commit()

            conflicts_checked = threading.Event()
            allow_restore = threading.Event()
            writer_attempted = threading.Event()
            writer_done = threading.Event()
            errors: list[BaseException] = []
            original_conflicts = service._rollback_conflicts

            def pause_after_conflict_check(
                entries: list[dict[str, Any]],
            ) -> list[dict[str, Any]]:
                result = original_conflicts(entries)
                conflicts_checked.set()
                if not allow_restore.wait(timeout=5):
                    raise AssertionError("rollback test timed out before restore")
                return result

            class ObservedTargetLock(TargetLock):
                def acquire(self) -> ObservedTargetLock:
                    if threading.current_thread().name == "concurrent-writer":
                        writer_attempted.set()
                    super().acquire()
                    return self

            def rollback() -> None:
                try:
                    service.rollback("itemless-rollback")
                except BaseException as exc:
                    errors.append(exc)

            replacement = service.begin(transaction_id="newer-write")
            replacement.write_text("Literature/note.md", "newer")

            def write_newer() -> None:
                try:
                    replacement.commit()
                except BaseException as exc:
                    errors.append(exc)
                finally:
                    writer_done.set()

            with (
                mock.patch.object(
                    service,
                    "_rollback_conflicts",
                    side_effect=pause_after_conflict_check,
                ),
                mock.patch.object(
                    transaction_module,
                    "TargetLock",
                    ObservedTargetLock,
                ),
            ):
                rollback_thread = threading.Thread(target=rollback)
                rollback_thread.start()
                self.assertTrue(conflicts_checked.wait(timeout=5))

                writer_thread = threading.Thread(
                    target=write_newer,
                    name="concurrent-writer",
                )
                writer_thread.start()
                self.assertTrue(writer_attempted.wait(timeout=5))
                self.assertFalse(writer_done.is_set())

                allow_restore.set()
                rollback_thread.join(timeout=10)
                writer_thread.join(timeout=10)

            self.assertFalse(rollback_thread.is_alive())
            self.assertFalse(writer_thread.is_alive())
            self.assertEqual(len(errors), 1)
            self.assertIsInstance(errors[0], TransactionConflictError)
            self.assertTrue(writer_done.is_set())
            self.assertEqual(note.read_text(encoding="utf-8"), "before")

    def test_rollback_rejects_manifest_backup_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            vault = Path(directory) / "vault"
            vault.mkdir()
            note = vault / "Literature" / "note.md"
            note.parent.mkdir()
            note.write_text("before", encoding="utf-8")
            outside = Path(directory) / "outside.txt"
            outside.write_text("outside", encoding="utf-8")
            service = TransactionService(vault)
            transaction = service.begin(transaction_id="tampered-backup-path")
            transaction.write_text("Literature/note.md", "managed")
            transaction.commit()

            manifest_path = (
                vault
                / ".obsidian-vault-mcp"
                / "backups"
                / "tampered-backup-path"
                / "manifest.json"
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            for invalid_path in ("../../../../outside.txt", str(outside.resolve())):
                manifest["operations"][0]["backupPath"] = invalid_path
                manifest_path.write_text(
                    json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                with self.subTest(invalid_path=invalid_path):
                    with self.assertRaisesRegex(
                        TransactionRollbackError,
                        "backup path is invalid",
                    ):
                        service.rollback(
                            "tampered-backup-path",
                            conflict_policy="overwrite-managed",
                        )
            self.assertEqual(note.read_text(encoding="utf-8"), "managed")
            self.assertEqual(outside.read_text(encoding="utf-8"), "outside")

    def test_rollback_validates_all_backup_hashes_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            vault = Path(directory)
            folder = vault / "Literature"
            folder.mkdir()
            first = folder / "first.md"
            second = folder / "second.md"
            first.write_text("before-first", encoding="utf-8")
            second.write_text("before-second", encoding="utf-8")
            service = TransactionService(vault)
            transaction = service.begin(transaction_id="tampered-backup-hash")
            transaction.write_text("Literature/first.md", "managed-first")
            transaction.write_text("Literature/second.md", "managed-second")
            transaction.commit()
            backup = (
                vault
                / ".obsidian-vault-mcp"
                / "backups"
                / "tampered-backup-hash"
                / "files"
                / "Literature"
                / "second.md"
            )
            backup.write_text("tampered", encoding="utf-8")

            with self.assertRaisesRegex(TransactionRollbackError, "checksum mismatch"):
                service.rollback(
                    "tampered-backup-hash",
                    conflict_policy="overwrite-managed",
                )
            self.assertEqual(first.read_text(encoding="utf-8"), "managed-first")
            self.assertEqual(second.read_text(encoding="utf-8"), "managed-second")

    def test_rollback_rejects_junction_in_backup_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            vault = root / "vault"
            vault.mkdir()
            note = vault / "Literature" / "note.md"
            note.parent.mkdir()
            note.write_text("before", encoding="utf-8")
            service = TransactionService(vault)
            transaction = service.begin(transaction_id="linked-backup")
            transaction.write_text("Literature/note.md", "managed")
            transaction.commit()
            backup_parent = (
                vault
                / ".obsidian-vault-mcp"
                / "backups"
                / "linked-backup"
                / "files"
            )
            backup_literature = backup_parent / "Literature"
            saved = backup_parent / "saved-literature"
            backup_literature.rename(saved)
            outside = root / "outside-backup"
            outside.mkdir()
            outside_note = outside / "note.md"
            outside_note.write_text("outside", encoding="utf-8")
            _create_directory_link(backup_literature, outside)
            try:
                with self.assertRaisesRegex(
                    TransactionRollbackError,
                    "escapes its transaction",
                ):
                    service.rollback(
                        "linked-backup",
                        conflict_policy="overwrite-managed",
                    )
                self.assertEqual(note.read_text(encoding="utf-8"), "managed")
                self.assertEqual(outside_note.read_text(encoding="utf-8"), "outside")
            finally:
                _remove_directory_link(backup_literature)


if __name__ == "__main__":
    unittest.main()
