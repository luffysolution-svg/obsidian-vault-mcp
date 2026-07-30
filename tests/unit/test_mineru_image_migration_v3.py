from __future__ import annotations

import json
import os
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

import obsidian_vault_mcp.application.mineru_image_migration_service as migration_module
from obsidian_vault_mcp.application.mineru_image_migration_service import (
    MinerUImageMigrationService,
)
from obsidian_vault_mcp.config.defaults import default_config
from obsidian_vault_mcp.domain.errors import TransactionError
from obsidian_vault_mcp.domain.frontmatter import compose_frontmatter
from obsidian_vault_mcp.interfaces.cli.main import main

MARKDOWN_ROOT = Path("Literature/attachment/MinerU")
IMAGE_ROOT = MARKDOWN_ROOT / "image"


def _write_paper(vault: Path, key: str, body: str) -> Path:
    path = vault / MARKDOWN_ROOT / f"{key}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        compose_frontmatter(
            {"title": f"Paper {key}", "zoteroKey": key},
            body,
        ),
        encoding="utf-8",
    )
    return path


def _write_flat_image(vault: Path, filename: str, content: bytes = b"image") -> Path:
    path = vault / IMAGE_ROOT / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _snapshot(vault: Path) -> dict[str, bytes]:
    return {
        path.relative_to(vault).as_posix(): path.read_bytes()
        for path in sorted(
            (candidate for candidate in vault.rglob("*") if candidate.is_file()),
            key=lambda candidate: candidate.as_posix().casefold(),
        )
    }


def _enable_case_sensitive_directory(path: Path) -> None:
    if os.name != "nt":
        return
    result = subprocess.run(
        ["fsutil.exe", "file", "setCaseSensitiveInfo", str(path), "enable"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        pytest.skip("case-sensitive Windows test directory is unavailable")


def test_two_key_migration_defaults_to_dry_run_without_mutation(tmp_path: Path) -> None:
    key_a = "ABCD1234"
    key_b = "WXYZ5678"
    _write_paper(tmp_path, key_a, f"![A](image/{key_a}-fig01.png)\n")
    _write_paper(tmp_path, key_b, f"![B](image/{key_b}-fig01.png)\n")
    _write_flat_image(tmp_path, f"{key_a}-fig01.png", b"A")
    _write_flat_image(tmp_path, f"{key_b}-fig01.png", b"B")
    before = _snapshot(tmp_path)

    report = MinerUImageMigrationService(tmp_path).migrate(
        transaction_id="mineru-images-preview"
    )

    assert report["status"] == "dry-run"
    assert report["dryRun"] is True
    assert report["applied"] is False
    assert report["changeCount"] == 4
    assert len(report["copiedImages"]) == 2
    assert report["movedImages"] == []
    assert len(report["preservedLegacyImages"]) == 2
    assert len(report["rewrittenMarkdown"]) == 2
    assert report["reparseZoteroKeys"] == []
    assert {
        entry["to"] for entry in report["copiedImages"]
    } == {
        f"Literature/attachment/MinerU/image/{key_a}/{key_a}-fig01.png",
        f"Literature/attachment/MinerU/image/{key_b}/{key_b}-fig01.png",
    }
    assert _snapshot(tmp_path) == before


def test_custom_mineru_markdown_name_is_owned_by_frontmatter_key(
    tmp_path: Path,
) -> None:
    key = "ABCD1234"
    config = default_config()
    config["mineru"]["markdownFolder"] = "Extracted/Markdown"
    config["mineru"]["imageFolder"] = "Extracted/Assets"
    config["naming"]["mineruMarkdown"] = (
        "parsed-{shortTitle}-{zoteroKey}.md"
    )
    markdown = (
        tmp_path
        / "Extracted"
        / "Markdown"
        / f"parsed-Custom title-{key}.md"
    )
    markdown.parent.mkdir(parents=True)
    markdown.write_text(
        compose_frontmatter(
            {"title": "Custom title", "zoteroKey": key},
            f"![figure](../Assets/{key}-fig01.png)\n",
        ),
        encoding="utf-8",
    )
    image = tmp_path / "Extracted" / "Assets" / f"{key}-fig01.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"image")

    report = MinerUImageMigrationService(tmp_path, config).migrate()

    assert report["changeCount"] == 2
    assert report["rewrittenMarkdown"] == [
        {
            "path": f"Extracted/Markdown/parsed-Custom title-{key}.md",
            "zoteroKey": key,
            "referenceCount": 1,
        }
    ]
    assert all(
        item["reason"] != "markdown-key-mismatch"
        for item in report["skipped"]
    )


def test_apply_rewrites_and_moves_in_one_transaction_then_rolls_back(
    tmp_path: Path,
) -> None:
    key = "ABCD1234"
    original_markdown = _write_paper(
        tmp_path,
        key,
        (
            f"![inline](image/{key}-fig01.jpg)\n\n"
            f"![[image/{key}-fig01.jpg|wiki]]\n"
        ),
    ).read_text(encoding="utf-8")
    source = _write_flat_image(tmp_path, f"{key}-fig01.jpg", b"jpeg-data")
    service = MinerUImageMigrationService(tmp_path)

    report = service.migrate(
        dry_run=False,
        apply=True,
        transaction_id="mineru-images-apply",
        cleanup_legacy=True,
        confirm_vault_offline=True,
    )

    target = tmp_path / IMAGE_ROOT / key / f"{key}-fig01.jpg"
    markdown = tmp_path / MARKDOWN_ROOT / f"{key}.md"
    assert report["status"] == "committed"
    assert report["changeCount"] == 3
    assert len(report["movedImages"]) == 1
    assert report["rewrittenMarkdown"][0]["referenceCount"] == 2
    assert not source.exists()
    assert target.read_bytes() == b"jpeg-data"
    migrated_text = markdown.read_text(encoding="utf-8")
    assert migrated_text.count(f"image/{key}/{key}-fig01.jpg") == 2

    rolled_back = service.rollback("mineru-images-apply")

    assert rolled_back["status"] == "rolled-back"
    assert source.read_bytes() == b"jpeg-data"
    assert not target.exists()
    assert markdown.read_text(encoding="utf-8") == original_markdown


def test_safe_apply_preserves_legacy_alias_and_is_idempotent(tmp_path: Path) -> None:
    key = "ABCD1234"
    markdown = _write_paper(
        tmp_path,
        key,
        f"![image](image/{key}-fig01.png)\n",
    )
    source = _write_flat_image(tmp_path, f"{key}-fig01.png", b"image-data")
    service = MinerUImageMigrationService(tmp_path)

    first = service.migrate(
        dry_run=False,
        apply=True,
        transaction_id="safe-copy",
    )

    target = tmp_path / IMAGE_ROOT / key / source.name
    assert first["status"] == "committed"
    assert first["changeCount"] == 2
    assert len(first["copiedImages"]) == 1
    assert first["movedImages"] == []
    assert first["preservedLegacyImages"] == [
        {
            "zoteroKey": key,
            "path": f"Literature/attachment/MinerU/image/{source.name}",
            "canonicalPath": (
                f"Literature/attachment/MinerU/image/{key}/{source.name}"
            ),
        }
    ]
    assert source.read_bytes() == b"image-data"
    assert target.read_bytes() == b"image-data"
    assert f"image/{key}/{source.name}" in markdown.read_text(encoding="utf-8")

    second = service.migrate(
        dry_run=False,
        apply=True,
        transaction_id="safe-copy-repeat",
    )

    assert second["status"] == "noop"
    assert second["changeCount"] == 0
    assert second["copiedImages"] == []
    assert second["movedImages"] == []
    assert source.read_bytes() == b"image-data"
    assert target.read_bytes() == b"image-data"


def test_safe_apply_cannot_break_reference_added_after_final_scan(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    key = "ABCD1234"
    markdown = _write_paper(
        tmp_path,
        key,
        f"![owner](image/{key}-fig01.png)\n",
    )
    source = _write_flat_image(tmp_path, f"{key}-fig01.png", b"original")
    external = tmp_path / "Concurrent user note.md"
    external_reference = (
        f"![shared](Literature/attachment/MinerU/image/{source.name})\n"
    )
    service = MinerUImageMigrationService(tmp_path)
    original_recheck = service._recheck_safe_plans

    def inject_after_recheck(*args: object, **kwargs: object) -> None:
        original_recheck(*args, **kwargs)
        external.write_text(external_reference, encoding="utf-8")

    monkeypatch.setattr(service, "_recheck_safe_plans", inject_after_recheck)

    report = service.migrate(
        dry_run=False,
        apply=True,
        transaction_id="post-scan-reference",
    )

    target = tmp_path / IMAGE_ROOT / key / source.name
    assert report["status"] == "committed"
    assert source.read_bytes() == b"original"
    assert target.read_bytes() == b"original"
    assert external.read_text(encoding="utf-8") == external_reference
    assert f"image/{key}/{source.name}" in markdown.read_text(encoding="utf-8")


def test_destructive_cleanup_requires_explicit_offline_confirmation(
    tmp_path: Path,
) -> None:
    key = "ABCD1234"
    markdown = _write_paper(
        tmp_path,
        key,
        f"![image](image/{key}-fig01.png)\n",
    )
    source = _write_flat_image(tmp_path, f"{key}-fig01.png", b"original")
    before = _snapshot(tmp_path)

    with pytest.raises(ValueError, match="confirm_vault_offline=True"):
        MinerUImageMigrationService(tmp_path).migrate(
            dry_run=False,
            apply=True,
            cleanup_legacy=True,
            transaction_id="missing-offline-confirmation",
        )

    assert _snapshot(tmp_path) == before
    assert source.read_bytes() == b"original"
    assert f"image/{key}-fig01.png" in markdown.read_text(encoding="utf-8")


@pytest.mark.parametrize("changed_file", ["markdown", "image"])
def test_apply_guard_rejects_files_changed_after_planning(
    changed_file: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    key = "ABCD1234"
    markdown = _write_paper(
        tmp_path,
        key,
        f"![image](image/{key}-fig01.png)\n",
    )
    source = _write_flat_image(tmp_path, f"{key}-fig01.png", b"original")

    class MutatingItemLock:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def __enter__(self) -> MutatingItemLock:
            if changed_file == "markdown":
                markdown.write_text(
                    markdown.read_text(encoding="utf-8") + "\nUSER-CONCURRENT-EDIT\n",
                    encoding="utf-8",
                )
            else:
                source.write_bytes(b"changed")
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    monkeypatch.setattr(migration_module, "ItemLock", MutatingItemLock)

    with pytest.raises(TransactionError, match="changed after planning"):
        MinerUImageMigrationService(tmp_path).migrate(
            dry_run=False,
            apply=True,
            transaction_id=f"changed-{changed_file}",
        )

    assert source.exists()
    assert not (tmp_path / IMAGE_ROOT / key / source.name).exists()
    if changed_file == "markdown":
        assert "USER-CONCURRENT-EDIT" in markdown.read_text(encoding="utf-8")
    else:
        assert source.read_bytes() == b"changed"


@pytest.mark.parametrize(
    "external_reference",
    [
        "![shared](Literature/attachment/MinerU/image/ABCD1234-fig01.png)\n",
        "![[ABCD1234-fig01.png|shared figure]]\n",
        '<img src="Literature/attachment/MinerU/image/ABCD1234-fig01.png">\n',
    ],
    ids=["markdown", "wiki", "html"],
)
def test_apply_guard_rejects_external_reference_added_after_planning(
    external_reference: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    key = "ABCD1234"
    markdown = _write_paper(
        tmp_path,
        key,
        f"![owner](image/{key}-fig01.png)\n",
    )
    source = _write_flat_image(tmp_path, f"{key}-fig01.png", b"original")
    external = tmp_path / "Concurrent user note.md"
    transaction_id = "external-reference-race"
    original_markdown = markdown.read_bytes()

    class ReferencingItemLock:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def __enter__(self) -> ReferencingItemLock:
            external.write_text(external_reference, encoding="utf-8")
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    monkeypatch.setattr(migration_module, "ItemLock", ReferencingItemLock)

    with pytest.raises(TransactionError, match="reference safety changed after planning"):
        MinerUImageMigrationService(tmp_path).migrate(
            dry_run=False,
            apply=True,
            transaction_id=transaction_id,
            cleanup_legacy=True,
            confirm_vault_offline=True,
        )

    assert external.read_text(encoding="utf-8") == external_reference
    assert markdown.read_bytes() == original_markdown
    assert source.read_bytes() == b"original"
    assert not (tmp_path / IMAGE_ROOT / key / source.name).exists()
    assert not (
        tmp_path / ".obsidian-vault-mcp" / "staging" / transaction_id
    ).exists()
    assert not (
        tmp_path / ".obsidian-vault-mcp" / "backups" / transaction_id
    ).exists()


@pytest.mark.parametrize("scan_failure", ["incomplete", "unreadable"])
def test_apply_guard_rejects_reference_scan_failure_after_planning(
    scan_failure: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    key = "ABCD1234"
    markdown = _write_paper(
        tmp_path,
        key,
        f"![owner](image/{key}-fig01.png)\n",
    )
    source = _write_flat_image(tmp_path, f"{key}-fig01.png", b"original")
    external = tmp_path / "Existing user note.md"
    external.write_text("# Safe before commit\n", encoding="utf-8")
    external_relative = external.relative_to(tmp_path).as_posix()
    transaction_id = f"reference-scan-{scan_failure}"
    original_markdown = markdown.read_bytes()
    state = {"guard": False}
    service = MinerUImageMigrationService(tmp_path)
    original_scan = service.fs.scan_owned_files
    original_read = service.fs.read_text_owned

    def guarded_scan(*args: object, **kwargs: object) -> tuple[list[str], list[str]]:
        files, rejected = original_scan(*args, **kwargs)
        if state["guard"] and scan_failure == "incomplete":
            return files, [external_relative]
        return files, rejected

    def guarded_read(relative: str | os.PathLike[str]) -> str:
        if (
            state["guard"]
            and scan_failure == "unreadable"
            and os.fspath(relative) == external_relative
        ):
            raise UnicodeError("concurrent non-UTF-8 content")
        return original_read(relative)

    class GuardedItemLock:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def __enter__(self) -> GuardedItemLock:
            state["guard"] = True
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    monkeypatch.setattr(service.fs, "scan_owned_files", guarded_scan)
    monkeypatch.setattr(service.fs, "read_text_owned", guarded_read)
    monkeypatch.setattr(migration_module, "ItemLock", GuardedItemLock)

    with pytest.raises(TransactionError, match="reference safety changed after planning"):
        service.migrate(
            dry_run=False,
            apply=True,
            transaction_id=transaction_id,
            cleanup_legacy=True,
            confirm_vault_offline=True,
        )

    assert markdown.read_bytes() == original_markdown
    assert source.read_bytes() == b"original"
    assert external.read_text(encoding="utf-8") == "# Safe before commit\n"
    assert not (tmp_path / IMAGE_ROOT / key / source.name).exists()
    assert not (
        tmp_path / ".obsidian-vault-mcp" / "staging" / transaction_id
    ).exists()
    assert not (
        tmp_path / ".obsidian-vault-mcp" / "backups" / transaction_id
    ).exists()


def test_shortcut_reference_is_rewritten_without_losing_definition_title(
    tmp_path: Path,
) -> None:
    key = "ABCD1234"
    markdown = _write_paper(
        tmp_path,
        key,
        (
            "![figure]\n\n"
            f'[figure]: image/{key}-fig01.png "Important definition title"\n'
        ),
    )
    source = _write_flat_image(tmp_path, f"{key}-fig01.png")

    report = MinerUImageMigrationService(tmp_path).migrate(
        dry_run=False,
        apply=True,
        transaction_id="shortcut",
        cleanup_legacy=True,
        confirm_vault_offline=True,
    )

    text = markdown.read_text(encoding="utf-8")
    assert report["status"] == "committed"
    assert "![figure]\n" in text
    assert (
        f'[figure]: image/{key}/{key}-fig01.png "Important definition title"'
        in text
    )
    assert not source.exists()


def test_html_legacy_image_blocks_the_whole_paper_and_requests_reparse(
    tmp_path: Path,
) -> None:
    key = "ABCD1234"
    markdown = _write_paper(
        tmp_path,
        key,
        f'<img alt="figure" src="image/{key}-fig01.png">\n',
    )
    source = _write_flat_image(tmp_path, f"{key}-fig01.png")
    before = markdown.read_text(encoding="utf-8")

    report = MinerUImageMigrationService(tmp_path).migrate(
        dry_run=False,
        apply=True,
        transaction_id="html",
    )

    assert report["status"] == "noop"
    assert report["movedImages"] == []
    assert report["rewrittenMarkdown"] == []
    assert report["reparseZoteroKeys"] == [key]
    assert "html-flat-image-reference" in {
        entry["reason"] for entry in report["skipped"]
    }
    assert source.exists()
    assert markdown.read_text(encoding="utf-8") == before


def test_reference_from_another_vault_note_blocks_the_owner_migration(
    tmp_path: Path,
) -> None:
    key = "ABCD1234"
    markdown = _write_paper(
        tmp_path,
        key,
        f"![owner](image/{key}-fig01.png)\n",
    )
    source = _write_flat_image(tmp_path, f"{key}-fig01.png")
    external = tmp_path / "Literature" / "User Notes.md"
    external.parent.mkdir(parents=True, exist_ok=True)
    external.write_text(
        f"![shared](attachment/MinerU/image/{key}-fig01.png)\n",
        encoding="utf-8",
    )
    before_markdown = markdown.read_text(encoding="utf-8")
    before_external = external.read_text(encoding="utf-8")

    report = MinerUImageMigrationService(tmp_path).migrate(
        dry_run=False,
        apply=True,
        transaction_id="external-reference",
        cleanup_legacy=True,
        confirm_vault_offline=True,
    )

    assert report["status"] == "noop"
    assert report["movedImages"] == []
    assert report["rewrittenMarkdown"] == []
    assert report["reparseZoteroKeys"] == [key]
    assert any(
        entry.get("path") == "Literature/User Notes.md"
        and entry.get("imagePath")
        == f"Literature/attachment/MinerU/image/{key}-fig01.png"
        and entry["reason"] == "external-flat-image-reference"
        for entry in report["skipped"]
    )
    assert source.exists()
    assert not (tmp_path / IMAGE_ROOT / key / source.name).exists()
    assert markdown.read_text(encoding="utf-8") == before_markdown
    assert external.read_text(encoding="utf-8") == before_external


def test_wiki_basename_reference_elsewhere_in_vault_blocks_migration(
    tmp_path: Path,
) -> None:
    key = "ABCD1234"
    _write_paper(tmp_path, key, f"![owner](image/{key}-fig01.png)\n")
    source = _write_flat_image(tmp_path, f"{key}-fig01.png")
    external = tmp_path / "Notes" / "Figure reuse.md"
    external.parent.mkdir(parents=True)
    external.write_text(f"![[{key}-fig01.png|shared figure]]\n", encoding="utf-8")

    report = MinerUImageMigrationService(tmp_path).migrate(
        dry_run=False,
        apply=True,
        transaction_id="external-wiki-reference",
        cleanup_legacy=True,
        confirm_vault_offline=True,
    )

    assert report["status"] == "noop"
    assert report["movedImages"] == []
    assert source.exists()
    assert any(
        entry.get("path") == "Notes/Figure reuse.md"
        and entry["reason"] == "external-flat-image-reference"
        for entry in report["skipped"]
    )


def test_inline_title_and_wiki_image_size_survive_migration(tmp_path: Path) -> None:
    key = "ABCD1234"
    markdown = _write_paper(
        tmp_path,
        key,
        (
            f'![figure](image/{key}-fig01.png "Important title")\n\n'
            f"![[image/{key}-fig01.png|300]]\n"
        ),
    )
    _write_flat_image(tmp_path, f"{key}-fig01.png")

    report = MinerUImageMigrationService(tmp_path).migrate(
        dry_run=False,
        apply=True,
        transaction_id="syntax",
    )

    text = markdown.read_text(encoding="utf-8")
    assert report["rewrittenMarkdown"][0]["referenceCount"] == 2
    assert (
        f'![figure](image/{key}/{key}-fig01.png "Important title")'
        in text
    )
    assert f"![[image/{key}/{key}-fig01.png|300]]" in text


def test_reference_without_destination_span_blocks_the_paper(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    key = "ABCD1234"
    markdown = _write_paper(
        tmp_path,
        key,
        f"![image](image/{key}-fig01.png)\n",
    )
    source = _write_flat_image(tmp_path, f"{key}-fig01.png")
    parse_references = migration_module.parse_image_references

    def without_destination_span(text: str) -> tuple[object, ...]:
        return tuple(
            replace(
                reference,
                destination_start=None,
                destination_end=None,
            )
            for reference in parse_references(text)
        )

    monkeypatch.setattr(
        migration_module,
        "parse_image_references",
        without_destination_span,
    )

    report = MinerUImageMigrationService(tmp_path).migrate(
        dry_run=False,
        apply=True,
        transaction_id="unrewritable",
    )

    assert report["status"] == "noop"
    assert report["reparseZoteroKeys"] == [key]
    assert "unrewritable-flat-reference" in {
        entry["reason"] for entry in report["skipped"]
    }
    assert source.exists()
    assert f"image/{key}-fig01.png" in markdown.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("collision", "reason"),
    [
        ("key-folder", "key-folder-case-collision"),
        ("target-file", "target-case-collision"),
    ],
)
def test_existing_case_variant_targets_block_the_paper(
    collision: str,
    reason: str,
    tmp_path: Path,
) -> None:
    _enable_case_sensitive_directory(tmp_path)
    key = "ABCD1234"
    _write_paper(tmp_path, key, f"![image](image/{key}-fig01.png)\n")
    source = _write_flat_image(tmp_path, f"{key}-fig01.png", b"source")
    if collision == "key-folder":
        existing = tmp_path / IMAGE_ROOT / key.lower() / "keep.txt"
    else:
        existing = tmp_path / IMAGE_ROOT / key / f"{key.lower()}-FIG01.PNG"
    existing.parent.mkdir(parents=True, exist_ok=True)
    existing.write_bytes(b"preexisting")

    report = MinerUImageMigrationService(tmp_path).migrate(
        dry_run=False,
        apply=True,
        transaction_id=f"case-{collision}",
    )

    target = tmp_path / IMAGE_ROOT / key / source.name
    assert report["status"] == "noop"
    assert report["movedImages"] == []
    assert reason in {entry["reason"] for entry in report["skipped"]}
    assert source.read_bytes() == b"source"
    assert existing.read_bytes() == b"preexisting"
    target_entries = (
        {entry.name for entry in target.parent.iterdir()}
        if target.parent.exists()
        else set()
    )
    assert target.name not in target_entries


def test_ambiguous_or_unowned_flat_images_are_skipped(tmp_path: Path) -> None:
    key = "ABCD1234"
    _write_paper(tmp_path, key, "# No image references\n")
    ambiguous = _write_flat_image(tmp_path, f"{key}-fig1.png", b"ambiguous")
    unowned = _write_flat_image(tmp_path, "UNKN5678-fig01.png", b"unowned")
    before = _snapshot(tmp_path)

    report = MinerUImageMigrationService(tmp_path).migrate(
        transaction_id="mineru-images-ambiguous"
    )

    assert report["movedImages"] == []
    assert report["rewrittenMarkdown"] == []
    assert {
        entry["reason"] for entry in report["skipped"]
    } >= {
        "unrecognized-flat-image-name",
        "image-ownership-uncertain",
    }
    assert ambiguous.exists()
    assert unowned.exists()
    assert _snapshot(tmp_path) == before


def test_missing_flat_reference_blocks_that_paper_and_requests_reparse(
    tmp_path: Path,
) -> None:
    key = "ABCD1234"
    markdown = _write_paper(
        tmp_path,
        key,
        (
            f"![present](image/{key}-fig01.png)\n"
            f"![missing](image/{key}-fig02.png)\n"
        ),
    )
    present = _write_flat_image(tmp_path, f"{key}-fig01.png", b"present")
    before = _snapshot(tmp_path)

    report = MinerUImageMigrationService(tmp_path).migrate(
        transaction_id="mineru-images-missing"
    )

    assert report["status"] == "dry-run"
    assert report["changeCount"] == 0
    assert report["movedImages"] == []
    assert report["rewrittenMarkdown"] == []
    assert report["reparseZoteroKeys"] == [key]
    assert report["missingReferencedImages"] == [
        {
            "zoteroKey": key,
            "markdownPath": f"Literature/attachment/MinerU/{key}.md",
            "imagePath": f"Literature/attachment/MinerU/image/{key}-fig02.png",
        }
    ]
    assert present.exists()
    assert f"image/{key}-fig01.png" in markdown.read_text(encoding="utf-8")
    assert _snapshot(tmp_path) == before


def test_key_folder_link_or_junction_is_never_traversed(tmp_path: Path) -> None:
    key = "ABCD1234"
    _write_paper(tmp_path, key, f"![image](image/{key}-fig01.png)\n")
    source = _write_flat_image(tmp_path, f"{key}-fig01.png", b"source")
    external = tmp_path / "junction-target"
    external.mkdir()
    marker = external / "keep.txt"
    marker.write_text("keep", encoding="utf-8")
    key_folder = tmp_path / IMAGE_ROOT / key

    if os.name == "nt":
        created = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(key_folder), str(external)],
            capture_output=True,
            check=False,
        )
        if created.returncode != 0:
            pytest.skip("Windows junction creation is unavailable")
    else:
        try:
            key_folder.symlink_to(external, target_is_directory=True)
        except OSError:
            pytest.skip("directory symlink creation is unavailable")

    try:
        report = MinerUImageMigrationService(tmp_path).migrate(
            dry_run=False,
            apply=True,
            transaction_id="mineru-images-junction",
        )

        assert report["status"] == "noop"
        assert report["movedImages"] == []
        assert "key-folder-reparse-point" in {
            entry["reason"] for entry in report["skipped"]
        }
        assert source.read_bytes() == b"source"
        assert marker.read_text(encoding="utf-8") == "keep"
        assert not (external / f"{key}-fig01.png").exists()
    finally:
        if key_folder.exists() or key_folder.is_symlink():
            if os.name == "nt":
                os.rmdir(key_folder)
            else:
                key_folder.unlink()


def test_cli_mineru_image_migration_requires_explicit_apply(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    calls: list[dict[str, object]] = []

    class FakeMigration:
        def __init__(self, vault_path: Path) -> None:
            self.vault_path = vault_path

        def migrate(self, **kwargs: object) -> dict[str, object]:
            calls.append({"vault_path": self.vault_path, **kwargs})
            return {
                "ok": True,
                "status": "dry-run" if kwargs["dry_run"] else "committed",
            }

    (tmp_path / ".obsidian").mkdir()
    monkeypatch.setitem(main.__globals__, "MinerUImageMigrationService", FakeMigration)

    preview = [
        "migrate",
        "mineru-images-v2-to-v3",
        "--vault-path",
        str(tmp_path),
    ]
    assert main(preview) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "dry-run"
    assert calls[-1]["dry_run"] is True
    assert calls[-1]["apply"] is False
    assert calls[-1]["cleanup_legacy"] is False
    assert calls[-1]["confirm_vault_offline"] is False

    applied = [
        "migrate",
        "mineru-images-v2-to-v3",
        "--vault-path",
        str(tmp_path),
        "--apply",
        "--transaction-id",
        "mineru-images-cli",
    ]
    assert main(applied) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "committed"
    assert calls[-1]["dry_run"] is False
    assert calls[-1]["apply"] is True
    assert calls[-1]["transaction_id"] == "mineru-images-cli"
    assert calls[-1]["cleanup_legacy"] is False
    assert calls[-1]["confirm_vault_offline"] is False

    destructive = [
        "migrate",
        "mineru-images-v2-to-v3",
        "--vault-path",
        str(tmp_path),
        "--apply",
        "--cleanup-legacy",
        "--confirm-vault-offline",
        "--transaction-id",
        "mineru-images-cleanup",
    ]
    assert main(destructive) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "committed"
    assert calls[-1]["cleanup_legacy"] is True
    assert calls[-1]["confirm_vault_offline"] is True


def test_mineru_image_migration_rejects_unimplemented_conflict_policies(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="only conflict_policy preserve-user"):
        MinerUImageMigrationService(tmp_path).migrate(conflict_policy="rename")
