from __future__ import annotations

import unittest

from obsidian_vault_mcp.adapters.obsidian.markdown_renderer import render_note_body, replace_managed_section


class MarkdownRendererTests(unittest.TestCase):
    def test_omits_missing_sections_and_uses_vault_relative_links(self) -> None:
        result = render_note_body(
            "Paper",
            pdf_path="Literature\\attachment\\ABCD1234.pdf",
        )
        self.assertIn("![[Literature/attachment/ABCD1234.pdf]]", result)
        self.assertNotIn("## Abstract", result)
        self.assertNotIn("## MinerU", result)
        self.assertIn("## Reading Notes", result)

    def test_repeated_render_preserves_user_fields_and_is_idempotent(self) -> None:
        first = render_note_body(
            "Old Title",
            abstract="First abstract.",
            pdf_path="Literature/attachment/ABCD1234.pdf",
            existing_body="# Old Title\n\n## Reading Notes\n\nKeep this.\n\n## My Analysis\n\nAlso keep this.\n",
        )
        second = render_note_body(
            "New Title",
            abstract="Updated abstract.",
            pdf_path="Literature/attachment/ABCD1234.pdf",
            mineru_path="Literature/attachment/MinerU/ABCD1234.md",
            existing_body=first,
        )
        third = render_note_body(
            "New Title",
            abstract="Updated abstract.",
            pdf_path="Literature/attachment/ABCD1234.pdf",
            mineru_path="Literature/attachment/MinerU/ABCD1234.md",
            existing_body=second,
        )
        self.assertEqual(second, third)
        self.assertIn("# New Title", second)
        self.assertNotIn("First abstract.", second)
        self.assertIn("Updated abstract.", second)
        self.assertIn("Keep this.", second)
        self.assertIn("Also keep this.", second)
        self.assertEqual(second.count("## Reading Notes"), 1)
        self.assertEqual(second.count("<!-- ovm:abstract:start -->"), 1)

    def test_bibtex_is_managed_without_affecting_user_sections(self) -> None:
        result = render_note_body(
            "Paper",
            bibtex="@article{key, title={Paper}}",
            zotero_notes="A child note.",
            existing_body="## Reading Notes\n\nHand written.\n",
        )
        self.assertIn("```bibtex", result)
        self.assertIn("<!-- ovm:zotero-notes:start -->", result)
        self.assertIn("Hand written.", result)

    def test_single_section_replacement_preserves_other_managed_blocks(self) -> None:
        original = render_note_body("Paper", abstract="Keep abstract", pdf_path="Literature/attachment/KEY.pdf")
        updated = replace_managed_section(
            original,
            "mineru",
            "MinerU",
            "- Full text: [[Literature/attachment/MinerU/KEY]]\n\n![[Literature/attachment/MinerU/KEY]]",
        )
        self.assertIn("Keep abstract", updated)
        self.assertIn("Literature/attachment/KEY.pdf", updated)
        self.assertIn("ovm:mineru:start", updated)
        removed = replace_managed_section(updated, "mineru", "MinerU", "")
        self.assertNotIn("## MinerU", removed)
        self.assertIn("Keep abstract", removed)

    def test_single_section_insertion_uses_canonical_managed_order(self) -> None:
        original = render_note_body("Paper", bibtex="@article{key, title={Paper}}")

        updated = replace_managed_section(
            original,
            "mineru",
            "MinerU",
            "- Full text: [[Literature/attachment/MinerU/KEY]]",
        )

        self.assertLess(updated.index("## MinerU"), updated.index("## BibTeX"))
        rerendered = render_note_body(
            "Paper",
            mineru_path="Literature/attachment/MinerU/KEY.md",
            bibtex="@article{key, title={Paper}}",
            existing_body=updated,
            embed_mineru=False,
        )
        self.assertEqual(updated, rerendered)


if __name__ == "__main__":
    unittest.main()
