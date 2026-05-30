import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PLUGIN_ROOT / "scripts" / "obsidian_vault_mcp.py"
SMOKE_SCRIPT_PATH = PLUGIN_ROOT / "scripts" / "smoke_integrations.py"
CHECK_SKILLS_SCRIPT_PATH = PLUGIN_ROOT / "scripts" / "check_skills_sync.py"


def load_module():
    spec = importlib.util.spec_from_file_location("obsidian_vault_mcp", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_smoke_module():
    spec = importlib.util.spec_from_file_location("smoke_integrations", SMOKE_SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ObsidianVaultMcpTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module()
        self.tempdir = tempfile.TemporaryDirectory(prefix="obsidian-vault-test-")
        self.vault = Path(self.tempdir.name).resolve()
        (self.vault / ".obsidian").mkdir()

    def tearDown(self):
        self.tempdir.cleanup()

    def write_note(self, path, content):
        full = self.vault / path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")

    def test_dry_run_returns_diff_without_writing(self):
        self.write_note("A.md", "---\ntags: alpha\n---\n\n# A\n")

        result = self.module.obsidian_update_properties(
            "A.md",
            json.dumps({"title": "A"}),
            str(self.vault),
            dry_run=True,
        )

        self.assertTrue(result["ok"])
        self.assertTrue(result["dryRun"])
        self.assertTrue(result["changed"])
        self.assertIn("+title: A", result["diff"])
        self.assertNotIn("title: A", (self.vault / "A.md").read_text(encoding="utf-8"))

    def test_zotero_wrappers_use_local_api_summaries(self):
        calls = []

        def fake_api(path, params=None, api_base=""):
            calls.append((path, params or {}, api_base))
            if path == "users/0/items":
                return [
                    {
                        "key": "ITEM1",
                        "data": {
                            "key": "ITEM1",
                            "itemType": "journalArticle",
                            "title": "Zotero Article",
                            "creators": [{"firstName": "Ada", "lastName": "Lovelace"}],
                            "date": "2024",
                            "DOI": "10.1000/zotero",
                            "tags": [{"tag": "zotero"}],
                        },
                    }
                ]
            if path == "users/0/items/ITEM1":
                return {
                    "key": "ITEM1",
                    "data": {
                        "key": "ITEM1",
                        "itemType": "journalArticle",
                        "title": "Zotero Article",
                        "creators": [{"firstName": "Ada", "lastName": "Lovelace"}],
                    },
                }
            if path == "users/0/items/ITEM1/children":
                return [
                    {"key": "NOTE1", "data": {"key": "NOTE1", "itemType": "note", "note": "<p>Child note</p>"}},
                    {"key": "PDF1", "data": {"key": "PDF1", "itemType": "attachment", "contentType": "application/pdf", "path": "C:/tmp/file.pdf"}},
                ]
            return []

        original = self.module._tools._zotero_api
        self.module._tools._zotero_api = fake_api
        try:
            search = self.module.obsidian_zotero_search_items("zotero")
            item = self.module.obsidian_zotero_get_item("ITEM1")
            children = self.module.obsidian_zotero_get_children("ITEM1")
            pdfs = self.module.obsidian_zotero_list_pdf_attachments(parent_key="ITEM1")
        finally:
            self.module._tools._zotero_api = original

        self.assertEqual(search[0]["key"], "ITEM1")
        self.assertEqual(item["title"], "Zotero Article")
        self.assertEqual(children["notes"][0]["note"], "Child note")
        self.assertEqual(pdfs[0]["key"], "PDF1")
        self.assertEqual(calls[0][0], "users/0/items")

    def test_doctor_reports_vault_and_templates(self):
        (self.vault / ".obsidian" / "templates.json").write_text(json.dumps({"folder": "Templates"}), encoding="utf-8")
        self.write_note("Templates/Default.md", "# {{title}}\n")

        result = self.module.obsidian_doctor(str(self.vault))

        self.assertTrue(result["ok"])
        names = {check["name"] for check in result["checks"]}
        self.assertIn("vault", names)
        self.assertIn("templates", names)

    def test_compat_entrypoint_runs_doctor(self):
        completed = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--doctor", "--vault", str(self.vault)],
            capture_output=True,
            timeout=30,
            check=False,
        )

        stdout = completed.stdout.decode("utf-8", errors="replace")
        stderr = completed.stderr.decode("utf-8", errors="replace")
        self.assertEqual(completed.returncode, 0, stderr)
        result = json.loads(stdout)
        self.assertTrue(result["ok"])
        self.assertEqual(result["checks"][0]["name"], "vault")

    def test_compat_entrypoint_runs_doctor_text_format(self):
        completed = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--doctor", "--doctor-format", "text", "--vault", str(self.vault)],
            capture_output=True,
            timeout=30,
            check=False,
        )

        stdout = completed.stdout.decode("utf-8", errors="replace")
        stderr = completed.stderr.decode("utf-8", errors="replace")
        self.assertEqual(completed.returncode, 0, stderr)
        self.assertIn("Obsidian Vault doctor", stdout)
        self.assertIn("Overall: OK", stdout)
        self.assertIn("[OK] vault", stdout)
        self.assertIn(str(self.vault), stdout)
        self.assertNotIn('"checks"', stdout)
        self.assertNotIn("command", stdout.lower())

    def test_search_regex_matches_pattern(self):
        self.write_note("A.md", "---\ntitle: A\n---\n\nThe year 2024 was pivotal. So was 1999.\n")

        results = self.module.obsidian_search(
            r"\b\d{4}\b", str(self.vault), use_regex=True
        )

        snippets = [r["snippet"] for r in results]
        self.assertTrue(any("2024" in s for s in snippets))
        self.assertTrue(any("1999" in s for s in snippets))

    def test_search_regex_case_sensitive(self):
        self.write_note("B.md", "---\ntitle: B\n---\n\nHello World. hello world.\n")

        results_insensitive = self.module.obsidian_search(
            r"hello", str(self.vault), use_regex=True, case_sensitive=False
        )
        results_sensitive = self.module.obsidian_search(
            r"hello", str(self.vault), use_regex=True, case_sensitive=True
        )

        self.assertEqual(len(results_insensitive), 2)
        self.assertEqual(len(results_sensitive), 1)
        self.assertIn("hello world", results_sensitive[0]["snippet"])

    def test_search_regex_invalid_pattern_returns_error(self):
        results = self.module.obsidian_search(
            r"[unclosed", str(self.vault), use_regex=True
        )

        self.assertEqual(len(results), 1)
        self.assertIn("error", results[0])
        self.assertIn("Invalid regex", results[0]["error"])

    def test_search_regex_false_preserves_existing_behavior(self):
        self.write_note("C.md", "---\ntitle: C\n---\n\nPlain text search target.\n")

        results = self.module.obsidian_search("Plain text", str(self.vault))

        self.assertTrue(any("Plain text" in r["snippet"] for r in results))

    def test_search_context_lines_returns_surrounding_lines(self):
        self.write_note("doc.md", "line1\nline2\nTARGET\nline4\nline5\n")
        results = self.module.obsidian_search(
            "TARGET", str(self.vault), context_lines=1
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["contextBefore"], ["line2"])
        self.assertEqual(results[0]["contextAfter"], ["line4"])

    def test_search_context_lines_zero_preserves_old_format(self):
        self.write_note("doc.md", "line1\nTARGET\nline3\n")
        results = self.module.obsidian_search("TARGET", str(self.vault), context_lines=0)
        self.assertNotIn("contextBefore", results[0])
        self.assertNotIn("contextAfter", results[0])

    def test_search_context_lines_clips_at_file_boundaries(self):
        self.write_note("doc.md", "TARGET\nline2\nline3\n")
        results = self.module.obsidian_search("TARGET", str(self.vault), context_lines=3)
        self.assertEqual(results[0]["contextBefore"], [])
        self.assertEqual(results[0]["contextAfter"], ["line2", "line3"])

    def test_search_context_lines_with_regex(self):
        self.write_note("regex_doc.md", "alpha\nbeta\nTARGET_X\ngamma\n")
        results = self.module.obsidian_search(
            r"TARGET_\w+", str(self.vault), use_regex=True, context_lines=1
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["contextBefore"], ["beta"])
        self.assertEqual(results[0]["contextAfter"], ["gamma"])

    def test_search_context_lines_last_line_boundary(self):
        self.write_note("last.md", "line1\nline2\nTARGET\n")
        results = self.module.obsidian_search("TARGET", str(self.vault), context_lines=2)
        self.assertEqual(results[0]["contextAfter"], [])
        self.assertEqual(results[0]["contextBefore"], ["line1", "line2"])

    # ------------------------------------------------------------------ #
    # literature pipeline simplification                                   #
    # ------------------------------------------------------------------ #

    def _patch_zotero_api(self, fake_api):
        original = self.module._tools._zotero_api
        self.module._tools._zotero_api = fake_api
        return original

    def _fake_pipeline_api(self, pdf_path=None, missing_key="FAIL1"):
        pdf_path = pdf_path or (self.vault / "zotero-article.pdf")
        if not pdf_path.exists():
            pdf_path.write_bytes(b"%PDF-1.4\n")

        def fake_api(path, params=None, api_base=""):
            if path == "users/0/items/ITEM1":
                return {
                    "key": "ITEM1",
                    "version": 7,
                    "data": {
                        "key": "ITEM1",
                        "version": 7,
                        "itemType": "journalArticle",
                        "title": "Zotero Article",
                        "creators": [{"firstName": "Ada", "lastName": "Lovelace"}],
                        "date": "2024-03-05",
                        "DOI": "10.1000/zotero",
                        "publicationTitle": "Journal of Tests",
                        "abstractNote": "Abstract from Zotero.",
                        "tags": [{"tag": "chemistry"}],
                    },
                }
            if path == "users/0/items/ITEM1/children":
                return [
                    {"key": "NOTE1", "data": {"key": "NOTE1", "itemType": "note", "note": "<p>Imported child note</p>"}},
                    {
                        "key": "PDF1",
                        "data": {
                            "key": "PDF1",
                            "itemType": "attachment",
                            "title": "PDF",
                            "contentType": "application/pdf",
                            "path": str(pdf_path),
                        },
                    },
                ]
            if path == f"users/0/items/{missing_key}":
                raise RuntimeError("item lookup failed")
            if path == "users/0/items":
                return []
            if path == "users/0/collections/COLL1/items/top":
                return [
                    {"key": "ITEM1", "version": 7, "data": {"key": "ITEM1", "itemType": "journalArticle"}},
                    {"key": missing_key, "version": 1, "data": {"key": missing_key, "itemType": "journalArticle"}},
                ]
            if path == "users/0/collections":
                return [{"key": "COLL1", "data": {"key": "COLL1", "name": "Demo Collection"}, "meta": {"numItems": 2}}]
            return []

        return fake_api

    def test_pipeline_config_defaults_and_custom_paths(self):
        defaults = self.module.obsidian_pipeline_config(str(self.vault))
        self.assertEqual(defaults["config"]["literatureFolder"], "literature")
        self.assertEqual(defaults["config"]["mineruAttachmentsFolder"], "attachments/mineru")

        (self.vault / ".obsidian-vault-pipeline.json").write_text(
            json.dumps({"literatureFolder": "论文", "mineruAttachmentsFolder": "assets/mineru"}),
            encoding="utf-8",
        )
        custom = self.module.obsidian_pipeline_config(str(self.vault))

        self.assertEqual(custom["config"]["literatureFolder"], "论文")
        self.assertEqual(custom["config"]["mineruAttachmentsFolder"], "assets/mineru")
        self.assertTrue(custom["exists"])

    def test_pipeline_ingest_item_without_mineru_creates_stable_note_and_links(self):
        fake_api = self._fake_pipeline_api()
        original = self._patch_zotero_api(fake_api)
        try:
            result = self.module.obsidian_pipeline_ingest_item("ITEM1", str(self.vault), parse_with_mineru=False)
        finally:
            self.module._tools._zotero_api = original

        self.assertTrue(result["ok"])
        self.assertEqual(result["literaturePath"], "literature/Lovelace 2024 - Zotero Article.md")
        self.assertEqual(result["pdfPath"], "attachments/zotero/ITEM1/zotero-article.pdf")
        self.assertTrue((self.vault / "attachments" / "zotero" / "ITEM1" / "zotero-article.pdf").exists())

        note = (self.vault / "literature" / "Lovelace 2024 - Zotero Article.md").read_text(encoding="utf-8")
        self.assertIn("zoteroAttachmentPaths:", note)
        self.assertIn("zotero://select/library/items/ITEM1", note)
        self.assertIn("zotero://open-pdf/library/items/PDF1", note)
        self.assertIn("[[attachments/zotero/ITEM1/zotero-article.pdf]]", note)
        self.assertIn("Imported child note", note)
        self.assertIn("## Reading Notes", note)
        self.assertIn("## AI Summary", note)
        self.assertNotIn("AI-generated", note)

    def test_pipeline_ingest_item_write_ai_summary_fills_empty_section(self):
        fake_api = self._fake_pipeline_api()
        original = self._patch_zotero_api(fake_api)
        try:
            result = self.module.obsidian_pipeline_ingest_item(
                "ITEM1",
                str(self.vault),
                parse_with_mineru=False,
                write_ai_summary=True,
            )
        finally:
            self.module._tools._zotero_api = original

        self.assertTrue(result["ok"])
        self.assertTrue(result["aiSummary"]["written"])
        note = (self.vault / "literature" / "Lovelace 2024 - Zotero Article.md").read_text(encoding="utf-8")
        self.assertIn("**Core Finding:** Abstract from Zotero.", note)
        self.assertIn("**Method:** Not specified in available Zotero or MinerU text.", note)

    def test_pipeline_repeated_ingest_preserves_user_fields_and_sections(self):
        fake_api = self._fake_pipeline_api()
        original = self._patch_zotero_api(fake_api)
        try:
            self.module.obsidian_pipeline_ingest_item("ITEM1", str(self.vault), parse_with_mineru=False)
            note_path = self.vault / "literature" / "Lovelace 2024 - Zotero Article.md"
            text = note_path.read_text(encoding="utf-8")
            props, body = self.module._split_frontmatter(text)
            props["status"] = "reading"
            props["project"] = "demo"
            props["customField"] = "keep-me"
            body = body.replace("## Reading Notes\n\n", "## Reading Notes\n\nMy durable reading note.\n\n")
            if "## AI Summary\n\n" in body:
                body = body.replace("## AI Summary\n\n", "## AI Summary\n\nSkill summary stays here.\n\n")
            else:
                body = body.replace("## AI Summary\n", "## AI Summary\n\nSkill summary stays here.\n")
            note_path.write_text(self.module._join_frontmatter(props, body), encoding="utf-8")

            self.module.obsidian_pipeline_ingest_item("ITEM1", str(self.vault), parse_with_mineru=False)
        finally:
            self.module._tools._zotero_api = original

        updated = (self.vault / "literature" / "Lovelace 2024 - Zotero Article.md").read_text(encoding="utf-8")
        updated_props, _ = self.module._split_frontmatter(updated)
        self.assertEqual(updated_props["status"], "reading")
        self.assertEqual(updated_props["project"], "demo")
        self.assertEqual(updated_props["customField"], "keep-me")
        self.assertIn("My durable reading note.", updated)
        self.assertIn("Skill summary stays here.", updated)

    def test_pipeline_write_ai_summary_does_not_overwrite_existing_summary(self):
        fake_api = self._fake_pipeline_api()
        original = self._patch_zotero_api(fake_api)
        try:
            self.module.obsidian_pipeline_ingest_item("ITEM1", str(self.vault), parse_with_mineru=False)
            note_path = self.vault / "literature" / "Lovelace 2024 - Zotero Article.md"
            text = note_path.read_text(encoding="utf-8")
            text = text.replace("## AI Summary\n", "## AI Summary\n\nMy hand-written summary.\n", 1)
            note_path.write_text(text, encoding="utf-8")

            result = self.module.obsidian_pipeline_ingest_item(
                "ITEM1",
                str(self.vault),
                parse_with_mineru=False,
                write_ai_summary=True,
            )
        finally:
            self.module._tools._zotero_api = original

        self.assertFalse(result["aiSummary"]["written"])
        updated = (self.vault / "literature" / "Lovelace 2024 - Zotero Article.md").read_text(encoding="utf-8")
        self.assertIn("My hand-written summary.", updated)
        self.assertNotIn("**Core Finding:** Abstract from Zotero.", updated)

    def test_pipeline_ingest_item_with_mineru_creates_machine_assets_and_index(self):
        def fake_extract(input_path, vault_path="", output_path="", **kwargs):
            out = Path(vault_path) / output_path
            (out / "images").mkdir(parents=True, exist_ok=True)
            (out / "images" / "figure1.png").write_bytes(b"png")
            (out / "paper.md").write_text(
                "# Extracted\n\n![process](images/figure1.png)\n\nFigure 1 Process flow diagram.\n",
                encoding="utf-8",
            )
            return {"ok": True, "markdownPath": f"{output_path}/paper.md", "outputPath": output_path}

        fake_api = self._fake_pipeline_api()
        original_api = self._patch_zotero_api(fake_api)
        original_extract = self.module._tools.obsidian_mineru_extract
        self.module._tools.obsidian_mineru_extract = fake_extract
        try:
            result = self.module.obsidian_pipeline_ingest_item("ITEM1", str(self.vault), parse_with_mineru=True)
        finally:
            self.module._tools._zotero_api = original_api
            self.module._tools.obsidian_mineru_extract = original_extract

        self.assertTrue(result["ok"])
        self.assertEqual(result["mineruMarkdown"], "attachments/mineru/ITEM1/paper.md")
        self.assertTrue((self.vault / "attachments" / "mineru" / "ITEM1" / "paper.md").exists())
        self.assertTrue((self.vault / "attachments" / "mineru" / "ITEM1" / "images-index.md").exists())
        self.assertTrue((self.vault / "attachments" / "mineru" / "ITEM1" / "images" / "fig-01-process-flow-diagram.png").exists())

        note = (self.vault / "literature" / "Lovelace 2024 - Zotero Article.md").read_text(encoding="utf-8")
        self.assertIn("mineruStatus: parsed", note)
        self.assertIn("[[attachments/mineru/ITEM1/paper]]", note)
        self.assertIn("[[attachments/mineru/ITEM1/images-index]]", note)
        self.assertIn("Imported child note", note)

    def test_pipeline_parse_with_mineru_write_ai_summary_fills_empty_section(self):
        def fake_extract(input_path, vault_path="", output_path="", **kwargs):
            out = Path(vault_path) / output_path
            (out / "images").mkdir(parents=True, exist_ok=True)
            (out / "images" / "figure1.png").write_bytes(b"png")
            (out / "paper.md").write_text(
                "# Extracted\n\nThe process reduces solvent loss in pilot testing.\n\n![fig](images/figure1.png)\n\nFigure 1 Process flow diagram.\n",
                encoding="utf-8",
            )
            return {"ok": True, "markdownPath": f"{output_path}/paper.md", "outputPath": output_path}

        fake_api = self._fake_pipeline_api()
        original_api = self._patch_zotero_api(fake_api)
        original_extract = self.module._tools.obsidian_mineru_extract
        self.module._tools.obsidian_mineru_extract = fake_extract
        try:
            self.module.obsidian_pipeline_ingest_item("ITEM1", str(self.vault), parse_with_mineru=False)
            result = self.module.obsidian_pipeline_parse_with_mineru(
                zotero_key="ITEM1",
                vault_path=str(self.vault),
                write_ai_summary=True,
            )
        finally:
            self.module._tools._zotero_api = original_api
            self.module._tools.obsidian_mineru_extract = original_extract

        self.assertTrue(result["ok"])
        self.assertTrue(result["aiSummary"]["written"])
        note = (self.vault / "literature" / "Lovelace 2024 - Zotero Article.md").read_text(encoding="utf-8")
        self.assertIn("**Core Finding:** Abstract from Zotero.", note)
        self.assertIn("## Reading Notes", note)

    def test_pipeline_rename_mineru_images_generates_english_index_and_mapping(self):
        base = self.vault / "attachments" / "mineru" / "ITEM1"
        (base / "images").mkdir(parents=True)
        (base / "images" / "image-a.png").write_bytes(b"png")
        (base / "images" / "old-unused.png").write_bytes(b"png")
        (base / "paper.md").write_text(
            "---\ntype: mineru-extraction\nzoteroKey: ITEM1\nparent: literature/Lovelace 2024 - Zotero Article.md\n---\n\n"
            "# Extracted\n\n![figure](images/image-a.png)\n\nFigure 1 Process flow diagram.\n",
            encoding="utf-8",
        )

        result = self.module.obsidian_pipeline_rename_mineru_images(
            zotero_key="ITEM1",
            mineru_markdown_path="attachments/mineru/ITEM1/paper.md",
            vault_path=str(self.vault),
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["renamed"], 1)
        self.assertTrue((base / "images" / "fig-01-process-flow-diagram.png").exists())
        paper = (base / "paper.md").read_text(encoding="utf-8")
        index = (base / "images-index.md").read_text(encoding="utf-8")
        self.assertIn("images/fig-01-process-flow-diagram.png", paper)
        self.assertIn("image-a.png", index)
        self.assertIn("fig-01-process-flow-diagram.png", index)
        self.assertIn("old-unused.png", result["cleanupCandidates"])

    def test_pipeline_collection_continues_after_item_failure(self):
        fake_api = self._fake_pipeline_api()
        original = self._patch_zotero_api(fake_api)
        try:
            result = self.module.obsidian_pipeline_ingest_collection("COLL1", str(self.vault), parse_with_mineru=False)
        finally:
            self.module._tools._zotero_api = original

        self.assertTrue(result["ok"])
        self.assertEqual(result["total"], 2)
        self.assertEqual(result["succeeded"], 1)
        self.assertEqual(result["failed"], 1)
        failed = [item for item in result["results"] if item["status"] == "failed"][0]
        self.assertEqual(failed["zoteroKey"], "FAIL1")
        self.assertIn("stage", failed)

    def test_pipeline_migrate_layout_dry_run_reports_moves_without_writing(self):
        (self.vault / "assets" / "zotero" / "ITEM1").mkdir(parents=True)
        (self.vault / "assets" / "zotero" / "ITEM1" / "PDF1.pdf").write_bytes(b"%PDF-1.4\n")
        self.write_note(
            "sources/mineru/Old Paper.md",
            "---\ntype: mineru-extraction\nzoteroKey: ITEM1\n---\n\n# Old extraction\n",
        )
        self.write_note(
            "literature/Old Paper.md",
            "---\ntype: literature\nzoteroKey: ITEM1\ntitle: Old Paper\nattachments:\n  - assets/zotero/ITEM1/PDF1.pdf\nmineruMarkdown: sources/mineru/Old Paper.md\n---\n\n# Old Paper\n\n![[assets/zotero/ITEM1/PDF1.pdf]]\n[[sources/mineru/Old Paper]]\n",
        )
        self.write_note("notes/User.md", "---\ntype: note\n---\n\n# User\n")

        result = self.module.obsidian_pipeline_migrate_layout(str(self.vault), dry_run=True)

        self.assertTrue(result["ok"])
        self.assertTrue(result["dryRun"])
        planned_to = {move["to"] for move in result["plannedMoves"]}
        self.assertIn("attachments/zotero/ITEM1/pdf1.pdf", planned_to)
        self.assertIn("attachments/mineru/ITEM1/paper.md", planned_to)
        self.assertTrue((self.vault / "assets" / "zotero" / "ITEM1" / "PDF1.pdf").exists())
        touched = {entry["path"] for entry in result["plannedYamlUpdates"]}
        self.assertIn("literature/Old Paper.md", touched)
        self.assertNotIn("notes/User.md", touched)

    def test_pipeline_migrate_layout_apply_updates_managed_paths_and_links(self):
        # Old-layout: PDF lives outside the configured zoteroAttachmentsFolder
        old_pdf = self.vault / "sources" / "old-paper.pdf"
        old_pdf.parent.mkdir(parents=True, exist_ok=True)
        old_pdf.write_bytes(b"%PDF-1.4\n")

        lit_dir = self.vault / "literature"
        lit_dir.mkdir(exist_ok=True)
        note = lit_dir / "Smith 2024 - Old Layout.md"
        note.write_text(
            "---\n"
            "type: literature\n"
            "zoteroKey: MIGR1234\n"
            "attachments:\n"
            "- sources/old-paper.pdf\n"
            "attachmentLinks:\n"
            "- '[[sources/old-paper.pdf]]'\n"
            "---\n\n"
            "See [[sources/old-paper.pdf]] for details.\n",
            encoding="utf-8",
        )

        result = self.module.obsidian_pipeline_migrate_layout(str(self.vault), dry_run=False)

        self.assertTrue(result["ok"])
        self.assertFalse(result["dryRun"])

        # File physically moved
        new_pdf = self.vault / "attachments" / "zotero" / "MIGR1234" / "old-paper.pdf"
        self.assertTrue(new_pdf.exists(), "PDF should have been moved to new location")
        self.assertFalse(old_pdf.exists(), "PDF should no longer exist at old location")

        # YAML and wikilinks updated in the note
        updated = note.read_text(encoding="utf-8")
        self.assertIn("attachments/zotero/MIGR1234/old-paper.pdf", updated)
        self.assertNotIn("sources/old-paper.pdf", updated)

    def test_pipeline_doctor_reports_profile_config_zotero_and_mineru(self):
        result = self.module.obsidian_pipeline_doctor(str(self.vault))

        self.assertIn("profile", result)
        self.assertIn("obsidian_pipeline_ingest_item", result["profile"]["tools"])
        self.assertIn("pipelineConfig", result)
        self.assertIn("zotero", result)
        self.assertIn("mineru", result)

    def test_pipeline_title_words_chinese_falls_back_to_slug(self):
        tw = self.module._tools._pipeline_title_words
        # Mostly-Chinese title with only "12" as ASCII → must not return "12"
        result = tw("陕西延炼12万吨/年苯乙烯装置设计与优化")
        self.assertGreater(len(result), 5, f"shortTitle too short: {result!r}")
        self.assertNotEqual(result, "12")

        # Fully-ASCII title must still capitalise words normally
        result_en = tw("efficient ethanol alkylation over zeolite")
        self.assertEqual(result_en, "Efficient Ethanol Alkylation Over Zeolite")

        # Short English abbreviation titles must NOT fall back to slug (no loss of capitalisation)
        result_short_en = tw("AI ML NLP")
        self.assertEqual(result_short_en, "AI ML NLP")

        # Mixed Chinese + meaningful ASCII (e.g. chemical formula) should fall back to slug
        result_mixed = tw("CO2氧化乙苯脱氢")
        self.assertNotEqual(result_mixed, "CO2")
        self.assertGreater(len(result_mixed), 3)

    def test_pipeline_repeated_mineru_parse_overwrites_machine_assets_preserves_user_content(self):
        # ----- First pass: ingest + MinerU -----
        def fake_extract_v1(input_path, vault_path="", output_path="", **kwargs):
            out = Path(vault_path) / output_path
            (out / "images").mkdir(parents=True, exist_ok=True)
            (out / "images" / "figure1.png").write_bytes(b"png-v1")
            (out / "paper.md").write_text(
                "# Extracted v1\n\n![fig](images/figure1.png)\n\nFigure 1 original diagram.\n",
                encoding="utf-8",
            )
            return {"ok": True, "markdownPath": f"{output_path}/paper.md", "outputPath": output_path}

        fake_api = self._fake_pipeline_api()
        original_api = self._patch_zotero_api(fake_api)
        original_extract = self.module._tools.obsidian_mineru_extract
        self.module._tools.obsidian_mineru_extract = fake_extract_v1
        try:
            result1 = self.module.obsidian_pipeline_ingest_item(
                "ITEM1", str(self.vault), parse_with_mineru=True
            )
        finally:
            self.module._tools._zotero_api = original_api
            self.module._tools.obsidian_mineru_extract = original_extract

        self.assertTrue(result1["ok"])
        lit_path = self.vault / "literature" / "Lovelace 2024 - Zotero Article.md"

        # ----- Add user content to the literature note -----
        text = lit_path.read_text(encoding="utf-8")
        text = text.replace("tags:", "status: reading\nproject: demo\ntags:", 1)
        text = text.replace(
            "## Reading Notes\n",
            "## Reading Notes\n\nThis is my important reading note. Do not delete.\n",
            1,
        )
        lit_path.write_text(text, encoding="utf-8")

        # ----- Second pass: re-parse with different MinerU output -----
        def fake_extract_v2(input_path, vault_path="", output_path="", **kwargs):
            out = Path(vault_path) / output_path
            (out / "images").mkdir(parents=True, exist_ok=True)
            (out / "images" / "figure1.png").write_bytes(b"png-v2")
            (out / "paper.md").write_text(
                "# Extracted v2\n\n![fig](images/figure1.png)\n\nFigure 1 updated diagram.\n",
                encoding="utf-8",
            )
            return {"ok": True, "markdownPath": f"{output_path}/paper.md", "outputPath": output_path}

        self.module._tools.obsidian_mineru_extract = fake_extract_v2
        try:
            result2 = self.module.obsidian_pipeline_parse_with_mineru(
                zotero_key="ITEM1", vault_path=str(self.vault)
            )
        finally:
            self.module._tools.obsidian_mineru_extract = original_extract

        self.assertTrue(result2["ok"])

        # Machine asset (paper.md) overwritten with v2 content
        paper_md = (self.vault / "attachments" / "mineru" / "ITEM1" / "paper.md").read_text(encoding="utf-8")
        self.assertIn("v2", paper_md)
        self.assertNotIn("v1", paper_md)

        # Literature note: user-owned fields and Reading Notes preserved
        updated_lit = lit_path.read_text(encoding="utf-8")
        self.assertIn("status: reading", updated_lit)
        self.assertIn("project: demo", updated_lit)
        self.assertIn("This is my important reading note. Do not delete.", updated_lit)

        # Plugin-owned MinerU fields updated
        self.assertIn("mineruStatus: parsed", updated_lit)

    def test_exactly_17_tools_registered(self):
        import sys
        # Fresh module load to count registrations
        for mod_name in list(sys.modules.keys()):
            if "obsidian_vault_mcp" in mod_name:
                del sys.modules[mod_name]
        sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))
        import obsidian_vault_mcp.tools  # noqa: F401
        from obsidian_vault_mcp.common import get_registered_tool_names
        names = set(get_registered_tool_names())
        expected = {
            "obsidian_pipeline_config", "obsidian_pipeline_doctor",
            "obsidian_pipeline_ingest_collection", "obsidian_pipeline_ingest_item",
            "obsidian_pipeline_migrate_layout", "obsidian_pipeline_parse_with_mineru",
            "obsidian_pipeline_rename_mineru_images", "obsidian_read_file",
            "obsidian_search", "obsidian_update_properties", "obsidian_write_file",
            "obsidian_zotero_get_children", "obsidian_zotero_get_item",
            "obsidian_zotero_list_collections", "obsidian_zotero_list_pdf_attachments",
            "obsidian_zotero_ping", "obsidian_zotero_search_items",
        }
        self.assertEqual(names, expected, f"Unexpected tools: {names - expected}, Missing: {expected - names}")

    def test_check_skills_sync_passes_repository(self):
        completed = subprocess.run(
            [sys.executable, str(CHECK_SKILLS_SCRIPT_PATH), "--json"],
            cwd=str(PLUGIN_ROOT),
            capture_output=True,
            timeout=30,
            check=False,
        )

        stdout = completed.stdout.decode("utf-8", errors="replace")
        stderr = completed.stderr.decode("utf-8", errors="replace")
        self.assertEqual(completed.returncode, 0, stderr or stdout)
        result = json.loads(stdout)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["errors"], [])


if __name__ == "__main__":
    unittest.main()
