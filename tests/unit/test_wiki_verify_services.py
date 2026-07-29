from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from obsidian_vault_mcp.application.evidence_service import EvidenceService
from obsidian_vault_mcp.application.verify_service import VerifyService
from obsidian_vault_mcp.application.wiki_service import WikiService
from obsidian_vault_mcp.config.defaults import default_config
from obsidian_vault_mcp.domain.errors import TransactionConflictError
from obsidian_vault_mcp.domain.frontmatter import compose_frontmatter, parse_frontmatter


class WikiServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.vault = Path(self.temporary.name)
        self.config = default_config()
        self._write_main_note(
            "ABCD1234",
            title="Photocatalytic Hydrogen Evolution",
            abstract="CdS catalyst for efficient hydrogen generation.",
            tags=["photocatalysis", "CdS"],
            body=(
                "# Photocatalytic Hydrogen Evolution\n\n"
                "## Zotero Notes\n\n"
                "<!-- ovm:zotero-notes:start -->\n"
                "The cocatalyst suppresses recombination.\n"
                "<!-- ovm:zotero-notes:end -->\n"
            ),
            mineru=True,
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _write_main_note(
        self,
        key: str,
        *,
        title: str,
        abstract: str = "",
        tags: list[str] | None = None,
        body: str = "# Paper\n",
        mineru: bool = False,
    ) -> None:
        note = self.vault / "Literature" / f"{key}.md"
        note.parent.mkdir(parents=True, exist_ok=True)
        fields = {
            "title": title,
            "itemType": "journalArticle",
            "tags": tags or [],
            "abstract": abstract,
            "zoteroKey": key,
        }
        if mineru:
            fields["attachmentMinerULink"] = f"[[Literature/attachment/MinerU/{key}]]"
            mineru_path = self.vault / "Literature" / "attachment" / "MinerU" / f"{key}.md"
            mineru_path.parent.mkdir(parents=True, exist_ok=True)
            mineru_path.write_text(
                compose_frontmatter(
                    {"title": title, "zoteroKey": key, "sourcePdf": f"../{key}.pdf"},
                    "MinerU full text discusses catalyst performance and hydrogen evolution.\n",
                ),
                encoding="utf-8",
            )
        note.write_text(compose_frontmatter(fields, body), encoding="utf-8")

    def test_context_returns_traceable_metadata_notes_and_mineru(self) -> None:
        result = WikiService(self.vault, self.config).context("photocatalysis")

        self.assertTrue(result["ok"])
        self.assertEqual(result["count"], 1)
        literature = result["relatedLiterature"][0]
        self.assertEqual(literature["zoteroKey"], "ABCD1234")
        self.assertIn("cocatalyst", literature["zoteroNotes"])
        self.assertIn("catalyst performance", literature["mineruExcerpt"])
        self.assertEqual(
            literature["noteLink"],
            "[[Literature/ABCD1234|Photocatalytic Hydrogen Evolution]]",
        )

    def test_write_adds_sources_frontmatter_and_supports_dry_run(self) -> None:
        service = WikiService(self.vault, self.config)
        preview = service.write(
            "CdS Cocatalysts",
            "# CdS Cocatalysts\n\nA synthesis.",
            ["ABCD1234"],
            updated_at="2026-07-22T12:00:00Z",
            dry_run=True,
            transaction_id="wiki-preview",
        )
        self.assertEqual(preview["status"], "dry-run")
        self.assertFalse((self.vault / "Literature" / "Wiki" / "CdS Cocatalysts.md").exists())

        result = service.write(
            "CdS Cocatalysts",
            "# CdS Cocatalysts\n\nA synthesis.",
            ["ABCD1234"],
            updated_at="2026-07-22T12:00:00Z",
            transaction_id="wiki-write",
        )
        self.assertEqual(result["status"], "committed")
        wiki_path = self.vault / "Literature" / "Wiki" / "CdS Cocatalysts.md"
        document = parse_frontmatter(wiki_path.read_text(encoding="utf-8"))
        self.assertEqual(document.fields["title"], "CdS Cocatalysts")
        self.assertEqual(document.fields["zoteroKeys"], ["ABCD1234"])
        self.assertEqual(document.fields["updatedAt"], "2026-07-22T12:00:00Z")
        self.assertIn("[[Literature/ABCD1234|Photocatalytic Hydrogen Evolution]]", document.body)
        self.assertEqual(service.list()[0]["path"], "Literature/Wiki/CdS Cocatalysts.md")

    def test_write_preserves_custom_fields_and_honors_conflicts(self) -> None:
        service = WikiService(self.vault, self.config)
        page = self.vault / "Literature" / "Wiki" / "Existing.md"
        page.parent.mkdir(parents=True)
        page.write_text(compose_frontmatter({"title": "Existing", "status": "reviewed"}, "Old\n"), encoding="utf-8")

        service.write(
            "Existing",
            "New synthesis",
            ["ABCD1234"],
            updated_at="2026-07-22T12:00:00Z",
            transaction_id="wiki-preserve",
        )
        document = parse_frontmatter(page.read_text(encoding="utf-8"))
        self.assertEqual(document.fields["status"], "reviewed")
        with self.assertRaises(TransactionConflictError):
            service.write(
                "Existing",
                "Again",
                ["ABCD1234"],
                conflict_policy="fail",
            )
        renamed = service.write(
            "Existing",
            "Renamed",
            ["ABCD1234"],
            updated_at="2026-07-22T12:00:00Z",
            transaction_id="wiki-rename",
            conflict_policy="rename",
        )
        self.assertEqual(renamed["path"], "Literature/Wiki/Existing-2.md")

    def test_write_rejects_unsafe_topic_and_local_paths(self) -> None:
        service = WikiService(self.vault, self.config)
        with self.assertRaises(ValueError):
            service.write("../escape", "Body", ["ABCD1234"])
        with self.assertRaises(ValueError):
            service.write("Unsafe", r"Local C:\Users\name\secret.pdf", ["ABCD1234"])
        with self.assertRaises(ValueError):
            service.write("Unsafe", "[raw](file:///tmp/raw.md)", ["ABCD1234"])


class VerifyServiceTests(unittest.TestCase):
    def test_clean_vault_is_ok(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            vault = Path(directory)
            note = vault / "Literature" / "ABCD1234.md"
            pdf = vault / "Literature" / "attachment" / "ABCD1234.pdf"
            mineru = vault / "Literature" / "attachment" / "MinerU" / "ABCD1234.md"
            note.parent.mkdir(parents=True)
            pdf.parent.mkdir(parents=True)
            mineru.parent.mkdir(parents=True)
            pdf.write_bytes(b"PDF")
            mineru_text = "---\nzoteroKey: ABCD1234\nsourcePdf: ../ABCD1234.pdf\n---\n\nText\n"
            mineru.write_text(mineru_text, encoding="utf-8")
            manifest = vault / ".obsidian-vault-mcp" / "cache" / "mineru-assets" / "ABCD1234" / "manifest.json"
            manifest.parent.mkdir(parents=True)
            manifest.write_text(
                json.dumps(
                    {
                        "schemaVersion": 1,
                        "zoteroKey": "ABCD1234",
                        "sourceMarkdown": "Literature/attachment/MinerU/ABCD1234.md",
                        "sourceMarkdownSha256": hashlib.sha256(mineru.read_bytes()).hexdigest(),
                        "generatedAt": "2026-07-29T00:00:00Z",
                        "assets": [],
                        "counts": {"total": 0, "referenced": 0, "unlinkedCandidates": 0, "invalid": 0},
                        "warnings": [],
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            note.write_text(
                compose_frontmatter(
                    {
                        "title": "Clean",
                        "itemType": "journalArticle",
                        "zoteroKey": "ABCD1234",
                        "attachmentPdfLink": "[[Literature/attachment/ABCD1234.pdf]]",
                        "attachmentMinerULink": "[[Literature/attachment/MinerU/ABCD1234]]",
                    },
                    "# Clean\n",
                ),
                encoding="utf-8",
            )
            EvidenceService(vault, default_config()).rebuild(
                "ABCD1234",
                transaction_id="clean-evidence",
                generated_at="2026-07-29T00:00:00Z",
            )

            result = VerifyService(vault, default_config()).verify()

            self.assertTrue(result["ok"])
            self.assertEqual(result["issueCount"], 0)
            self.assertEqual(result["counts"]["mainNotes"], 1)

    def test_verify_ignores_all_top_level_dot_directories(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            vault = Path(directory)
            for relative in (
                ".agents/instructions.md",
                ".claude/settings.base",
                ".custom/nested/state.md",
            ):
                hidden = vault / relative
                hidden.parent.mkdir(parents=True, exist_ok=True)
                hidden.write_text(r"path: C:\Users\name\private" + "\n", encoding="utf-8")

            visible = vault / "Literature" / "Visible.base"
            visible.parent.mkdir(parents=True)
            visible.write_text(r"path: C:\Users\name\paper.pdf" + "\n", encoding="utf-8")

            result = VerifyService(vault, default_config()).verify()

            self.assertEqual(result["counts"]["filesScanned"], 1)
            self.assertEqual(result["counts"]["byCode"], {"windows-absolute-path": 1})
            self.assertEqual([issue["path"] for issue in result["issues"]], ["Literature/Visible.base"])

    def test_verify_reports_identity_links_locations_and_unsafe_references(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            vault = Path(directory)
            literature = vault / "Literature"
            literature.mkdir()
            common = {"itemType": "journalArticle", "doi": "10.1000/SAME"}
            (literature / "ABCD1234.md").write_text(
                compose_frontmatter(
                    {
                        **common,
                        "title": "First",
                        "zoteroKey": "ABCD1234",
                        "attachmentPdfLink": "[[Literature/attachment/missing.pdf]]",
                    },
                    "# First\n",
                ),
                encoding="utf-8",
            )
            (literature / "Copy-ABCD1234.md").write_text(
                compose_frontmatter(
                    {"title": "Copy", "itemType": "journalArticle", "zoteroKey": "ABCD1234"},
                    "# Copy\n",
                ),
                encoding="utf-8",
            )
            (literature / "WXYZ5678.md").write_text(
                compose_frontmatter(
                    {
                        **common,
                        "doi": "https://doi.org/10.1000/same",
                        "title": "Second",
                        "zoteroKey": "WXYZ5678",
                    },
                    "# Second\n",
                ),
                encoding="utf-8",
            )
            rogue = literature / "Nested" / "ROGUE999.md"
            rogue.parent.mkdir()
            rogue.write_text(
                compose_frontmatter(
                    {"title": "Rogue", "itemType": "journalArticle", "zoteroKey": "ROGUE999"},
                    "# Rogue\n",
                ),
                encoding="utf-8",
            )
            (literature / "Literature.base").write_text(
                "source: file:///tmp/private\npath: C:\\Users\\name\\paper.pdf\n"
                "raw: .obsidian-vault-mcp/staging/tx/raw.md\n",
                encoding="utf-8",
            )

            result = VerifyService(vault, default_config()).verify()
            codes = {issue["code"] for issue in result["issues"]}

            self.assertFalse(result["ok"])
            self.assertIn("duplicate-zotero-key", codes)
            self.assertIn("duplicate-doi", codes)
            self.assertIn("broken-pdf-link", codes)
            self.assertIn("missing-mineru-link", codes)
            self.assertIn("illegal-main-note-location", codes)
            self.assertIn("file-url", codes)
            self.assertIn("windows-absolute-path", codes)
            self.assertIn("staging-reference", codes)
            self.assertEqual(result["issueCount"], sum(result["counts"]["byCode"].values()))


if __name__ == "__main__":
    unittest.main()
