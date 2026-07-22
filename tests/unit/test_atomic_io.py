from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from obsidian_vault_mcp.adapters.vault import atomic_writer
from obsidian_vault_mcp.adapters.vault.atomic_writer import atomic_write_text
from obsidian_vault_mcp.adapters.vault.lock import ItemLock
from obsidian_vault_mcp.application.transaction_service import TransactionService
from obsidian_vault_mcp.domain.errors import AtomicWriteError, LockTimeoutError, TransactionConflictError, TransactionError


class AtomicIoTests(unittest.TestCase):
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
            original_replace = atomic_writer.atomic_replace
            calls = 0

            def fail_second(source: Path, destination: Path) -> Path:
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise AtomicWriteError("injected failure")
                return original_replace(source, destination)

            with mock.patch.object(atomic_writer, "atomic_replace", side_effect=fail_second):
                with self.assertRaises(TransactionError) as caught:
                    tx.commit()
            self.assertTrue(caught.exception.details["restored"])
            self.assertEqual((folder / "a.md").read_text(encoding="utf-8"), "old-a")
            self.assertEqual((folder / "b.md").read_text(encoding="utf-8"), "old-b")
            self.assertFalse((vault / ".obsidian-vault-mcp" / "staging" / "failing").exists())

    def test_item_lock_is_exclusive(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first = ItemLock(directory, "ABCD1234", timeout=0)
            second = ItemLock(directory, "ABCD1234", timeout=0)
            with first:
                with self.assertRaises(LockTimeoutError):
                    second.acquire()
            with second:
                self.assertTrue(second.acquired)

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


if __name__ == "__main__":
    unittest.main()
