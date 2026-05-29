# Tool-to-Skill Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Shrink obsidian-vault-mcp from 82 MCP tools to 17 (literature profile only), converting 55 legacy tools to skill docs and deleting 10 deprecated ones, then publish v1.1.0.

**Architecture:** The single `literature` profile is kept; all profile-gating logic is removed from `common.py`. Legacy tool handlers are deleted from `tools.py`. Their workflows become `SKILL.md` files that instruct Claude to use the 17 remaining MCP tools plus built-in tools (Read, Write, Bash, Grep). Skills live in both `skills/<name>/SKILL.md` (bundled) and `.claude/skills/<name>.md` (local Claude Code).

**Tech Stack:** Python 3.10+, FastMCP, pytest, ruff, twine, gh CLI, pyproject.toml (setuptools)

---

## File Map

| File | Change |
|------|--------|
| `scripts/obsidian_vault_mcp/common.py` | Remove profile system, BIBTEX regexes |
| `scripts/obsidian_vault_mcp/tools.py` | Remove 65 legacy @tool functions |
| `scripts/obsidian_vault_mcp/server.py` | Simplify to single-profile |
| `scripts/obsidian_vault_mcp/cli.py` | Remove profile import; keep `obsidian_doctor` as non-MCP helper |
| `tests/test_obsidian_vault_mcp.py` | Remove 25+ legacy tests; add tool-count assertion |
| `skills/obsidian-vault/SKILL.md` | Enhanced: graph, lint, wiki, schema, bulk-edit |
| `skills/obsidian-cli/SKILL.md` | Enhanced: all 13 CLI wrappers as Bash commands |
| `skills/obsidian-views/SKILL.md` | Enhanced: Canvas JSON, Bases YAML, Dataview DQL |
| `skills/obsidian-graph/SKILL.md` | NEW: citation network, communities, insights |
| `skills/obsidian-graph/agents/openai.yaml` | NEW |
| `skills/obsidian-mineru/SKILL.md` | Enhanced: extract, extract-and-ingest, batch |
| `.claude/skills/obsidian-vault.md` | Mirror |
| `.claude/skills/obsidian-cli.md` | Mirror |
| `.claude/skills/obsidian-views.md` | Mirror |
| `.claude/skills/obsidian-graph.md` | Mirror |
| `.claude/skills/obsidian-mineru.md` | Mirror |
| `README.md` | Rewrite: skill-based architecture, 17-tool list |
| `README.en.md` | English mirror of README.md |
| `docs/TECHNICAL_GUIDE.md` | Trim deleted-tool sections |
| `pyproject.toml` | Bump version 1.0.27 → 1.1.0 |

---

## Tool Classification Reference

### Keep (17 tools — literature profile)
`obsidian_pipeline_config`, `obsidian_pipeline_doctor`, `obsidian_pipeline_ingest_collection`, `obsidian_pipeline_ingest_item`, `obsidian_pipeline_migrate_layout`, `obsidian_pipeline_parse_with_mineru`, `obsidian_pipeline_rename_mineru_images`, `obsidian_read_file`, `obsidian_search`, `obsidian_update_properties`, `obsidian_write_file`, `obsidian_zotero_get_children`, `obsidian_zotero_get_item`, `obsidian_zotero_list_collections`, `obsidian_zotero_list_pdf_attachments`, `obsidian_zotero_ping`, `obsidian_zotero_search_items`

### Delete Group A (10 tools — code removed, no skill)
`obsidian_ingest_bibtex`, `obsidian_ingest_mineru_markdown`, `obsidian_ingest_pdf_attachment`, `obsidian_ingest_reference`, `obsidian_ingest_source_note`, `obsidian_ingest_zotero_collection`, `obsidian_ingest_zotero_item`, `obsidian_mineru_rename_images`, `obsidian_mineru_status`, `obsidian_parse_bibtex`

### Convert Group B (55 tools → skills)
**obsidian-vault:** `obsidian_add_wikilinks`, `obsidian_append_wiki_log`, `obsidian_apply_edit_plan`, `obsidian_apply_schema_defaults`, `obsidian_batch_move_files`, `obsidian_build_graph`, `obsidian_build_reading_digest`, `obsidian_create_note`, `obsidian_delete_file`, `obsidian_doctor`, `obsidian_find_broken_links`, `obsidian_find_orphans`, `obsidian_lint_vault`, `obsidian_list_files`, `obsidian_list_schema_presets`, `obsidian_list_user_templates`, `obsidian_move_file`, `obsidian_preview_edit_plan`, `obsidian_rename_file`, `obsidian_rollback_edit_plan`, `obsidian_update_wiki_index`, `obsidian_validate_vault_schema`, `obsidian_vault_stats`, `obsidian_vault_status`, `obsidian_wiki_context`, `obsidian_wiki_stale_pages`, `obsidian_write_wiki_page`

**obsidian-cli:** `obsidian_cli`, `obsidian_cli_backlinks`, `obsidian_cli_base_query`, `obsidian_cli_move_or_rename`, `obsidian_cli_open`, `obsidian_cli_plugin_reload`, `obsidian_cli_properties`, `obsidian_cli_property_read`, `obsidian_cli_property_remove`, `obsidian_cli_property_set`, `obsidian_cli_read`, `obsidian_cli_screenshot`, `obsidian_cli_tasks`

**obsidian-views:** `obsidian_create_base`, `obsidian_create_base_template`, `obsidian_create_canvas`, `obsidian_create_canvas_from_graph`, `obsidian_create_dataview_note`, `obsidian_list_base_templates`, `obsidian_list_dataview_templates`

**obsidian-graph:** `obsidian_build_citation_network`, `obsidian_build_graph_communities`, `obsidian_graph_insights`, `obsidian_suggest_graph_improvements`

**obsidian-mineru:** `obsidian_mineru_extract`, `obsidian_mineru_extract_and_ingest`, `obsidian_mineru_extract_folder`, `obsidian_zotero_extract_pdf_text`

---

## Task 1 — Baseline

**Files:** Read-only

- [ ] **Run existing test suite and record results**

```powershell
cd "F:\化工设计比赛\plugins\obsidian-vault"
python -m pytest tests/ -v 2>&1 | tee baseline.txt
```

Expected: All tests pass. Note total count.

- [ ] **Verify current tool count**

```powershell
python -c "
import scripts.obsidian_vault_mcp.tools
from scripts.obsidian_vault_mcp.common import get_registered_tool_names
lit = get_registered_tool_names('literature')
full = get_registered_tool_names('full')
print(f'Literature: {len(lit)}, Full: {len(full)}')
"
```

Expected output: `Literature: 17, Full: 82`

- [ ] **Commit baseline marker**

```powershell
git add -A
git commit -m "chore: record baseline before tool-to-skill migration"
```

---

## Task 2 — Simplify common.py

**Files:**
- Modify: `scripts/obsidian_vault_mcp/common.py`
- Modify: `scripts/obsidian_vault_mcp/server.py`

The profile system (`FULL_TOOL_PROFILES`, `KNOWN_TOOL_PROFILES`, `LITERATURE_PROFILE_TOOLS`, `_normalize_tool_profile`, profile arguments to `get_registered_tools`) is removed. All registered tools are the single, default set.

- [ ] **Replace the profile system block in common.py**

In `common.py`, find the block from `DEFAULT_TOOL_PROFILE = "literature"` to the end of `get_registered_tool_names`. Replace it with:

```python
REGISTERED_TOOLS: list[Any] = []


def tool():
    def decorator(func):
        REGISTERED_TOOLS.append(func)
        return func
    return decorator


def get_registered_tools() -> list[Any]:
    return list(REGISTERED_TOOLS)


def get_registered_tool_names() -> list[str]:
    return [func.__name__ for func in REGISTERED_TOOLS]
```

Also remove these two regex constants (only used by Group A BibTeX tools):

```python
BIBTEX_ENTRY_RE = re.compile(r"@(?P<type>[A-Za-z]+)\s*\{\s*(?P<key>[^,\s]+)\s*,(?P<body>.*?)(?=^\s*@|\Z)", re.DOTALL | re.MULTILINE)
BIBTEX_FIELD_RE = re.compile(r"(?P<name>[A-Za-z][A-Za-z0-9_-]*)\s*=\s*(?P<value>\{(?:[^{}]|\{[^{}]*\})*\}|\"(?:[^\"\\]|\\.)*\"|[^,\n]+)\s*,?", re.DOTALL)
```

- [ ] **Simplify server.py**

Replace the entire `server.py` with:

```python
import os

from mcp.server.fastmcp import FastMCP

from . import tools as tools  # noqa: F401 - importing registers tool functions
from .common import get_registered_tools


def create_server() -> FastMCP:
    server = FastMCP("obsidian-vault")
    for func in get_registered_tools():
        server.tool()(func)
    return server


mcp = create_server()


def main() -> None:
    mcp.run()
```

- [ ] **Commit**

```powershell
git add scripts/obsidian_vault_mcp/common.py scripts/obsidian_vault_mcp/server.py
git commit -m "refactor: remove multi-profile system from common.py and server.py"
```

---

## Task 3 — Remove Group A tool functions from tools.py

**Files:**
- Modify: `scripts/obsidian_vault_mcp/tools.py`

Remove the entire function body (including the `@tool()` decorator line) for each of these 10 functions. They are defined with `@tool()` and `def <name>(...)`. Delete the decorator line, the `def` line, the docstring, and all indented body lines up to (but not including) the next `@tool()` or end of file.

- [ ] **Delete these 10 functions from tools.py (one grep-and-delete pass):**

Functions to remove (search each by name, delete from `@tool()` through the last line of the body):
1. `obsidian_parse_bibtex`
2. `obsidian_ingest_bibtex`
3. `obsidian_ingest_reference`
4. `obsidian_ingest_source_note`
5. `obsidian_ingest_pdf_attachment`
6. `obsidian_ingest_mineru_markdown`
7. `obsidian_ingest_zotero_item`
8. `obsidian_ingest_zotero_collection`
9. `obsidian_mineru_rename_images`
10. `obsidian_mineru_status`

- [ ] **Verify the functions are gone**

```powershell
python -c "
import scripts.obsidian_vault_mcp.tools
from scripts.obsidian_vault_mcp.common import get_registered_tool_names
names = get_registered_tool_names()
group_a = ['obsidian_parse_bibtex','obsidian_ingest_bibtex','obsidian_ingest_reference',
           'obsidian_ingest_source_note','obsidian_ingest_pdf_attachment',
           'obsidian_ingest_mineru_markdown','obsidian_ingest_zotero_item',
           'obsidian_ingest_zotero_collection','obsidian_mineru_rename_images','obsidian_mineru_status']
found = [n for n in group_a if n in names]
print('Still present (should be empty):', found)
print('Total registered:', len(names))
"
```

Expected: `Still present (should be empty): []`, `Total registered: 72`

- [ ] **Commit**

```powershell
git add scripts/obsidian_vault_mcp/tools.py
git commit -m "refactor: remove 10 deprecated Group A tool handlers"
```

---

## Task 4 — Remove Group B tool functions from tools.py

**Files:**
- Modify: `scripts/obsidian_vault_mcp/tools.py`

Remove all 55 Group B `@tool()` functions. Same technique as Task 3: delete from `@tool()` through the function body.

- [ ] **Delete obsidian-vault group (27 functions)**

Remove these function definitions completely:
`obsidian_vault_status`, `obsidian_vault_stats`, `obsidian_list_files`, `obsidian_delete_file`, `obsidian_move_file`, `obsidian_rename_file`, `obsidian_batch_move_files`, `obsidian_list_user_templates`, `obsidian_add_wikilinks`, `obsidian_build_graph`, `obsidian_lint_vault`, `obsidian_find_orphans`, `obsidian_find_broken_links`, `obsidian_update_wiki_index`, `obsidian_append_wiki_log`, `obsidian_wiki_context`, `obsidian_wiki_stale_pages`, `obsidian_write_wiki_page`, `obsidian_build_reading_digest`, `obsidian_validate_vault_schema`, `obsidian_apply_schema_defaults`, `obsidian_list_schema_presets`, `obsidian_create_note`, `obsidian_preview_edit_plan`, `obsidian_apply_edit_plan`, `obsidian_rollback_edit_plan`, `obsidian_doctor`

> NOTE: `obsidian_doctor` is removed as an MCP **tool** but its helper function in `helpers.py` should be kept — cli.py's `--doctor` flag calls it. Only delete the `@tool()` decorated wrapper in `tools.py`.

- [ ] **Delete obsidian-cli group (13 functions)**

`obsidian_cli`, `obsidian_cli_read`, `obsidian_cli_open`, `obsidian_cli_backlinks`, `obsidian_cli_base_query`, `obsidian_cli_properties`, `obsidian_cli_property_read`, `obsidian_cli_property_set`, `obsidian_cli_property_remove`, `obsidian_cli_tasks`, `obsidian_cli_screenshot`, `obsidian_cli_plugin_reload`, `obsidian_cli_move_or_rename`

- [ ] **Delete obsidian-views group (7 functions)**

`obsidian_create_canvas`, `obsidian_create_canvas_from_graph`, `obsidian_create_base`, `obsidian_create_base_template`, `obsidian_list_base_templates`, `obsidian_list_dataview_templates`, `obsidian_create_dataview_note`

- [ ] **Delete obsidian-graph group (4 functions)**

`obsidian_build_citation_network`, `obsidian_build_graph_communities`, `obsidian_graph_insights`, `obsidian_suggest_graph_improvements`

- [ ] **Delete obsidian-mineru group (4 functions)**

`obsidian_mineru_extract`, `obsidian_mineru_extract_and_ingest`, `obsidian_mineru_extract_folder`, `obsidian_zotero_extract_pdf_text`

- [ ] **Verify only 17 tools remain**

```powershell
python -c "
import scripts.obsidian_vault_mcp.tools
from scripts.obsidian_vault_mcp.common import get_registered_tool_names
names = sorted(get_registered_tool_names())
print(f'Registered tools: {len(names)}')
for n in names: print(' ', n)
"
```

Expected: `Registered tools: 17`, followed by the 17 literature tool names.

- [ ] **Commit**

```powershell
git add scripts/obsidian_vault_mcp/tools.py
git commit -m "refactor: remove 55 Group B legacy tool handlers from tools.py"
```

---

## Task 5 — Update tests

**Files:**
- Modify: `tests/test_obsidian_vault_mcp.py`

Remove all test methods that call removed tools. Add a new test that asserts exactly 17 tools are registered.

- [ ] **Write the failing test first**

Add this test method to `ObsidianVaultMcpTests`:

```python
def test_exactly_17_literature_tools_registered(self):
    from scripts.obsidian_vault_mcp.common import get_registered_tool_names
    import scripts.obsidian_vault_mcp.tools  # trigger registration
    names = get_registered_tool_names()
    self.assertEqual(len(names), 17, f"Expected 17 tools, got {len(names)}: {sorted(names)}")
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
    self.assertEqual(set(names), expected)
```

- [ ] **Run it — expect FAIL if tests haven't been cleaned yet, or PASS if Task 4 is done**

```powershell
python -m pytest tests/test_obsidian_vault_mcp.py::ObsidianVaultMcpTests::test_exactly_17_literature_tools_registered -v
```

- [ ] **Remove these test methods** (all reference removed tools):

Delete the following complete `def test_...` methods including their bodies:

1. `test_graph_resolves_aliases_and_counts_inline_tags`
2. `test_lint_reports_unresolved_links_and_missing_wiki_files`
3. `test_update_wiki_index_creates_generated_catalogue`
4. `test_append_wiki_log_adds_chronological_entry`
5. `test_ingest_source_note_creates_linked_wiki_pages`
6. `test_base_template_list_includes_project_templates`
7. `test_create_base_template_writes_yaml`
8. `test_create_base_template_dry_run_does_not_write`
9. `test_create_canvas_from_graph_writes_file_nodes_and_edges`
10. `test_create_canvas_from_graph_dry_run_does_not_write`
11. `test_create_dataview_note_writes_query_block`
12. `test_create_note_can_apply_user_template`
13. `test_create_note_merges_template_frontmatter_and_templater_variables`
14. `test_vault_config_overrides_default_output_folders`
15. `test_validate_vault_schema_reports_frontmatter_and_canvas_errors`
16. `test_validate_vault_schema_reports_strict_canvas_and_base_errors`
17. `test_apply_schema_defaults_fills_missing_frontmatter`
18. `test_graph_improvements_suggest_unresolved_and_markdown_links`
19. `test_canvas_from_graph_grouped_layout_creates_group_nodes`
20. `test_structured_cli_wrappers_parse_json_and_build_commands`
21. `test_structured_cli_mutating_wrappers`
22. `test_cli_json_parser_handles_no_rows_messages`
23. `test_cli_json_parser_skips_failed_results`
24. `test_obsidian_cli_treats_zero_exit_error_text_as_failure`
25. `test_obsidian_cli_does_not_use_shell_fallback_on_windows`
26. `test_edit_plan_preview_apply_and_rollback`
27. `test_edit_plan_accepts_operation_alias`
28. `test_edit_plan_rejects_duplicate_targets_and_escaping_paths`
29. `test_edit_plan_rejects_unsafe_transaction_id`
30. `test_ingest_zotero_item_copies_pdf_and_creates_note`
31. `test_zotero_attachment_naming_strategy_and_duplicate_detection`

Also remove `import subprocess` from the top of the test file if it's no longer used after removing CLI tests.

- [ ] **Run full test suite — all remaining tests must pass**

```powershell
python -m pytest tests/ -v
```

Expected: All tests pass including `test_exactly_17_literature_tools_registered`. No failures.

- [ ] **Commit**

```powershell
git add tests/test_obsidian_vault_mcp.py
git commit -m "test: remove legacy tests, add 17-tool registry assertion"
```

---

## Task 6 — Enhance obsidian-vault skill

**Files:**
- Modify: `skills/obsidian-vault/SKILL.md`

Replace the entire file with the enhanced version below. This adds graph, lint, wiki, schema, bulk-edit, and file-management workflows that now rely on Claude's built-in tools + the 17 MCP tools instead of removed @tool functions.

- [ ] **Write the new SKILL.md**

```markdown
---
name: obsidian-vault
description: "Work with local Obsidian vaults as linked knowledge bases. Use when the user needs to inspect, edit, organise, maintain, or analyse vault notes, YAML frontmatter, wikilinks, graph structure, wiki index/log, schema, or bulk edits. 当用户提到 Obsidian 仓库、笔记、YAML 属性、双链、图谱、批量修改、索引日志、模板或本地知识库维护时使用。"
---

# Obsidian Vault

Use the 17 MCP tools in the `literature` profile plus Claude's built-in tools (Read, Write, Edit, Grep, Bash) for all vault work.

## Core MCP Tools

- `obsidian_read_file` / `obsidian_write_file` — read and write vault notes
- `obsidian_search` — full-text search across the vault
- `obsidian_update_properties` — safely merge/replace YAML frontmatter

## File Management

To list files: use `obsidian_search` with an empty query, or use the `Glob` tool with the vault path.

To delete a file: use `Bash` → `Remove-Item "vault_path\relative\path.md"` (Windows) or `rm`.

To move/rename a file: use `Bash` → `Move-Item` (Windows) or `mv`. If Obsidian is open, use the `obsidian-cli` skill to preserve wikilink integrity.

To batch-move files: use `Bash` with a loop or `Get-ChildItem | Move-Item`.

## Graph Maintenance

To analyse the wikilink graph:
1. Use `obsidian_search` with `query=""` to list all `.md` files.
2. For each file, use `obsidian_read_file` to extract `[[wikilinks]]` with regex `\[\[([^\]]+)\]\]`.
3. Build an edge list and identify orphans (nodes with no in-links) and dead links (targets that don't exist as files).
4. Report findings. Suggest `obsidian_write_file` fixes for broken links.

To find orphans: collect all filenames, collect all link targets, subtract linked from all.

To find broken links: collect all link targets, subtract existing filenames.

To add wikilinks: use `obsidian_read_file` + `obsidian_write_file` with the updated content.

## Vault Health (Lint)

Run this sequence:
1. `obsidian_search` with `query=""` — get all notes.
2. Read each note with `obsidian_read_file` and check:
   - Missing required frontmatter fields (type, title, tags).
   - Dead `[[links]]` pointing to non-existent notes.
   - Notes with no outgoing or incoming links (orphans).
3. Report a structured issues list grouped by type.

## Wiki Maintenance

To update the wiki index (`index.md`):
1. Use `obsidian_search` to list notes by tag or folder.
2. Build a markdown catalogue grouped by tag.
3. Use `obsidian_write_file` to write the catalogue between `<!-- obsidian-vault:index:start -->` and `<!-- obsidian-vault:index:end -->` markers.

To append a wiki log entry (`log.md`):
1. Use `obsidian_read_file` to read existing `log.md` (or create if absent).
2. Prepend a new `## YYYY-MM-DD` entry with the summary and touched paths.
3. Use `obsidian_write_file` to save.

## Schema Validation

To validate frontmatter schema:
1. Use `obsidian_search` to find notes by folder prefix (e.g. `sources/`, `entities/`).
2. For each note, use `obsidian_read_file` and parse the YAML frontmatter block.
3. Check required fields: `sources/` → `{type, title, tags}`, `entities/` → `{type, title, sources}`.
4. Report missing or invalid fields.

To apply schema defaults:
1. For notes missing required fields, use `obsidian_update_properties` with `merge_mode="merge"` to fill in defaults.
2. Use `dry_run=true` first to preview.

## Bulk Editing (Edit Plans)

To preview a multi-file edit:
1. Collect the list of files and planned changes.
2. Use `obsidian_read_file` on each, show before/after diffs inline.
3. Ask the user to confirm before writing.

To apply:
1. For each file, use `obsidian_write_file` or `obsidian_update_properties`.
2. Keep a backup list of original content for rollback.

To rollback: restore each file from the backup content using `obsidian_write_file`.

## Note Creation with Templates

To create a note with a template:
1. Use `obsidian_search` in the templates folder (check `.obsidian/templates.json` for path).
2. Use `obsidian_read_file` to load the template.
3. Substitute `{{title}}`, `{{body}}`, `{{status}}` and Templater tokens (`<% tp.date.now(...) %>`).
4. Merge template frontmatter with supplied properties (supplied properties win).
5. Use `obsidian_write_file` to write the note.

## Safety

- Always use `dry_run=true` before broad mutations.
- Never write outside the vault root.
- Prefer `obsidian_update_properties` for frontmatter edits — it preserves body content.
- When Obsidian desktop is open, prefer the `obsidian-cli` skill for moves and renames.

---

## 中文说明

使用 17 个 MCP 工具加上 Claude 内置工具处理所有 vault 操作。图谱分析、lint 检查、wiki 维护、schema 验证和批量编辑现在通过 `obsidian_search` + `obsidian_read_file` + `obsidian_write_file` 组合完成，不再依赖独立的 MCP 工具。
```

- [ ] **Commit**

```powershell
git add skills/obsidian-vault/SKILL.md
git commit -m "docs(skill): enhance obsidian-vault skill with graph/lint/wiki/schema/bulk workflows"
```

---

## Task 7 — Enhance obsidian-cli skill

**Files:**
- Modify: `skills/obsidian-cli/SKILL.md`

Replace the file content with the version below. The 13 removed @tool CLI wrappers become concrete Bash commands in the skill.

- [ ] **Write the new SKILL.md**

```markdown
---
name: obsidian-cli
description: "Drive the Obsidian desktop app via its CLI. Use when the user needs to open notes, query backlinks, read or set note properties, run Base queries, list tasks, take screenshots, reload plugins, or move/rename files with live wikilink updates inside a running Obsidian instance. 当需要控制 Obsidian 桌面应用、读取/写入属性、查询 Bases、列出任务或在 Obsidian 运行时移动/重命名文件时使用。"
---

# Obsidian CLI

The `obsidian` CLI is available when Obsidian 1.12.7+ is running and the CLI is on PATH. Check availability with `Bash` → `obsidian --version`.

All commands use the pattern: `obsidian <command> [params] [flags]`

## Reading

**Read note content:**
```bash
obsidian read --path "folder/note.md"
```

**Open a note in Obsidian:**
```bash
obsidian open --path "folder/note.md"
```

**Get backlinks (JSON):**
```bash
obsidian backlinks --path "folder/note.md" --format json [--counts]
```

**Get note properties (YAML frontmatter, JSON output):**
```bash
obsidian properties --path "folder/note.md" --format json [--counts]
```

## Properties

**Read a single property:**
```bash
obsidian property:read --name "status" --path "folder/note.md"
```

**Set a property:**
```bash
obsidian property:set --name "status" --value "done" --type "text" --path "folder/note.md"
```

**Remove a property:**
```bash
obsidian property:remove --name "status" --path "folder/note.md"
```

## Bases & Dataview

**Query a Base file:**
```bash
obsidian base:query --path "bases/literature.base" --view "Main" --format json
```

## Tasks

**List tasks in a note:**
```bash
obsidian tasks --path "folder/note.md" --format json [--todo] [--done]
```

## App Control

**Take a screenshot:**
```bash
obsidian screenshot --output "shot.png"
```

**Reload a plugin:**
```bash
obsidian plugin:reload --id "obsidian-git"
```

## Move & Rename (with wikilink updates)

**Move a note:**
```bash
obsidian move --path "old/note.md" --to "new/note.md"
```

**Rename a note:**
```bash
obsidian rename --path "folder/note.md" --name "new-name.md"
```

Use these instead of filesystem `mv`/`rename` when Obsidian is running — they update all internal wikilinks automatically.

## Parsing CLI Output

All `--format json` commands return a JSON array of objects. Parse with Python:
```python
import json, subprocess
result = subprocess.run(["obsidian", "backlinks", "--path", "note.md", "--format", "json"], capture_output=True, text=True)
data = json.loads(result.stdout)
```

Or use `Bash` → pipe to `python -m json.tool` for quick inspection.

## Error Handling

If `stdout` contains `"Vault not found."` or similar error text, treat as failure even if exit code is 0. Check `returnCode != 0` **and** scan stdout for known error patterns.

Do not use `shell=True` on Windows — pass the executable path directly.

---

## 中文说明

当 Obsidian 桌面运行时，所有文件移动、重命名、属性读写、任务查询等操作优先通过 `obsidian` CLI 完成，以确保内部双链自动更新。使用 Bash 工具执行上述命令，解析 `--format json` 输出。
```

- [ ] **Commit**

```powershell
git add skills/obsidian-cli/SKILL.md
git commit -m "docs(skill): enhance obsidian-cli skill with all 13 CLI wrapper command equivalents"
```

---

## Task 8 — Enhance obsidian-views skill

**Files:**
- Modify: `skills/obsidian-views/SKILL.md`

- [ ] **Write the new SKILL.md**

```markdown
---
name: obsidian-views
description: "Build visual and query views for an Obsidian vault. Use when the user needs to create or update JSON Canvas maps, Obsidian Bases files, or Dataview notes. 当用户提到 Canvas、Bases、Dataview、视图、图谱布局、表格卡片视图或查询笔记时使用。"
---

# Obsidian Views

Use `obsidian_write_file` to write Canvas (`.canvas`), Bases (`.base`), and Dataview (`.md`) files. Use `obsidian_search` and `obsidian_read_file` to gather vault content first.

## Canvas (JSON Canvas)

A `.canvas` file is a JSON object with `nodes` and `edges` arrays.

**Minimal Canvas structure:**
```json
{
  "nodes": [
    {"id": "a", "type": "file", "file": "notes/A.md", "x": 0, "y": 0, "width": 250, "height": 60},
    {"id": "b", "type": "file", "file": "notes/B.md", "x": 300, "y": 0, "width": 250, "height": 60}
  ],
  "edges": [
    {"id": "e1", "fromNode": "a", "toNode": "b", "toEnd": "arrow"}
  ]
}
```

**Node types:** `file` (vault note), `text` (inline text), `link` (URL), `group` (container).

**Layouts:**
- Grid: place nodes at evenly spaced `(x, y)` positions, e.g. 300px apart.
- Radial: compute angles around a centre point.
- Grouped: create `group` nodes first, position member nodes inside group bounds.
- Layered: arrange by folder depth (x) and index within folder (y).

**Steps to create a Canvas from vault links:**
1. `obsidian_search` with `query=""` to get all notes.
2. `obsidian_read_file` each note to extract `[[wikilinks]]`.
3. Build node list (one node per note) and edge list (one edge per link).
4. Apply layout to assign `x`, `y` coordinates.
5. `obsidian_write_file` the JSON to `<path>.canvas`.

## Obsidian Bases

A `.base` file is YAML that defines a database-style table over vault notes.

**Standard structure:**
```yaml
filters:
  and:
    - file.ext == "md"
    - file.inFolder("sources")
views:
  - type: table
    name: Main
    columns:
      - property: title
        width: 200
      - property: tags
        width: 120
      - property: status
        width: 100
    order: file.name
    groupBy:
      property: status
      direction: ASC
```

**Built-in Base templates** (write with `obsidian_write_file`):

`literature` template — for `literatureFolder` notes:
```yaml
filters:
  and:
    - file.ext == "md"
    - file.inFolder("01-literature")
views:
  - type: table
    name: Literature
    columns:
      - {property: title, width: 240}
      - {property: authors, width: 160}
      - {property: year, width: 60}
      - {property: doi, width: 120}
      - {property: tags, width: 120}
    order: file.mtime
```

For other templates (equipment, economics, sources, project, devices), construct the YAML to match the folder/tag for that domain.

## Dataview

A Dataview note is a standard Markdown file containing one or more `dataview` code fences.

**Standard DQL query block:**
````markdown
```dataview
TABLE title, authors, year, doi
FROM #chemistry AND "01-literature"
WHERE file.ext = "md"
SORT file.mtime DESC
```
````

**Steps:**
1. Confirm the user has the Dataview plugin installed.
2. Identify the target folder and tag filter.
3. Build the DQL query.
4. `obsidian_write_file` a `.md` file containing the query block.

## Validation

After writing a Canvas or Base file, use `obsidian_read_file` to confirm the file was written correctly. For Bases, check that all required `type`, `filters`, and `views` keys are present.

---

## 中文说明

Canvas 文件是 JSON，Bases 文件是 YAML，Dataview 是 Markdown 中的代码块。使用 `obsidian_write_file` 写入目标路径，使用 `obsidian_search` + `obsidian_read_file` 收集 vault 内容后再构建视图。
```

- [ ] **Commit**

```powershell
git add skills/obsidian-views/SKILL.md
git commit -m "docs(skill): enhance obsidian-views skill with Canvas/Bases/Dataview step-by-step workflows"
```

---

## Task 9 — Create obsidian-graph skill

**Files:**
- Create: `skills/obsidian-graph/SKILL.md`
- Create: `skills/obsidian-graph/agents/openai.yaml`

- [ ] **Write SKILL.md**

```markdown
---
name: obsidian-graph
description: "Analyse the citation and wikilink graph of an Obsidian vault using networkx. Use when the user needs citation network construction, community detection, connectivity metrics, or graph improvement suggestions. 当用户需要引用网络分析、社区检测、连通性指标或图谱改善建议时使用。"
---

# Obsidian Graph Analysis

Use `obsidian_search` and `obsidian_read_file` to gather vault data, then run Python/networkx analysis via `Bash`.

## Citation Network

**Goal:** Build a directed graph where nodes are vault notes and edges are `[[wikilinks]]` or Zotero `related` relations.

**Steps:**
1. `obsidian_search` with `query=""`, `extensions=".md"` — get all notes.
2. For each note, `obsidian_read_file` and extract:
   - Outgoing links: regex `\[\[([^\]|#]+)` on the file body.
   - Zotero citekey from frontmatter `citekey` field.
3. Write a Python script and run with `Bash`:

```python
import json, re, pathlib, sys

vault = sys.argv[1]
notes = {}  # path -> {title, links}
for md in pathlib.Path(vault).rglob("*.md"):
    rel = str(md.relative_to(vault))
    text = md.read_text(encoding="utf-8", errors="ignore")
    links = re.findall(r'\[\[([^\]|#\n]+)', text)
    notes[rel] = links

# Write edge list
edges = []
for src, targets in notes.items():
    for tgt in targets:
        edges.append({"source": src, "target": tgt + ".md"})

print(json.dumps({"nodeCount": len(notes), "edgeCount": len(edges), "edges": edges[:100]}, indent=2))
```

Run: `python graph_build.py "F:\vault\path"`

## Community Detection

Uses the Louvain method via networkx (requires `python-louvain` or networkx's built-in community detection).

```python
import networkx as nx, json, sys

edges_json = sys.argv[1]  # JSON string of edge list
data = json.loads(edges_json)
G = nx.DiGraph()
for e in data["edges"]:
    G.add_edge(e["source"], e["target"])

# Convert to undirected for community detection
U = G.to_undirected()
communities = list(nx.community.greedy_modularity_communities(U))
result = [{"community": i, "nodes": list(c)[:10], "size": len(c)}
          for i, c in enumerate(communities)]
print(json.dumps(result, indent=2))
```

Run via `Bash` with the edge list from the citation network step.

## Connectivity Metrics

From the directed graph, compute:
- **Hub nodes**: high in-degree (many incoming links) — most-cited notes.
- **Authority nodes**: high out-degree (link to many others) — index/survey notes.
- **Orphans**: nodes with in-degree = 0 and out-degree = 0.
- **Weakly connected components**: clusters of notes that link to each other but not to the main body.

```python
import networkx as nx
# ... build G as above ...
hubs = sorted(G.in_degree(), key=lambda x: x[1], reverse=True)[:10]
orphans = [n for n in G.nodes if G.in_degree(n) == 0 and G.out_degree(n) == 0]
components = list(nx.weakly_connected_components(G))
```

## Graph Improvement Suggestions

After computing metrics, suggest:
1. **Create missing notes**: For each dead link target (node with no `.md` source), suggest `obsidian_write_file` to create a stub.
2. **Convert markdown links**: Find `[text](file.md)` patterns in notes → suggest converting to `[[file]]`.
3. **Connect isolated clusters**: Identify the two largest weakly connected components; find thematically related notes between them (by tag overlap) and suggest adding wikilinks.
4. **Remove orphans**: List orphan notes and ask the user if they should be linked or deleted.

---

## 中文说明

通过 `obsidian_search` + `obsidian_read_file` 收集 vault 数据，用 Bash 运行 Python/networkx 脚本完成引用网络构建、社区检测和连通性分析。分析结果转化为可操作的 `obsidian_write_file` 建议。
```

- [ ] **Write agents/openai.yaml**

```yaml
interface:
  display_name: "Obsidian Graph"
  short_description: "Analyse citation networks and graph communities in an Obsidian vault"
  default_prompt: "Use $obsidian-graph to analyse the wikilink and citation graph of my Obsidian vault."
```

- [ ] **Commit**

```powershell
git add skills/obsidian-graph/
git commit -m "docs(skill): add obsidian-graph skill for citation network and community analysis"
```

---

## Task 10 — Enhance obsidian-mineru skill

**Files:**
- Modify: `skills/obsidian-mineru/SKILL.md`

Read the current file first, then add extract/batch/extract-and-ingest workflow sections.

- [ ] **Read existing skill**

```powershell
Get-Content "skills/obsidian-mineru/SKILL.md"
```

- [ ] **Add these workflow sections after the existing content**

Append below the current `## Safety` section (or equivalent final section):

```markdown
## Direct Extraction (without Zotero)

To parse a PDF directly with MinerU without going through the Zotero pipeline:

1. Confirm MinerU is available: `Bash` → `mineru-open-api --version` (or the value of `MINERU_CLI_COMMAND`).
2. Run MinerU on a PDF path:

```bash
mineru-open-api --files "C:\path\to\paper.pdf" --output-dir "C:\vault\mineru-output" --method auto
```

3. The output directory will contain:
   - `paper.md` — extracted Markdown
   - `images/` — extracted figures
4. Use `obsidian_read_file` on the generated `.md` to review.
5. Use `obsidian_write_file` to copy/move the content into the vault's literature folder.

## Extract and Ingest

To extract a PDF and immediately create a literature note:
1. Run MinerU as above.
2. Read the generated Markdown.
3. Create the literature note with `obsidian_write_file`, including frontmatter and a link to the extracted Markdown's images.
4. Use `obsidian_pipeline_rename_mineru_images` (MCP) to rename extracted images to semantic English slugs.

## Batch Folder Extraction

To process all PDFs in a folder:

```powershell
Get-ChildItem "C:\zotero-exports" -Filter "*.pdf" | ForEach-Object {
    $out = "C:\vault\mineru-batch\$($_.BaseName)"
    mineru-open-api --files $_.FullName --output-dir $out --method auto
}
```

Then ingest each output folder individually following the "Extract and Ingest" workflow above.

## Zotero PDF Text Extraction

To extract text from a Zotero-managed PDF without full MinerU parsing:
1. Get the PDF path from `obsidian_zotero_list_pdf_attachments` (returns `path` for each attachment).
2. Use Bash + `pypdf`:

```python
import pypdf, sys
reader = pypdf.PdfReader(sys.argv[1])
text = "\n".join(page.extract_text() or "" for page in reader.pages)
print(text[:5000])  # first 5000 chars
```

Run: `python extract_text.py "C:\Zotero\storage\KEY\paper.pdf"`
```

- [ ] **Commit**

```powershell
git add skills/obsidian-mineru/SKILL.md
git commit -m "docs(skill): enhance obsidian-mineru skill with direct extract, batch, and text-only workflows"
```

---

## Task 11 — Create .claude/skills/ mirrors

**Files:**
- Create: `.claude/skills/obsidian-vault.md`
- Create: `.claude/skills/obsidian-cli.md`
- Create: `.claude/skills/obsidian-views.md`
- Create: `.claude/skills/obsidian-graph.md`
- Create: `.claude/skills/obsidian-mineru.md`

The `.claude/skills/` mirrors are concise versions (trigger description + key workflows, no bilingual blocks) for local Claude Code usage.

- [ ] **Create the directory**

```powershell
New-Item -ItemType Directory -Path ".claude\skills" -Force
```

- [ ] **Write .claude/skills/obsidian-vault.md**

```markdown
---
name: obsidian-vault
description: "Inspect, edit, organise, or maintain Obsidian vault notes, frontmatter, wikilinks, graph, wiki, schema, or bulk edits. 维护 Obsidian vault 笔记、属性、双链、图谱、schema 或批量编辑时使用。"
---

Use 17 MCP tools (literature profile) + Claude built-in tools. Key tools: `obsidian_read_file`, `obsidian_write_file`, `obsidian_search`, `obsidian_update_properties`.

- **Graph/lint**: search all notes → read each → extract wikilinks → report orphans/dead links
- **Wiki index**: search by tag → build catalogue → write between index markers
- **Schema**: read frontmatter → check required fields → `obsidian_update_properties` to fill defaults
- **Bulk edit**: read → show diff → confirm → write; keep backup for rollback
- **File ops**: Bash `Move-Item`/`Remove-Item` for move/delete; `obsidian-cli` skill for Obsidian-open moves
```

- [ ] **Write .claude/skills/obsidian-cli.md**

```markdown
---
name: obsidian-cli
description: "Drive Obsidian desktop via CLI — open notes, backlinks, property CRUD, Base queries, tasks, screenshots, plugin reload, wikilink-safe move/rename. 控制 Obsidian 桌面应用、读写属性、查询 Bases、列出任务时使用。"
---

All commands: `obsidian <command> [params]`. Use `Bash` tool to run.

- Read: `obsidian read --path "note.md"`
- Open: `obsidian open --path "note.md"`
- Backlinks: `obsidian backlinks --path "note.md" --format json`
- Properties: `obsidian properties --path "note.md" --format json`
- Set property: `obsidian property:set --name "status" --value "done" --type "text" --path "note.md"`
- Base query: `obsidian base:query --path "bases/lit.base" --view "Main" --format json`
- Tasks: `obsidian tasks --path "note.md" --format json --todo`
- Move: `obsidian move --path "old.md" --to "new.md"` (updates wikilinks)
- Rename: `obsidian rename --path "note.md" --name "new-name.md"`
- Screenshot: `obsidian screenshot --output "shot.png"`
- Plugin reload: `obsidian plugin:reload --id "plugin-id"`
```

- [ ] **Write .claude/skills/obsidian-views.md**

```markdown
---
name: obsidian-views
description: "Create Canvas maps, Obsidian Bases, or Dataview notes. 创建 Canvas、Bases 或 Dataview 视图时使用。"
---

Use `obsidian_write_file` to write views. Use `obsidian_search` + `obsidian_read_file` first to gather vault data.

- **Canvas**: write JSON `{nodes:[...], edges:[...]}` to `<name>.canvas`. Node types: file/text/link/group. Layouts: grid, radial, grouped, layered.
- **Bases**: write YAML `{filters:{and:[...]}, views:[{type:table, columns:[...]}]}` to `<name>.base`.
- **Dataview**: write a `.md` file with ` ```dataview TABLE ... FROM ... ``` ` blocks.
```

- [ ] **Write .claude/skills/obsidian-graph.md**

```markdown
---
name: obsidian-graph
description: "Analyse Obsidian vault citation networks, graph communities, and connectivity. 引用网络分析、社区检测、图谱指标时使用。"
---

1. `obsidian_search` (all `.md`) → `obsidian_read_file` each → extract `[[links]]` with regex.
2. Run Python/networkx via `Bash` for community detection (`nx.community.greedy_modularity_communities`).
3. Compute hubs (high in-degree), orphans (no links), weak components.
4. Suggest: create stub notes for dead links; convert `[text](file.md)` to `[[file]]`; link isolated clusters.
```

- [ ] **Write .claude/skills/obsidian-mineru.md**

```markdown
---
name: obsidian-mineru
description: "Parse PDFs with MinerU — direct extraction, batch folders, Zotero PDF text extraction. MinerU 直接解析 PDF、批量处理或 Zotero PDF 文本提取时使用。"
---

- **Pipeline** (recommended): use `obsidian_pipeline_parse_with_mineru` (MCP) for Zotero-attached PDFs.
- **Direct**: `Bash` → `mineru-open-api --files "path.pdf" --output-dir "out/" --method auto`
- **Batch**: PowerShell loop over `*.pdf` → run `mineru-open-api` for each.
- **Text only**: `Bash` → `python -c "import pypdf; r=pypdf.PdfReader('f.pdf'); print('\n'.join(p.extract_text() for p in r.pages))"`
- After extraction: use `obsidian_pipeline_rename_mineru_images` (MCP) to rename images to semantic slugs.
```

- [ ] **Commit**

```powershell
git add .claude/skills/
git commit -m "docs(skill): add .claude/skills/ mirrors for all five enhanced skills"
```

---

## Task 12 — Update README files

**Files:**
- Modify: `README.md`
- Modify: `README.en.md`

These files currently have large tool tables. Replace them with a concise skill-based architecture description. Keep Setup and Usage sections intact; trim the tool listing to 17 tools only.

- [ ] **Update README.md (Chinese)**

Replace the "工具列表" / tool table sections with:

```markdown
## 工具列表（17个核心工具）

默认配置文件 `literature` 提供以下 17 个 MCP 工具，专注于 Zotero→MinerU→Obsidian 文献管道：

| 类别 | 工具 |
|------|------|
| Pipeline | `obsidian_pipeline_doctor`, `obsidian_pipeline_config`, `obsidian_pipeline_migrate_layout` |
| 文献导入 | `obsidian_pipeline_ingest_item`, `obsidian_pipeline_ingest_collection` |
| MinerU | `obsidian_pipeline_parse_with_mineru`, `obsidian_pipeline_rename_mineru_images` |
| Zotero | `obsidian_zotero_ping`, `obsidian_zotero_search_items`, `obsidian_zotero_list_collections`, `obsidian_zotero_get_item`, `obsidian_zotero_get_children`, `obsidian_zotero_list_pdf_attachments` |
| Vault 基础 | `obsidian_read_file`, `obsidian_write_file`, `obsidian_search`, `obsidian_update_properties` |

## Skills（技能）

图谱分析、Wiki 维护、Canvas/Bases/Dataview 视图、Obsidian CLI 控制等高级工作流已转为 Skills，通过 Claude Code 或 Codex 调用：

| Skill | 功能 |
|-------|------|
| `obsidian-vault` | 图谱、lint、wiki、schema、批量编辑 |
| `obsidian-cli` | Obsidian 桌面 CLI 控制 |
| `obsidian-views` | Canvas、Bases、Dataview |
| `obsidian-graph` | 引用网络、社区检测、连通性分析 |
| `obsidian-mineru` | MinerU 直接解析、批量处理 |
| `obsidian-zotero` | Zotero 搜索与文献导入 |
```

Remove any remaining references to `OBSIDIAN_VAULT_TOOL_PROFILE=full` or `legacy` profile.

- [ ] **Update README.en.md (English)**

Apply the same structural change in English. Replace the tool table section with:

```markdown
## Tools (17 core tools)

The default `literature` profile exposes 17 MCP tools for the Zotero→MinerU→Obsidian literature pipeline:

| Category | Tools |
|----------|-------|
| Pipeline | `obsidian_pipeline_doctor`, `obsidian_pipeline_config`, `obsidian_pipeline_migrate_layout` |
| Ingestion | `obsidian_pipeline_ingest_item`, `obsidian_pipeline_ingest_collection` |
| MinerU | `obsidian_pipeline_parse_with_mineru`, `obsidian_pipeline_rename_mineru_images` |
| Zotero | `obsidian_zotero_ping`, `obsidian_zotero_search_items`, `obsidian_zotero_list_collections`, `obsidian_zotero_get_item`, `obsidian_zotero_get_children`, `obsidian_zotero_list_pdf_attachments` |
| Vault | `obsidian_read_file`, `obsidian_write_file`, `obsidian_search`, `obsidian_update_properties` |

## Skills

Advanced workflows (graph analysis, wiki maintenance, Canvas/Bases/Dataview, Obsidian CLI) are delivered as Skills invoked through Claude Code or Codex — no extra MCP tools required:

| Skill | Purpose |
|-------|---------|
| `obsidian-vault` | Graph, lint, wiki, schema, bulk editing |
| `obsidian-cli` | Obsidian desktop CLI control |
| `obsidian-views` | Canvas, Bases, Dataview |
| `obsidian-graph` | Citation network, community detection |
| `obsidian-mineru` | Direct MinerU extraction, batch processing |
| `obsidian-zotero` | Zotero search and literature import |
```

Remove all `OBSIDIAN_VAULT_TOOL_PROFILE` environment variable documentation.

- [ ] **Commit**

```powershell
git add README.md README.en.md
git commit -m "docs: rewrite README (zh+en) for skill-based v1.1.0 architecture"
```

---

## Task 13 — Trim TECHNICAL_GUIDE.md

**Files:**
- Modify: `docs/TECHNICAL_GUIDE.md`

- [ ] **Remove sections for deleted tools**

Delete or collapse any sections in `docs/TECHNICAL_GUIDE.md` that document:
- Group A tools (BibTeX ingestion, old reference ingestion, old ingest variants)
- Full/legacy profile usage (`OBSIDIAN_VAULT_TOOL_PROFILE=full`)

Keep: architecture overview, setup/installation steps, literature pipeline workflow, Zotero/MinerU configuration.

- [ ] **Commit**

```powershell
git add docs/TECHNICAL_GUIDE.md
git commit -m "docs: trim TECHNICAL_GUIDE.md — remove deleted tool documentation"
```

---

## Task 14 — Bump version, build, and publish

**Files:**
- Modify: `pyproject.toml`

- [ ] **Bump version**

In `pyproject.toml`, change:
```toml
version = "1.0.27"
```
to:
```toml
version = "1.1.0"
```

- [ ] **Run full test suite one final time**

```powershell
python -m pytest tests/ -v
```

All tests must pass.

- [ ] **Commit version bump**

```powershell
git add pyproject.toml
git commit -m "chore: bump version to 1.1.0 for tool-to-skill migration release"
```

- [ ] **Build distribution packages**

```powershell
python -m build
```

Expected output: `dist/zotero_obsidian_mcp-1.1.0-py3-none-any.whl` and `dist/zotero_obsidian_mcp-1.1.0.tar.gz`

- [ ] **Upload to PyPI**

```powershell
$env:TWINE_PASSWORD = "<YOUR_PYPI_TOKEN>"   # set from the token provided out-of-band
python -m twine upload dist/zotero_obsidian_mcp-1.1.0* --username __token__
```

> SECURITY: Set the token as an environment variable. Never paste it into a file or commit it.

Expected: `View at: https://pypi.org/project/zotero-obsidian-mcp/1.1.0/`

- [ ] **Create GitHub Release with zip**

```powershell
gh release create v1.1.0 `
  "dist/zotero_obsidian_mcp-1.1.0.tar.gz" `
  "dist/zotero_obsidian_mcp-1.1.0-py3-none-any.whl" `
  --title "v1.1.0 — Tool-to-Skill Migration" `
  --notes "## What's Changed

### Breaking Changes
- Removed 65 legacy MCP tools. Only the 17-tool \`literature\` profile is now available.
- \`OBSIDIAN_VAULT_TOOL_PROFILE\` environment variable is removed.

### New Skills
- \`obsidian-graph\`: Citation network, community detection, connectivity metrics.

### Enhanced Skills
- \`obsidian-vault\`: Graph, lint, wiki, schema, bulk-edit workflows.
- \`obsidian-cli\`: All 13 CLI wrapper equivalents as direct Bash commands.
- \`obsidian-views\`: Canvas JSON, Bases YAML, Dataview DQL step-by-step.
- \`obsidian-mineru\`: Direct extraction, batch, text-only workflows.

### Migration
Legacy workflows are now handled by Skills (Claude Code / Codex). Install the bundled skills from the \`skills/\` directory."
```

- [ ] **Push to main**

```powershell
git push origin main
```

---

## Success Criteria

- [ ] `python -m pytest tests/ -v` passes with exactly the `test_exactly_17_literature_tools_registered` test confirming 17 tools
- [ ] `python -c "import scripts.obsidian_vault_mcp.tools; from scripts.obsidian_vault_mcp.common import get_registered_tool_names; print(len(get_registered_tool_names()))"` prints `17`
- [ ] `skills/obsidian-graph/SKILL.md` exists and contains citation network + community detection workflows
- [ ] `.claude/skills/` directory contains 5 mirror files
- [ ] `README.md` and `README.en.md` contain no references to `full` or `legacy` profile or `OBSIDIAN_VAULT_TOOL_PROFILE`
- [ ] PyPI `zotero-obsidian-mcp==1.1.0` is live
- [ ] GitHub Release `v1.1.0` exists with `.whl` and `.tar.gz` attached
