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

    def test_graph_resolves_aliases_and_counts_inline_tags(self):
        self.write_note(
            "A.md",
            "---\ntitle: A\naliases: [Alpha Note]\ntags: [alpha]\n---\n\n# A\nSee [[Beta Note]]. #inline/tag\n",
        )
        self.write_note("B.md", "---\ntitle: B\naliases: [Beta Note]\ntags: gamma\n---\n\n# B\n")

        graph = self.module.obsidian_build_graph(str(self.vault))

        self.assertEqual(graph["edgeCount"], 1)
        self.assertEqual(graph["edges"][0]["target"], "B.md")
        self.assertEqual(graph["backlinks"]["B.md"], ["A.md"])
        self.assertEqual({item["tag"] for item in graph["tags"]}, {"alpha", "gamma", "inline/tag"})

    def test_lint_reports_unresolved_links_and_missing_wiki_files(self):
        self.write_note("A.md", "---\ntitle: A\n---\n\n# A\nSee [[Missing]].\n")

        result = self.module.obsidian_lint_vault(str(self.vault))
        codes = {issue["code"] for issue in result["issues"]}

        self.assertFalse(result["ok"])
        self.assertIn("unresolved_links", codes)
        self.assertIn("missing_wiki_files", codes)

    def test_update_wiki_index_creates_generated_catalogue(self):
        self.write_note("notes/A.md", "---\ntitle: Alpha\ntags: [topic]\n---\n\n# Alpha\n")

        result = self.module.obsidian_update_wiki_index(str(self.vault))

        self.assertTrue(result["ok"])
        self.assertTrue(result["changed"])
        index = (self.vault / "index.md").read_text(encoding="utf-8")
        self.assertIn("obsidian-vault:index:start", index)
        self.assertIn("[[notes/A|Alpha]]", index)
        self.assertIn("`#topic`", index)

    def test_append_wiki_log_adds_chronological_entry(self):
        result = self.module.obsidian_append_wiki_log(
            "Updated project notes",
            str(self.vault),
            touched_paths_json=json.dumps(["notes/A.md"]),
            metadata_json=json.dumps({"mode": "test"}),
        )

        self.assertTrue(result["ok"])
        log = (self.vault / "log.md").read_text(encoding="utf-8")
        self.assertIn("# Log", log)
        self.assertIn("Updated project notes", log)
        self.assertIn("[[notes/A]]", log)
        self.assertIn("`mode`: test", log)

    def test_ingest_source_note_creates_linked_wiki_pages(self):
        result = self.module.obsidian_ingest_source_note(
            "sources/Paper.md",
            "Raw extraction text.",
            str(self.vault),
            title="Important Paper",
            summary="A concise source summary.",
            metadata_json=json.dumps({"doi": "10.0000/example"}),
            entities_json=json.dumps([{"name": "Example Entity", "summary": "An important entity."}]),
            concepts_json=json.dumps(["Example Concept"]),
            overwrite=True,
        )

        self.assertTrue(result["ok"])
        source = (self.vault / "sources" / "Paper.md").read_text(encoding="utf-8")
        entity = (self.vault / "entities" / "Example Entity.md").read_text(encoding="utf-8")
        concept = (self.vault / "concepts" / "Example Concept.md").read_text(encoding="utf-8")
        index = (self.vault / "index.md").read_text(encoding="utf-8")
        log = (self.vault / "log.md").read_text(encoding="utf-8")

        self.assertIn("[[entities/Example Entity|Example Entity]]", source)
        self.assertIn("[[concepts/Example Concept|Example Concept]]", source)
        self.assertIn("[[sources/Paper|Important Paper]]", entity)
        self.assertIn("type: concept", concept)
        self.assertIn("[[sources/Paper|Important Paper]]", index)
        self.assertIn("Ingested source note: Important Paper", log)

    def test_base_template_list_includes_project_templates(self):
        templates = self.module.obsidian_list_base_templates()

        self.assertIn("literature", templates)
        self.assertIn("equipment", templates)
        self.assertIn("economics", templates)

    def test_create_base_template_writes_yaml(self):
        result = self.module.obsidian_create_base_template(
            "equipment",
            "bases/equipment.base",
            str(self.vault),
            options_json=json.dumps({"folder": "02-equipment", "tag": "equipment", "title": "Equipment Register"}),
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["template"], "equipment")
        content = (self.vault / "bases" / "equipment.base").read_text(encoding="utf-8")
        self.assertIn("Equipment Register", content)
        self.assertIn('file.inFolder("02-equipment")', content)
        self.assertIn("tag_no", content)
        self.assertIn("summaries", content)

    def test_create_base_template_dry_run_does_not_write(self):
        result = self.module.obsidian_create_base_template(
            "sources",
            "bases/sources.base",
            str(self.vault),
            dry_run=True,
        )

        self.assertTrue(result["ok"])
        self.assertTrue(result["dryRun"])
        self.assertTrue(result["changed"])
        self.assertIn("+views:", result["diff"])
        self.assertFalse((self.vault / "bases" / "sources.base").exists())

    def test_create_canvas_from_graph_writes_file_nodes_and_edges(self):
        self.write_note("A.md", "---\ntitle: A\ntags: [concept]\n---\n\n# A\nSee [[B]].\n")
        self.write_note("B.md", "---\ntitle: B\ntags: [concept]\n---\n\n# B\n")

        result = self.module.obsidian_create_canvas_from_graph(
            "maps/topic.canvas",
            str(self.vault),
            tag="concept",
            layout="grid",
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["noteNodeCount"], 2)
        self.assertEqual(result["edgeCount"], 1)
        payload = json.loads((self.vault / "maps" / "topic.canvas").read_text(encoding="utf-8"))
        file_nodes = [node for node in payload["nodes"] if node["type"] == "file"]
        self.assertEqual({node["file"] for node in file_nodes}, {"A.md", "B.md"})
        self.assertEqual(payload["edges"][0]["toEnd"], "arrow")

    def test_create_canvas_from_graph_dry_run_does_not_write(self):
        self.write_note("A.md", "---\ntitle: A\ntags: [source]\n---\n\n# A\n")

        result = self.module.obsidian_create_canvas_from_graph(
            "maps/source.canvas",
            str(self.vault),
            tag="source",
            dry_run=True,
        )

        self.assertTrue(result["ok"])
        self.assertTrue(result["dryRun"])
        self.assertIn("+  \"nodes\": [", result["diff"])
        self.assertFalse((self.vault / "maps" / "source.canvas").exists())

    def test_create_dataview_note_writes_query_block(self):
        result = self.module.obsidian_create_dataview_note(
            "equipment",
            "views/equipment.md",
            str(self.vault),
            options_json=json.dumps({"folder": "equipment", "tag": "equipment", "title": "Equipment View"}),
        )

        self.assertTrue(result["ok"])
        content = (self.vault / "views" / "equipment.md").read_text(encoding="utf-8")
        self.assertIn("```dataview", content)
        self.assertIn('FROM #equipment AND "equipment"', content)
        self.assertIn("TABLE tag_no, service, area, status, cost, vendor", content)

    def test_create_note_can_apply_user_template(self):
        (self.vault / ".obsidian" / "templates.json").write_text(json.dumps({"folder": "Templates"}), encoding="utf-8")
        self.write_note("Templates/Literature.md", "Template for {{title}}\n\n{{body}}\n\nStatus: {{status}}\n")

        templates = self.module.obsidian_list_user_templates(str(self.vault))
        result = self.module.obsidian_create_note(
            "notes/Templated",
            body="Body text.",
            properties_json=json.dumps({"status": "draft"}),
            vault_path=str(self.vault),
            template_name="Literature",
        )

        self.assertEqual(templates["templates"][0]["path"], "Templates/Literature.md")
        self.assertEqual(result["template"], "Templates/Literature.md")
        note = (self.vault / "notes" / "Templated.md").read_text(encoding="utf-8")
        self.assertIn("Template for Templated", note)
        self.assertIn("Status: draft", note)

    def test_create_note_merges_template_frontmatter_and_templater_variables(self):
        (self.vault / ".obsidian" / "templates.json").write_text(json.dumps({"folder": "Templates"}), encoding="utf-8")
        self.write_note(
            "Templates/Project.md",
            "---\ntype: project\nstatus: template\ncreated: \"<% tp.date.now('YYYY-MM-DD') %>\"\nowner: \"{{property:owner}}\"\n---\n# <% tp.file.title %>\n\n{{content}}\n",
        )

        result = self.module.obsidian_create_note(
            "projects/Alpha",
            body="Project body.",
            properties_json=json.dumps({"status": "active", "owner": "Ada"}),
            vault_path=str(self.vault),
            template_name="Project",
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["properties"]["type"], "project")
        self.assertEqual(result["properties"]["status"], "active")
        self.assertEqual(result["properties"]["owner"], "Ada")
        note = (self.vault / "projects" / "Alpha.md").read_text(encoding="utf-8")
        self.assertIn("created:", note)
        self.assertIn("# Alpha", note)
        self.assertIn("Project body.", note)

    def test_vault_config_overrides_default_output_folders(self):
        (self.vault / ".obsidian-vault-mcp.json").write_text(
            json.dumps({"literatureFolder": "01-literature", "zoteroAttachmentsFolder": "assets/zotero"}),
            encoding="utf-8",
        )
        metadata = {"title": "Configured Folder Paper", "citekey": "configured2026"}

        result = self.module.obsidian_ingest_reference(json.dumps(metadata), str(self.vault), overwrite=True)

        self.assertTrue(result["ok"])
        self.assertEqual(result["referencePath"], "01-literature/Configured Folder Paper.md")
        self.assertTrue((self.vault / "01-literature" / "Configured Folder Paper.md").exists())

    def test_validate_vault_schema_reports_frontmatter_and_canvas_errors(self):
        self.write_note("sources/Bad.md", "---\ntype: source\ntags: source\n---\n\n# Bad\n")
        (self.vault / "bad.canvas").write_text(json.dumps({"nodes": [{"id": "a", "type": "file"}], "edges": []}), encoding="utf-8")

        result = self.module.obsidian_validate_vault_schema(str(self.vault))
        messages = [issue["message"] for issue in result["issues"]]

        self.assertFalse(result["ok"])
        self.assertIn("Missing required property.", messages)
        self.assertIn("Canvas node is missing a required field.", messages)

    def test_validate_vault_schema_reports_strict_canvas_and_base_errors(self):
        (self.vault / "bad.canvas").write_text(
            json.dumps(
                {
                    "nodes": [{"id": "a", "type": "unknown", "x": 0, "y": 0, "width": -1, "height": 100}],
                    "edges": [{"id": "e1", "fromNode": "a", "toNode": "missing", "fromSide": "middle"}],
                }
            ),
            encoding="utf-8",
        )
        (self.vault / "bad.base").write_text(
            "filters:\n  xor:\n    - file.ext == \"md\"\nviews:\n  - type: table\n    groupBy:\n      property: status\n      direction: SIDEWAYS\n    order: file.name\n",
            encoding="utf-8",
        )

        result = self.module.obsidian_validate_vault_schema(str(self.vault))
        messages = [issue["message"] for issue in result["issues"]]

        self.assertFalse(result["ok"])
        self.assertIn("Canvas node type must be text, file, link, or group.", messages)
        self.assertIn("Canvas node size must be positive.", messages)
        self.assertIn("Canvas edge side must be top, right, bottom, or left.", messages)
        self.assertIn("Base filter operator must be and, or, or not.", messages)
        self.assertIn("Base view order must be a list of property strings.", messages)
        self.assertIn("Base groupBy direction must be ASC or DESC.", messages)

    def test_apply_schema_defaults_fills_missing_frontmatter(self):
        self.write_note("entities/Example Entity.md", "# Example Entity\n\nEntity note.")

        dry = self.module.obsidian_apply_schema_defaults(str(self.vault), dry_run=True)
        self.assertTrue(dry["ok"])
        self.assertTrue(dry["dryRun"])
        self.assertEqual(dry["updateCount"], 1)
        self.assertIn("+title: Example Entity", dry["changes"][0]["diff"])
        self.assertFalse((self.vault / "entities" / "Example Entity.md").read_text(encoding="utf-8").startswith("---"))

        applied = self.module.obsidian_apply_schema_defaults(str(self.vault), dry_run=False)
        self.assertTrue(applied["ok"])
        note = (self.vault / "entities" / "Example Entity.md").read_text(encoding="utf-8")
        self.assertIn("type: entity", note)
        self.assertIn("sources: []", note)

    def test_graph_improvements_suggest_unresolved_and_markdown_links(self):
        self.write_note("A.md", "---\ntitle: A\ntags: [topic]\n---\n\n# A\nSee [[Missing]] and [B](B.md).\n")

        result = self.module.obsidian_suggest_graph_improvements(str(self.vault))
        kinds = {suggestion["kind"] for suggestion in result["suggestions"]}

        self.assertIn("create_note", kinds)
        self.assertIn("markdown_links", kinds)

    def test_canvas_from_graph_grouped_layout_creates_group_nodes(self):
        self.write_note("sources/A.md", "---\ntitle: A\ntags: [source]\n---\n\n# A\nSee [[entities/B]].\n")
        self.write_note("entities/B.md", "---\ntitle: B\ntags: [entity]\n---\n\n# B\n")

        result = self.module.obsidian_create_canvas_from_graph(
            "maps/grouped.canvas",
            str(self.vault),
            layout="grouped",
            group_by="tag",
        )

        self.assertTrue(result["ok"])
        self.assertGreaterEqual(result["groupCount"], 2)
        payload = json.loads((self.vault / "maps" / "grouped.canvas").read_text(encoding="utf-8"))
        group_labels = {node["label"] for node in payload["nodes"] if node["type"] == "group"}
        self.assertIn("source", group_labels)
        self.assertIn("entity", group_labels)

    def test_structured_cli_wrappers_parse_json_and_build_commands(self):
        calls = []

        def fake_cli(command, params_json="{}", flags_json="[]", vault="", cwd="", timeout_seconds=30):
            calls.append((command, json.loads(params_json), json.loads(flags_json), vault, timeout_seconds))
            if command in {"backlinks", "base:query", "properties", "tasks"}:
                return {"ok": True, "command": ["obsidian", command], "returnCode": 0, "stdout": '[{\"file\":\"A.md\"}]', "stderr": ""}
            return {"ok": True, "command": ["obsidian", command], "returnCode": 0, "stdout": "plain", "stderr": ""}

        original = self.module._tools.obsidian_cli
        self.module._tools.obsidian_cli = fake_cli
        try:
            backlinks = self.module.obsidian_cli_backlinks(path="A.md", counts=True)
            base = self.module.obsidian_cli_base_query(path="bases/test.base", view="Main")
            props = self.module.obsidian_cli_properties(path="A.md", counts=True)
            tasks = self.module.obsidian_cli_tasks(path="A.md", todo=True)
            read = self.module.obsidian_cli_read(path="A.md")
        finally:
            self.module._tools.obsidian_cli = original

        self.assertEqual(backlinks["data"], [{"file": "A.md"}])
        self.assertEqual(base["data"], [{"file": "A.md"}])
        self.assertEqual(props["data"], [{"file": "A.md"}])
        self.assertEqual(tasks["data"], [{"file": "A.md"}])
        self.assertEqual(read["content"], "plain")
        self.assertIn(("backlinks", {"path": "A.md", "format": "json"}, ["counts"], "", 30), calls)
        self.assertIn(("base:query", {"path": "bases/test.base", "view": "Main", "format": "json"}, [], "", 30), calls)

    def test_structured_cli_mutating_wrappers(self):
        calls = []

        def fake_cli(command, params_json="{}", flags_json="[]", vault="", cwd="", timeout_seconds=30):
            calls.append((command, json.loads(params_json), json.loads(flags_json), vault))
            return {"ok": True, "command": ["obsidian", command], "returnCode": 0, "stdout": "", "stderr": ""}

        original = self.module._tools.obsidian_cli
        self.module._tools.obsidian_cli = fake_cli
        try:
            set_result = self.module.obsidian_cli_property_set("status", "done", path="A.md", property_type="text")
            remove_result = self.module.obsidian_cli_property_remove("status", path="A.md")
            screenshot = self.module.obsidian_cli_screenshot("shot.png")
            reload_result = self.module.obsidian_cli_plugin_reload("obsidian-git")
            dry_move = self.module.obsidian_cli_move_or_rename("move", path="A.md", to="Archive/A.md")
            applied_rename = self.module.obsidian_cli_move_or_rename("rename", path="A.md", name="B.md", dry_run=False)
        finally:
            self.module._tools.obsidian_cli = original

        self.assertTrue(set_result["ok"])
        self.assertTrue(remove_result["ok"])
        self.assertTrue(screenshot["ok"])
        self.assertTrue(reload_result["ok"])
        self.assertTrue(dry_move["dryRun"])
        self.assertEqual(dry_move["command"][-1], "to=Archive/A.md")
        self.assertFalse(applied_rename["dryRun"])
        self.assertIn(("property:set", {"name": "status", "value": "done", "type": "text", "path": "A.md"}, [], ""), calls)
        self.assertIn(("rename", {"path": "A.md", "name": "B.md"}, [], ""), calls)

    def test_cli_json_parser_handles_no_rows_messages(self):
        parsed = self.module._parse_cli_stdout(
            {"ok": True, "command": ["obsidian", "tasks"], "returnCode": 0, "stdout": "\nNo tasks found.\n", "stderr": ""},
            "json",
        )

        self.assertEqual(parsed["data"], [])
        self.assertNotIn("parseError", parsed)

    def test_cli_json_parser_skips_failed_results(self):
        parsed = self.module._parse_cli_stdout(
            {"ok": False, "command": ["obsidian", "tasks"], "returnCode": 0, "stdout": "Vault not found.\n", "stderr": "", "error": "Vault not found."},
            "json",
        )

        self.assertFalse(parsed["ok"])
        self.assertEqual(parsed["error"], "Vault not found.")
        self.assertNotIn("parseError", parsed)

    def test_obsidian_cli_treats_zero_exit_error_text_as_failure(self):
        class Completed:
            returncode = 0
            stdout = "Vault not found.\n"
            stderr = ""

        original_which = self.module.shutil.which
        original_run = self.module.subprocess.run
        self.module.shutil.which = lambda command: "obsidian.CMD"
        self.module.subprocess.run = lambda *args, **kwargs: Completed()
        try:
            result = self.module.obsidian_cli("read", params_json=json.dumps({"path": "A.md"}))
        finally:
            self.module.shutil.which = original_which
            self.module.subprocess.run = original_run

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "Vault not found.")

    def test_obsidian_cli_does_not_use_shell_fallback_on_windows(self):
        calls = []

        class Completed:
            returncode = 1
            stdout = ""
            stderr = ""

        def fake_run(args, **kwargs):
            calls.append((args, kwargs))
            return Completed()

        original_which = self.module.shutil.which
        original_run = self.module.subprocess.run
        self.module.shutil.which = lambda command: "obsidian.CMD"
        self.module.subprocess.run = fake_run
        try:
            result = self.module.obsidian_cli("base:query", params_json=json.dumps({"path": "A.md & bad"}))
        finally:
            self.module.shutil.which = original_which
            self.module.subprocess.run = original_run

        self.assertFalse(result["ok"])
        self.assertEqual(len(calls), 1)
        self.assertNotIn("fallbackCommand", result)
        self.assertFalse(calls[0][1].get("shell", False))
        self.assertEqual(calls[0][0][0], "obsidian.CMD")

    def test_edit_plan_preview_apply_and_rollback(self):
        self.write_note("A.md", "---\ntitle: A\ntags: [topic]\n---\n\n# A\nOld text.\n")
        plan = {
            "operations": [
                {"op": "update_properties", "path": "A.md", "properties": {"status": "draft"}},
                {"op": "write", "path": "B.md", "content": "# B\nCreated.\n"},
            ]
        }

        preview = self.module.obsidian_preview_edit_plan(json.dumps(plan), str(self.vault))
        self.assertEqual(preview["operationCount"], 2)
        self.assertEqual(preview["changeCount"], 2)
        self.assertFalse((self.vault / "B.md").exists())

        applied = self.module.obsidian_apply_edit_plan(json.dumps(plan), str(self.vault), transaction_id="tx-test")
        self.assertTrue(applied["ok"])
        self.assertTrue((self.vault / ".obsidian-vault-backups" / "tx-test" / "manifest.json").exists())
        self.assertIn("status: draft", (self.vault / "A.md").read_text(encoding="utf-8"))
        self.assertTrue((self.vault / "B.md").exists())

        rollback_preview = self.module.obsidian_rollback_edit_plan("tx-test", str(self.vault), dry_run=True)
        self.assertTrue(rollback_preview["dryRun"])
        self.assertTrue((self.vault / "B.md").exists())

        rolled_back = self.module.obsidian_rollback_edit_plan("tx-test", str(self.vault))
        self.assertTrue(rolled_back["ok"])
        self.assertNotIn("status: draft", (self.vault / "A.md").read_text(encoding="utf-8"))
        self.assertFalse((self.vault / "B.md").exists())

    def test_edit_plan_accepts_operation_alias(self):
        self.write_note("A.md", "# A\nOld text.\n")
        plan = {
            "operations": [
                {"operation": "replace", "path": "A.md", "old": "Old text.", "new": "New text."},
            ]
        }

        preview = self.module.obsidian_preview_edit_plan(json.dumps(plan), str(self.vault))

        self.assertEqual(preview["changes"][0]["op"], "replace")
        self.assertIn("+New text.", preview["changes"][0]["diff"])

    def test_edit_plan_rejects_duplicate_targets_and_escaping_paths(self):
        duplicate_plan = {
            "operations": [
                {"op": "write", "path": "A.md", "content": "one"},
                {"op": "append", "path": "A.md", "content": "two"},
            ]
        }
        escape_plan = {"operations": [{"op": "write", "path": "../outside.md", "content": "bad"}]}

        with self.assertRaises(ValueError):
            self.module.obsidian_preview_edit_plan(json.dumps(duplicate_plan), str(self.vault))
        with self.assertRaises(ValueError):
            self.module.obsidian_preview_edit_plan(json.dumps(escape_plan), str(self.vault))

    def test_edit_plan_rejects_unsafe_transaction_id(self):
        plan = {"operations": [{"op": "write", "path": "A.md", "content": "created"}]}

        with self.assertRaises(ValueError):
            self.module.obsidian_apply_edit_plan(json.dumps(plan), str(self.vault), transaction_id="../escape")
        with self.assertRaises(ValueError):
            self.module.obsidian_rollback_edit_plan("../escape", str(self.vault))

        self.assertFalse((self.vault.parent / "escape").exists())

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

    def test_ingest_zotero_item_copies_pdf_and_creates_note(self):
        pdf = self.vault / "external.pdf"
        supplement = self.vault / "supplement.pdf"
        missing = self.vault / "missing.pdf"
        pdf.write_bytes(b"%PDF-1.4\n")
        supplement.write_bytes(b"%PDF-1.4\n")

        def fake_api(path, params=None, api_base=""):
            if path == "users/0/items/ITEM1":
                return {
                    "key": "ITEM1",
                    "data": {
                        "key": "ITEM1",
                        "itemType": "journalArticle",
                        "title": "Zotero Article",
                        "creators": [{"firstName": "Ada", "lastName": "Lovelace"}],
                        "date": "2024",
                        "DOI": "10.1000/zotero",
                        "abstractNote": "Abstract from Zotero.",
                        "tags": [{"tag": "chemistry"}],
                    },
                }
            if path == "users/0/items/ITEM1/children":
                return [
                    {"key": "NOTE1", "data": {"key": "NOTE1", "itemType": "note", "note": "<p>Imported note</p>"}},
                    {"key": "PDF1", "data": {"key": "PDF1", "itemType": "attachment", "title": "PDF", "contentType": "application/pdf", "path": str(pdf)}},
                    {"key": "PDF2", "data": {"key": "PDF2", "itemType": "attachment", "title": "Supplement", "contentType": "application/pdf", "path": str(supplement)}},
                    {"key": "PDF3", "data": {"key": "PDF3", "itemType": "attachment", "title": "Missing", "contentType": "application/pdf", "path": str(missing)}},
                ]
            return []

        original = self.module._tools._zotero_api
        self.module._tools._zotero_api = fake_api
        try:
            result = self.module.obsidian_ingest_zotero_item(
                "ITEM1",
                str(self.vault),
                source_folder="zotero",
                attachments_folder="attachments/zotero",
                copy_pdf_attachments=True,
                overwrite=True,
            )
        finally:
            self.module._tools._zotero_api = original

        self.assertTrue(result["ok"])
        self.assertEqual(result["children"]["attachments"], 3)
        self.assertTrue((self.vault / "attachments" / "zotero" / "ITEM1" / "external.pdf").exists())
        self.assertTrue((self.vault / "attachments" / "zotero" / "ITEM1" / "supplement.pdf").exists())
        self.assertEqual(
            result["linkedAttachments"],
            ["attachments/zotero/ITEM1/external.pdf", "attachments/zotero/ITEM1/supplement.pdf"],
        )
        self.assertEqual(len(result["attachmentErrors"]), 1)
        note = (self.vault / "zotero" / "Lovelace (2024) - Zotero Article.md").read_text(encoding="utf-8")
        self.assertIn("zoteroKey: ITEM1", note)
        self.assertIn("zoteroSelect: zotero://select/library/items/ITEM1", note)
        self.assertIn("zotero://open-pdf/library/items/PDF1", note)
        self.assertIn("Imported note", note)
        self.assertIn("![[attachments/zotero/ITEM1/external.pdf]]", note)
        self.assertIn("![[attachments/zotero/ITEM1/supplement.pdf]]", note)
        self.assertIn("Attachment Import Warnings", note)

    def test_zotero_attachment_naming_strategy_and_duplicate_detection(self):
        pdf = self.vault / "Original Name.pdf"
        pdf.write_bytes(b"%PDF-1.4\n")

        def fake_api(path, params=None, api_base=""):
            if path == "users/0/items/ITEM1":
                return {
                    "key": "ITEM1",
                    "data": {
                        "key": "ITEM1",
                        "itemType": "journalArticle",
                        "title": "Named Attachment Paper",
                        "creators": [{"lastName": "Doe"}],
                        "date": "2026",
                        "DOI": "10.1000/named",
                    },
                }
            if path == "users/0/items/ITEM1/children":
                return [{"key": "PDF1", "data": {"key": "PDF1", "itemType": "attachment", "contentType": "application/pdf", "path": str(pdf)}}]
            return []

        original = self.module._tools._zotero_api
        self.module._tools._zotero_api = fake_api
        try:
            result = self.module.obsidian_ingest_zotero_item(
                "ITEM1",
                str(self.vault),
                copy_pdf_attachments=True,
                attachment_name_strategy="zotero_key",
                overwrite=True,
            )
            duplicate = self.module.obsidian_ingest_zotero_item("ITEM1", str(self.vault))
        finally:
            self.module._tools._zotero_api = original

        self.assertTrue(result["ok"])
        self.assertEqual(result["linkedAttachments"], ["attachments/zotero/ITEM1/PDF1.pdf"])
        self.assertTrue((self.vault / "attachments" / "zotero" / "ITEM1" / "PDF1.pdf").exists())
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(duplicate["matchedOn"], "zoteroKey")

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

    def test_smoke_integrations_reports_success_without_writing(self):
        smoke = load_smoke_module()
        calls = []

        class FakeTools:
            @staticmethod
            def obsidian_vault_status(vault_path=""):
                calls.append(("status", vault_path))
                return {"vaultPath": vault_path, "fileCount": 3}

            @staticmethod
            def obsidian_create_note(path, title="", body="", properties_json="{}", vault_path="", dry_run=False, overwrite=False):
                calls.append(("create_note", path, dry_run, overwrite))
                return {"ok": True, "dryRun": dry_run, "changed": True, "path": path}

            @staticmethod
            def obsidian_zotero_ping():
                calls.append(("zotero_ping",))
                return {"ok": True, "sampleCount": 1}

            @staticmethod
            def obsidian_zotero_search_items(query, limit=1):
                calls.append(("zotero_search", query, limit))
                return [{"key": "ITEM1", "itemType": "journalArticle", "title": "Example", "rawData": {"private": True}}]

            @staticmethod
            def obsidian_cli(command, params_json="{}", timeout_seconds=30):
                calls.append(("cli", command, params_json, timeout_seconds))
                return {"ok": True, "stdout": "F:/Vault\n"}

        result = smoke.run_smoke("F:/Vault", tools=FakeTools)

        self.assertTrue(result["ok"])
        self.assertEqual(result["summary"]["failed"], 0)
        zotero_search = next(check for check in result["checks"] if check["name"] == "zotero_search")
        self.assertEqual(zotero_search["data"], [{"key": "ITEM1", "itemType": "journalArticle", "title": "Example"}])
        self.assertIn(("create_note", ".obsidian-vault-smoke.md", True, True), calls)
        self.assertFalse((self.vault / ".obsidian-vault-smoke.md").exists())

    def test_smoke_integrations_treats_optional_checks_as_warnings(self):
        smoke = load_smoke_module()

        class FakeTools:
            @staticmethod
            def obsidian_vault_status(vault_path=""):
                return {"vaultPath": vault_path}

            @staticmethod
            def obsidian_create_note(*args, **kwargs):
                return {"ok": True, "dryRun": True}

            @staticmethod
            def obsidian_zotero_ping():
                return {"ok": False, "error": "Zotero is closed"}

            @staticmethod
            def obsidian_zotero_search_items(query, limit=1):
                raise AssertionError("search should be skipped when ping fails")

            @staticmethod
            def obsidian_cli(command, params_json="{}", timeout_seconds=30):
                return {"ok": False, "error": "CLI unavailable"}

        result = smoke.run_smoke("F:/Vault", tools=FakeTools)

        self.assertTrue(result["ok"])
        self.assertEqual(result["summary"]["warning"], 2)
        self.assertEqual(result["summary"]["failed"], 0)

    def test_smoke_integrations_warns_when_obsidian_cli_uses_different_vault(self):
        smoke = load_smoke_module()

        class FakeTools:
            @staticmethod
            def obsidian_vault_status(vault_path=""):
                return {"vaultPath": vault_path}

            @staticmethod
            def obsidian_create_note(*args, **kwargs):
                return {"ok": True, "dryRun": True}

            @staticmethod
            def obsidian_zotero_ping():
                return {"ok": False}

            @staticmethod
            def obsidian_zotero_search_items(query, limit=1):
                return []

            @staticmethod
            def obsidian_cli(command, params_json="{}", timeout_seconds=30):
                return {"ok": True, "stdout": "F:/OtherVault\n"}

        result = smoke.run_smoke("F:/Vault", tools=FakeTools)
        cli_check = next(check for check in result["checks"] if check["name"] == "obsidian_cli_vault")

        self.assertTrue(result["ok"])
        self.assertEqual(cli_check["status"], "warning")
        self.assertEqual(cli_check["data"]["activeVault"], "F:/OtherVault")

    def test_parse_bibtex_normalizes_reference_metadata(self):
        bibtex = """@string{jcp = "Journal of " # "Catalysis"}
        @comment{ignored}
        @article{smith2024example,
          title={{Example} process design},
          author={Smith, Jane and Doe, John},
          journal=jcp,
          month=jan # " 15",
          year=2024,
          doi={10.1000/example},
          keywords={example, process}
        }"""

        result = self.module.obsidian_parse_bibtex(bibtex)

        self.assertEqual(result["entryCount"], 1)
        entry = result["entries"][0]
        self.assertEqual(entry["citekey"], "smith2024example")
        self.assertEqual(entry["authors"], ["Smith, Jane", "Doe, John"])
        self.assertEqual(entry["year"], 2024)
        self.assertEqual(entry["journal"], "Journal of Catalysis")
        self.assertEqual(entry["month"], "January 15")
        self.assertEqual(entry["keywords"], ["example", "process"])

    def test_ingest_reference_dry_run_and_apply(self):
        metadata = {
            "title": "Example Process Design",
            "authors": ["Jane Smith"],
            "year": 2024,
            "doi": "10.1000/example",
            "citekey": "smith2024example",
        }

        dry = self.module.obsidian_ingest_reference(
            json.dumps(metadata),
            str(self.vault),
            source_folder="literature",
            abstract="Reference abstract.",
            dry_run=True,
        )
        self.assertTrue(dry["dryRun"])
        self.assertFalse((self.vault / "literature" / "Smith (2024) - Example Process Design.md").exists())

        applied = self.module.obsidian_ingest_reference(
            json.dumps(metadata),
            str(self.vault),
            source_folder="literature",
            abstract="Reference abstract.",
            overwrite=True,
        )
        self.assertTrue(applied["ok"])
        note = (self.vault / "literature" / "Smith (2024) - Example Process Design.md").read_text(encoding="utf-8")
        self.assertIn("type: literature", note)
        self.assertIn("10.1000/example", note)

    def test_ingest_bibtex_creates_literature_note(self):
        bibtex = """@article{doe2025energy,
          title={Energy integration},
          author={Doe, Jane},
          year={2025}
        }"""

        result = self.module.obsidian_ingest_bibtex(bibtex, str(self.vault), source_folder="papers", overwrite=True)

        self.assertTrue(result["ok"])
        self.assertEqual(result["entryCount"], 1)
        self.assertTrue((self.vault / "papers" / "Doe (2025) - Energy integration.md").exists())

    def test_ingest_mineru_markdown_and_pdf_attachment(self):
        self.write_note("extracts/paper.md", "# Extracted Paper\n\nThis paragraph came from MinerU.")
        (self.vault / "attachments").mkdir(exist_ok=True)
        (self.vault / "attachments" / "paper.pdf").write_bytes(b"%PDF-1.4\n")

        mineru = self.module.obsidian_ingest_mineru_markdown(
            markdown_path="extracts/paper.md",
            pdf_attachment_path="attachments/paper.pdf",
            vault_path=str(self.vault),
            title="MinerU Paper",
            source_path="sources/mineru-paper.md",
            metadata_json=json.dumps({"project": "demo"}),
            overwrite=True,
        )
        pdf = self.module.obsidian_ingest_pdf_attachment(
            "attachments/paper.pdf",
            str(self.vault),
            source_path="sources/pdf-paper.md",
            title="PDF Paper",
            overwrite=True,
        )

        self.assertTrue(mineru["ok"])
        self.assertTrue(pdf["ok"])
        mineru_note = (self.vault / "sources" / "mineru-paper.md").read_text(encoding="utf-8")
        pdf_note = (self.vault / "sources" / "pdf-paper.md").read_text(encoding="utf-8")
        self.assertIn("mineru_markdown: extracts/paper.md", mineru_note)
        self.assertIn("![[attachments/paper.pdf]]", mineru_note)
        self.assertIn("type: pdf", pdf_note)

    def test_mineru_status_reports_missing_cli(self):
        original_which = self.module.shutil.which
        self.module.shutil.which = lambda command: None
        try:
            status = self.module.obsidian_mineru_status("missing-mineru")
        finally:
            self.module.shutil.which = original_which

        self.assertFalse(status["available"])
        self.assertIn("Install MinerU CLI", status["installHint"])

    def test_mineru_extract_dry_run_redacts_token(self):
        (self.vault / "input.pdf").write_bytes(b"%PDF-1.4\n")
        original_which = self.module.shutil.which
        original_run = self.module.subprocess.run
        self.module.shutil.which = lambda command: "mineru-open-api"
        self.module.subprocess.run = lambda *args, **kwargs: type("Completed", (), {"returncode": 0, "stdout": "version", "stderr": ""})()
        try:
            result = self.module.obsidian_mineru_extract(
                "input.pdf",
                str(self.vault),
                output_path="mineru-output/input",
                token="secret-token",
                dry_run=True,
            )
        finally:
            self.module.shutil.which = original_which
            self.module.subprocess.run = original_run

        self.assertTrue(result["ok"])
        self.assertTrue(result["dryRun"])
        self.assertIn("--token", result["command"])
        self.assertIn("***", result["command"])
        self.assertNotIn("secret-token", result["command"])
        self.assertEqual(result["command"][0], "mineru-open-api")
        self.assertFalse((self.vault / "mineru-output").exists())

    def test_mineru_extract_and_ingest_uses_cli_output(self):
        (self.vault / "attachments").mkdir(exist_ok=True)
        (self.vault / "attachments" / "paper.pdf").write_bytes(b"%PDF-1.4\n")

        class Completed:
            def __init__(self, returncode=0, stdout="", stderr=""):
                self.returncode = returncode
                self.stdout = stdout
                self.stderr = stderr

        def fake_run(args, capture_output=True, text=True, timeout=0, check=False):
            if args[1] == "version":
                return Completed(0, "mineru-open-api version v0.test")
            self.assertEqual(args[0], "C:\\tools\\mineru-open-api.CMD")
            output_path = self.module.Path(args[args.index("-o") + 1])
            output_path.mkdir(parents=True, exist_ok=True)
            (output_path / "paper.md").write_text("# MinerU Output\n\nExtracted by fake CLI.", encoding="utf-8")
            return Completed(0, "ok")

        original_which = self.module.shutil.which
        original_run = self.module.subprocess.run
        self.module.shutil.which = lambda command: "C:\\tools\\mineru-open-api.CMD"
        self.module.subprocess.run = fake_run
        try:
            result = self.module.obsidian_mineru_extract_and_ingest(
                "attachments/paper.pdf",
                str(self.vault),
                output_path="mineru-output/paper",
                source_path="sources/mineru-cli-paper.md",
                title="MinerU CLI Paper",
                overwrite=True,
            )
        finally:
            self.module.shutil.which = original_which
            self.module.subprocess.run = original_run

        self.assertTrue(result["ok"])
        self.assertEqual(result["extraction"]["markdownPath"], "mineru-output/paper/paper.md")
        note = (self.vault / "sources" / "mineru-cli-paper.md").read_text(encoding="utf-8")
        self.assertIn("mineru_markdown: mineru-output/paper/paper.md", note)
        self.assertIn("![[attachments/paper.pdf]]", note)

    def test_build_graph_scans_body_not_frontmatter(self):
        # Wikilink inside a YAML value should NOT create an edge
        self.write_note("A.md", "---\ntitle: A\nrelated: '[[B]]'\n---\n\n# A\nNo body links.\n")
        self.write_note("B.md", "---\ntitle: B\n---\n\n# B\n")

        graph = self.module.obsidian_build_graph(str(self.vault))

        # related field is a citation edge, not a wikilink edge
        wikilink_edges = [e for e in graph["edges"] if e["kind"] == "wikilink"]
        self.assertEqual(len(wikilink_edges), 0)

    def test_build_graph_extracts_citation_edges(self):
        self.write_note("A.md", "---\ntitle: A\nentities:\n  - entities/E.md\ncites:\n  - '[[B]]'\n---\n\n# A\n")
        self.write_note("B.md", "---\ntitle: B\n---\n\n# B\n")
        self.write_note("entities/E.md", "---\ntitle: E\n---\n\n# E\n")

        graph = self.module.obsidian_build_graph(str(self.vault))

        kinds = {e["kind"] for e in graph["edges"]}
        self.assertIn("entities", kinds)
        self.assertIn("cites", kinds)
        entity_edge = next(e for e in graph["edges"] if e["kind"] == "entities")
        self.assertEqual(entity_edge["source"], "A.md")
        self.assertEqual(entity_edge["target"], "entities/E.md")

    def test_build_graph_cache_returns_same_result(self):
        self.write_note("A.md", "---\ntitle: A\n---\n\n# A\nSee [[B]].\n")
        self.write_note("B.md", "---\ntitle: B\n---\n\n# B\n")

        result1 = self.module.obsidian_build_graph(str(self.vault))
        result2 = self.module.obsidian_build_graph(str(self.vault))

        self.assertIs(result1, result2)

    def test_build_graph_cache_invalidates_on_file_change(self):
        self.write_note("A.md", "---\ntitle: A\n---\n\n# A\n")

        result1 = self.module.obsidian_build_graph(str(self.vault))
        import time
        time.sleep(0.01)
        self.write_note("B.md", "---\ntitle: B\n---\n\n# B\n")
        result2 = self.module.obsidian_build_graph(str(self.vault))

        self.assertIsNot(result1, result2)
        self.assertEqual(result2["nodeCount"], 2)

    def test_suggest_improvements_max_reciprocal(self):
        # Create a chain A→B→C→D so there are 3 one-directional edges
        self.write_note("A.md", "---\ntitle: A\n---\n\n# A\nSee [[B]].\n")
        self.write_note("B.md", "---\ntitle: B\n---\n\n# B\nSee [[C]].\n")
        self.write_note("C.md", "---\ntitle: C\n---\n\n# C\nSee [[D]].\n")
        self.write_note("D.md", "---\ntitle: D\n---\n\n# D\n")

        result_limited = self.module.obsidian_suggest_graph_improvements(str(self.vault), max_reciprocal=1)
        result_zero = self.module.obsidian_suggest_graph_improvements(str(self.vault), max_reciprocal=0)

        reciprocal_limited = [s for s in result_limited["suggestions"] if s["kind"] == "consider_reciprocal_link"]
        reciprocal_zero = [s for s in result_zero["suggestions"] if s["kind"] == "consider_reciprocal_link"]
        self.assertLessEqual(len(reciprocal_limited), 1)
        self.assertEqual(len(reciprocal_zero), 0)

    def test_suggest_improvements_no_false_positive_duplicate_titles(self):
        # "My Note" and "MyNote" should NOT be flagged as duplicates
        self.write_note("My Note.md", "---\ntitle: My Note\n---\n\n# My Note\n")
        self.write_note("MyNote.md", "---\ntitle: MyNote\n---\n\n# MyNote\n")

        result = self.module.obsidian_suggest_graph_improvements(str(self.vault))
        duplicates = [s for s in result["suggestions"] if s["kind"] == "possible_duplicate"]

        self.assertEqual(len(duplicates), 0)

    def test_suggest_improvements_detects_hyphen_space_duplicates(self):
        # "My-Note" and "My Note" SHOULD be flagged as duplicates (same words)
        self.write_note("My-Note.md", "---\ntitle: My-Note\n---\n\n# My-Note\n")
        self.write_note("My Note.md", "---\ntitle: My Note\n---\n\n# My Note\n")

        result = self.module.obsidian_suggest_graph_improvements(str(self.vault))
        duplicates = [s for s in result["suggestions"] if s["kind"] == "possible_duplicate"]

        self.assertEqual(len(duplicates), 1)

    def test_canvas_from_graph_custom_layer_order(self):
        import json as _json
        self.write_note("A.md", "---\ntitle: A\ntags: [literature]\n---\n\n# A\n")
        self.write_note("B.md", "---\ntitle: B\ntags: [entity]\n---\n\n# B\n")

        result = self.module.obsidian_create_canvas_from_graph(
            "maps/layered.canvas",
            str(self.vault),
            layout="layered",
            layer_order_json='["entity", "literature"]',
        )

        self.assertTrue(result["ok"])
        payload = _json.loads((self.vault / "maps" / "layered.canvas").read_text(encoding="utf-8"))
        file_nodes = {n["file"]: n for n in payload["nodes"] if n["type"] == "file"}
        # entity is layer 0, literature is layer 1 → entity.x < literature.x
        self.assertLess(file_nodes["B.md"]["x"], file_nodes["A.md"]["x"])


if __name__ == "__main__":
    unittest.main()
