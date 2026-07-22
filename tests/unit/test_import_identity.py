from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import obsidian_vault_mcp.application.import_service as import_service_module
from obsidian_vault_mcp.adapters.zotero.client import TransportResponse, ZoteroClient
from obsidian_vault_mcp.application.import_service import ImportService
from obsidian_vault_mcp.config import default_config
from obsidian_vault_mcp.config.loader import initialize_config, load_config


class FakeZotero:
    def __init__(self, pdf: Path) -> None:
        self.pdf = pdf
        self.title = "Original Title"
        self.version = 1

    def get_item_tree(self, key):
        return {
            "parent": {
                "key": key,
                "version": self.version,
                "itemType": "journalArticle",
                "title": self.title,
                "year": "2024",
                "journal": "Journal",
                "tags": ["CdS"],
                "doi": "10.1/example",
                "url": "https://example.test",
                "abstract": "Abstract.",
                "creators": [{"firstName": "Ada", "lastName": "Lovelace"}],
            },
            "children": {
                "notes": [{"note": "Child note."}],
                "annotations": [],
                "attachments": [{"key": "PDFKEY01", "contentType": "application/pdf", "filename": "paper.pdf", "zoteroPdfLink": "zotero://open-pdf/library/items/PDFKEY01"}],
            },
        }

    def resolve_attachment_source(self, attachment):
        return self.pdf

    def get_bibtex(self, key, **kwargs):
        return {"provider": "builtin", "bibtex": f"@article{{{key}, title={{{self.title}}}}}", "errors": []}

    def list_collection_items(self, key):
        return [{"key": "ABCD1234", "itemType": "journalArticle"}]


def test_import_service_passes_linked_attachment_base_to_zotero_client(tmp_path, monkeypatch):
    captured: dict[str, object] = {}

    class CapturingClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    config = default_config()
    config["zotero"]["linkedAttachmentBaseDir"] = str(tmp_path / "Linked PDFs")
    monkeypatch.setattr(import_service_module, "ZoteroClient", CapturingClient)

    ImportService(tmp_path, config=config)

    assert captured["linked_attachment_base_dir"] == str(tmp_path / "Linked PDFs")


def test_import_copies_zotero_linked_attachment_from_configured_base(tmp_path):
    vault = tmp_path / "Vault"
    (vault / ".obsidian").mkdir(parents=True)
    linked_base = tmp_path / "Linked PDFs"
    linked_pdf = linked_base / "LLM_Agent" / "tech debit" / "linked article.pdf"
    linked_pdf.parent.mkdir(parents=True)
    linked_pdf.write_bytes(b"%PDF-1.4 linked")
    config = default_config()
    config["zotero"]["linkedAttachmentBaseDir"] = str(linked_base)
    config["bibtex"]["enabled"] = False

    class LinkedTransport:
        def request(self, method, url, *, headers, timeout):
            del method, headers, timeout
            parsed = urlsplit(url)
            query = parse_qs(parsed.query)
            if parsed.path == "/api/users/0/items/ITEM1":
                payload = {
                    "key": "ITEM1",
                    "version": 7,
                    "data": {
                        "key": "ITEM1",
                        "itemType": "journalArticle",
                        "title": "Linked Zotero Article",
                        "creators": [{"firstName": "Ada", "lastName": "Lovelace"}],
                        "date": "2024",
                    },
                }
            elif parsed.path == "/api/users/0/items/ITEM1/children":
                payload = (
                    [
                        {
                            "key": "PDF1",
                            "version": 1,
                            "data": {
                                "key": "PDF1",
                                "itemType": "attachment",
                                "contentType": "application/pdf",
                                "path": "attachments:LLM_Agent/tech debit/linked article.pdf",
                            },
                        }
                    ]
                    if query.get("start") == ["0"]
                    else []
                )
            elif parsed.path == "/api/users/0/items" and query.get("itemType") == ["annotation"]:
                payload = []
            else:
                raise AssertionError(f"unexpected route: {parsed.path} {query}")
            return TransportResponse(200, json.dumps(payload).encode("utf-8"))

    client = ZoteroClient(
        transport=LinkedTransport(),
        linked_attachment_base_dir=config["zotero"]["linkedAttachmentBaseDir"],
    )
    result = ImportService(vault, zotero_client=client, config=config).import_item("ITEM1")

    copied = vault / "Literature" / "attachment" / "ITEM1.pdf"
    assert result["pdfPath"] == "Literature/attachment/ITEM1.pdf"
    assert copied.read_bytes() == linked_pdf.read_bytes()
    assert str(linked_pdf) not in (vault / "Literature" / "ITEM1.md").read_text(encoding="utf-8")


def _tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted((path for path in root.rglob("*") if path.is_file()), key=lambda item: item.relative_to(root).as_posix()):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def test_ten_imports_and_title_change_keep_one_note_and_preserve_user_content():
    with tempfile.TemporaryDirectory(prefix="中文 Vault ") as directory:
        vault = Path(directory)
        (vault / ".obsidian").mkdir()
        initialize_config(vault)
        pdf = vault.parent / f"{vault.name}-source.pdf"
        pdf.write_bytes(b"%PDF-1.4 test")
        client = FakeZotero(pdf)
        service = ImportService(vault, zotero_client=client)
        first = service.import_item("ABCD1234")
        note = vault / "Literature" / "ABCD1234.md"
        text = note.read_text(encoding="utf-8")
        text = text.replace("zoteroKey: ABCD1234", "zoteroKey: ABCD1234\nstatus: reading\nrating: 4")
        text = text.replace("## Reading Notes\n", "## Reading Notes\n\nDurable user note.\n")
        note.write_text(text, encoding="utf-8", newline="\n")
        service.import_item("ABCD1234")
        stable_hash = _tree_hash(vault)
        for _ in range(8):
            result = service.import_item("ABCD1234")
            assert result["status"] == "noop"
        assert _tree_hash(vault) == stable_hash
        client.title = "Renamed Title"
        client.version = 2
        renamed = service.import_item("ABCD1234")
        assert renamed["status"] == "committed"
        assert list((vault / "Literature").glob("ABCD1234.md")) == [note]
        updated = note.read_text(encoding="utf-8")
        assert "title: Renamed Title" in updated
        assert "Durable user note." in updated
        assert "status: reading" in updated
        assert str(pdf) not in updated
        state = json.loads((vault / ".obsidian-vault-mcp" / "state" / "items" / "ABCD1234.json").read_text(encoding="utf-8"))
        assert state["sourcePdfPath"] == str(pdf)
        assert first["notePath"] == renamed["notePath"] == "Literature/ABCD1234.md"
        pdf.unlink()


def test_missing_optional_metadata_omits_fields_and_dry_run_writes_nothing():
    with tempfile.TemporaryDirectory() as directory:
        vault = Path(directory)
        (vault / ".obsidian").mkdir()
        initialize_config(vault)

        class Minimal(FakeZotero):
            def __init__(self):
                self.title = "Minimal"
                self.version = 1
                self.pdf = Path("missing.pdf")

            def get_item_tree(self, key):
                tree = super().get_item_tree(key)
                tree["parent"].update(doi="", url="", abstract="", tags=[])
                tree["children"].update(notes=[], attachments=[])
                return tree

        result = ImportService(vault, zotero_client=Minimal()).import_item("ABCD1234", dry_run=True)
        assert result["status"] == "dry-run"
        assert not (vault / "Literature").exists()

        ImportService(vault, zotero_client=Minimal()).import_item("ABCD1234")
        text = (vault / "Literature" / "ABCD1234.md").read_text(encoding="utf-8")
        assert "\ndoi:" not in text
        assert "\nurl:" not in text
        assert "\nabstract:" not in text
        assert "attachmentPdfLink" not in text
        assert "attachmentMinerULink" not in text


def test_rename_policy_never_overwrites_another_identity():
    with tempfile.TemporaryDirectory() as directory:
        vault = Path(directory)
        (vault / ".obsidian").mkdir()
        initialize_config(vault)
        literature = vault / "Literature"
        literature.mkdir()
        occupied = literature / "ABCD1234.md"
        occupied.write_text("---\ntitle: Other\nzoteroKey: OTHER999\n---\n\n# Other\n", encoding="utf-8")
        client = FakeZotero(Path("missing.pdf"))
        result = ImportService(vault, zotero_client=client).import_item("ABCD1234", conflict_policy="rename")

        assert result["notePath"] == "Literature/ABCD1234-2.md"
        assert "OTHER999" in occupied.read_text(encoding="utf-8")
        assert (literature / "ABCD1234-2.md").is_file()


def test_pdf_never_policy_keeps_existing_copy_and_tracks_both_hashes():
    with tempfile.TemporaryDirectory() as directory:
        vault = Path(directory)
        (vault / ".obsidian").mkdir()
        initialize_config(vault)
        source = vault.parent / f"{vault.name}-source.pdf"
        source.write_bytes(b"first")
        client = FakeZotero(source)
        config = load_config(vault)
        config["attachments"]["overwritePolicy"] = "never"
        service = ImportService(vault, zotero_client=client, config=config)
        service.import_item("ABCD1234")
        copied = vault / "Literature" / "attachment" / "ABCD1234.pdf"
        assert copied.read_bytes() == b"first"

        source.write_bytes(b"second")
        client.version = 2
        service.import_item("ABCD1234")
        state = json.loads((vault / ".obsidian-vault-mcp/state/items/ABCD1234.json").read_text(encoding="utf-8"))
        assert copied.read_bytes() == b"first"
        assert state["sourcePdfSha256"] == hashlib.sha256(b"second").hexdigest()
        assert state["copiedPdfSha256"] == hashlib.sha256(b"first").hexdigest()
        source.unlink()


def test_collection_import_processes_all_500_items_but_bounds_the_response():
    class CollectionClient:
        def list_collection_items(self, _key):
            return [
                {"key": f"ITEM{index:04d}", "itemType": "journalArticle"}
                for index in range(500)
            ]

    class CountingService(ImportService):
        def __init__(self, vault):
            super().__init__(vault, zotero_client=CollectionClient())
            self.seen = []

        def import_item(self, zotero_key, **_kwargs):
            self.seen.append(zotero_key)
            return {
                "ok": True,
                "status": "committed",
                "notePath": f"Literature/{zotero_key}.md",
            }

    with tempfile.TemporaryDirectory() as directory:
        service = CountingService(Path(directory))
        result = service.import_collection("COLLECTION")

    assert len(service.seen) == 500
    assert service.seen[0] == "ITEM0000"
    assert service.seen[-1] == "ITEM0499"
    assert result["total"] == result["succeeded"] == 500
    assert result["failed"] == 0
    assert len(result["results"]) == 20
    assert result["truncated"] is True
    assert result["nextCursor"] == "20"
