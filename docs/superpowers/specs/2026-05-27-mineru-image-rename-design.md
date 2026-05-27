# Design: MinerU Image Rename — Caption-Based Slug Renaming

**Date:** 2026-05-27
**Status:** Approved
**Scope:** New `obsidian_mineru_rename_images` tool + `rename_images` parameter on existing MinerU tools

---

## Problem

MinerU extracts images from PDFs and names them with internal UUIDs or sequential hashes
(e.g., `abc123def456.png`). These names carry no semantic meaning, which makes them
useless as nodes in the Obsidian knowledge graph and difficult to reason about.

**Goal:** Rename each extracted image using its figure caption from the parsed Markdown,
update all references in the Markdown file, and integrate the rename step into the existing
extraction pipeline as an opt-in flag.

---

## Approach: Sliding-Window Caption Heuristics

No new external dependencies. Pure Python (re, pathlib). Follows the existing project pattern
of private helpers in `helpers.py` and public `@tool()` functions in `tools.py`.

---

## Data Flow

```
Read markdown file
    ↓
Scan for all image references  (![alt](images/uuid.png)  and  ![[uuid.png]])
    ↓
For each image, extract caption via sliding-window heuristics → generate slug
    ↓
Resolve naming conflicts (dedup)
    ↓
dry_run=False:
  1. Rename image files on disk
  2. Replace all references in markdown text (handles repeated references)
  3. Write updated markdown back to disk
```

---

## Tool Interface

### New Tool: `obsidian_mineru_rename_images`

```python
@tool()
def obsidian_mineru_rename_images(
    markdown_path: str,
    vault_path: str = "",
    doc_slug: str = "",          # optional prefix; auto-inferred from filename if empty
    caption_window: int = 3,     # lines to scan before/after each image for captions
    dry_run: bool = True,        # default True: preview only, no disk changes
) -> dict[str, Any]:
    """Rename MinerU-extracted images using figure captions found in the Markdown.

    Caption extraction priority:
    1. Non-empty alt text (>3 chars)
    2. Lines AFTER image within caption_window — strong pattern first, then weak
    3. Lines BEFORE image within caption_window — same priority
    4. Any line within the full window matching a strong caption pattern
    5. Fallback: {doc_slug}_img_{N:03d}

    dry_run=True (default): return the planned rename list without touching any files.
    """
```

**Return value:**
```python
{
    "ok": True,
    "markdownPath": "mineru-output/paper/paper.md",
    "totalImages": 8,
    "renamed": 6,        # caption successfully extracted
    "fallback": 2,       # fell back to positional numbering
    "skipped": 0,        # already renamed (idempotent skip)
    "errors": [],        # per-file rename errors (non-fatal)
    "dryRun": False,
    "renames": [
        {
            "old": "images/abc123.png",
            "new": "images/paper_二氧化碳吸收速率对比.png",
            "caption": "图1 二氧化碳吸收速率对比",
            "strategy": "caption_after"
            # strategy values: alt / caption_after / caption_before / radius / fallback
        },
        ...
    ]
}
```

### Modified Tool: `obsidian_mineru_extract_and_ingest`

Add one optional parameter:
```python
rename_images: bool = False,   # call obsidian_mineru_rename_images after successful ingest
```

The rename step runs only when both extraction and ingestion succeed. Its result is included
in the return value under `"imageRename"`.

### Modified Tool: `obsidian_mineru_extract_folder`

Add one optional parameter:
```python
rename_images: bool = False,   # forwarded to each extract_and_ingest call
```

---

## Caption Extraction Logic

### Supported Image Reference Formats

```
![alt text](images/uuid.png)     # standard Markdown
![[uuid.png]]                    # Obsidian wikilink
```

Both formats are detected; only the filename portion is replaced in the output.

### Caption Regex Patterns

```python
# Strong: starts with figure/table keyword + number (Chinese or English)
CAPTION_STRONG_RE = re.compile(
    r"^[>\s*_]*(?:图|表|Figure|Table|Scheme|Chart|式|公式)\s*\d+",
    re.IGNORECASE
)

# Weak: entire line is bold or italic (common inline caption style)
CAPTION_WEAK_RE = re.compile(r"^\*{1,2}.+\*{1,2}$")
```

### Sliding-Window Priority

For image reference at line index `idx` in `lines`:

| Priority | Source | Condition |
|----------|--------|-----------|
| 1 | `alt` text | non-empty, `len(alt.strip()) > 3` |
| 2 | `lines[idx+1 .. idx+window]` | first non-empty line matching strong, then weak |
| 3 | `lines[idx-window .. idx-1]` (reversed) | first non-empty line matching strong, then weak |
| 4 | `lines[idx-window .. idx+window]` | first line matching strong pattern anywhere in window |
| 5 | fallback | `f"{doc_slug}_img_{N:03d}"` |

### Slug Generation Rules

1. Take the matched caption text in full (e.g., `图1 二氧化碳吸收速率对比`)
2. Clean illegal filename characters: `< > : " / \ | ? * \n \r \t` and leading/trailing spaces
3. Replace runs of ASCII whitespace with `-`; Chinese characters and digits kept as-is
4. Truncate to 60 characters (measured in characters, not bytes)
5. Format: `{doc_slug}_{cleaned_caption}{original_ext}`  (e.g., `paper_图1-二氧化碳吸收速率对比.png`)
6. Dedup: if slug already used in this run, append `_2`, `_3`, …

**Chinese character handling:** kept verbatim. Only ASCII-illegal characters are removed.
No transliteration, no translation.

### Idempotency

If an image filename already starts with `{doc_slug}_`, it is counted as `skipped` and not
processed again. Safe to re-run on already-renamed output.

---

## Error Handling

| Situation | Behavior |
|-----------|----------|
| `markdown_path` does not exist | `{"ok": False, "error": "..."}` immediately |
| Image directory does not exist | skip all images, report in `errors` |
| Image file missing from disk | skip that image, add to `errors`, continue |
| Slug cleaned to empty string | fall back to positional `fallback` strategy |
| File rename OS error (permissions/lock) | add to `errors`, continue with remaining images |
| Markdown write-back failure | `{"ok": False, "error": "..."}`, already-renamed files are **not rolled back** (recorded in `renames` for manual inspection) |

---

## Private Helpers (added to `helpers.py`)

| Function | Responsibility |
|----------|----------------|
| `_mineru_find_images(lines)` | scan markdown lines, return list of `(line_idx, raw_ref, img_path, alt)` |
| `_mineru_extract_caption(lines, img_line_idx, window)` | sliding-window caption search; returns `(caption_text, strategy)` |
| `_mineru_caption_to_slug(caption, doc_slug, ext, used)` | clean + dedup → final filename |

All helpers are pure functions (no I/O) to keep them easily unit-testable.

---

## Integration Points

```
obsidian_mineru_extract_folder(rename_images=True)
    └─► obsidian_mineru_extract_and_ingest(rename_images=True)
            └─► obsidian_mineru_rename_images(dry_run=False)
                    ├─► _mineru_find_images()
                    ├─► _mineru_extract_caption()
                    └─► _mineru_caption_to_slug()
```

Standalone usage is also fully supported — call `obsidian_mineru_rename_images` directly
on any existing MinerU Markdown output.

---

## Testing Strategy

Tests live in `tests/test_obsidian_vault_mcp.py` using the existing `unittest.TestCase`
temp-vault fixture.

Key test cases:
- `test_rename_images_uses_alt_text` — alt text present → used as slug
- `test_rename_images_caption_after` — caption on line after image → extracted
- `test_rename_images_caption_before` — caption on line before image → extracted
- `test_rename_images_chinese_caption_kept` — Chinese characters preserved in filename
- `test_rename_images_fallback_positional` — no caption found → `doc_img_001.png`
- `test_rename_images_dedup_conflict` — two images same caption → `_2` suffix
- `test_rename_images_dry_run_no_write` — dry_run=True → no disk changes
- `test_rename_images_idempotent_skip` — already renamed → skipped count increments
- `test_rename_images_updates_markdown_references` — markdown text updated correctly
- `test_rename_images_missing_image_file_skipped` — missing file → error, continues
- `test_extract_and_ingest_rename_flag` — `rename_images=True` triggers rename after ingest

---

## Out of Scope

- AI-assisted caption translation (no LLM calls in this feature)
- Moving images to a centralized vault attachments folder (in-place only)
- Renaming images referenced in notes other than the MinerU Markdown itself
