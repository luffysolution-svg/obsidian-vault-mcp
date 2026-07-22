from __future__ import annotations

import json
import tempfile
from pathlib import Path

from obsidian_vault_mcp.application.import_service import ImportService
from obsidian_vault_mcp.application.mineru_service import MinerUService
from obsidian_vault_mcp.config.loader import initialize_config, load_config
from tests.unit.test_import_identity import FakeZotero


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
        official_image = vault / "Literature" / "attachment" / "MinerU" / "image" / "ABCD1234-fig01.png"
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
        config["mineru"]["markdownFolder"] = "Extracted/Markdown"
        config["mineru"]["imageFolder"] = "Extracted/Assets/Figures"
        source_pdf = vault.parent / f"{vault.name}-source.pdf"
        source_pdf.write_bytes(b"pdf")
        ImportService(vault, zotero_client=FakeZotero(source_pdf)).import_item("ABCD1234")

        result = MinerUService(vault, mineru_client=FakeMinerU(), config=config).parse("ABCD1234")

        assert result["ok"]
        markdown = (vault / "Extracted" / "Markdown" / "ABCD1234.md").read_text(encoding="utf-8")
        assert "![figure](../Assets/Figures/ABCD1234-fig01.png)" in markdown
        assert (vault / "Extracted" / "Assets" / "Figures" / "ABCD1234-fig01.png").is_file()
        source_pdf.unlink()
