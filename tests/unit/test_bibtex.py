from __future__ import annotations

import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from obsidian_vault_mcp.adapters.zotero.bibtex import (
    BibTeXResult,
    generate_builtin_bibtex,
)
from obsidian_vault_mcp.adapters.zotero.client import TransportResponse, ZoteroClient
from obsidian_vault_mcp.application.import_service import ImportService
from obsidian_vault_mcp.config.loader import initialize_config


def _metadata(item_type: str, **values):
    return {
        "key": "ABCD1234",
        "citationKey": "lovelaceComputing1843",
        "itemType": item_type,
        "title": "Notes on the Analytical Engine",
        "date": "1843-01-01",
        "creators": [
            {
                "creatorType": "inventor" if item_type == "patent" else "author",
                "firstName": "Ada",
                "lastName": "Lovelace",
            }
        ],
        "DOI": "10.1000/example",
        "url": "https://example.test/paper",
        **values,
    }


@pytest.mark.parametrize(
    ("item_type", "extra", "expected_entry", "expected_field"),
    [
        ("journalArticle", {"publicationTitle": "Scientific Memoirs"}, "article", "journal = {Scientific Memoirs}"),
        ("conferencePaper", {"conferenceName": "Computing 1843"}, "inproceedings", "booktitle = {Computing 1843}"),
        ("book", {"publisher": "Taylor"}, "book", "publisher = {Taylor}"),
        ("bookSection", {"bookTitle": "Collected Works"}, "incollection", "booktitle = {Collected Works}"),
        ("thesis", {"university": "University of London", "thesisType": "PhD thesis"}, "phdthesis", "school = {University of London}"),
        ("report", {"institution": "Royal Society", "reportNumber": "42"}, "techreport", "institution = {Royal Society}"),
        ("preprint", {"repository": "arXiv", "archiveID": "2401.00001"}, "misc", "eprint = {2401.00001}"),
        ("patent", {"patentNumber": "GB-1843-1", "assignee": "Analytical Engines Ltd"}, "misc", "number = {GB-1843-1}"),
    ],
)
def test_builtin_bibtex_supports_required_zotero_types(
    item_type,
    extra,
    expected_entry,
    expected_field,
):
    bibtex = generate_builtin_bibtex(_metadata(item_type, **extra))

    assert bibtex.startswith(f"@{expected_entry}{{lovelaceComputing1843,")
    assert "author = {Lovelace, Ada}" in bibtex
    assert "year = {1843}" in bibtex
    assert expected_field in bibtex


def test_master_thesis_uses_mastersthesis_entry():
    bibtex = generate_builtin_bibtex(_metadata("thesis", university="University of London", thesisType="Master's Thesis"))

    assert bibtex.startswith("@mastersthesis{")


class BibTeXTransport:
    def __init__(self, bbt: TransportResponse, zotero: TransportResponse):
        self.bbt = bbt
        self.zotero = zotero
        self.calls: list[tuple[str, dict[str, list[str]]]] = []

    def request(self, method, url, *, headers, timeout):
        del method, headers, timeout
        parsed = urlsplit(url)
        query = parse_qs(parsed.query)
        self.calls.append((parsed.path, query))
        if parsed.path == "/better-bibtex/export/item":
            return self.bbt
        if parsed.path == "/api/users/0/items/ABCD1234":
            return self.zotero
        raise AssertionError(f"unexpected BibTeX route: {parsed.path}")


def test_get_bibtex_prefers_better_bibtex_and_stops_after_success():
    better = b"@article{betterKey,\n  title = {Better}\n}"
    transport = BibTeXTransport(
        TransportResponse(200, better),
        TransportResponse(200, b"@article{zoteroKey,}"),
    )
    result = ZoteroClient(transport=transport).get_bibtex(
        "ABCD1234",
        item=_metadata("journalArticle", publicationTitle="Journal"),
    )

    assert isinstance(result, BibTeXResult)
    assert result["provider"] == "better-bibtex"
    assert result["bibtex"] == better.decode()
    assert result["errors"] == []
    assert len(transport.calls) == 1
    path, query = transport.calls[0]
    assert path == "/better-bibtex/export/item"
    assert query["citationKeys"] == ["lovelaceComputing1843"]
    assert query["translator"] == ["bibtex"]


def test_get_bibtex_falls_back_to_zotero_export_and_keeps_bbt_error():
    zotero = b"@article{zoteroKey,\n  title = {Zotero Export}\n}"
    transport = BibTeXTransport(
        TransportResponse(404, b"Better BibTeX not installed"),
        TransportResponse(200, zotero),
    )
    result = ZoteroClient(transport=transport).get_bibtex(
        "ABCD1234",
        item=_metadata("journalArticle", publicationTitle="Journal"),
    )

    assert result.provider == "zotero-export"
    assert result.bibtex == zotero.decode()
    assert [error["provider"] for error in result.errors] == ["better-bibtex"]
    assert result.errors[0]["code"] == "http_error"
    assert [path for path, _query in transport.calls] == [
        "/better-bibtex/export/item",
        "/api/users/0/items/ABCD1234",
    ]


def test_get_bibtex_removes_local_attachment_fields_from_zotero_export():
    zotero = r"""@article{zoteroKey,
  title = {Zotero Export},
  file = {Full Text PDF:C:\Users\Alice\Zotero\storage\ABCD1234\paper.pdf:application/pdf},
  attachment = {Snapshot:file:///C:/Users/Alice/Zotero/storage/ABCD1234/page.html:text/html},
  local-url = {file:///C:/Users/Alice/Documents/paper.pdf},
  url = {https://doi.org/10.1000/example}
}""".encode()
    transport = BibTeXTransport(
        TransportResponse(500, b"not used"),
        TransportResponse(200, zotero),
    )

    result = ZoteroClient(transport=transport).get_bibtex(
        "ABCD1234",
        item=_metadata("journalArticle", publicationTitle="Journal"),
        provider="zotero",
        fallback=False,
    )

    assert result.provider == "zotero-export"
    assert "title = {Zotero Export}" in result.bibtex
    assert "url = {https://doi.org/10.1000/example}" in result.bibtex
    assert "file =" not in result.bibtex
    assert "attachment =" not in result.bibtex
    assert "local-url =" not in result.bibtex
    assert r"C:\Users\Alice" not in result.bibtex
    assert "file:///C:/Users/Alice" not in result.bibtex


def test_imported_note_does_not_expose_zotero_bibtex_local_path():
    zotero = r"""@article{zoteroKey,
  title = {Zotero Export},
  file = {Full Text PDF:C:\Users\Alice\Zotero\storage\ABCD1234\paper.pdf:application/pdf},
  url = {https://doi.org/10.1000/example}
}""".encode()
    transport = BibTeXTransport(
        TransportResponse(404, b"Better BibTeX not installed"),
        TransportResponse(200, zotero),
    )

    class ImportClient(ZoteroClient):
        def get_item_tree(self, key):
            return {
                "parent": _metadata("journalArticle", key=key, publicationTitle="Journal"),
                "children": {"notes": [], "annotations": [], "attachments": []},
            }

    with tempfile.TemporaryDirectory() as directory:
        vault = Path(directory)
        (vault / ".obsidian").mkdir()
        initialize_config(vault)
        result = ImportService(
            vault,
            zotero_client=ImportClient(transport=transport),
        ).import_item("ABCD1234")

        note = (vault / result["notePath"]).read_text(encoding="utf-8")

    assert "title = {Zotero Export}" in note
    assert "url = {https://doi.org/10.1000/example}" in note
    assert "file =" not in note
    assert r"C:\Users\Alice" not in note


def test_get_bibtex_falls_back_to_builtin_and_reports_both_http_failures():
    transport = BibTeXTransport(
        TransportResponse(404, b"Better BibTeX not installed"),
        TransportResponse(500, b"Zotero export failed"),
    )
    result = ZoteroClient(transport=transport).get_bibtex(
        "ABCD1234",
        item=_metadata("report", institution="Royal Society", reportNumber="42"),
    )

    assert result.provider == "builtin"
    assert result.bibtex.startswith("@techreport{lovelaceComputing1843,")
    assert [error["provider"] for error in result.errors] == [
        "better-bibtex",
        "zotero-export",
    ]
    assert all(error["code"] == "http_error" for error in result.errors)
    assert result.to_dict()["ok"] is True


def test_missing_bbt_citation_key_is_a_visible_fallback_error():
    item = _metadata("book", publisher="Taylor")
    item.pop("citationKey")
    transport = BibTeXTransport(
        TransportResponse(200, b"should not be called"),
        TransportResponse(500, b"Zotero export failed"),
    )
    result = ZoteroClient(transport=transport).get_bibtex("ABCD1234", item=item)

    assert result.provider == "builtin"
    assert result.errors[0]["provider"] == "better-bibtex"
    assert result.errors[0]["code"] == "missing_citation_key"
    assert [path for path, _query in transport.calls] == ["/api/users/0/items/ABCD1234"]
