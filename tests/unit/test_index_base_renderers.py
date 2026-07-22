from __future__ import annotations

import unittest

import yaml

from obsidian_vault_mcp.adapters.obsidian.base_renderer import render_base
from obsidian_vault_mcp.adapters.obsidian.index_renderer import render_index


class IndexAndBaseRendererTests(unittest.TestCase):
    def setUp(self) -> None:
        self.records = [
            {
                "zoteroKey": "BBBB2222",
                "title": "Beta",
                "year": 2023,
                "journal": "Journal B",
                "tags": ["catalysis"],
                "doi": "",
                "attachmentPdfLink": "",
                "attachmentMinerULink": "",
                "lastImportedAt": "2026-01-01T00:00:00Z",
            },
            {
                "zoteroKey": "AAAA1111",
                "title": "Alpha",
                "notePath": "Literature/Smith-2024-Alpha-AAAA1111.md",
                "year": 2024,
                "journal": "Journal A",
                "tags": ["CdS", "catalysis"],
                "doi": "10.1/alpha",
                "attachmentPdfLink": "[[Literature/attachment/AAAA1111.pdf]]",
                "attachmentMinerULink": "[[Literature/attachment/MinerU/AAAA1111]]",
                "lastImportedAt": "2026-02-01T00:00:00Z",
            },
        ]

    def test_index_is_deterministic_and_contains_all_managed_sections(self) -> None:
        first = render_index(self.records, ["CdS Cocatalysts", "Hydrogen Evolution"])
        second = render_index(reversed(self.records), ["Hydrogen Evolution", "CdS Cocatalysts"])
        self.assertEqual(first, second)
        self.assertIn("- Total literature: 2", first)
        self.assertIn("- With PDF: 1", first)
        self.assertIn("[[Literature/Smith-2024-Alpha-AAAA1111|Alpha]]", first)
        for name in ("recent", "year", "journal", "tags", "wiki", "maintenance"):
            self.assertIn(f"<!-- ovm:index:{name}:start -->", first)
            self.assertIn(f"<!-- ovm:index:{name}:end -->", first)

    def test_index_uses_the_configured_wiki_folder(self) -> None:
        rendered = render_index(
            self.records,
            ["CdS Cocatalysts"],
            wiki_folder="Knowledge/Topics",
        )
        self.assertIn("[[Knowledge/Topics/CdS Cocatalysts]]", rendered)
        self.assertNotIn("[[Wiki/CdS Cocatalysts]]", rendered)

    def test_unknown_year_is_grouped_after_known_years(self) -> None:
        records = [*self.records, {"zoteroKey": "NONE0001", "title": "Undated"}]
        rendered = render_index(records)
        year_block = rendered.split("<!-- ovm:index:year:start -->", 1)[1].split("<!-- ovm:index:year:end -->", 1)[0]
        self.assertLess(year_block.index("### 2024"), year_block.index("### Unknown"))

    def test_base_is_valid_yaml_and_has_seven_v2_views(self) -> None:
        rendered = render_base()
        self.assertEqual(rendered, render_base())
        payload = yaml.safe_load(rendered)
        self.assertEqual(len(payload["views"]), 7)
        self.assertEqual(payload["views"][0]["name"], "Literature Matrix")
        self.assertIn('file.folder == "Literature"', payload["filters"]["and"])
        self.assertNotIn('file.inFolder("Literature")', payload["filters"]["and"])
        self.assertEqual(payload["properties"]["note.attachmentMinerULink"]["displayName"], "MinerU")


if __name__ == "__main__":
    unittest.main()
