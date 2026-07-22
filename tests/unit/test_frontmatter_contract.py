from __future__ import annotations

import unittest

from obsidian_vault_mcp.domain.errors import FrontmatterError
from obsidian_vault_mcp.domain.frontmatter import (
    MANAGED_FIELD_ORDER,
    compose_frontmatter,
    merge_frontmatter,
    parse_frontmatter,
    update_frontmatter,
)


class FrontmatterContractTests(unittest.TestCase):
    def test_managed_order_omit_empty_and_utf8(self) -> None:
        fields = {
            "zoteroKey": "ABCD1234",
            "doi": "",
            "title": "中文标题",
            "tags": ["光催化", "CdS"],
            "url": None,
        }
        text = compose_frontmatter(fields, "# 中文标题\n")
        self.assertLess(text.index("title:"), text.index("tags:"))
        self.assertLess(text.index("tags:"), text.index("zoteroKey:"))
        self.assertNotIn("doi:", text)
        self.assertNotIn("url:", text)
        self.assertEqual(text.encode("utf-8").decode("utf-8"), text)

    def test_unknown_fields_and_body_are_preserved(self) -> None:
        original = (
            "---\n"
            "title: Old\n"
            "zoteroKey: ABCD1234\n"
            "status: reading\n"
            "rating: 4\n"
            "---\n\n"
            "## Reading Notes\n\nDo not touch.\n"
        )
        updated = update_frontmatter(original, {"title": "New", "doi": None})
        document = parse_frontmatter(updated)
        self.assertEqual(document.fields["title"], "New")
        self.assertEqual(document.fields["status"], "reading")
        self.assertEqual(document.fields["rating"], 4)
        self.assertEqual(document.body, "\n## Reading Notes\n\nDo not touch.\n")
        positions = [updated.index(f"{name}:") for name in MANAGED_FIELD_ORDER if name in document.fields]
        self.assertEqual(positions, sorted(positions))

    def test_unknown_plugin_input_cannot_overwrite_existing_user_field(self) -> None:
        merged = merge_frontmatter({"status": "reading"}, {"status": "done", "title": "Paper"})
        self.assertEqual(merged["status"], "reading")

    def test_invalid_or_duplicate_yaml_is_rejected(self) -> None:
        with self.assertRaises(FrontmatterError):
            parse_frontmatter("---\ntitle: one\ntitle: two\n---\n")
        with self.assertRaises(FrontmatterError):
            parse_frontmatter("---\ntitle: [broken\n---\n")


if __name__ == "__main__":
    unittest.main()
