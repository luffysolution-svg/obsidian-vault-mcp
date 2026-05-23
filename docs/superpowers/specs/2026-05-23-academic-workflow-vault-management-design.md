# Design: Academic Workflow Deepening & Vault Management

**Date:** 2026-05-23  
**Status:** Approved  
**Scope:** Two independent subsystems — Zotero annotation structuring and core vault file operations

---

## Subsystem 1: Zotero Structured Annotations

### Problem

`_zotero_notes_and_annotations()` currently concatenates all Zotero annotations into a flat text string. Color, annotation type, and page number information are discarded. The user employs a personal color-coding system where each Zotero highlight color carries a semantic meaning (背景, 理论, 数据, etc.), which is lost on import.

### Color → Semantic Label Mapping

Default mapping (based on Zotero's standard palette + user convention):

| Hex | Color | Default Label | Callout Type |
|---|---|---|---|
| `#ffd400` | 🟡 Yellow | 背景 | `[!quote]` |
| `#ff6666` | 🔴 Red | 理论 | `[!quote]` |
| `#2ea8e5` | 🔵 Blue | 数据 | `[!quote]` |
| `#5fb236` | 🟢 Green | 假设 | `[!quote]` |
| `#a28ae5` | 🟣 Purple | 实验 | `[!quote]` |
| `#e56eee` | 🩷 Magenta | 结论 | `[!quote]` |
| `#f19837` | 🟠 Orange | 分析 | `[!quote]` |
| `#aaaaaa` | ⬜ Gray | 重要 | `[!quote]` |
| none | — | — | `[!note]` |

All highlights use `[!quote]` callout (semantic match: quoting paper text). Pure notes with no highlighted text use `[!note]`. Color emoji + semantic label provide visual differentiation without callout-type complexity.

Color matching uses approximate RGB distance (tolerance ±20) to handle slight variations from plugins like Ethereal Style.

### Output Format

```markdown
## Annotations

> [!quote]+ 🟡 背景 — p.3
> "Deep learning has revolutionized computer vision..."
>
> *注：与 Smith 2021 的方法对比*

> [!quote]+ 🩷 结论 — p.12
> "Our method outperforms baseline by 15%..."

> [!note]+ 📝 p.7
> 这里的实验设计有问题，样本量不足
```

Rules:
- Highlight with text → `[!quote]` + emoji + label + page
- Pure note (no highlighted text) → `[!note]` + 📝 + page
- Both highlight and comment → `[!quote]` with original text as body, comment as italic line below

Annotations are sorted by page number (ascending). The entire section is wrapped in `<!-- obsidian-vault:generated:start/end -->` for idempotent updates and rollback support.

### Configuration

Users can override the default mapping in two ways:

**1. Vault config file** (`.obsidian/obsidian-vault-mcp.json`, persistent):
```json
{
  "annotationColorLabels": {
    "#ffd400": "背景",
    "#ff6666": "理论",
    "#2ea8e5": "数据",
    "#5fb236": "假设",
    "#a28ae5": "实验",
    "#e56eee": "结论",
    "#f19837": "分析",
    "#aaaaaa": "重要"
  }
}
```

**2. Tool parameter** `color_labels_json` (one-off override, takes precedence over vault config).

### Interface Changes

Add `annotations_mode` parameter to two existing tools:

```python
obsidian_ingest_zotero_item(
    ...
    annotations_mode: str = "flat",   # "flat" | "structured"
    color_labels_json: str = "{}",    # optional per-call override
)

obsidian_ingest_zotero_collection(
    ...
    annotations_mode: str = "flat",
    color_labels_json: str = "{}",
)
```

Default `"flat"` preserves existing behavior — fully backward compatible.

### Internal Refactor

Split `_zotero_notes_and_annotations()` into two functions:

- `_zotero_notes_flat(children)` — preserves current behavior, called when `annotations_mode="flat"`
- `_zotero_annotations_structured(children, color_labels, vault)` — new structured renderer

A new helper `_resolve_annotation_color_labels(vault, color_labels_json)` merges vault config defaults with per-call overrides.

---

## Subsystem 2: Vault Management Three-Pack

### Problem

Three common file operations are missing or require workarounds:
1. **Delete** — only possible via `obsidian_apply_edit_plan` with `op: "delete"`, which is verbose
2. **Move / Rename** — only via the CLI wrapper `obsidian_cli_move_or_rename`, which requires Obsidian to be running and defaults to `dry_run=True`
3. **Regex search** — `obsidian_search` supports only substring matching

### New Tool: `obsidian_delete_file`

```python
obsidian_delete_file(
    path: str,
    vault_path: str = "",
    backup: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]
```

- `dry_run=True` returns the would-be deleted path and backup location without executing
- `backup=True` (default) copies the file to `.obsidian-vault-backups/manual/<timestamp>/<path>` before deletion — consistent with the existing edit plan backup directory structure
- Returns `{"ok": True, "path": "...", "backup": "...", "dryRun": false}`

### New Tool: `obsidian_move_file`

```python
obsidian_move_file(
    path: str,
    to: str,                        # target directory, vault-relative
    vault_path: str = "",
    update_wikilinks: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]
```

### New Tool: `obsidian_rename_file`

```python
obsidian_rename_file(
    path: str,
    name: str,                      # new filename including extension
    vault_path: str = "",
    update_wikilinks: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]
```

**`update_wikilinks=False` (default):** Only moves/renames the file. Fast. Does not touch other notes.

**`update_wikilinks=True`:** After moving/renaming, scans all `.md` files in the vault for references to the old path/stem/name (matching `[[old_stem]]`, `[[old/path]]`, `[[old/path|label]]`) and rewrites them to point to the new location. Returns:
```json
{
  "ok": true,
  "from": "old/path.md",
  "to": "new/path.md",
  "updatedFiles": ["A.md", "B.md"],
  "replacementCount": 5
}
```

Both tools use `shutil.move()` under the hood — no dependency on the Obsidian CLI or Obsidian being open.

### Enhanced: `obsidian_search` Regex Support

Add one parameter to the existing tool:

```python
obsidian_search(
    query: str,
    ...,
    use_regex: bool = False,    # new
) -> list[dict[str, Any]]
```

- `use_regex=False` → existing behavior, fully backward compatible
- `use_regex=True` → compiles `query` with `re.compile()`, respects existing `case_sensitive` flag
- On invalid regex, returns a clean error response rather than raising:
  `{"error": "Invalid regex: unterminated character set at position 3"}`

---

## Files to Change

| File | Change |
|---|---|
| `scripts/obsidian_vault_mcp/helpers.py` | Add `_zotero_annotations_structured()`, `_zotero_notes_flat()`, `_resolve_annotation_color_labels()` |
| `scripts/obsidian_vault_mcp/tools.py` | Add `annotations_mode` + `color_labels_json` to `obsidian_ingest_zotero_item` and `obsidian_ingest_zotero_collection`; add `obsidian_delete_file`, `obsidian_move_file`, `obsidian_rename_file`; add `use_regex` to `obsidian_search` |
| `tests/test_obsidian_vault_mcp.py` | New test cases for all new/changed tools |

No new dependencies. All changes use stdlib only (`re`, `shutil`, `pathlib`).

---

## Testing Plan

- `test_zotero_annotations_structured_groups_by_page_and_color` — verify callout output, page sorting, comment formatting
- `test_zotero_annotations_structured_custom_color_labels` — verify vault config + per-call override
- `test_zotero_annotations_flat_mode_unchanged` — regression: flat mode output identical to current
- `test_delete_file_creates_backup_before_deleting` — verify backup path, file gone after
- `test_delete_file_dry_run_does_not_delete` — verify dry run
- `test_move_file_updates_wikilinks` — verify cross-note wikilink rewrite
- `test_rename_file_no_wikilink_update` — verify file renamed, other notes untouched
- `test_search_regex_matches_pattern` — verify regex matching works
- `test_search_regex_invalid_pattern_returns_error` — verify friendly error on bad regex
