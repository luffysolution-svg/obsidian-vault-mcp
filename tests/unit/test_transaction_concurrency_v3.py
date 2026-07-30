from __future__ import annotations

from pathlib import Path

import pytest

import obsidian_vault_mcp.application.transaction_service as transaction_module
from obsidian_vault_mcp.application.transaction_service import TransactionService
from obsidian_vault_mcp.domain.errors import TransactionError


def test_commit_preserves_destination_edited_after_backup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    note = tmp_path / "Literature" / "note.md"
    note.parent.mkdir()
    note.write_text("old", encoding="utf-8")
    service = TransactionService(tmp_path)
    original_write_manifest = service._write_manifest
    injected = False

    def write_manifest(transaction_id: str, value: dict[str, object]) -> None:
        nonlocal injected
        original_write_manifest(transaction_id, value)
        if value.get("status") == "prepared" and not injected:
            injected = True
            note.write_text("concurrent-user-edit", encoding="utf-8")

    monkeypatch.setattr(service, "_write_manifest", write_manifest)
    transaction = service.begin(transaction_id="concurrent-after-backup")
    transaction.write_text("Literature/note.md", "managed")

    with pytest.raises(TransactionError, match="changed before commit") as caught:
        transaction.commit()

    assert note.read_text(encoding="utf-8") == "concurrent-user-edit"
    assert caught.value.details["touchedPaths"] == []
    assert caught.value.details["restored"] is True


def test_later_concurrent_edit_rolls_back_earlier_committed_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    first = tmp_path / "Literature" / "a.md"
    second = tmp_path / "Literature" / "b.md"
    first.parent.mkdir()
    first.write_text("old-a", encoding="utf-8")
    second.write_text("old-b", encoding="utf-8")
    service = TransactionService(tmp_path)
    original_replace = transaction_module._replace_owned
    replacement_count = 0

    def replace_and_edit(
        filesystem: object,
        source_relative: str,
        destination_relative: str,
    ) -> None:
        nonlocal replacement_count
        original_replace(filesystem, source_relative, destination_relative)
        replacement_count += 1
        if replacement_count == 1:
            second.write_text("concurrent-user-edit", encoding="utf-8")

    monkeypatch.setattr(transaction_module, "_replace_owned", replace_and_edit)
    transaction = service.begin(transaction_id="concurrent-later-path")
    transaction.write_text("Literature/a.md", "new-a")
    transaction.write_text("Literature/b.md", "new-b")

    with pytest.raises(TransactionError, match="changed before commit") as caught:
        transaction.commit()

    assert first.read_text(encoding="utf-8") == "old-a"
    assert second.read_text(encoding="utf-8") == "concurrent-user-edit"
    assert caught.value.details["restored"] is True
    assert caught.value.details["touchedPaths"] == ["Literature/a.md"]
