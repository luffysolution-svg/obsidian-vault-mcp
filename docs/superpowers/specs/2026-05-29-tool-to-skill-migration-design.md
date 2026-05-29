# Tool-to-Skill Migration Design

**Date:** 2026-05-29  
**Status:** Approved  
**Scope:** obsidian-vault-mcp v1.1.0

---

## Overview

The plugin currently exposes 82 MCP tools across two profiles: `literature` (20 tools, default) and `full`/`legacy` (82 tools). This migration:

1. Retains the 20 `literature` profile tools unchanged.
2. Deletes ~10 truly deprecated tools (replaced by the Zotero pipeline).
3. Converts ~45 legacy tools into skill documents so their workflows remain accessible without burdening the MCP server.
4. Ships updated Chinese + English README docs, a new GitHub Release, a PyPI publish, and a zip package.

---

## §1 — Tool Classification (82 → 20 MCP tools)

### Group A — Delete (≈10 tools, code removed entirely)

These tools are fully superseded by the Zotero→MinerU→Obsidian pipeline:

| Tool | Replacement |
|------|-------------|
| `obsidian_parse_bibtex` | `zotero_get_item` |
| `obsidian_ingest_bibtex` | `pipeline_ingest_item` |
| `obsidian_ingest_reference` | `pipeline_ingest_item` |
| `obsidian_ingest_source_note` | Deprecated workflow |
| `obsidian_ingest_pdf_attachment` | Pipeline-internal PDF copy |
| `obsidian_ingest_mineru_markdown` | `pipeline_parse_with_mineru` |
| `obsidian_mineru_extract_folder` | Skill description (batch via script) |

Additional legacy aliases and profile-gating helpers in `common.py` are cleaned up together.

### Group B — Convert to Skills (≈45 tools)

| Target Skill | Tool Categories Covered |
|--------------|------------------------|
| `obsidian-vault` (enhanced) | Graph build, lint, orphan/dead-link detection, wikilinks, wiki index/log, schema validation, bulk editing, create_note, vault status/stats |
| `obsidian-cli` (enhanced) | All 13 CLI wrappers (read, open, backlinks, base query, property CRUD, tasks, screenshot, plugin reload, move/rename) |
| `obsidian-views` (enhanced) | Canvas creation, Obsidian Bases, Dataview query templates |
| `obsidian-graph` (**new**) | Citation network, community detection, connectivity metrics, improvement suggestions |

### Group C — Keep (20 tools, literature profile)

No changes. These remain as MCP tools:
- Pipeline infrastructure: `pipeline_doctor`, `pipeline_config`, `pipeline_migrate_layout`
- Zotero: `zotero_ping`, `zotero_search_items`, `zotero_list_collections`, `zotero_get_item`, `zotero_get_children`, `zotero_list_pdf_attachments`, `zotero_extract_pdf_text`
- Ingestion: `pipeline_ingest_item`, `pipeline_ingest_collection`
- MinerU: `pipeline_parse_with_mineru`, `pipeline_rename_mineru_images`, `obsidian_mineru_extract`, `obsidian_mineru_extract_and_ingest`
- Vault basics: `obsidian_read_file`, `obsidian_write_file`, `obsidian_search`, `obsidian_update_properties`
- Utility: `obsidian_doctor`

---

## §2 — Skill Architecture

Each skill consists of:
- `skills/<name>/SKILL.md` — full workflow guide (bilingual EN + Chinese), bundled into the Python package
- `.claude/skills/<name>.md` — concise Claude Code–local mirror

### `obsidian-vault` (enhanced)

Add workflow sections:
- **Graph maintenance**: how to trigger `obsidian_build_graph`, interpret output, update wikilinks
- **Vault health**: lint workflow (orphans → `obsidian_find_orphans`, dead links → `obsidian_find_broken_links`)
- **Wiki maintenance**: index/log updates via `obsidian_update_wiki_index` + `obsidian_append_wiki_log`
- **Schema**: preset selection → `obsidian_validate_vault_schema` → `obsidian_apply_schema_defaults`
- **Bulk editing**: create_note with templates, preview/apply/rollback edit plans

### `obsidian-cli` (enhanced)

Add concrete `obsidian-cli` Bash command examples for each of the 13 wrappers. Organise by sub-task: reading, properties, navigation, tasks, plugin management.

### `obsidian-views` (enhanced)

Add:
- Canvas JSON structure and step-by-step creation guide
- Obsidian Bases: schema definition, query syntax
- Dataview: template catalogue and insertion workflow

### `obsidian-graph` (new)

Cover:
- Citation network construction (Zotero `related` relations → edge list)
- Community detection via `networkx` (Bash/Python one-liner)
- Connectivity metrics interpretation
- Actionable improvement suggestions (unresolved links, isolated nodes)

---

## §3 — File Structure Changes

```
skills/
  obsidian-vault/SKILL.md        ← enhanced
  obsidian-cli/SKILL.md          ← enhanced
  obsidian-views/SKILL.md        ← enhanced
  obsidian-graph/SKILL.md        ← NEW
  obsidian-graph/agents/openai.yaml ← NEW
  obsidian-zotero/               ← unchanged
  obsidian-mineru/               ← unchanged

.claude/skills/
  obsidian-vault.md              ← enhanced mirror
  obsidian-cli.md                ← enhanced mirror
  obsidian-views.md              ← enhanced mirror
  obsidian-graph.md              ← NEW mirror

scripts/obsidian_vault_mcp/
  tools.py                       ← remove Group A + B tool handlers
  helpers.py                     ← remove Group A + B helper functions
  common.py                      ← remove legacy profile definitions, clean registry
```

---

## §4 — Documentation Updates

Two files updated (concise):

| File | Change |
|------|--------|
| `README.md` | Remove old tool table; replace with skill-based architecture diagram + 20-tool list |
| `README.en.md` | Mirror of README.md in English |

`docs/TECHNICAL_GUIDE.md` — trim or remove sections describing deleted tools. Keep only the architecture overview and setup guide references.

No new documentation files created.

---

## §5 — Release & Publishing

1. Bump version in `pyproject.toml`: `1.0.27` → `1.1.0`
2. Run full test suite (`pytest`)
3. `python -m build` → produces `dist/zotero_obsidian_mcp-1.1.0.tar.gz` + `.whl`
4. `twine upload dist/*` → publish to PyPI (token provided out-of-band, not stored in repo)
5. `gh release create v1.1.0` with:
   - Release notes summarising the migration
   - Attach zip of `dist/zotero_obsidian_mcp-1.1.0.tar.gz`
6. Push `main` branch

---

## §6 — Implementation Order

1. **Code cleanup** — Remove Group A + B handlers from `tools.py`, `helpers.py`, `common.py`
2. **Skill authoring** — Use `superpowers:writing-skills` to write/enhance the 4 skill files; place in both `skills/` and `.claude/skills/`
3. **Tests** — Ensure existing test suite passes; update any tests that reference deleted tools
4. **Docs** — Rewrite `README.md` and `README.en.md`
5. **Version bump** — Update `pyproject.toml`
6. **Build & publish** — Build, PyPI upload, GitHub Release, zip
7. **Commit & push** — Final commit on `main`

---

## Success Criteria

- MCP server starts with exactly 20 tools in `literature` profile
- `pytest` passes with no references to deleted tools
- `skills/obsidian-graph/` exists with complete SKILL.md
- `obsidian-vault`, `obsidian-cli`, `obsidian-views` SKILL.md files each cover their new workflow sections
- `README.md` and `README.en.md` reflect the new skill-based architecture
- PyPI `zotero-obsidian-mcp==1.1.0` is live
- GitHub Release `v1.1.0` exists with attached zip
