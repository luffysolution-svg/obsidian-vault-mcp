# MinerU Image Rename Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `obsidian_mineru_rename_images` tool that renames MinerU-extracted images using figure captions from the Markdown, plus a `rename_images=True` flag on the two existing batch tools.

**Architecture:** Three private pure helpers added to `helpers.py` handle scanning, caption extraction (sliding-window heuristics), and slug generation. The public tool in `tools.py` orchestrates I/O. Two existing tools get a `rename_images` opt-in parameter. Tests use the existing `unittest.TestCase` temp-vault fixture.

**Tech Stack:** Python 3.10+, `re`, `pathlib`, FastMCP `@tool()`, `unittest`

---

## File Structure

**Modified files:**
- `scripts/obsidian_vault_mcp/helpers.py` — append 3 new private helpers after `_mineru_command_args` (~line 1800)
- `scripts/obsidian_vault_mcp/tools.py` — insert new tool after `obsidian_mineru_extract_folder` (~line 1604); add `rename_images` param to `obsidian_mineru_extract_and_ingest` (~line 1376) and `obsidian_mineru_extract_folder` (~line 1494)
- `tests/test_obsidian_vault_mcp.py` — append all new tests

**No new files required.**

---

## Task 1: Private helpers — `_mineru_find_images`, `_mineru_extract_caption`, `_mineru_caption_to_slug`

**Files:**
- Modify: `scripts/obsidian_vault_mcp/helpers.py` — append after `_mineru_command_args`
- Test: `tests/test_obsidian_vault_mcp.py`

These three functions are pure (no I/O). They are tested through the main tool in Task 2 — no separate test task needed here.

- [ ] **Step 1: Append the three helpers to `helpers.py`**

Append the following block after the closing brace of `_mineru_command_args` (after line ~1799, before `_property_config`):

```python
# ── MinerU image rename helpers ─────────────────────────────────────────────

# Matches  ![alt](path)  anywhere on a line
_MINERU_MD_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
# Matches  ![[path]]  (Obsidian wikilink image)
_MINERU_WIKI_IMAGE_RE = re.compile(r"!\[\[([^\]]+)\]\]")

# Strong caption: starts with 图/表/Figure/Table/Scheme/Chart/式/公式 + optional space + digit
_MINERU_CAPTION_STRONG_RE = re.compile(
    r"^[>\s*_]*(?:图|表|Figure|Table|Scheme|Chart|式|公式)\s*\d+",
    re.IGNORECASE,
)
# Weak caption: entire line is bold or italic markdown (common inline caption)
_MINERU_CAPTION_WEAK_RE = re.compile(r"^\*{1,2}.+\*{1,2}$")

# Characters illegal in filenames on Windows/macOS/Linux
_MINERU_ILLEGAL_CHARS_RE = re.compile(r'[<>:"/\\|?*\n\r\t]')


def _mineru_find_images(lines: list[str]) -> list[tuple[int, str, str, str]]:
    """Scan markdown lines for image references.

    Returns a list of (line_idx, raw_ref, img_path, alt) tuples.
      raw_ref  — the full original text matched, e.g. ![alt](images/uuid.png)
      img_path — just the path/filename portion, e.g. images/uuid.png
      alt      — alt text (empty string for wikilink format)
    One entry per occurrence; the same img_path may appear multiple times.
    """
    results: list[tuple[int, str, str, str]] = []
    for idx, line in enumerate(lines):
        for m in _MINERU_MD_IMAGE_RE.finditer(line):
            alt = m.group(1)
            path = m.group(2)
            results.append((idx, m.group(0), path, alt))
        for m in _MINERU_WIKI_IMAGE_RE.finditer(line):
            path = m.group(1)
            # Only treat as image if it looks like an image file
            if Path(path).suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp"}:
                results.append((idx, m.group(0), path, ""))
    return results


def _mineru_extract_caption(
    lines: list[str], img_line_idx: int, window: int
) -> tuple[str, str]:
    """Sliding-window caption search around an image line.

    Returns (caption_text, strategy) where strategy is one of:
      "caption_after"   — caption found on a line after the image
      "caption_before"  — caption found on a line before the image
      "radius"          — caption found anywhere in the window (strong only)
      ""                — nothing found (caller applies fallback)
    """
    total = len(lines)

    def _is_strong(line: str) -> bool:
        return bool(_MINERU_CAPTION_STRONG_RE.match(line.strip()))

    def _is_weak(line: str) -> bool:
        stripped = line.strip()
        return bool(_MINERU_CAPTION_WEAK_RE.match(stripped)) and len(stripped) > 3

    # Priority 2: scan lines AFTER the image
    for i in range(img_line_idx + 1, min(total, img_line_idx + window + 1)):
        text = lines[i].strip()
        if not text:
            continue
        if _is_strong(text) or _is_weak(text):
            return text, "caption_after"
        break  # stop at first non-empty line that doesn't match

    # Priority 3: scan lines BEFORE the image (reversed)
    for i in range(img_line_idx - 1, max(-1, img_line_idx - window - 1), -1):
        text = lines[i].strip()
        if not text:
            continue
        if _is_strong(text) or _is_weak(text):
            return text, "caption_before"
        break  # stop at first non-empty line that doesn't match

    # Priority 4: anywhere in the full window — strong pattern only
    start = max(0, img_line_idx - window)
    end = min(total, img_line_idx + window + 1)
    for i in range(start, end):
        if i == img_line_idx:
            continue
        text = lines[i].strip()
        if _is_strong(text):
            return text, "radius"

    return "", ""


def _mineru_caption_to_slug(
    caption: str, doc_slug: str, ext: str, used: set[str]
) -> str:
    """Convert a caption string into a deduplicated image filename.

    Rules:
    - Illegal filename characters removed
    - ASCII whitespace runs replaced with '-'
    - Chinese characters kept verbatim
    - Truncated to 60 characters
    - Format: {doc_slug}_{cleaned_caption}{ext}
    - Appends _2, _3, … if the name is already in `used`
    """
    cleaned = _MINERU_ILLEGAL_CHARS_RE.sub("", caption).strip()
    cleaned = re.sub(r"[ \t]+", "-", cleaned)
    cleaned = cleaned[:60].rstrip("-")
    if not cleaned:
        cleaned = "img"

    stem = f"{doc_slug}_{cleaned}" if doc_slug else cleaned
    candidate = f"{stem}{ext}"
    if candidate not in used:
        used.add(candidate)
        return candidate
    counter = 2
    while True:
        candidate = f"{stem}_{counter}{ext}"
        if candidate not in used:
            used.add(candidate)
            return candidate
        counter += 1
```

- [ ] **Step 2: Verify helpers import cleanly**

```
python -c "from obsidian_vault_mcp.helpers import _mineru_find_images, _mineru_extract_caption, _mineru_caption_to_slug; print('OK')"
```

Run from `F:\化工设计比赛\plugins\obsidian-vault\scripts\`.
Expected: `OK`

- [ ] **Step 3: Commit**

```
git add scripts/obsidian_vault_mcp/helpers.py
git commit -m "feat: add _mineru_find_images, _mineru_extract_caption, _mineru_caption_to_slug helpers"
```

---

## Task 2: New tool `obsidian_mineru_rename_images`

**Files:**
- Modify: `scripts/obsidian_vault_mcp/tools.py` — insert after `obsidian_mineru_extract_folder` (after line ~1603, before `obsidian_ingest_pdf_attachment`)
- Test: `tests/test_obsidian_vault_mcp.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_obsidian_vault_mcp.py`:

```python
# ── obsidian_mineru_rename_images ────────────────────────────────────────────

def _make_mineru_dir(self, slug: str) -> tuple:
    """Helper: create a temp MinerU output directory with a markdown file and images folder."""
    md_dir = self.vault / "mineru" / slug
    md_dir.mkdir(parents=True, exist_ok=True)
    img_dir = md_dir / "images"
    img_dir.mkdir(exist_ok=True)
    return md_dir, img_dir

def test_rename_images_uses_alt_text(self):
    md_dir, img_dir = self._make_mineru_dir("p1")
    (img_dir / "abc.png").write_bytes(b"\x89PNG\r\n")
    (md_dir / "p1.md").write_text("![图1 示意图](images/abc.png)\n\n", encoding="utf-8")
    result = self.module.obsidian_mineru_rename_images(
        "mineru/p1/p1.md", str(self.vault), dry_run=False
    )
    self.assertTrue(result["ok"])
    self.assertEqual(result["renames"][0]["strategy"], "alt")
    self.assertIn("图1", result["renames"][0]["new"])
    # Old file gone, new file exists
    self.assertFalse((img_dir / "abc.png").exists())
    new_stem = result["renames"][0]["new"].split("/")[-1]
    self.assertTrue((img_dir / new_stem).exists())

def test_rename_images_caption_after(self):
    md_dir, img_dir = self._make_mineru_dir("p2")
    (img_dir / "uuid001.png").write_bytes(b"\x89PNG\r\n")
    (md_dir / "p2.md").write_text(
        "![](images/uuid001.png)\n\n图2 反应器示意图\n", encoding="utf-8"
    )
    result = self.module.obsidian_mineru_rename_images(
        "mineru/p2/p2.md", str(self.vault), dry_run=False
    )
    self.assertEqual(result["renames"][0]["strategy"], "caption_after")
    new_stem = result["renames"][0]["new"].split("/")[-1]
    self.assertTrue((img_dir / new_stem).exists())

def test_rename_images_caption_before(self):
    md_dir, img_dir = self._make_mineru_dir("p3")
    (img_dir / "uuid002.png").write_bytes(b"\x89PNG\r\n")
    (md_dir / "p3.md").write_text(
        "图3 温度曲线\n\n![](images/uuid002.png)\n\nSome text after\n", encoding="utf-8"
    )
    result = self.module.obsidian_mineru_rename_images(
        "mineru/p3/p3.md", str(self.vault), dry_run=False
    )
    self.assertEqual(result["renames"][0]["strategy"], "caption_before")
    self.assertIn("图3", result["renames"][0]["new"])

def test_rename_images_fallback_positional(self):
    md_dir, img_dir = self._make_mineru_dir("p4")
    (img_dir / "noid.png").write_bytes(b"\x89PNG\r\n")
    (md_dir / "p4.md").write_text(
        "![](images/noid.png)\n\nSome unrelated text here\n", encoding="utf-8"
    )
    result = self.module.obsidian_mineru_rename_images(
        "mineru/p4/p4.md", str(self.vault), dry_run=False
    )
    self.assertEqual(result["renames"][0]["strategy"], "fallback")
    self.assertIn("_img_001", result["renames"][0]["new"])
    self.assertEqual(result["fallback"], 1)
    self.assertEqual(result["renamed"], 0)

def test_rename_images_dry_run_no_write(self):
    md_dir, img_dir = self._make_mineru_dir("p5")
    (img_dir / "img001.png").write_bytes(b"\x89PNG\r\n")
    (md_dir / "p5.md").write_text(
        "![](images/img001.png)\n\n图1 压力温度曲线\n", encoding="utf-8"
    )
    result = self.module.obsidian_mineru_rename_images(
        "mineru/p5/p5.md", str(self.vault), dry_run=True
    )
    self.assertTrue(result["dryRun"])
    # Original file still exists
    self.assertTrue((img_dir / "img001.png").exists())
    self.assertEqual(len(result["renames"]), 1)
    self.assertTrue(result["ok"])

def test_rename_images_updates_markdown_references(self):
    md_dir, img_dir = self._make_mineru_dir("p6")
    (img_dir / "xyz.png").write_bytes(b"\x89PNG\r\n")
    # Image appears twice in the document
    (md_dir / "p6.md").write_text(
        "![](images/xyz.png)\n\n图3 流程图\n\nSee also: ![](images/xyz.png)\n",
        encoding="utf-8",
    )
    self.module.obsidian_mineru_rename_images(
        "mineru/p6/p6.md", str(self.vault), dry_run=False
    )
    new_text = (md_dir / "p6.md").read_text(encoding="utf-8")
    # Old name no longer anywhere in the file
    self.assertNotIn("xyz.png", new_text)

def test_rename_images_dedup_conflict(self):
    md_dir, img_dir = self._make_mineru_dir("p7")
    (img_dir / "a.png").write_bytes(b"\x89PNG\r\n")
    (img_dir / "b.png").write_bytes(b"\x89PNG\r\n")
    (md_dir / "p7.md").write_text(
        "![](images/a.png)\n\n图1 相同图注\n\n![](images/b.png)\n\n图1 相同图注\n",
        encoding="utf-8",
    )
    result = self.module.obsidian_mineru_rename_images(
        "mineru/p7/p7.md", str(self.vault), dry_run=False
    )
    new_names = [r["new"] for r in result["renames"]]
    self.assertEqual(len(set(new_names)), 2, "Duplicate filenames detected")

def test_rename_images_idempotent_skip(self):
    md_dir, img_dir = self._make_mineru_dir("p8")
    (img_dir / "p8_图1-示意图.png").write_bytes(b"\x89PNG\r\n")
    (md_dir / "p8.md").write_text(
        "![](images/p8_图1-示意图.png)\n\n图1 示意图\n", encoding="utf-8"
    )
    result = self.module.obsidian_mineru_rename_images(
        "mineru/p8/p8.md", str(self.vault), dry_run=False
    )
    self.assertEqual(result["skipped"], 1)
    self.assertEqual(result["renamed"] + result["fallback"], 0)

def test_rename_images_missing_file_recorded_in_errors(self):
    md_dir, img_dir = self._make_mineru_dir("p9")
    # Markdown references a file that does NOT exist on disk
    (md_dir / "p9.md").write_text(
        "![](images/ghost.png)\n\n图1 幽灵图\n", encoding="utf-8"
    )
    result = self.module.obsidian_mineru_rename_images(
        "mineru/p9/p9.md", str(self.vault), dry_run=False
    )
    self.assertGreater(len(result["errors"]), 0)
    self.assertEqual(result["errors"][0]["path"], "images/ghost.png")

def test_rename_images_chinese_caption_kept(self):
    md_dir, img_dir = self._make_mineru_dir("p10")
    (img_dir / "cn001.png").write_bytes(b"\x89PNG\r\n")
    (md_dir / "p10.md").write_text(
        "![](images/cn001.png)\n\n图1 二氧化碳吸收速率对比分析\n", encoding="utf-8"
    )
    result = self.module.obsidian_mineru_rename_images(
        "mineru/p10/p10.md", str(self.vault), dry_run=False
    )
    new_name = result["renames"][0]["new"]
    self.assertIn("二氧化碳", new_name)

def test_rename_images_markdown_not_found(self):
    result = self.module.obsidian_mineru_rename_images(
        "mineru/nonexistent/nonexistent.md", str(self.vault)
    )
    self.assertFalse(result["ok"])
    self.assertIn("error", result)

def test_rename_images_custom_doc_slug(self):
    md_dir, img_dir = self._make_mineru_dir("p11")
    (img_dir / "img.png").write_bytes(b"\x89PNG\r\n")
    (md_dir / "p11.md").write_text(
        "![](images/img.png)\n\n图1 结果对比\n", encoding="utf-8"
    )
    result = self.module.obsidian_mineru_rename_images(
        "mineru/p11/p11.md", str(self.vault),
        doc_slug="my-paper",
        dry_run=False,
    )
    self.assertTrue(result["renames"][0]["new"].startswith("images/my-paper_"))
```

- [ ] **Step 2: Run tests to verify they fail**

```
python -m unittest tests.test_obsidian_vault_mcp -v -k "test_rename_images"
```

Expected: FAIL — `module has no attribute 'obsidian_mineru_rename_images'`

- [ ] **Step 3: Insert `obsidian_mineru_rename_images` into `tools.py`**

Insert the following block after the closing `}` of `obsidian_mineru_extract_folder` (after the line `    }` that contains `"results": results,`, before `@tool() def obsidian_ingest_pdf_attachment`):

```python
@tool()
def obsidian_mineru_rename_images(
    markdown_path: str,
    vault_path: str = "",
    doc_slug: str = "",
    caption_window: int = 3,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Rename MinerU-extracted images using figure captions found in the Markdown.

    Scans the Markdown for image references (![alt](path) and ![[path]]), extracts
    captions via a sliding-window heuristic, and renames each image file in-place,
    updating all references in the Markdown.

    Caption extraction priority:
    1. Non-empty alt text (>3 chars)
    2. Lines AFTER image within caption_window (strong pattern, then weak)
    3. Lines BEFORE image within caption_window (strong pattern, then weak)
    4. Any line in window matching strong caption pattern
    5. Fallback: {doc_slug}_img_{N:03d}

    dry_run=True (default): return planned renames without touching any files.
    """
    vault = _vault(vault_path)
    md_full = _safe_path(vault, markdown_path)
    if not md_full.exists():
        return {"ok": False, "error": f"Markdown file not found: {markdown_path}",
                "markdownPath": markdown_path, "totalImages": 0,
                "renamed": 0, "fallback": 0, "skipped": 0,
                "errors": [], "dryRun": dry_run, "renames": []}

    content = _read_text(md_full)
    lines = content.splitlines()
    md_dir = md_full.parent

    # Auto-infer doc_slug from markdown filename stem if not provided
    effective_slug = doc_slug.strip() or _slug_filename(md_full.stem)

    # Collect all image references; deduplicate by img_path (keep first occurrence)
    all_refs = _mineru_find_images(lines)
    first_occurrence: dict[str, tuple[int, str, str, str]] = {}
    for entry in all_refs:
        line_idx, raw_ref, img_path, alt = entry
        if img_path not in first_occurrence:
            first_occurrence[img_path] = entry

    used_names: set[str] = set()
    renames: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    renamed = 0
    fallback_count = 0
    skipped = 0
    fallback_counter = 0

    # Process images in document order (by line_idx of first occurrence)
    ordered = sorted(first_occurrence.values(), key=lambda e: e[0])

    for line_idx, raw_ref, img_path, alt in ordered:
        ext = Path(img_path).suffix
        img_stem = Path(img_path).stem
        img_full = md_dir / img_path

        # Idempotency: already renamed (stem starts with doc_slug prefix)
        if img_stem.startswith(f"{effective_slug}_"):
            skipped += 1
            continue

        # For non-dry-run: check image file actually exists
        if not dry_run and not img_full.exists():
            errors.append({"path": img_path, "error": "Image file not found on disk"})
            continue

        # Caption extraction
        caption = ""
        strategy = "fallback"

        # Priority 1: alt text
        if alt.strip() and len(alt.strip()) > 3:
            caption = alt.strip()
            strategy = "alt"
        else:
            caption, strategy = _mineru_extract_caption(lines, line_idx, caption_window)

        if not caption:
            fallback_counter += 1
            new_name = f"{effective_slug}_img_{fallback_counter:03d}{ext}"
            while new_name in used_names:
                fallback_counter += 1
                new_name = f"{effective_slug}_img_{fallback_counter:03d}{ext}"
            used_names.add(new_name)
            strategy = "fallback"
            fallback_count += 1
        else:
            new_name = _mineru_caption_to_slug(caption, effective_slug, ext, used_names)
            renamed += 1

        new_img_path = str(Path(img_path).parent / new_name).replace("\\", "/")
        renames.append({
            "old": img_path,
            "new": new_img_path,
            "caption": caption,
            "strategy": strategy,
        })

    result: dict[str, Any] = {
        "ok": True,
        "markdownPath": markdown_path,
        "totalImages": len(first_occurrence),
        "renamed": renamed,
        "fallback": fallback_count,
        "skipped": skipped,
        "errors": errors,
        "dryRun": dry_run,
        "renames": renames,
    }

    if dry_run:
        return result

    # Apply renames: rename files and patch markdown text
    new_content = content
    for entry in renames:
        old_path = entry["old"]
        new_path = entry["new"]
        img_full_old = md_dir / old_path
        img_full_new = md_dir / new_path

        if not img_full_old.exists():
            errors.append({"path": old_path, "error": "Image file not found on disk"})
            result["ok"] = False
            continue

        try:
            img_full_new.parent.mkdir(parents=True, exist_ok=True)
            img_full_old.rename(img_full_new)
        except OSError as exc:
            errors.append({"path": old_path, "error": str(exc)})
            result["ok"] = False
            continue

        # Replace all occurrences in markdown (handles repeated references)
        new_content = new_content.replace(old_path, new_path)
        # Also handle bare wikilink format  ![[old_name.ext]]
        old_name = Path(old_path).name
        new_name_only = Path(new_path).name
        if old_name != new_name_only:
            new_content = new_content.replace(f"![[{old_name}]]", f"![[{new_name_only}]]")

    try:
        _write_text(md_full, new_content)
    except Exception as exc:
        result["ok"] = False
        result["error"] = f"Failed to write updated markdown: {exc}"

    result["errors"] = errors
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

```
python -m unittest tests.test_obsidian_vault_mcp -v -k "test_rename_images"
```

Expected: PASS (12 tests)

- [ ] **Step 5: Commit**

```
git add scripts/obsidian_vault_mcp/tools.py tests/test_obsidian_vault_mcp.py
git commit -m "feat: add obsidian_mineru_rename_images with caption-based slug renaming"
```

---

## Task 3: Add `rename_images` to `obsidian_mineru_extract_and_ingest`

**Files:**
- Modify: `scripts/obsidian_vault_mcp/tools.py:1376-1490`
- Test: `tests/test_obsidian_vault_mcp.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_obsidian_vault_mcp.py`:

```python
# ── rename_images integration flag ───────────────────────────────────────────

def test_extract_and_ingest_rename_flag_calls_rename(self):
    import unittest.mock as mock
    fake_extraction = {
        "ok": True,
        "markdownPath": "mineru-output/paper/paper.md",
        "returnCode": 0, "stdout": "", "stderr": "",
        "outputPath": "mineru-output/paper",
        "mode": "flash-extract", "tokenSource": "none",
        "command": [], "mineru": {"ok": True},
    }
    fake_ingest = {"ok": True, "sourcePath": "sources/mineru/paper.md"}
    fake_rename = {
        "ok": True, "markdownPath": "mineru-output/paper/paper.md",
        "totalImages": 2, "renamed": 2, "fallback": 0, "skipped": 0,
        "errors": [], "dryRun": False, "renames": [],
    }
    with mock.patch.object(
        self.module, "obsidian_mineru_extract", return_value=fake_extraction
    ), mock.patch.object(
        self.module, "obsidian_ingest_mineru_markdown", return_value=fake_ingest
    ), mock.patch.object(
        self.module, "obsidian_mineru_rename_images", return_value=fake_rename
    ) as mock_rename:
        result = self.module.obsidian_mineru_extract_and_ingest(
            "paper.pdf", str(self.vault), rename_images=True
        )
    mock_rename.assert_called_once_with(
        "mineru-output/paper/paper.md",
        vault_path=str(self.vault),
        dry_run=False,
    )
    self.assertIn("imageRename", result)
    self.assertTrue(result["imageRename"]["ok"])

def test_extract_and_ingest_rename_flag_false_does_not_call_rename(self):
    import unittest.mock as mock
    fake_extraction = {
        "ok": True,
        "markdownPath": "mineru-output/paper/paper.md",
        "returnCode": 0, "stdout": "", "stderr": "",
        "outputPath": "mineru-output/paper",
        "mode": "flash-extract", "tokenSource": "none",
        "command": [], "mineru": {"ok": True},
    }
    fake_ingest = {"ok": True, "sourcePath": "sources/mineru/paper.md"}
    with mock.patch.object(
        self.module, "obsidian_mineru_extract", return_value=fake_extraction
    ), mock.patch.object(
        self.module, "obsidian_ingest_mineru_markdown", return_value=fake_ingest
    ), mock.patch.object(
        self.module, "obsidian_mineru_rename_images"
    ) as mock_rename:
        result = self.module.obsidian_mineru_extract_and_ingest(
            "paper.pdf", str(self.vault), rename_images=False
        )
    mock_rename.assert_not_called()
    self.assertNotIn("imageRename", result)
```

- [ ] **Step 2: Run tests to verify they fail**

```
python -m unittest tests.test_obsidian_vault_mcp -v -k "test_extract_and_ingest_rename_flag"
```

Expected: FAIL — `obsidian_mineru_extract_and_ingest() got an unexpected keyword argument 'rename_images'`

- [ ] **Step 3: Modify `obsidian_mineru_extract_and_ingest` in `tools.py`**

**3a.** Add `rename_images: bool = False,` to the function signature. In `tools.py`, find the parameter list of `obsidian_mineru_extract_and_ingest` (starts at line ~1376). Add it immediately before `dry_run`:

```python
    verbose: bool = False,
    rename_images: bool = False,
    dry_run: bool = False,
```

**3b.** Add the rename block after the existing ingest result handling. Find this existing block near line ~1472:

```python
    result["ingest"] = ingest
    result["ok"] = bool(ingest.get("ok"))
```

After that block (before the `if zotero_key` block), insert:

```python
    if rename_images and result["ok"]:
        markdown_rel = str(extraction.get("markdownPath") or "")
        if markdown_rel:
            rename_result = obsidian_mineru_rename_images(
                markdown_rel,
                vault_path=str(vault),
                dry_run=False,
            )
            result["imageRename"] = rename_result
```

- [ ] **Step 4: Run tests to verify they pass**

```
python -m unittest tests.test_obsidian_vault_mcp -v -k "test_extract_and_ingest_rename_flag"
```

Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```
git add scripts/obsidian_vault_mcp/tools.py tests/test_obsidian_vault_mcp.py
git commit -m "feat: add rename_images flag to obsidian_mineru_extract_and_ingest"
```

---

## Task 4: Add `rename_images` to `obsidian_mineru_extract_folder`

**Files:**
- Modify: `scripts/obsidian_vault_mcp/tools.py:1494-1603`
- Test: `tests/test_obsidian_vault_mcp.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_obsidian_vault_mcp.py`:

```python
def test_extract_folder_rename_flag_forwarded(self):
    import unittest.mock as mock
    fake_extract = {
        "ok": True,
        "markdownPath": "mineru/paper/paper.md",
        "returnCode": 0, "stdout": "", "stderr": "",
        "outputPath": "mineru/paper",
        "mode": "flash-extract", "tokenSource": "none",
        "command": [], "mineru": {"ok": True},
    }
    fake_rename = {
        "ok": True, "markdownPath": "mineru/paper/paper.md",
        "totalImages": 1, "renamed": 1, "fallback": 0, "skipped": 0,
        "errors": [], "dryRun": False, "renames": [],
    }

    # Create a fake PDF in a temp folder so the function can enumerate it
    pdf_folder = self.vault / "pdfs"
    pdf_folder.mkdir()
    (pdf_folder / "paper.pdf").write_bytes(b"%PDF-1.4\n")

    with mock.patch.object(
        self.module, "obsidian_mineru_extract", return_value=fake_extract
    ), mock.patch.object(
        self.module, "obsidian_mineru_rename_images", return_value=fake_rename
    ) as mock_rename:
        result = self.module.obsidian_mineru_extract_folder(
            "pdfs", str(self.vault),
            ingest=False,
            rename_images=True,
            dry_run=False,
        )

    mock_rename.assert_called_once_with(
        "mineru/paper/paper.md",
        vault_path=str(self.vault),
        dry_run=False,
    )
    self.assertIn("imageRename", result["results"][0])
```

- [ ] **Step 2: Run test to verify it fails**

```
python -m unittest tests.test_obsidian_vault_mcp -v -k "test_extract_folder_rename_flag_forwarded"
```

Expected: FAIL — `obsidian_mineru_extract_folder() got an unexpected keyword argument 'rename_images'`

- [ ] **Step 3: Modify `obsidian_mineru_extract_folder` in `tools.py`**

**3a.** Add `rename_images: bool = False,` to the function signature (line ~1503). Add it immediately before `dry_run`:

```python
    ingest: bool = False,
    token: str = "",
    rename_images: bool = False,
    dry_run: bool = False,
```

**3b.** Update the docstring to document the new parameter. Find the existing docstring:

```python
    """Batch-extract all PDF files in a folder using MinerU.

    skip_extracted=true (default): skip any PDF whose output directory already contains a .md file.
    ingest=true: automatically call obsidian_ingest_mineru_markdown after each successful extraction.
    dry_run=true: enumerate PDFs and show skip/extract decisions without running MinerU.
    """
```

Replace with:

```python
    """Batch-extract all PDF files in a folder using MinerU.

    skip_extracted=true (default): skip any PDF whose output directory already contains a .md file.
    ingest=true: automatically call obsidian_ingest_mineru_markdown after each successful extraction.
    rename_images=true: call obsidian_mineru_rename_images on each successfully extracted Markdown.
    dry_run=true: enumerate PDFs and show skip/extract decisions without running MinerU.
    """
```

**3c.** In the extraction loop, find the block that appends a successful entry (around line ~1572):

```python
            if res.get("ok"):
                extracted += 1
                entry: dict[str, Any] = {
                    "input": pdf_rel,
                    "status": "extracted",
                    "outputPath": res.get("markdownPath", ""),
                }
                if ingest and res.get("markdownPath"):
                    ingest_res = obsidian_ingest_mineru_markdown(
                        markdown_path=res["markdownPath"],
                        vault_path=str(vault),
                    )
                    entry["ingested"] = ingest_res.get("ok", False)
                results.append(entry)
```

Replace with:

```python
            if res.get("ok"):
                extracted += 1
                entry: dict[str, Any] = {
                    "input": pdf_rel,
                    "status": "extracted",
                    "outputPath": res.get("markdownPath", ""),
                }
                if ingest and res.get("markdownPath"):
                    ingest_res = obsidian_ingest_mineru_markdown(
                        markdown_path=res["markdownPath"],
                        vault_path=str(vault),
                    )
                    entry["ingested"] = ingest_res.get("ok", False)
                if rename_images and res.get("markdownPath"):
                    rename_res = obsidian_mineru_rename_images(
                        res["markdownPath"],
                        vault_path=str(vault),
                        dry_run=False,
                    )
                    entry["imageRename"] = rename_res
                results.append(entry)
```

- [ ] **Step 4: Run test to verify it passes**

```
python -m unittest tests.test_obsidian_vault_mcp -v -k "test_extract_folder_rename_flag_forwarded"
```

Expected: PASS (1 test)

- [ ] **Step 5: Run the full test suite to ensure no regressions**

```
python -m unittest tests.test_obsidian_vault_mcp -v
```

Expected: all tests PASS

- [ ] **Step 6: Run linter**

```
python -m ruff check scripts/obsidian_vault_mcp/helpers.py scripts/obsidian_vault_mcp/tools.py
```

Expected: no errors

- [ ] **Step 7: Commit**

```
git add scripts/obsidian_vault_mcp/tools.py tests/test_obsidian_vault_mcp.py
git commit -m "feat: add rename_images flag to obsidian_mineru_extract_folder"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task |
|------------------|------|
| New `obsidian_mineru_rename_images` tool | Task 2 ✓ |
| Alt text priority 1 | Task 2, test `test_rename_images_uses_alt_text` ✓ |
| Caption-after priority 2 | Task 2, test `test_rename_images_caption_after` ✓ |
| Caption-before priority 3 | Task 2, test `test_rename_images_caption_before` ✓ |
| Fallback positional naming | Task 2, test `test_rename_images_fallback_positional` ✓ |
| dry_run=True default | Task 2, test `test_rename_images_dry_run_no_write` ✓ |
| Update all markdown references | Task 2, test `test_rename_images_updates_markdown_references` ✓ |
| Dedup conflict handling | Task 2, test `test_rename_images_dedup_conflict` ✓ |
| Idempotency skip | Task 2, test `test_rename_images_idempotent_skip` ✓ |
| Missing image file → errors list | Task 2, test `test_rename_images_missing_file_recorded_in_errors` ✓ |
| Chinese characters preserved | Task 2, test `test_rename_images_chinese_caption_kept` ✓ |
| `_mineru_find_images` helper | Task 1, tested indirectly through Task 2 ✓ |
| `_mineru_extract_caption` helper | Task 1, tested indirectly through Task 2 ✓ |
| `_mineru_caption_to_slug` helper | Task 1, tested indirectly through Task 2 ✓ |
| `rename_images` on `extract_and_ingest` | Task 3 ✓ |
| `rename_images` on `extract_folder` | Task 4 ✓ |
| Obsidian wikilink format support | Task 1 (`_MINERU_WIKI_IMAGE_RE`) ✓ |
| In-place rename (not move to new folder) | Task 2 (`md_dir / img_path`) ✓ |

**Placeholder scan:** No TBD, TODO, "similar to", or vague steps found.

**Type consistency check:**
- `_mineru_find_images` returns `list[tuple[int, str, str, str]]` — matches usage in Task 2 `for line_idx, raw_ref, img_path, alt in ordered` ✓
- `_mineru_extract_caption` returns `tuple[str, str]` — matches `caption, strategy = _mineru_extract_caption(...)` ✓
- `_mineru_caption_to_slug` takes `(caption: str, doc_slug: str, ext: str, used: set[str])` — matches call in Task 2 ✓
- `obsidian_mineru_rename_images` called in Task 3 as `obsidian_mineru_rename_images(markdown_rel, vault_path=..., dry_run=False)` — matches signature ✓
- `obsidian_mineru_rename_images` called in Task 4 as `obsidian_mineru_rename_images(res["markdownPath"], vault_path=..., dry_run=False)` — matches ✓
