# Design: LLM Wiki Page Generation

**Date:** 2026-05-27  
**Status:** Approved  
**Scope:** Add `obsidian_wiki_context` and `obsidian_write_wiki_page` to support LLM-driven wiki page generation from vault knowledge  
**Inspired by:** [llm_wiki](https://github.com/nashsu/llm_wiki)

---

## Problem

The vault accumulates orphan notes and isolated concepts that are never synthesised into structured wiki pages. There is no tool to gather all relevant vault context (wikilink neighbours, full-text search results, Zotero literature, entity/concept nodes) around a topic and present it to a calling LLM so it can generate a structured wiki draft. The MCP server should act as the context collector and persistence layer; the LLM remains the content generator.

---

## Architecture Overview

### New Tools (2)

| Tool | Responsibility |
|---|---|
| `obsidian_wiki_context` | Given a topic string or an existing note path, collect context from 4 sources and return a structured JSON bundle |
| `obsidian_write_wiki_page` | Accept LLM-generated Markdown, write it to `wiki/`, update index and log |

### New Internal Helpers (helpers.py)

| Helper | Responsibility |
|---|---|
| `_wiki_neighbors(vault, topic_id, graph, max_n, snippet_chars)` | Extract 1-hop wikilink neighbours from the graph, read a snippet from each note |
| `_wiki_search_results(vault, topic, max_n, context_chars)` | Full-text search across the vault for the topic string |
| `_wiki_zotero_items(topic, max_n, api_base)` | Search Zotero by topic keyword, return title + abstract |
| `_wiki_entity_concept_nodes(vault, topic, graph, max_n, snippet_chars)` | Search the `entities/` and `concepts/` folders for nodes matching the topic |

### Data Flow

```
Calling LLM
    │
    ▼
obsidian_wiki_context(topic="X"  and/or  note_path="X.md")
    ├── 1. Full-text search          (reuses obsidian_search logic)
    ├── 2. Wikilink neighbours       (obsidian_build_graph → 1-hop)
    ├── 3. Zotero items              (obsidian_zotero_search_items logic, graceful degradation)
    └── 4. Entity/concept nodes      (search in entities/ + concepts/ folders)
    │
    └──▶ Structured JSON context bundle (+ suggestedFrontmatter + suggestedSections)
    │
    ▼  (LLM generates Markdown content)
    │
    ▼
obsidian_write_wiki_page(path="wiki/X.md", content="...")
    ├── Assemble frontmatter (type=wiki, tags=[wiki], title, created, merged extras)
    ├── Write file (overwrite guard)
    ├── obsidian_update_wiki_index  (optional, default on)
    └── obsidian_append_wiki_log    (optional, default on, event_type="wiki_generated")
```

### No New Dependencies

All operations reuse existing helpers: `_vault()`, `_safe_path()`, `_read_text()`, `_write_text()`, `obsidian_build_graph()`, and existing Zotero API functions. No new Python packages required.

---

## Section 1: `obsidian_wiki_context`

### Signature

```python
def obsidian_wiki_context(
    topic: str = "",
    note_path: str = "",
    vault_path: str = "",
    max_neighbors: int = 10,
    max_search_results: int = 10,
    max_zotero_items: int = 5,
    max_entity_nodes: int = 10,
    neighbor_snippet_chars: int = 300,
    zotero_api_base: str = "",
    folder: str = "",
) -> dict[str, Any]
```

### Parameter Semantics

- `topic` and `note_path` may both be provided. `note_path` anchors the graph neighbour lookup; `topic` drives full-text search and Zotero search.
- If only `note_path` is given, `topic` is inferred from the file stem (e.g. `"reactor_design"` → `"reactor design"`).
- If only `topic` is given, the neighbours step is skipped (no graph anchor node).
- Both empty → `ValueError("topic or note_path is required")`.

### Execution Order

1. `_vault()` — resolve vault path.
2. If `note_path` is provided: read existing note content and frontmatter (`existingNote`).
3. Determine query string: `topic` or stem-inferred from `note_path`.
4. Collect sequentially (steps are independent):
   - Full-text search via `_wiki_search_results`.
   - Graph neighbours via `obsidian_build_graph` + `_wiki_neighbors`.
   - Zotero items via `_wiki_zotero_items` (wrapped in try/except).
   - Entity/concept nodes via `_wiki_entity_concept_nodes`.
5. Assemble `suggestedFrontmatter` from collected results.
6. Return bundle.

### Return Structure

```json
{
  "topic": "反应釜设计",
  "notePath": "sources/reactor_design.md",
  "existingNote": {
    "path": "sources/reactor_design.md",
    "properties": {"title": "...", "type": "source"},
    "body": "..."
  },
  "neighbors": [
    {"path": "entities/heat_transfer.md", "title": "传热", "snippet": "..."}
  ],
  "searchResults": [
    {"path": "sources/distillation.md", "line": 14, "snippet": "..."}
  ],
  "zoteroItems": [
    {"key": "ABC123", "title": "Reactor Design Principles", "abstract": "...", "authors": ["Smith"], "year": 2021}
  ],
  "entityNodes": [
    {"path": "entities/agitator.md", "title": "搅拌器", "snippet": "..."}
  ],
  "conceptNodes": [
    {"path": "concepts/residence_time.md", "title": "停留时间", "snippet": "..."}
  ],
  "zoteroAvailable": true,
  "suggestedFrontmatter": {
    "title": "反应釜设计",
    "type": "wiki",
    "tags": ["wiki"],
    "related": ["entities/heat_transfer.md", "concepts/residence_time.md"],
    "zoteroKeys": ["ABC123"]
  },
  "suggestedSections": [
    "## Overview",
    "## Key Concepts",
    "## Related Notes",
    "## References"
  ]
}
```

`existingNote` and `notePath` are `null` when `note_path` is not provided.  
`body` in `existingNote` is capped at 2000 characters.

### Error Handling

| Condition | Behaviour |
|---|---|
| Both `topic` and `note_path` empty | `raise ValueError("topic or note_path is required")` |
| `note_path` does not exist | Continue; `existingNote: null` — useful for not-yet-created topics |
| Zotero unavailable (not running / timeout) | Silent degradation; `zoteroItems: []`, `zoteroAvailable: false` |
| Graph build fails | `neighbors: []`; does not abort overall execution |
| `entities/` or `concepts/` folder absent | `entityNodes: []` / `conceptNodes: []`; no error |

---

## Section 2: `obsidian_write_wiki_page`

### Signature

```python
def obsidian_write_wiki_page(
    path: str,
    content: str,
    vault_path: str = "",
    title: str = "",
    properties_json: str = "{}",
    overwrite: bool = False,
    update_index: bool = True,
    append_log: bool = True,
    index_path: str = "index.md",
    log_path: str = "log.md",
    dry_run: bool = False,
) -> dict[str, Any]
```

### Write Logic

**Frontmatter assembly:**
1. Base fields: `title` (from parameter or path stem), `type: wiki`, `tags: [wiki]`, `created` (UTC ISO timestamp).
2. Merge extra fields from `properties_json` (caller / LLM may inject `related`, `zoteroKeys`, etc.). Merged fields override base fields except `type` and `created`.
3. Final file content = `_write_frontmatter(props) + "\n" + content`.

**File write:**
- Target exists and `overwrite=False` → return `{"ok": false, "error": "Wiki page already exists. Pass overwrite=true to replace it."}`.
- Otherwise → `_write_text(full_path, final_content)` (parent directories created automatically).
- `dry_run=True` → return preview without writing.

**Post-write actions (skipped when `dry_run=True`):**
- `update_index=True` → call `obsidian_update_wiki_index(vault_path, index_path=index_path)`.
- `append_log=True` → call `obsidian_append_wiki_log(message, event_type="wiki_generated", touched_paths_json=[path])` where `message` is auto-generated as `"Wiki page generated: {title}"`.

### Return Structure

```json
{
  "ok": true,
  "path": "wiki/reactor_design.md",
  "created": true,
  "dryRun": false,
  "indexUpdated": true,
  "logAppended": true,
  "content": null
}
```

`content` is non-null only when `dry_run=True`, containing the full file content preview.  
`created: false` means an existing file was overwritten.  
If index or log update fails, the file write is **not** rolled back; `indexUpdated: false` / `logAppended: false` are reported with an `indexError` / `logError` field.

### Consistency with Existing Tools

| Existing tool | Alignment |
|---|---|
| `obsidian_ingest_source_note` — `overwrite` guard | Identical pattern |
| `obsidian_create_note` — frontmatter assembly | Reuses `_write_frontmatter` |
| All ingest tools — `dry_run` | Identical semantics |
| `obsidian_append_wiki_log` — `event_type` | New value `"wiki_generated"` added |

### Error Handling

| Condition | Behaviour |
|---|---|
| `path` empty | `raise ValueError("path is required")` |
| `content` empty | `raise ValueError("content is required")` |
| File exists and `overwrite=False` | Return `{"ok": false, "error": "..."}` |
| `properties_json` invalid JSON | `raise ValueError("properties_json must be valid JSON")` |
| Path escapes vault | Caught by existing `_safe_path()` check |
| Index / log update fails | File write kept; error fields added to return value |

---

## Section 3: Testing Strategy

~12 new tests appended to `tests/test_obsidian_vault_mcp.py`, following the existing `tmp_path` fixture + `monkeypatch` style.

### `obsidian_wiki_context` Tests (~7)

| Test | Coverage |
|---|---|
| `test_wiki_context_by_topic` | Pure topic string, no note_path; returns searchResults, suggestedSections |
| `test_wiki_context_by_note_path` | note_path provided; existingNote filled, neighbors from graph |
| `test_wiki_context_topic_inferred_from_path` | Only note_path given; topic inferred from stem |
| `test_wiki_context_no_topic_or_path_raises` | Both empty → ValueError |
| `test_wiki_context_zotero_unavailable` | Monkeypatch Zotero raises → zoteroAvailable=false, other fields intact |
| `test_wiki_context_missing_entity_folder` | entities/ absent → entityNodes=[], no crash |
| `test_wiki_context_suggested_frontmatter` | related and zoteroKeys assembled correctly |

### `obsidian_write_wiki_page` Tests (~5)

| Test | Coverage |
|---|---|
| `test_write_wiki_page_creates_file` | Normal write; verify frontmatter (type=wiki, tags=[wiki], title, created) |
| `test_write_wiki_page_overwrite_guard` | Exists + overwrite=False → ok=false; overwrite=True → success |
| `test_write_wiki_page_dry_run` | dry_run=True → no file on disk, content preview returned |
| `test_write_wiki_page_properties_merge` | properties_json fields merged into frontmatter |
| `test_write_wiki_page_invalid_json_raises` | Malformed properties_json → ValueError |

---

## Implementation Checklist

- [ ] Add `_wiki_neighbors` helper to `helpers.py`
- [ ] Add `_wiki_search_results` helper to `helpers.py`
- [ ] Add `_wiki_zotero_items` helper to `helpers.py`
- [ ] Add `_wiki_entity_concept_nodes` helper to `helpers.py`
- [ ] Implement `obsidian_wiki_context` tool in `tools.py`
- [ ] Implement `obsidian_write_wiki_page` tool in `tools.py`
- [ ] Add `"wiki_generated"` as a recognised `event_type` in `obsidian_append_wiki_log` (or leave open — current implementation accepts any string)
- [ ] Write 12 tests in `tests/test_obsidian_vault_mcp.py`
- [ ] Bump version to `1.0.23` in `pyproject.toml`
- [ ] Update `TECHNICAL_GUIDE.md` with the two new tools
