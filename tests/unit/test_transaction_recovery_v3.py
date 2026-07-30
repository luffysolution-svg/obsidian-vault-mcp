from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

import obsidian_vault_mcp.application.transaction_service as transaction_module
from obsidian_vault_mcp.application.mineru_image_migration_service import (
    MinerUImageMigrationService,
)
from obsidian_vault_mcp.application.transaction_service import TransactionService
from obsidian_vault_mcp.domain.errors import (
    AtomicWriteError,
    TransactionConflictError,
    TransactionError,
    TransactionRollbackError,
)
from obsidian_vault_mcp.domain.frontmatter import compose_frontmatter


def test_backup_aba_is_rejected_before_formal_write(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    note = tmp_path / "Literature" / "note.md"
    note.parent.mkdir()
    note.write_text("old", encoding="utf-8")
    service = TransactionService(tmp_path)
    transaction = service.begin(transaction_id="backup-aba")
    transaction.write_text("Literature/note.md", "managed")
    original_copy = service.fs.atomic_copy_owned

    def copy_transient_edit(source: str, destination: str) -> Path:
        if destination.endswith(
            "backups/backup-aba/files/Literature/note.md"
        ):
            note.write_text("transient-user-edit", encoding="utf-8")
            try:
                return original_copy(source, destination)
            finally:
                note.write_text("old", encoding="utf-8")
        return original_copy(source, destination)

    monkeypatch.setattr(
        service.fs,
        "atomic_copy_owned",
        copy_transient_edit,
    )

    with pytest.raises(TransactionError, match="backup changed"):
        transaction.commit()

    assert note.read_text(encoding="utf-8") == "old"


def test_automatic_recovery_preserves_edit_after_own_write(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    first = tmp_path / "Literature" / "a.md"
    second = tmp_path / "Literature" / "b.md"
    first.parent.mkdir()
    first.write_text("old-a", encoding="utf-8")
    second.write_text("old-b", encoding="utf-8")
    service = TransactionService(tmp_path)
    transaction = service.begin(transaction_id="post-write-user-edit")
    transaction.write_text("Literature/a.md", "new-a")
    transaction.write_text("Literature/b.md", "new-b")
    original_replace = transaction_module._replace_owned
    calls = 0

    def edit_first_then_fail_second(
        filesystem: object,
        source: str,
        destination: str,
    ) -> Path:
        nonlocal calls
        calls += 1
        if calls == 1:
            result = original_replace(filesystem, source, destination)
            first.write_text("post-write-user-edit", encoding="utf-8")
            return result
        raise AtomicWriteError("injected later failure")

    monkeypatch.setattr(
        transaction_module,
        "_replace_owned",
        edit_first_then_fail_second,
    )

    with pytest.raises(TransactionError) as caught:
        transaction.commit()

    assert first.read_text(encoding="utf-8") == "post-write-user-edit"
    assert second.read_text(encoding="utf-8") == "old-b"
    assert caught.value.details["restored"] is False
    assert [
        failure["path"]
        for failure in caught.value.details["recoveryErrors"]
    ] == ["Literature/a.md"]


def test_staging_edit_is_not_accepted_as_new_destination_baseline(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    note = tmp_path / "Literature" / "note.md"
    note.parent.mkdir()
    note.write_text("old", encoding="utf-8")
    service = TransactionService(tmp_path)
    transaction = service.begin(transaction_id="staging-edit")
    transaction.write_text("Literature/note.md", "managed")
    original_write = service.fs.atomic_write_bytes_owned

    def write_then_edit(relative: str, data: bytes) -> Path:
        result = original_write(relative, data)
        if str(relative).endswith(
            "staging/staging-edit/transaction-files/Literature/note.md"
        ):
            note.write_text("user-edit-during-staging", encoding="utf-8")
        return result

    monkeypatch.setattr(
        service.fs,
        "atomic_write_bytes_owned",
        write_then_edit,
    )

    with pytest.raises(TransactionError, match="changed after planning"):
        transaction.commit()

    assert note.read_text(encoding="utf-8") == "user-edit-during-staging"


def test_copy_source_aba_is_rejected_before_formal_write(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "Literature" / "source.bin"
    source.parent.mkdir()
    source.write_bytes(b"original")
    service = TransactionService(tmp_path)
    transaction = service.begin(transaction_id="copy-source-aba")
    transaction.copy(source, "Literature/copied.bin")
    original_copy = service.fs.atomic_copy_stream_owned

    def copy_changed_source(relative: str, stream: object) -> Path:
        if str(relative).endswith(
            "transaction-files/Literature/copied.bin"
        ):
            source.write_bytes(b"concurrent")
            try:
                return original_copy(relative, stream)
            finally:
                source.write_bytes(b"original")
        return original_copy(relative, stream)

    monkeypatch.setattr(
        service.fs,
        "atomic_copy_stream_owned",
        copy_changed_source,
    )

    with pytest.raises(TransactionError, match="copy source changed"):
        transaction.commit()

    assert source.read_bytes() == b"original"
    assert not (tmp_path / "Literature" / "copied.bin").exists()


def test_guard_cannot_redefine_an_absent_destination_baseline(
    tmp_path: Path,
) -> None:
    target = tmp_path / "Literature" / "new.md"
    target.parent.mkdir()
    service = TransactionService(tmp_path)
    transaction = service.begin(transaction_id="guard-target-appeared")
    transaction.write_text("Literature/new.md", "managed")
    transaction.guard(
        lambda: target.write_text("user-created", encoding="utf-8")
    )

    with pytest.raises(
        TransactionConflictError,
        match="changed after planning",
    ):
        transaction.commit()

    assert target.read_text(encoding="utf-8") == "user-created"


def test_partial_rollback_can_resume_with_preserve_user(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    first = tmp_path / "Literature" / "a.md"
    second = tmp_path / "Literature" / "b.md"
    first.parent.mkdir()
    first.write_text("old-a", encoding="utf-8")
    second.write_text("old-b", encoding="utf-8")
    service = TransactionService(tmp_path)
    transaction = service.begin(transaction_id="resumable-rollback")
    transaction.write_text("Literature/a.md", "new-a")
    transaction.write_text("Literature/b.md", "new-b")
    transaction.commit()
    original_copy = service.fs.atomic_copy_owned

    def fail_second_restore(source: str, destination: str) -> Path:
        if source.endswith(
            "backups/resumable-rollback/files/Literature/b.md"
        ):
            raise AtomicWriteError("restore unavailable")
        return original_copy(source, destination)

    with (
        monkeypatch.context() as patch,
        pytest.raises(TransactionRollbackError),
    ):
        patch.setattr(
            service.fs,
            "atomic_copy_owned",
            fail_second_restore,
        )
        service.rollback("resumable-rollback")

    assert first.read_text(encoding="utf-8") == "old-a"
    assert second.read_text(encoding="utf-8") == "new-b"

    resumed = service.rollback("resumable-rollback")

    assert resumed["status"] == "rolled-back"
    assert first.read_text(encoding="utf-8") == "old-a"
    assert second.read_text(encoding="utf-8") == "old-b"


def test_copy_rejects_a_vault_internal_directory_link(
    tmp_path: Path,
) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    outside_source = outside / "source.bin"
    outside_source.write_bytes(b"outside")
    linked = tmp_path / "linked-source"
    if os.name == "nt":
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(linked), str(outside)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            pytest.skip("Windows junction creation is unavailable")
    else:
        try:
            linked.symlink_to(outside, target_is_directory=True)
        except OSError:
            pytest.skip("directory symlink creation is unavailable")
    try:
        service = TransactionService(tmp_path)
        transaction = service.begin(transaction_id="linked-copy-source")
        with pytest.raises(
            TransactionConflictError,
            match="copy source is unsafe",
        ):
            transaction.copy(
                linked / "source.bin",
                "Literature/copied.bin",
            )
        assert not (tmp_path / "Literature" / "copied.bin").exists()
    finally:
        if os.name == "nt":
            os.rmdir(linked)
        else:
            linked.unlink()
        outside_source.unlink()
        outside.rmdir()


def test_mineru_target_appearing_after_guard_is_preserved(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    key = "ABCD1234"
    markdown_root = tmp_path / "Literature" / "attachment" / "MinerU"
    image_root = markdown_root / "image"
    image_root.mkdir(parents=True)
    markdown = markdown_root / f"{key}.md"
    markdown.write_text(
        compose_frontmatter(
            {"title": "Paper", "zoteroKey": key},
            f"![figure](image/{key}-fig01.png)\n",
        ),
        encoding="utf-8",
    )
    source = image_root / f"{key}-fig01.png"
    source.write_bytes(b"legacy")
    target = image_root / key / source.name
    service = MinerUImageMigrationService(tmp_path)
    original_recheck = service._recheck_safe_plans

    def recheck_then_create_target(*args: object, **kwargs: object) -> None:
        original_recheck(*args, **kwargs)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"user-target")

    monkeypatch.setattr(
        service,
        "_recheck_safe_plans",
        recheck_then_create_target,
    )

    with pytest.raises(TransactionError, match="changed after planning"):
        service.migrate(
            dry_run=False,
            apply=True,
            transaction_id="late-mineru-target",
        )

    assert target.read_bytes() == b"user-target"
    assert source.read_bytes() == b"legacy"
    assert f"image/{key}-fig01.png" in markdown.read_text(encoding="utf-8")
