from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

import pytest

from obsidian_vault_mcp.application.import_service import ImportService
from obsidian_vault_mcp.application.mineru_service import MinerUService
from obsidian_vault_mcp.config.loader import initialize_config, load_config, save_config
from tests.unit.test_import_identity import FakeZotero


def _create_directory_link(link: Path, target: Path) -> None:
    if os.name == "nt":
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            pytest.skip(f"could not create a Windows junction: {result.stderr or result.stdout}")
        return
    link.symlink_to(target, target_is_directory=True)


def _remove_directory_link(link: Path) -> None:
    if not os.path.lexists(link):
        return
    if os.name == "nt":
        os.rmdir(link)
    else:
        link.unlink()


class FakeMinerU:
    def __init__(self, fail: bool = False, version: str = "v1") -> None:
        self.fail = fail
        self.version = version

    def parse(self, pdf_path, output_dir, **kwargs):
        del pdf_path, kwargs
        output = Path(output_dir)
        (output / "images").mkdir(parents=True, exist_ok=True)
        (output / "images" / "raw.png").write_bytes(self.version.encode())
        (output / "paper.md").write_text(
            f"# Raw {self.version}\n\nContent {self.version}.\n\n![figure](images/raw.png)\n",
            encoding="utf-8",
        )
        if self.fail:
            raise RuntimeError("simulated MinerU failure")


def test_mineru_failure_keeps_previous_official_output_and_success_replaces_set():
    with tempfile.TemporaryDirectory() as directory:
        vault = Path(directory)
        (vault / ".obsidian").mkdir()
        initialize_config(vault)
        source_pdf = vault.parent / f"{vault.name}-source.pdf"
        source_pdf.write_bytes(b"pdf")
        zotero = FakeZotero(source_pdf)
        ImportService(vault, zotero_client=zotero).import_item("ABCD1234")
        service = MinerUService(vault, mineru_client=FakeMinerU(version="v1"))
        first = service.parse("ABCD1234")
        assert first["ok"]
        official_md = vault / "Literature" / "attachment" / "MinerU" / "ABCD1234.md"
        official_image = (
            vault
            / "Literature"
            / "attachment"
            / "MinerU"
            / "image"
            / "ABCD1234"
            / "ABCD1234-fig01.png"
        )
        before_md = official_md.read_bytes()
        before_image = official_image.read_bytes()

        failed = MinerUService(vault, mineru_client=FakeMinerU(fail=True, version="broken")).parse("ABCD1234")
        assert not failed["ok"]
        assert failed["stage"] == "extract"
        assert failed["stateTransaction"]["transactionId"] != failed["transactionId"]
        assert official_md.read_bytes() == before_md
        assert official_image.read_bytes() == before_image
        state = json.loads((vault / ".obsidian-vault-mcp" / "state" / "items" / "ABCD1234.json").read_text(encoding="utf-8"))
        assert state["status"] == "error"

        second = MinerUService(vault, mineru_client=FakeMinerU(version="v2")).parse("ABCD1234")
        assert second["ok"]
        assert b"v2" in official_md.read_bytes()
        assert official_image.read_bytes() == b"v2"
        note = (vault / "Literature" / "ABCD1234.md").read_text(encoding="utf-8")
        assert "[[Literature/attachment/MinerU/ABCD1234]]" in note
        assert str(source_pdf) not in note
        repeated = ImportService(vault, zotero_client=zotero).import_item("ABCD1234", dry_run=True)
        assert repeated["changed"] is False
        source_pdf.unlink()


def test_remove_mineru_output_is_backed_up_and_rollback_restores_it():
    with tempfile.TemporaryDirectory() as directory:
        vault = Path(directory)
        (vault / ".obsidian").mkdir()
        initialize_config(vault)
        source_pdf = vault.parent / f"{vault.name}-source.pdf"
        source_pdf.write_bytes(b"pdf")
        ImportService(vault, zotero_client=FakeZotero(source_pdf)).import_item("ABCD1234")
        service = MinerUService(vault, mineru_client=FakeMinerU())
        service.parse("ABCD1234")
        removed = service.remove_output("ABCD1234")
        assert removed["ok"]
        assert not (vault / "Literature" / "attachment" / "MinerU" / "ABCD1234.md").exists()
        service.transactions.rollback(removed["transactionId"])
        assert (vault / "Literature" / "attachment" / "MinerU" / "ABCD1234.md").exists()
        source_pdf.unlink()


def test_mineru_image_links_are_relative_to_configured_output_folders():
    with tempfile.TemporaryDirectory() as directory:
        vault = Path(directory)
        (vault / ".obsidian").mkdir()
        initialize_config(vault)
        config = load_config(vault)
        config["mineru"]["imageFolder"] = "Extracted/Assets/Figures"
        source_pdf = vault.parent / f"{vault.name}-source.pdf"
        source_pdf.write_bytes(b"pdf")
        ImportService(vault, zotero_client=FakeZotero(source_pdf)).import_item("ABCD1234")

        result = MinerUService(vault, mineru_client=FakeMinerU(), config=config).parse("ABCD1234")

        assert result["ok"]
        markdown = (vault / "Literature" / "attachment" / "MinerU" / "ABCD1234.md").read_text(encoding="utf-8")
        assert "![figure](../../../Extracted/Assets/Figures/ABCD1234/ABCD1234-fig01.png)" in markdown
        assert (vault / "Extracted" / "Assets" / "Figures" / "ABCD1234" / "ABCD1234-fig01.png").is_file()
        source_pdf.unlink()


def test_parse_and_remove_use_configured_mineru_markdown_path():
    with tempfile.TemporaryDirectory() as directory:
        vault = Path(directory)
        (vault / ".obsidian").mkdir()
        initialize_config(vault)
        config = load_config(vault)
        config["mineru"]["markdownFolder"] = "Extracted/Markdown"
        config["naming"]["mineruMarkdown"] = (
            "parsed-{shortTitle}-{zoteroKey}.md"
        )
        save_config(vault, config)
        source_pdf = vault.parent / f"{vault.name}-custom-mineru.pdf"
        source_pdf.write_bytes(b"pdf")
        try:
            ImportService(vault, zotero_client=FakeZotero(source_pdf)).import_item("ABCD1234")

            parsed = MinerUService(
                vault,
                mineru_client=FakeMinerU(),
            ).parse("ABCD1234")

            custom_path = (
                vault
                / "Extracted"
                / "Markdown"
                / "parsed-Original Title-ABCD1234.md"
            )
            assert parsed["ok"]
            assert parsed["mineruPath"] == (
                "Extracted/Markdown/parsed-Original Title-ABCD1234.md"
            )
            assert custom_path.is_file()
            assert not (
                vault / "Literature" / "attachment" / "MinerU" / "ABCD1234.md"
            ).exists()
            note = (vault / "Literature" / "ABCD1234.md").read_text(
                encoding="utf-8"
            )
            assert (
                "[[Extracted/Markdown/parsed-Original Title-ABCD1234]]"
                in note
            )
            state_path = (
                vault
                / ".obsidian-vault-mcp"
                / "state"
                / "items"
                / "ABCD1234.json"
            )
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state.pop("mineruPath")
            state_path.write_text(
                json.dumps(state, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            removed = MinerUService(vault).remove_output("ABCD1234")

            assert removed["ok"]
            assert removed["mineruPath"] == (
                "Extracted/Markdown/parsed-Original Title-ABCD1234.md"
            )
            assert not custom_path.exists()
            MinerUService(vault).transactions.rollback(removed["transactionId"])
            assert custom_path.is_file()
        finally:
            source_pdf.unlink(missing_ok=True)


def test_remove_and_reparse_are_isolated_to_the_requested_key():
    with tempfile.TemporaryDirectory() as directory:
        vault = Path(directory)
        (vault / ".obsidian").mkdir()
        initialize_config(vault)
        sources = {}
        for key in ("ABCD1234", "WXYZ5678"):
            source = vault.parent / f"{vault.name}-{key}.pdf"
            source.write_bytes(key.encode())
            sources[key] = source
            ImportService(vault, zotero_client=FakeZotero(source)).import_item(key)
            assert MinerUService(vault, mineru_client=FakeMinerU(version=key)).parse(key)["ok"]

        image_root = vault / "Literature" / "attachment" / "MinerU" / "image"
        b_image = image_root / "WXYZ5678" / "WXYZ5678-fig01.png"
        before_b = b_image.read_bytes()
        (image_root / "ABCD1234" / "ABCD1234-old.png").write_bytes(b"old")

        reparsed = MinerUService(vault, mineru_client=FakeMinerU(version="new-a")).parse("ABCD1234")
        assert reparsed["ok"]
        assert not (image_root / "ABCD1234" / "ABCD1234-old.png").exists()
        assert b_image.read_bytes() == before_b

        removed = MinerUService(vault).remove_output("ABCD1234")
        assert removed["ok"]
        assert not (image_root / "ABCD1234" / "ABCD1234-fig01.png").exists()
        assert b_image.read_bytes() == before_b
        for source in sources.values():
            source.unlink()


def test_missing_referenced_image_fails_without_committing_official_output():
    class MissingImageMinerU:
        def parse(self, pdf_path, output_dir, **kwargs):
            del pdf_path, kwargs
            output = Path(output_dir)
            output.mkdir(parents=True, exist_ok=True)
            (output / "paper.md").write_text("![missing](images/missing.png)\n", encoding="utf-8")

    with tempfile.TemporaryDirectory() as directory:
        vault = Path(directory)
        (vault / ".obsidian").mkdir()
        initialize_config(vault)
        source = vault.parent / f"{vault.name}-missing.pdf"
        source.write_bytes(b"pdf")
        ImportService(vault, zotero_client=FakeZotero(source)).import_item("ABCD1234")
        result = MinerUService(vault, mineru_client=MissingImageMinerU()).parse("ABCD1234")

        assert not result["ok"]
        assert result["stage"] == "normalize"
        assert not (vault / "Literature" / "attachment" / "MinerU" / "ABCD1234.md").exists()
        assert not (vault / "Literature" / "attachment" / "MinerU" / "image" / "ABCD1234").exists()
        assert not (vault / ".obsidian-vault-mcp" / "state" / "evidence").exists()
        assert not (vault / ".obsidian-vault-mcp" / "state" / "coverage").exists()
        assert not (vault / ".obsidian-vault-mcp" / "state" / "uncertainties").exists()
        source.unlink()


def test_parse_and_remove_refuse_junctioned_item_image_folder() -> None:
    with tempfile.TemporaryDirectory() as directory:
        vault = Path(directory)
        (vault / ".obsidian").mkdir()
        initialize_config(vault)
        source = vault.parent / f"{vault.name}-junction-image.pdf"
        source.write_bytes(b"pdf")
        ImportService(vault, zotero_client=FakeZotero(source)).import_item("ABCD1234")
        image_root = vault / "Literature" / "attachment" / "MinerU" / "image"
        victim = image_root / "WXYZ5678"
        victim.mkdir(parents=True)
        marker = victim / "WXYZ5678-keep.png"
        marker.write_bytes(b"keep")
        linked = image_root / "ABCD1234"
        _create_directory_link(linked, victim)
        try:
            service = MinerUService(vault, mineru_client=FakeMinerU(version="unsafe"))
            parsed = service.parse("ABCD1234", transaction_id="image-junction-parse")

            assert not parsed["ok"]
            assert "linked or reparse" in parsed["error"]
            assert marker.read_bytes() == b"keep"
            with pytest.raises(RuntimeError, match="linked or reparse"):
                service.remove_output("ABCD1234", transaction_id="image-junction-remove")
            assert marker.read_bytes() == b"keep"
        finally:
            _remove_directory_link(linked)
            source.unlink()


def test_transaction_staging_junction_is_rejected_before_mineru_runs() -> None:
    class RecordingMinerU:
        called = False

        def parse(self, *_args, **_kwargs):
            self.called = True
            raise RuntimeError("MinerU client must not run")

    with tempfile.TemporaryDirectory() as directory:
        vault = Path(directory)
        (vault / ".obsidian").mkdir()
        initialize_config(vault)
        source = vault.parent / f"{vault.name}-junction-transaction.pdf"
        source.write_bytes(b"pdf")
        ImportService(vault, zotero_client=FakeZotero(source)).import_item("ABCD1234")
        staging = vault / ".obsidian-vault-mcp" / "staging"
        staging.mkdir(parents=True, exist_ok=True)
        victim = vault / "other-vault-directory"
        victim.mkdir()
        marker = victim / "keep.txt"
        marker.write_text("keep", encoding="utf-8")
        linked = staging / "linked-transaction"
        _create_directory_link(linked, victim)
        client = RecordingMinerU()
        try:
            result = MinerUService(vault, mineru_client=client).parse(
                "ABCD1234",
                transaction_id="linked-transaction",
            )

            assert not result["ok"]
            assert not client.called
            assert "linked or reparse" in result["error"]
            assert "linked or reparse" in result["cleanupError"]
            assert marker.read_text(encoding="utf-8") == "keep"
        finally:
            _remove_directory_link(linked)
            source.unlink()


def test_cleanup_refusal_preserves_original_parse_error_and_victim() -> None:
    class JunctionThenFailMinerU:
        def __init__(self, victim: Path) -> None:
            self.victim = victim

        def parse(self, _pdf_path, output_dir, **_kwargs):
            output = Path(output_dir)
            output.parent.mkdir(parents=True, exist_ok=True)
            _create_directory_link(output, self.victim)
            raise RuntimeError("original MinerU parse failure")

    with tempfile.TemporaryDirectory() as directory:
        vault = Path(directory)
        (vault / ".obsidian").mkdir()
        initialize_config(vault)
        source = vault.parent / f"{vault.name}-junction-cleanup.pdf"
        source.write_bytes(b"pdf")
        ImportService(vault, zotero_client=FakeZotero(source)).import_item("ABCD1234")
        victim = vault / "other-vault-output"
        victim.mkdir()
        marker = victim / "keep.txt"
        marker.write_text("keep", encoding="utf-8")
        linked = vault / ".obsidian-vault-mcp" / "staging" / "cleanup-junction" / "mineru"
        try:
            result = MinerUService(vault, mineru_client=JunctionThenFailMinerU(victim)).parse(
                "ABCD1234",
                transaction_id="cleanup-junction",
            )

            assert not result["ok"]
            assert result["error"] == "original MinerU parse failure"
            assert "linked or reparse" in result["cleanupError"]
            assert marker.read_text(encoding="utf-8") == "keep"
        finally:
            _remove_directory_link(linked)
            source.unlink()
