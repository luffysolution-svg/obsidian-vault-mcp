# Literature Pipeline Simplification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refocus the Obsidian Vault MCP plugin default surface on a Zotero + MinerU + Obsidian literature pipeline while preserving the old broad toolbox through `full` and `legacy` profiles.

**Architecture:** Keep existing low-level tools in place for compatibility, add profile-aware MCP registration in `common.py`/`server.py`, and add focused pipeline helpers plus high-level `obsidian_pipeline_*` tools. Pipeline writes are idempotent and derive all managed paths from `.obsidian-vault-pipeline.json`; literature notes preserve user-owned YAML and sections while MinerU outputs are treated as regenerable machine artifacts.

**Tech Stack:** Python 3.10+, stdlib filesystem/JSON/subprocess, PyYAML frontmatter helpers already present in the plugin, Zotero Desktop local API, optional MinerU CLI, `unittest`.

---

## File Structure

- Modify `scripts/obsidian_vault_mcp/common.py`: profile constants, profile-aware `tool()` decorator, registry query helpers.
- Modify `scripts/obsidian_vault_mcp/server.py`: create MCP server using selected profile; default to `literature`, allow `full` and `legacy`.
- Modify `scripts/obsidian_vault_mcp/helpers.py`: pipeline config/path planning, stable literature filename generation, owned-field/section preservation, image slug/index helpers, migration helpers.
- Modify `scripts/obsidian_vault_mcp/tools.py`: add seven high-level `obsidian_pipeline_*` tools and profile metadata for default lower-level tools.
- Modify `scripts/obsidian_vault_mcp/cli.py`: let `--doctor` call `obsidian_pipeline_doctor` and optionally accept/display profile when useful.
- Modify `tests/test_obsidian_vault_mcp.py`: add focused tests for profile filtering, config/path planning, ingest, MinerU fixture path, image rename/index, repeat protection, collection failure reporting, and migration dry-run.
- Modify `.codex-plugin/plugin.json` and `.claude-plugin/plugin.json`: reposition description/default prompts toward the literature pipeline while noting full/legacy compatibility.
- Modify `README.md`, `README.en.md`, `README.zh-CN.md`, `docs/TECHNICAL_GUIDE.md`, and bundled skill docs: document default pipeline tools, vault-local config, layout, and legacy profile usage.

---

### Task 1: Profile-Aware Tool Registration

**Files:**
- Modify: `scripts/obsidian_vault_mcp/common.py`
- Modify: `scripts/obsidian_vault_mcp/server.py`
- Test: `tests/test_obsidian_vault_mcp.py`

- [ ] **Step 1: Write failing tests for default and full profile tool lists**

Add tests that import the compatibility module and assert:

```python
def test_default_literature_profile_exposes_pipeline_surface_only(self):
    names = self.module.get_registered_tool_names("literature")
    self.assertIn("obsidian_pipeline_ingest_item", names)
    self.assertIn("obsidian_pipeline_rename_mineru_images", names)
    self.assertIn("obsidian_search", names)
    self.assertIn("obsidian_zotero_get_item", names)
    self.assertNotIn("obsidian_create_canvas", names)
    self.assertNotIn("obsidian_wiki_context", names)

def test_full_and_legacy_profiles_expose_legacy_tools(self):
    full = self.module.get_registered_tool_names("full")
    legacy = self.module.get_registered_tool_names("legacy")
    self.assertIn("obsidian_create_canvas", full)
    self.assertIn("obsidian_wiki_context", full)
    self.assertEqual(full, legacy)
```

- [ ] **Step 2: Run tests to verify RED**

Run: `python -m unittest tests.test_obsidian_vault_mcp.ObsidianVaultMcpTests.test_default_literature_profile_exposes_pipeline_surface_only tests.test_obsidian_vault_mcp.ObsidianVaultMcpTests.test_full_and_legacy_profiles_expose_legacy_tools -v`

Expected: FAIL because `get_registered_tool_names` and pipeline tools do not exist yet.

- [ ] **Step 3: Implement minimal profile registry**

In `common.py`, store `(func, profiles)` records, expose:

```python
DEFAULT_TOOL_PROFILE = "literature"
FULL_TOOL_PROFILES = {"full", "legacy"}
LITERATURE_PROFILE_TOOLS = {...}

def tool(*profiles: str):
    ...

def get_registered_tools(profile: str = DEFAULT_TOOL_PROFILE) -> list[Any]:
    ...

def get_registered_tool_names(profile: str = DEFAULT_TOOL_PROFILE) -> list[str]:
    ...
```

The decorator must support existing `@tool()` calls by registering legacy tools for `full`/`legacy`, while functions named in the default literature set are also exposed in `literature`.

- [ ] **Step 4: Update `server.py` to filter by profile**

Use `OBSIDIAN_VAULT_TOOL_PROFILE` when no explicit profile is passed:

```python
def create_server(profile: str = "") -> FastMCP:
    selected = profile or os.environ.get("OBSIDIAN_VAULT_TOOL_PROFILE", DEFAULT_TOOL_PROFILE)
    for func in get_registered_tools(selected):
        server.tool()(func)
```

- [ ] **Step 5: Run profile tests to verify GREEN**

Run the same two tests. Expected: PASS.

---

### Task 2: Pipeline Config and Path Planning

**Files:**
- Modify: `scripts/obsidian_vault_mcp/helpers.py`
- Modify: `scripts/obsidian_vault_mcp/tools.py`
- Test: `tests/test_obsidian_vault_mcp.py`

- [ ] **Step 1: Write failing tests for config defaults and custom folders**

Add tests for `obsidian_pipeline_config`:

```python
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
```

- [ ] **Step 2: Run config test to verify RED**

Run: `python -m unittest tests.test_obsidian_vault_mcp.ObsidianVaultMcpTests.test_pipeline_config_defaults_and_custom_paths -v`

Expected: FAIL because `obsidian_pipeline_config` is missing.

- [ ] **Step 3: Implement pipeline config helpers**

Add defaults for:

```python
PIPELINE_CONFIG_FILE = ".obsidian-vault-pipeline.json"
PIPELINE_DEFAULT_CONFIG = {
    "literatureFolder": "literature",
    "zoteroAttachmentsFolder": "attachments/zotero",
    "mineruAttachmentsFolder": "attachments/mineru",
    "noteFilenamePattern": "{firstAuthor} {year} - {shortTitle}",
    "pdfFilenamePattern": "{shortTitle}",
    "mineruMarkdownName": "paper.md",
    "mineruImagesIndexName": "images-index.md",
}
```

Merge vault-local config over defaults and normalize path separators without rejecting non-English folder names.

- [ ] **Step 4: Implement `obsidian_pipeline_config`**

Return config, source path, whether it exists, and planned root folders.

- [ ] **Step 5: Run config test to verify GREEN**

Run the same test. Expected: PASS.

---

### Task 3: Single Zotero Item Pipeline Without MinerU

**Files:**
- Modify: `scripts/obsidian_vault_mcp/helpers.py`
- Modify: `scripts/obsidian_vault_mcp/tools.py`
- Test: `tests/test_obsidian_vault_mcp.py`

- [ ] **Step 1: Write failing test for stable literature note and PDF links**

Fake Zotero API with one parent item, one child note, and one PDF. Assert:

```python
result = self.module.obsidian_pipeline_ingest_item("ITEM1", str(self.vault), parse_with_mineru=False)
self.assertTrue(result["ok"])
self.assertEqual(result["literaturePath"], "literature/Lovelace 2024 - Zotero Article.md")
self.assertTrue((self.vault / "attachments" / "zotero" / "ITEM1" / "zotero-article.pdf").exists())
note = ...
self.assertIn("zoteroAttachmentPaths:", note)
self.assertIn("zotero://select/library/items/ITEM1", note)
self.assertIn("zotero://open-pdf/library/items/PDF1", note)
self.assertIn("[[attachments/zotero/ITEM1/zotero-article.pdf]]", note)
self.assertIn("## Reading Notes", note)
self.assertIn("## AI Summary", note)
```

- [ ] **Step 2: Run the test to verify RED**

Expected: FAIL because the high-level pipeline tool is missing.

- [ ] **Step 3: Implement metadata/path planning**

Add helpers that derive:
- `FirstAuthor Year - Short Title.md`
- PDF filename from `{shortTitle}` as lowercase ASCII slug
- Obsidian wikilinks for copied PDFs
- Zotero select/open-pdf links

- [ ] **Step 4: Implement literature note writer**

Merge plugin-owned fields into YAML, preserve user-owned/custom YAML, and render managed sections:
`Abstract`, `PDF`, `Zotero Notes & Annotations`, `MinerU Extraction`.

- [ ] **Step 5: Implement `obsidian_pipeline_ingest_item` no-MinerU path**

Fetch item/children/PDFs, copy PDFs, write/update literature note, return structured report.

- [ ] **Step 6: Run the test to verify GREEN**

Run the single-item no-MinerU test. Expected: PASS.

---

### Task 4: Preserve User-Owned Fields and Sections on Repeated Runs

**Files:**
- Modify: `scripts/obsidian_vault_mcp/helpers.py`
- Test: `tests/test_obsidian_vault_mcp.py`

- [ ] **Step 1: Write failing repeat-run test**

After first ingest, manually add:

```yaml
status: reading
project: demo
customField: keep-me
```

and content under `## Reading Notes` plus `## AI Summary`. Run ingest again and assert those fields/sections remain unchanged.

- [ ] **Step 2: Run repeat-run test to verify RED**

Expected: FAIL until section preservation is implemented.

- [ ] **Step 3: Implement section replacement by headings**

Only replace plugin-owned sections. Preserve the exact text of `## Reading Notes` and `## AI Summary` from existing note when present; create empty sections only for new notes.

- [ ] **Step 4: Run repeat-run test to verify GREEN**

Expected: PASS.

---

### Task 5: MinerU Parse, Image Rename, and Images Index

**Files:**
- Modify: `scripts/obsidian_vault_mcp/helpers.py`
- Modify: `scripts/obsidian_vault_mcp/tools.py`
- Test: `tests/test_obsidian_vault_mcp.py`

- [ ] **Step 1: Write failing fixture test for parse with MinerU**

Mock the existing `obsidian_mineru_extract` to create `paper.md` plus `images/figure1.png`; call:

```python
result = self.module.obsidian_pipeline_ingest_item("ITEM1", str(self.vault), parse_with_mineru=True)
```

Assert:
- `attachments/mineru/ITEM1/paper.md` exists
- `attachments/mineru/ITEM1/images-index.md` exists
- image renamed to `fig-01-process-flow-diagram.png`
- literature note YAML/body link to MinerU Markdown and image index

- [ ] **Step 2: Write failing test for image rename/index directly**

Create `attachments/mineru/ITEM1/paper.md` with image references and captions; call `obsidian_pipeline_rename_mineru_images`; assert English slug names, rewritten Markdown, mapping table, cleanup candidates.

- [ ] **Step 3: Run MinerU tests to verify RED**

Expected: FAIL because the pipeline parse/rename tools do not exist.

- [ ] **Step 4: Implement English semantic slugging**

Use caption first, then nearby context. Infer prefix:
- `table` when caption starts with table
- `scheme` for scheme/pathway/mechanism/process scheme
- `eq` for equation/rate equation/formula
- `fig` for figure/chart/diagram
- `img` fallback

Generate `<type>-<number>-<english-semantic-slug>.<ext>` and strip non-ASCII words into portable English fallback tokens when needed.

- [ ] **Step 5: Implement image index writer**

Write `images-index.md` with YAML `type: mineru-image-index`, parent links, source extraction links, and table columns `ID`, `Image`, `File`, `Caption`, `Used For`, `Original`.

- [ ] **Step 6: Implement `obsidian_pipeline_parse_with_mineru`**

Resolve literature note by `zotero_key` or path, find copied PDF, run MinerU into `attachments/mineru/<zoteroKey>/`, normalize Markdown to configured name, rename images, write image index, update literature note MinerU fields.

- [ ] **Step 7: Run MinerU tests to verify GREEN**

Expected: PASS.

---

### Task 6: Collection Pipeline and Failure Reporting

**Files:**
- Modify: `scripts/obsidian_vault_mcp/tools.py`
- Test: `tests/test_obsidian_vault_mcp.py`

- [ ] **Step 1: Write failing collection test**

Fake a collection with two top-level parent items. Make one item succeed and one fail during item fetch or PDF resolution. Assert:

```python
self.assertTrue(result["ok"])
self.assertEqual(result["total"], 2)
self.assertEqual(result["succeeded"], 1)
self.assertEqual(result["failed"], 1)
self.assertEqual(result["results"][1]["status"], "failed")
self.assertIn("stage", result["results"][1])
```

- [ ] **Step 2: Run collection test to verify RED**

Expected: FAIL because `obsidian_pipeline_ingest_collection` is missing.

- [ ] **Step 3: Implement collection wrapper**

Fetch collection top items, skip attachments/notes/annotations, call single-item pipeline per key, continue on exceptions, and return full batch report with counts for created/updated/MinerU/image statuses.

- [ ] **Step 4: Run collection test to verify GREEN**

Expected: PASS.

---

### Task 7: Layout Migration Dry-Run

**Files:**
- Modify: `scripts/obsidian_vault_mcp/helpers.py`
- Modify: `scripts/obsidian_vault_mcp/tools.py`
- Test: `tests/test_obsidian_vault_mcp.py`

- [ ] **Step 1: Write failing dry-run migration test**

Create old-style `sources/mineru/Paper.md`, `assets/zotero/ITEM1/PDF1.pdf`, and a literature note with `type: literature`, `zoteroKey`, and old paths. Call `obsidian_pipeline_migrate_layout(dry_run=True)` and assert:
- no files moved
- `plannedMoves` includes new `attachments/zotero/ITEM1/...` and `attachments/mineru/ITEM1/paper.md`
- `plannedYamlUpdates` and `plannedMarkdownLinkUpdates` include the literature note
- unrelated user notes are not included

- [ ] **Step 2: Run migration test to verify RED**

Expected: FAIL because migration tool is missing.

- [ ] **Step 3: Implement dry-run migration planner**

Scan only Markdown files with recognized `type` and `zoteroKey`; plan movement and YAML/link updates using current pipeline config.

- [ ] **Step 4: Implement apply mode**

When `dry_run=False`, move plugin-managed files only, update YAML and links, and report warnings instead of deleting obsolete files.

- [ ] **Step 5: Run migration tests to verify GREEN**

Expected: PASS.

---

### Task 8: Doctor, Docs, Manifests, and Verification

**Files:**
- Modify: `scripts/obsidian_vault_mcp/tools.py`
- Modify: `scripts/obsidian_vault_mcp/cli.py`
- Modify: `.codex-plugin/plugin.json`
- Modify: `.claude-plugin/plugin.json`
- Modify: `README.md`, `README.en.md`, `README.zh-CN.md`, `docs/TECHNICAL_GUIDE.md`
- Modify: skill docs under `skills/` and packaged `scripts/obsidian_vault_mcp/skills/`
- Test: `tests/test_obsidian_vault_mcp.py`

- [ ] **Step 1: Add doctor test**

Assert `obsidian_pipeline_doctor` reports vault config, Zotero, MinerU, profile, and pipeline folder readiness.

- [ ] **Step 2: Implement `obsidian_pipeline_doctor`**

Reuse `_doctor`, include profile/default exposed tool list, Zotero ping status, MinerU CLI status, and config source.

- [ ] **Step 3: Update docs and plugin metadata**

Default description should emphasize “Zotero + MinerU + Obsidian literature pipeline”. Document `OBSIDIAN_VAULT_TOOL_PROFILE=full` or `legacy` to expose old tools.

- [ ] **Step 4: Run targeted unit tests**

Run: `python -m unittest tests.test_obsidian_vault_mcp.ObsidianVaultMcpTests -v`

Expected: PASS.

- [ ] **Step 5: Run lint**

Run: `python -m ruff check .`

Expected: PASS or report exact remaining issues.

- [ ] **Step 6: Run local Zotero API check**

Run a Python one-liner or direct tool call equivalent to `obsidian_zotero_ping()`. If Zotero Desktop is unavailable, report the API error and rely on mocked unit tests for behavior.

- [ ] **Step 7: Run local Obsidian vault check**

Use a temporary local vault with `.obsidian/` to verify actual file generation, YAML/wikilinks, repeat protection, image index, and migration dry-run.

- [ ] **Step 8: Run MinerU availability check**

Call `obsidian_mineru_status()` or `mineru-open-api version`. If available, run a real parse on a small PDF; if unavailable, report that real MinerU parsing was skipped and fixture/mock path was verified.

---

## Self-Review

Spec coverage:
- Default literature profile and full/legacy compatibility: Task 1.
- Vault-local config and layout: Task 2.
- Stable literature note and PDF/Zotero links: Task 3.
- User-owned YAML/sections protection: Task 4.
- MinerU output placement, image slug rename, image index: Task 5.
- Collection non-interrupting batch report: Task 6.
- Layout migration default dry-run: Task 7.
- Product boundary/docs and doctor: Task 8.

Placeholder scan: no `TBD` or open-ended “add tests” steps remain; every task names files, behavior, commands, and expected outcomes.

Type consistency: public tool names match the design document exactly: `obsidian_pipeline_doctor`, `obsidian_pipeline_config`, `obsidian_pipeline_migrate_layout`, `obsidian_pipeline_ingest_item`, `obsidian_pipeline_ingest_collection`, `obsidian_pipeline_parse_with_mineru`, and `obsidian_pipeline_rename_mineru_images`.
