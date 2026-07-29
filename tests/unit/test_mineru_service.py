from __future__ import annotations

import hashlib
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


class AssetMinerU:
    def __init__(self, version: str = "v1", *, omit_second: bool = False, broken_reference: bool = False) -> None:
        self.version = version
        self.omit_second = omit_second
        self.broken_reference = broken_reference

    def parse(self, pdf_path, output_dir, **kwargs):
        del pdf_path, kwargs
        output = Path(output_dir)
        images = output / "images"
        images.mkdir(parents=True, exist_ok=True)
        (images / "first.png").write_bytes(f"first-{self.version}".encode())
        if not self.omit_second:
            (images / "second.jpg").write_bytes(f"second-{self.version}".encode())
        (images / "candidate.webp").write_bytes(f"candidate-{self.version}".encode())
        reference = "images/missing.png" if self.broken_reference else "images/first.png"
        body = f"# Raw\n\n![first]({reference})\n"
        if not self.omit_second:
            body += "\n![second](images/second.jpg)\n"
        (output / "paper.md").write_text(body, encoding="utf-8")


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
        evidence_path = vault / ".obsidian-vault-mcp" / "state" / "evidence" / "ABCD1234.json"
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        assert first["evidencePath"] == ".obsidian-vault-mcp/state/evidence/ABCD1234.json"
        assert first["evidenceCount"] == len(evidence["chunks"])
        transaction_manifest = json.loads(
            (vault / ".obsidian-vault-mcp" / "backups" / first["transactionId"] / "manifest.json").read_text(encoding="utf-8")
        )
        assert first["evidencePath"] in {operation["path"] for operation in transaction_manifest["operations"]}
        official_md = vault / "Literature" / "attachment" / "MinerU" / "ABCD1234.md"
        official_image = vault / "Literature" / "attachment" / "MinerU" / "image" / "ABCD1234-fig01.png"
        markdown = official_md.read_text(encoding="utf-8")
        assert all(markdown.count(f"^{chunk['blockId']}") == 1 for chunk in evidence["chunks"])
        image_manifest = json.loads((vault / first["manifestPath"]).read_text(encoding="utf-8"))
        assert image_manifest["sourceMarkdownSha256"] == hashlib.sha256(official_md.read_bytes()).hexdigest()
        assert evidence["sourceMarkdownSha256"] == hashlib.sha256(official_md.read_bytes()).hexdigest()
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
        evidence_path = vault / ".obsidian-vault-mcp" / "state" / "evidence" / "ABCD1234.json"
        assert evidence_path.is_file()
        removed = service.remove_output("ABCD1234")
        assert removed["ok"]
        assert not (vault / "Literature" / "attachment" / "MinerU" / "ABCD1234.md").exists()
        assert not evidence_path.exists()
        service.transactions.rollback(removed["transactionId"])
        assert (vault / "Literature" / "attachment" / "MinerU" / "ABCD1234.md").exists()
        assert evidence_path.is_file()
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


def test_mineru_manifest_candidates_cleanup_and_rollback_share_one_transaction():
    with tempfile.TemporaryDirectory() as directory:
        vault = Path(directory)
        (vault / ".obsidian").mkdir()
        initialize_config(vault)
        source_pdf = vault.parent / f"{vault.name}-source.pdf"
        source_pdf.write_bytes(b"pdf")
        ImportService(vault, zotero_client=FakeZotero(source_pdf)).import_item("ABCD1234")

        service = MinerUService(vault, mineru_client=AssetMinerU("v1"))
        first = service.parse("ABCD1234")
        assert first["ok"]
        manifest_path = vault / ".obsidian-vault-mcp" / "cache" / "mineru-assets" / "ABCD1234" / "manifest.json"
        first_manifest = manifest_path.read_bytes()
        manifest = json.loads(first_manifest)
        assert first["manifestPath"] == ".obsidian-vault-mcp/cache/mineru-assets/ABCD1234/manifest.json"
        assert first["counts"] == {"total": 3, "referenced": 2, "unlinkedCandidates": 1, "invalid": 0}
        candidate = vault / manifest["assets"][2]["cachePath"]
        assert candidate.read_bytes() == b"candidate-v1"
        second_formal = vault / "Literature" / "attachment" / "MinerU" / "image" / "ABCD1234-fig02.jpg"
        assert second_formal.is_file()
        repeated = service.parse("ABCD1234")
        assert repeated["status"] == "noop"
        assert manifest_path.read_bytes() == first_manifest

        unrelated = second_formal.parent / "WXYZ5678-ABCD1234-fig99.png"
        unrelated.write_bytes(b"other item")
        before_update = {
            "manifest": first_manifest,
            "candidate": candidate.read_bytes(),
            "second": second_formal.read_bytes(),
        }

        service.client = AssetMinerU("v2", omit_second=True)
        updated = service.parse("ABCD1234")
        assert updated["ok"]
        assert not second_formal.exists()
        assert unrelated.read_bytes() == b"other item"
        updated_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        updated_candidate = vault / next(asset["cachePath"] for asset in updated_manifest["assets"] if asset["status"] == "unlinked_candidate")
        assert updated_candidate.read_bytes() == b"candidate-v2"

        rolled_back = service.transactions.rollback(updated["transactionId"])
        assert rolled_back["status"] == "rolled-back"
        assert manifest_path.read_bytes() == before_update["manifest"]
        assert candidate.read_bytes() == before_update["candidate"]
        assert second_formal.read_bytes() == before_update["second"]
        assert unrelated.read_bytes() == b"other item"
        source_pdf.unlink()


def test_normalization_failure_preserves_previous_manifest_markdown_images_and_candidates():
    with tempfile.TemporaryDirectory() as directory:
        vault = Path(directory)
        (vault / ".obsidian").mkdir()
        initialize_config(vault)
        source_pdf = vault.parent / f"{vault.name}-source.pdf"
        source_pdf.write_bytes(b"pdf")
        ImportService(vault, zotero_client=FakeZotero(source_pdf)).import_item("ABCD1234")
        service = MinerUService(vault, mineru_client=AssetMinerU("v1"))
        assert service.parse("ABCD1234")["ok"]

        roots = (
            vault / "Literature" / "attachment" / "MinerU",
            vault / ".obsidian-vault-mcp" / "cache" / "mineru-assets" / "ABCD1234",
        )

        def snapshot() -> dict[str, bytes]:
            return {
                path.relative_to(vault).as_posix(): path.read_bytes()
                for root in roots
                for path in root.rglob("*")
                if path.is_file()
            }

        before = snapshot()
        service.client = AssetMinerU("broken", broken_reference=True)
        failed = service.parse("ABCD1234")
        assert not failed["ok"]
        assert failed["stage"] == "normalize"
        assert snapshot() == before
        source_pdf.unlink()


def test_remove_mineru_output_removes_and_rollback_restores_manifest_and_candidates():
    with tempfile.TemporaryDirectory() as directory:
        vault = Path(directory)
        (vault / ".obsidian").mkdir()
        initialize_config(vault)
        source_pdf = vault.parent / f"{vault.name}-source.pdf"
        source_pdf.write_bytes(b"pdf")
        ImportService(vault, zotero_client=FakeZotero(source_pdf)).import_item("ABCD1234")
        service = MinerUService(vault, mineru_client=AssetMinerU())
        service.parse("ABCD1234")
        asset_root = vault / ".obsidian-vault-mcp" / "cache" / "mineru-assets" / "ABCD1234"
        before = {path.relative_to(vault).as_posix(): path.read_bytes() for path in asset_root.rglob("*") if path.is_file()}

        removed = service.remove_output("ABCD1234")
        assert not any(path.is_file() for path in asset_root.rglob("*"))
        service.transactions.rollback(removed["transactionId"])
        assert {path.relative_to(vault).as_posix(): path.read_bytes() for path in asset_root.rglob("*") if path.is_file()} == before
        source_pdf.unlink()


def test_mineru_candidate_and_manifest_configuration_is_live():
    with tempfile.TemporaryDirectory() as directory:
        vault = Path(directory)
        (vault / ".obsidian").mkdir()
        initialize_config(vault)
        config = load_config(vault)
        config["mineru"]["preserveUnlinkedImageCandidates"] = False
        config["mineru"]["imageManifestEnabled"] = False
        config["mineru"]["candidateCacheFolder"] = ".obsidian-vault-mcp/cache/custom-assets"
        source_pdf = vault.parent / f"{vault.name}-source.pdf"
        source_pdf.write_bytes(b"pdf")
        ImportService(vault, zotero_client=FakeZotero(source_pdf)).import_item("ABCD1234")

        result = MinerUService(vault, mineru_client=AssetMinerU(), config=config).parse("ABCD1234")

        assert result["ok"]
        assert result["manifestPath"] == ".obsidian-vault-mcp/cache/custom-assets/ABCD1234/manifest.json"
        assert not (vault / result["manifestPath"]).exists()
        assert not (vault / ".obsidian-vault-mcp" / "cache" / "custom-assets" / "ABCD1234" / "assets").exists()
        assert result["counts"]["unlinkedCandidates"] == 0
        assert (vault / result["evidencePath"]).is_file()
        source_pdf.unlink()


def test_mineru_candidate_cache_root_change_is_transactional_and_cleans_legacy_root():
    with tempfile.TemporaryDirectory() as directory:
        vault = Path(directory)
        (vault / ".obsidian").mkdir()
        initialize_config(vault)
        source_pdf = vault.parent / f"{vault.name}-source.pdf"
        source_pdf.write_bytes(b"pdf")
        ImportService(vault, zotero_client=FakeZotero(source_pdf)).import_item("ABCD1234")

        original = MinerUService(vault, mineru_client=AssetMinerU("v1"))
        assert original.parse("ABCD1234")["ok"]
        old_root = vault / ".obsidian-vault-mcp" / "cache" / "mineru-assets" / "ABCD1234"
        old_snapshot = {
            path.relative_to(vault).as_posix(): path.read_bytes()
            for path in old_root.rglob("*")
            if path.is_file()
        }
        assert old_snapshot

        config = load_config(vault)
        config["mineru"]["candidateCacheFolder"] = ".obsidian-vault-mcp/cache/custom-assets"
        moved = MinerUService(vault, mineru_client=AssetMinerU("v2"), config=config).parse("ABCD1234")
        new_root = vault / ".obsidian-vault-mcp" / "cache" / "custom-assets" / "ABCD1234"

        assert moved["ok"]
        assert not any(path.is_file() for path in old_root.rglob("*"))
        assert any(path.is_file() for path in new_root.rglob("*"))
        state = json.loads((vault / ".obsidian-vault-mcp" / "state" / "items" / "ABCD1234.json").read_text(encoding="utf-8"))
        assert state["mineruAssetRoot"] == ".obsidian-vault-mcp/cache/custom-assets/ABCD1234"

        assert original.transactions.rollback(moved["transactionId"])["status"] == "rolled-back"
        assert {
            path.relative_to(vault).as_posix(): path.read_bytes()
            for path in old_root.rglob("*")
            if path.is_file()
        } == old_snapshot
        assert not any(path.is_file() for path in new_root.rglob("*"))
        source_pdf.unlink()
