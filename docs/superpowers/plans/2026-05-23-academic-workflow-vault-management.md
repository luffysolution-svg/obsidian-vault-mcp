# Academic Workflow & Vault Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add structured Zotero annotation rendering (foldable callouts with color emojis, sorted by page) and three new vault file-management tools (delete, move, rename) plus regex search support.

**Architecture:** All tool functions live in `scripts/obsidian_vault_mcp/tools.py`; pure helper functions go in `scripts/obsidian_vault_mcp/helpers.py`. Color label resolution layers vault config over Ethereal Style prefs over built-in English names. File operations use `shutil`/`pathlib` only — no Obsidian CLI dependency. Every task follows TDD: write failing test → implement → confirm pass → commit.

**Tech Stack:** Python 3.11+, stdlib only (`re`, `shutil`, `pathlib`, `json`). Test runner: `pytest` via `python -m pytest tests/ -v`.

---

## File Map

| File | What changes |
|---|---|
| `scripts/obsidian_vault_mcp/helpers.py` | Add `_ANNOTATION_COLOR_EMOJIS`, `_annotation_emoji()`, `_resolve_annotation_color_labels()`, `_zotero_annotations_structured()`, `_rewrite_wikilinks()` |
| `scripts/obsidian_vault_mcp/tools.py` | Add `annotations_mode`+`color_labels_json` to `obsidian_ingest_zotero_item` and `obsidian_ingest_zotero_collection`; add `obsidian_delete_file`, `obsidian_move_file`, `obsidian_rename_file`; add `use_regex` to `obsidian_search` |
| `tests/test_obsidian_vault_mcp.py` | New test methods in `ObsidianVaultMcpTests` |

---

## Task 1: Color emoji map + `_annotation_emoji` + `_resolve_annotation_color_labels`

**Files:**
- Modify: `scripts/obsidian_vault_mcp/helpers.py` (after line 1314, after `_ANNOTATION_COLOR_NAMES`)

- [ ] **Step 1: Write the failing tests**

Add these two methods to `ObsidianVaultMcpTests` in `tests/test_obsidian_vault_mcp.py`:

```python
def test_annotation_emoji_returns_correct_emoji_for_known_colors(self):
    m = self.module._tools  # access helpers via tools module
    self.assertEqual(m._annotation_emoji("#ffd400"), "🟡")
    self.assertEqual(m._annotation_emoji("#ff6666"), "🔴")
    self.assertEqual(m._annotation_emoji("#5fb236"), "🟢")
    self.assertEqual(m._annotation_emoji("#2ea8e5"), "🔵")
    self.assertEqual(m._annotation_emoji("#a28ae5"), "🟣")
    self.assertEqual(m._annotation_emoji("#e56eee"), "🩷")
    self.assertEqual(m._annotation_emoji("#f19837"), "🟠")
    self.assertEqual(m._annotation_emoji("#aaaaaa"), "⬜")
    self.assertEqual(m._annotation_emoji(None), "📝")
    self.assertEqual(m._annotation_emoji(""), "📝")

def test_resolve_annotation_color_labels_layers_sources(self):
    # vault config overrides built-in
    config_path = self.vault / ".obsidian" / "obsidian-vault-mcp.json"
    config_path.write_text(
        '{"annotationColorLabels": {"#ffd400": "背景", "#ff6666": "理论"}}',
        encoding="utf-8",
    )
    m = self.module._tools
    labels = m._resolve_annotation_color_labels(self.vault, "{}")
    self.assertEqual(labels["#ffd400"], "背景")
    self.assertEqual(labels["#ff6666"], "理论")
    # per-call JSON overrides vault config
    labels2 = m._resolve_annotation_color_labels(
        self.vault, '{"#ffd400": "context"}'
    )
    self.assertEqual(labels2["#ffd400"], "context")
    self.assertEqual(labels2["#ff6666"], "理论")  # vault config still applies
```

- [ ] **Step 2: Run tests to verify they fail**

```
python -m pytest tests/test_obsidian_vault_mcp.py::ObsidianVaultMcpTests::test_annotation_emoji_returns_correct_emoji_for_known_colors tests/test_obsidian_vault_mcp.py::ObsidianVaultMcpTests::test_resolve_annotation_color_labels_layers_sources -v
```

Expected: FAIL with `AttributeError: module has no attribute '_annotation_emoji'`

- [ ] **Step 3: Implement in helpers.py**

Find the line `_ANNOTATION_COLOR_NAMES: dict[str, str] = {` (around line 1305). After the closing `}` of that dict (line 1314), insert:

```python
_ANNOTATION_COLOR_EMOJIS: dict[str, str] = {
    "#ffd400": "🟡",
    "#ff6666": "🔴",
    "#5fb236": "🟢",
    "#2ea8e5": "🔵",
    "#a28ae5": "🟣",
    "#e56eee": "🩷",
    "#f19837": "🟠",
    "#aaaaaa": "⬜",
}


def _annotation_emoji(color: str | None) -> str:
    if not color:
        return "📝"
    key = color.lower()
    if key in _ANNOTATION_COLOR_EMOJIS:
        return _ANNOTATION_COLOR_EMOJIS[key]
    nearest_emoji, nearest_dist = min(
        ((emoji, _color_distance(key, hex_c)) for hex_c, emoji in _ANNOTATION_COLOR_EMOJIS.items()),
        key=lambda x: x[1],
    )
    return nearest_emoji if nearest_dist <= 20 else "📝"


def _resolve_annotation_color_labels(vault: Path, color_labels_json: str) -> dict[str, str]:
    labels: dict[str, str] = dict(_ANNOTATION_COLOR_NAMES)
    labels.update(_load_ethereal_color_labels())
    vault_cfg = _vault_config(vault).get("annotationColorLabels", {})
    if isinstance(vault_cfg, dict):
        labels.update({k.lower(): str(v) for k, v in vault_cfg.items()})
    if color_labels_json and color_labels_json.strip() not in ("{}", ""):
        try:
            param_labels = json.loads(color_labels_json)
            if isinstance(param_labels, dict):
                labels.update({k.lower(): str(v) for k, v in param_labels.items()})
        except json.JSONDecodeError:
            pass
    return labels
```

- [ ] **Step 4: Run tests to verify they pass**

```
python -m pytest tests/test_obsidian_vault_mcp.py::ObsidianVaultMcpTests::test_annotation_emoji_returns_correct_emoji_for_known_colors tests/test_obsidian_vault_mcp.py::ObsidianVaultMcpTests::test_resolve_annotation_color_labels_layers_sources -v
```

Expected: 2 passed

- [ ] **Step 5: Run full suite to check no regressions**

```
python -m pytest tests/ -v
```

Expected: all previous tests still pass

- [ ] **Step 6: Commit**

```bash
git add scripts/obsidian_vault_mcp/helpers.py tests/test_obsidian_vault_mcp.py
git commit -m "feat: add annotation color emoji map and label resolution helpers"
```

---

## Task 2: `_zotero_annotations_structured` renderer

**Files:**
- Modify: `scripts/obsidian_vault_mcp/helpers.py` (after `_zotero_notes_and_annotations`, around line 1468)

- [ ] **Step 1: Write the failing test**

Add to `ObsidianVaultMcpTests`:

```python
def test_zotero_annotations_structured_format(self):
    m = self.module._tools
    children = {
        "notes": [],
        "annotations": [
            {
                "annotationType": "highlight",
                "annotationColor": "#ffd400",
                "annotationText": "Deep learning changed everything.",
                "annotationComment": "Core thesis",
                "annotationPageLabel": "3",
            },
            {
                "annotationType": "highlight",
                "annotationColor": "#e56eee",
                "annotationText": "Our method outperforms baseline.",
                "annotationComment": "",
                "annotationPageLabel": "12",
            },
            {
                "annotationType": "note",
                "annotationColor": None,
                "annotationText": "",
                "annotationComment": "Check this later",
                "annotationPageLabel": "7",
            },
        ],
    }
    color_labels = {"#ffd400": "背景", "#e56eee": "结论"}
    result = m._zotero_annotations_structured(children, color_labels)

    # p.3 highlight with comment
    self.assertIn("> [!quote]+ 🟡 背景 — p.3", result)
    self.assertIn("> Deep learning changed everything.", result)
    self.assertIn("> *Core thesis*", result)

    # p.7 note (no highlight text) — should appear between p.3 and p.12
    self.assertIn("> [!note]+ 📝 — p.7", result)
    self.assertIn("> Check this later", result)

    # p.12 highlight without comment
    self.assertIn("> [!quote]+ 🩷 结论 — p.12", result)

    # sorted: p.3 appears before p.7 which appears before p.12
    self.assertLess(result.index("p.3"), result.index("p.7"))
    self.assertLess(result.index("p.7"), result.index("p.12"))
```

- [ ] **Step 2: Run test to verify it fails**

```
python -m pytest tests/test_obsidian_vault_mcp.py::ObsidianVaultMcpTests::test_zotero_annotations_structured_format -v
```

Expected: FAIL with `AttributeError: module has no attribute '_zotero_annotations_structured'`

- [ ] **Step 3: Implement in helpers.py**

Add after `_zotero_notes_and_annotations` (after its closing `return` statement, around line 1468):

```python
def _zotero_annotations_structured(
    children: dict[str, list[dict[str, Any]]],
    color_labels: dict[str, str],
) -> str:
    """Render annotations as foldable callouts sorted by page, with color emoji and semantic labels."""
    lines: list[str] = []
    notes = children.get("notes", [])
    annotations = children.get("annotations", [])

    if notes:
        lines.extend(["## Zotero Notes", ""])
        for note in notes:
            lines.extend([f"### Note {note.get('key')}", "", str(note.get("note") or "").strip(), ""])

    if annotations:
        lines.extend(["## Annotations", ""])

        def _page_sort_key(ann: dict[str, Any]) -> tuple[int, Any]:
            page = str(ann.get("annotationPageLabel") or "")
            try:
                return (0, int(page))
            except ValueError:
                return (1, page)

        for annotation in sorted(annotations, key=_page_sort_key):
            text = str(annotation.get("annotationText") or "").strip()
            comment = str(annotation.get("annotationComment") or "").strip()
            ann_type = str(annotation.get("annotationType") or "highlight")
            page = str(annotation.get("annotationPageLabel") or "").strip()
            color = annotation.get("annotationColor")

            emoji = _annotation_emoji(color)
            label = ""
            if color:
                key = color.lower()
                if key in color_labels:
                    label = color_labels[key]
                elif color_labels:
                    nearest = min(
                        ((lbl, _color_distance(key, cfg)) for cfg, lbl in color_labels.items()),
                        key=lambda x: x[1],
                    )
                    if nearest[1] <= 20:
                        label = nearest[0]

            header_parts = [emoji]
            if label:
                header_parts.append(label)
            if page:
                header_parts.append(f"— p.{page}")
            header = " ".join(header_parts)

            if ann_type == "note" and not text:
                if comment:
                    lines.append(f"> [!note]+ {header}")
                    lines.append(f"> {comment}")
                    lines.append("")
            else:
                if text:
                    lines.append(f"> [!quote]+ {header}")
                    lines.append(f"> {text}")
                    if comment:
                        lines.append("> ")
                        lines.append(f"> *{comment}*")
                    lines.append("")
                elif comment:
                    lines.append(f"> [!note]+ {header}")
                    lines.append(f"> {comment}")
                    lines.append("")

    return "\n".join(lines).strip()
```

- [ ] **Step 4: Run test to verify it passes**

```
python -m pytest tests/test_obsidian_vault_mcp.py::ObsidianVaultMcpTests::test_zotero_annotations_structured_format -v
```

Expected: 1 passed

- [ ] **Step 5: Run full suite**

```
python -m pytest tests/ -v
```

Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add scripts/obsidian_vault_mcp/helpers.py tests/test_obsidian_vault_mcp.py
git commit -m "feat: add _zotero_annotations_structured renderer"
```

---

## Task 3: Wire `annotations_mode` into `obsidian_ingest_zotero_item`

**Files:**
- Modify: `scripts/obsidian_vault_mcp/tools.py` (`obsidian_ingest_zotero_item` function, around line 1309)

- [ ] **Step 1: Write the failing test**

Add to `ObsidianVaultMcpTests`:

```python
def test_ingest_zotero_item_structured_annotations(self):
    def fake_api(path, params=None, api_base=""):
        if path == "users/0/items/ANN1":
            return {
                "key": "ANN1",
                "data": {
                    "key": "ANN1",
                    "itemType": "journalArticle",
                    "title": "Annotation Test Paper",
                    "creators": [{"lastName": "Smith"}],
                    "date": "2025",
                },
            }
        if path == "users/0/items/ANN1/children":
            return [
                {
                    "key": "A1",
                    "data": {
                        "key": "A1",
                        "itemType": "annotation",
                        "annotationType": "highlight",
                        "annotationColor": "#ffd400",
                        "annotationText": "Key finding here.",
                        "annotationComment": "Important",
                        "annotationPageLabel": "5",
                    },
                }
            ]
        return []

    original = self.module._tools._zotero_api
    self.module._tools._zotero_api = fake_api
    try:
        result = self.module.obsidian_ingest_zotero_item(
            "ANN1",
            str(self.vault),
            overwrite=True,
            annotations_mode="structured",
            color_labels_json='{"#ffd400": "背景"}',
        )
    finally:
        self.module._tools._zotero_api = original

    self.assertTrue(result["ok"])
    note_path = self.vault / "literature" / "Smith (2025) - Annotation Test Paper.md"
    note = note_path.read_text(encoding="utf-8")
    self.assertIn("> [!quote]+ 🟡 背景 — p.5", note)
    self.assertIn("> Key finding here.", note)
    self.assertIn("> *Important*", note)

def test_ingest_zotero_item_flat_mode_unchanged(self):
    """flat mode (default) must not produce the new foldable format."""
    def fake_api(path, params=None, api_base=""):
        if path == "users/0/items/FLAT1":
            return {"key": "FLAT1", "data": {"key": "FLAT1", "itemType": "journalArticle", "title": "Flat Paper", "creators": [{"lastName": "Doe"}], "date": "2025"}}
        if path == "users/0/items/FLAT1/children":
            return [{"key": "A1", "data": {"key": "A1", "itemType": "annotation", "annotationType": "highlight", "annotationColor": "#ffd400", "annotationText": "Some text.", "annotationComment": "", "annotationPageLabel": "2"}}]
        return []

    original = self.module._tools._zotero_api
    self.module._tools._zotero_api = fake_api
    try:
        result = self.module.obsidian_ingest_zotero_item("FLAT1", str(self.vault), overwrite=True)
    finally:
        self.module._tools._zotero_api = original

    self.assertTrue(result["ok"])
    note = (self.vault / "literature" / "Doe (2025) - Flat Paper.md").read_text(encoding="utf-8")
    # flat mode uses existing format (no + foldable)
    self.assertNotIn("[!quote]+", note)
```

- [ ] **Step 2: Run tests to verify they fail**

```
python -m pytest tests/test_obsidian_vault_mcp.py::ObsidianVaultMcpTests::test_ingest_zotero_item_structured_annotations tests/test_obsidian_vault_mcp.py::ObsidianVaultMcpTests::test_ingest_zotero_item_flat_mode_unchanged -v
```

Expected: FAIL (TypeError: unexpected keyword argument `annotations_mode`)

- [ ] **Step 3: Add parameters and branch in tools.py**

In `obsidian_ingest_zotero_item`, add two parameters after `include_annotations: bool = True`:

```python
annotations_mode: str = "flat",
color_labels_json: str = "{}",
```

Then find the block starting at `notes_content = _zotero_notes_and_annotations(` (around line 1401) and replace it:

```python
_ann_children = {
    "notes": children.get("notes", []) if include_child_notes else [],
    "annotations": children.get("annotations", []) if include_annotations else [],
}
if annotations_mode == "structured":
    _color_labels = _resolve_annotation_color_labels(vault, color_labels_json)
    notes_content = _zotero_annotations_structured(_ann_children, _color_labels)
else:
    notes_content = _zotero_notes_and_annotations(_ann_children)
```

- [ ] **Step 4: Run tests to verify they pass**

```
python -m pytest tests/test_obsidian_vault_mcp.py::ObsidianVaultMcpTests::test_ingest_zotero_item_structured_annotations tests/test_obsidian_vault_mcp.py::ObsidianVaultMcpTests::test_ingest_zotero_item_flat_mode_unchanged -v
```

Expected: 2 passed

- [ ] **Step 5: Run full suite**

```
python -m pytest tests/ -v
```

Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add scripts/obsidian_vault_mcp/tools.py tests/test_obsidian_vault_mcp.py
git commit -m "feat: add annotations_mode param to obsidian_ingest_zotero_item"
```

---

## Task 4: Forward `annotations_mode` in `obsidian_ingest_zotero_collection`

**Files:**
- Modify: `scripts/obsidian_vault_mcp/tools.py` (`obsidian_ingest_zotero_collection`, around line 1545)

- [ ] **Step 1: Write the failing test**

Add to `ObsidianVaultMcpTests`:

```python
def test_ingest_zotero_collection_forwards_annotations_mode(self):
    """annotations_mode and color_labels_json must reach obsidian_ingest_zotero_item."""
    calls = []
    original_item = self.module._tools.obsidian_ingest_zotero_item

    def fake_ingest_item(key, **kwargs):
        calls.append(kwargs.get("annotations_mode"))
        return {"ok": True, "upToDate": False, "duplicate": False, "changed": False}

    def fake_api(path, params=None, api_base=""):
        if path == "users/0/collections/COL1/items/top":
            return [{"key": "K1", "data": {"key": "K1", "itemType": "journalArticle"}}]
        return []

    orig_api = self.module._tools._zotero_api
    self.module._tools._zotero_api = fake_api
    self.module._tools.obsidian_ingest_zotero_item = fake_ingest_item
    try:
        self.module.obsidian_ingest_zotero_collection(
            collection_key="COL1",
            vault_path=str(self.vault),
            annotations_mode="structured",
        )
    finally:
        self.module._tools._zotero_api = orig_api
        self.module._tools.obsidian_ingest_zotero_item = original_item

    self.assertEqual(calls, ["structured"])
```

- [ ] **Step 2: Run test to verify it fails**

```
python -m pytest tests/test_obsidian_vault_mcp.py::ObsidianVaultMcpTests::test_ingest_zotero_collection_forwards_annotations_mode -v
```

Expected: FAIL (TypeError: unexpected keyword argument `annotations_mode`)

- [ ] **Step 3: Add parameters and forward in tools.py**

In `obsidian_ingest_zotero_collection`, add after `include_annotations: bool = True`:

```python
annotations_mode: str = "flat",
color_labels_json: str = "{}",
```

Then in the `obsidian_ingest_zotero_item(...)` call inside the loop, add:

```python
annotations_mode=annotations_mode,
color_labels_json=color_labels_json,
```

- [ ] **Step 4: Run tests to verify they pass**

```
python -m pytest tests/test_obsidian_vault_mcp.py::ObsidianVaultMcpTests::test_ingest_zotero_collection_forwards_annotations_mode -v
```

Expected: 1 passed

- [ ] **Step 5: Run full suite**

```
python -m pytest tests/ -v
```

Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add scripts/obsidian_vault_mcp/tools.py tests/test_obsidian_vault_mcp.py
git commit -m "feat: forward annotations_mode to obsidian_ingest_zotero_collection"
```

---

## Task 5: `obsidian_delete_file`

**Files:**
- Modify: `scripts/obsidian_vault_mcp/tools.py` (add new tool after `obsidian_write_file`, around line 132)

- [ ] **Step 1: Write the failing tests**

Add to `ObsidianVaultMcpTests`:

```python
def test_delete_file_creates_backup_and_removes_file(self):
    self.write_note("to_delete.md", "# Delete me\n")

    result = self.module.obsidian_delete_file("to_delete.md", str(self.vault))

    self.assertTrue(result["ok"])
    self.assertFalse(result["dryRun"])
    self.assertFalse((self.vault / "to_delete.md").exists())
    self.assertTrue(result["backup"])
    backup_path = self.vault / result["backup"]
    self.assertTrue(backup_path.exists())
    self.assertEqual(backup_path.read_text(encoding="utf-8"), "# Delete me\n")

def test_delete_file_dry_run_does_not_delete(self):
    self.write_note("keep.md", "# Keep me\n")

    result = self.module.obsidian_delete_file("keep.md", str(self.vault), dry_run=True)

    self.assertTrue(result["ok"])
    self.assertTrue(result["dryRun"])
    self.assertTrue((self.vault / "keep.md").exists())

def test_delete_file_no_backup_option(self):
    self.write_note("no_backup.md", "content\n")

    result = self.module.obsidian_delete_file("no_backup.md", str(self.vault), backup=False)

    self.assertTrue(result["ok"])
    self.assertFalse((self.vault / "no_backup.md").exists())
    self.assertEqual(result["backup"], "")

def test_delete_file_missing_returns_error(self):
    result = self.module.obsidian_delete_file("ghost.md", str(self.vault))
    self.assertFalse(result["ok"])
    self.assertIn("error", result)
```

- [ ] **Step 2: Run tests to verify they fail**

```
python -m pytest tests/test_obsidian_vault_mcp.py::ObsidianVaultMcpTests::test_delete_file_creates_backup_and_removes_file tests/test_obsidian_vault_mcp.py::ObsidianVaultMcpTests::test_delete_file_dry_run_does_not_delete tests/test_obsidian_vault_mcp.py::ObsidianVaultMcpTests::test_delete_file_no_backup_option tests/test_obsidian_vault_mcp.py::ObsidianVaultMcpTests::test_delete_file_missing_returns_error -v
```

Expected: FAIL with `AttributeError: module has no attribute 'obsidian_delete_file'`

- [ ] **Step 3: Implement in tools.py**

Add after `obsidian_write_file` (after its closing `return` line, around line 132):

```python
@tool()
def obsidian_delete_file(
    path: str,
    vault_path: str = "",
    backup: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Delete a vault-relative file, optionally backing it up to .obsidian-vault-backups/ first."""
    vault = _vault(vault_path)
    full = _safe_path(vault, path)
    rel = _rel(vault, full)
    if not full.exists():
        return {"ok": False, "path": rel, "error": "File does not exist."}
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_rel = f"{BACKUP_DIR}/manual/{timestamp}/{rel}" if backup else ""
    if dry_run:
        return {"ok": True, "path": rel, "backup": backup_rel, "dryRun": True}
    if backup:
        backup_full = vault / backup_rel
        backup_full.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(full, backup_full)
    full.unlink()
    return {"ok": True, "path": rel, "backup": backup_rel, "dryRun": False}
```

Note: `datetime`, `timezone`, `BACKUP_DIR`, and `shutil` are already available in the module namespace via the helpers import chain.

- [ ] **Step 4: Run tests to verify they pass**

```
python -m pytest tests/test_obsidian_vault_mcp.py::ObsidianVaultMcpTests::test_delete_file_creates_backup_and_removes_file tests/test_obsidian_vault_mcp.py::ObsidianVaultMcpTests::test_delete_file_dry_run_does_not_delete tests/test_obsidian_vault_mcp.py::ObsidianVaultMcpTests::test_delete_file_no_backup_option tests/test_obsidian_vault_mcp.py::ObsidianVaultMcpTests::test_delete_file_missing_returns_error -v
```

Expected: 4 passed

- [ ] **Step 5: Run full suite**

```
python -m pytest tests/ -v
```

Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add scripts/obsidian_vault_mcp/tools.py tests/test_obsidian_vault_mcp.py
git commit -m "feat: add obsidian_delete_file with optional backup"
```

---

## Task 6: `_rewrite_wikilinks` + `obsidian_move_file` + `obsidian_rename_file`

**Files:**
- Modify: `scripts/obsidian_vault_mcp/helpers.py` (add `_rewrite_wikilinks` after `_collect_markdown`, around line 534)
- Modify: `scripts/obsidian_vault_mcp/tools.py` (add two new tools after `obsidian_delete_file`)

- [ ] **Step 1: Write the failing tests**

Add to `ObsidianVaultMcpTests`:

```python
def test_move_file_relocates_file(self):
    self.write_note("notes/paper.md", "# Paper\n")

    result = self.module.obsidian_move_file("notes/paper.md", "archive", str(self.vault))

    self.assertTrue(result["ok"])
    self.assertFalse((self.vault / "notes" / "paper.md").exists())
    self.assertTrue((self.vault / "archive" / "paper.md").exists())
    self.assertEqual(result["from"], "notes/paper.md")
    self.assertEqual(result["to"], "archive/paper.md")

def test_move_file_dry_run(self):
    self.write_note("notes/dry.md", "content\n")

    result = self.module.obsidian_move_file("notes/dry.md", "archive", str(self.vault), dry_run=True)

    self.assertTrue(result["ok"])
    self.assertTrue(result["dryRun"])
    self.assertTrue((self.vault / "notes" / "dry.md").exists())
    self.assertFalse((self.vault / "archive" / "dry.md").exists())

def test_move_file_updates_wikilinks(self):
    self.write_note("notes/moved.md", "# Moved\n")
    self.write_note("ref.md", "---\ntitle: Ref\n---\n\nSee [[moved]] and [[notes/moved]].\n")

    result = self.module.obsidian_move_file(
        "notes/moved.md", "archive", str(self.vault), update_wikilinks=True
    )

    self.assertTrue(result["ok"])
    self.assertGreater(result["replacementCount"], 0)
    ref = (self.vault / "ref.md").read_text(encoding="utf-8")
    self.assertIn("[[archive/moved]]", ref)
    self.assertNotIn("[[notes/moved]]", ref)

def test_rename_file_renames_in_place(self):
    self.write_note("notes/old_name.md", "# Old\n")

    result = self.module.obsidian_rename_file("notes/old_name.md", "new_name.md", str(self.vault))

    self.assertTrue(result["ok"])
    self.assertFalse((self.vault / "notes" / "old_name.md").exists())
    self.assertTrue((self.vault / "notes" / "new_name.md").exists())
    self.assertEqual(result["from"], "notes/old_name.md")
    self.assertEqual(result["to"], "notes/new_name.md")

def test_rename_file_updates_wikilinks(self):
    self.write_note("docs/alpha.md", "# Alpha\n")
    self.write_note("index.md", "---\ntitle: Index\n---\n\nSee [[alpha]] and [[docs/alpha]].\n")

    result = self.module.obsidian_rename_file(
        "docs/alpha.md", "beta.md", str(self.vault), update_wikilinks=True
    )

    self.assertTrue(result["ok"])
    self.assertGreater(result["replacementCount"], 0)
    index = (self.vault / "index.md").read_text(encoding="utf-8")
    self.assertIn("[[beta]]", index)
    self.assertNotIn("[[alpha]]", index)
```

- [ ] **Step 2: Run tests to verify they fail**

```
python -m pytest tests/test_obsidian_vault_mcp.py::ObsidianVaultMcpTests::test_move_file_relocates_file tests/test_obsidian_vault_mcp.py::ObsidianVaultMcpTests::test_rename_file_renames_in_place -v
```

Expected: FAIL with `AttributeError: module has no attribute 'obsidian_move_file'`

- [ ] **Step 3: Add `_rewrite_wikilinks` to helpers.py**

Find `def _collect_markdown(vault: Path)` (line 534). Add after its function body:

```python
def _rewrite_wikilinks(vault: Path, old_rel: str, new_rel: str) -> dict[str, Any]:
    """Rewrite [[wikilinks]] across all .md files after a file move or rename."""
    old_stem = Path(old_rel).stem
    new_stem = Path(new_rel).stem
    old_no_ext = re.sub(r"\.md$", "", old_rel)
    new_no_ext = re.sub(r"\.md$", "", new_rel)

    patterns: list[tuple[re.Pattern[str], str]] = [
        (re.compile(rf"\[\[{re.escape(old_no_ext)}\]\]"), f"[[{new_no_ext}]]"),
        (re.compile(rf"\[\[{re.escape(old_no_ext)}\|([^\]]+)\]\]"), rf"[[{new_no_ext}|\1]]"),
    ]
    if old_stem != old_no_ext:
        patterns.extend([
            (re.compile(rf"\[\[{re.escape(old_stem)}\]\]"), f"[[{new_stem}]]"),
            (re.compile(rf"\[\[{re.escape(old_stem)}\|([^\]]+)\]\]"), rf"[[{new_stem}|\1]]"),
        ])

    updated_files: list[str] = []
    total_count = 0
    for md_path in _collect_markdown(vault):
        rel = _rel(vault, md_path)
        if rel == old_rel:
            continue
        text = _read_text(md_path)
        new_text = text
        count = 0
        for pattern, replacement in patterns:
            new_text, n = pattern.subn(replacement, new_text)
            count += n
        if count > 0:
            _write_text(md_path, new_text)
            updated_files.append(rel)
            total_count += count
    return {"files": updated_files, "count": total_count}
```

- [ ] **Step 4: Add `obsidian_move_file` and `obsidian_rename_file` to tools.py**

Add after `obsidian_delete_file`:

```python
@tool()
def obsidian_move_file(
    path: str,
    to: str,
    vault_path: str = "",
    update_wikilinks: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Move a vault-relative file to a different directory. Pass update_wikilinks=true to rewrite [[links]] across the vault."""
    vault = _vault(vault_path)
    src_full = _safe_path(vault, path)
    src_rel = _rel(vault, src_full)
    if not src_full.exists():
        return {"ok": False, "path": src_rel, "error": "File does not exist."}
    to_dir = _safe_path(vault, to)
    dest_full = to_dir / src_full.name
    dest_rel = (Path(to.strip("/")) / src_full.name).as_posix()
    if not dry_run and dest_full.exists():
        return {"ok": False, "path": src_rel, "error": f"Destination already exists: {dest_rel}"}
    if dry_run:
        return {"ok": True, "from": src_rel, "to": dest_rel, "dryRun": True}
    dest_full.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src_full), str(dest_full))
    result: dict[str, Any] = {"ok": True, "from": src_rel, "to": dest_rel, "dryRun": False}
    if update_wikilinks:
        rewrites = _rewrite_wikilinks(vault, src_rel, dest_rel)
        result["updatedFiles"] = rewrites["files"]
        result["replacementCount"] = rewrites["count"]
    return result


@tool()
def obsidian_rename_file(
    path: str,
    name: str,
    vault_path: str = "",
    update_wikilinks: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Rename a vault-relative file in place. Pass update_wikilinks=true to rewrite [[links]] across the vault."""
    vault = _vault(vault_path)
    src_full = _safe_path(vault, path)
    src_rel = _rel(vault, src_full)
    if not src_full.exists():
        return {"ok": False, "path": src_rel, "error": "File does not exist."}
    if "/" in name or "\\" in name:
        return {"ok": False, "path": src_rel, "error": "name must be a filename only, not a path. Use obsidian_move_file to change directories."}
    dest_full = src_full.parent / name
    dest_rel = _rel(vault, dest_full)
    if not dry_run and dest_full.exists():
        return {"ok": False, "path": src_rel, "error": f"Destination already exists: {dest_rel}"}
    if dry_run:
        return {"ok": True, "from": src_rel, "to": dest_rel, "dryRun": True}
    src_full.rename(dest_full)
    result: dict[str, Any] = {"ok": True, "from": src_rel, "to": dest_rel, "dryRun": False}
    if update_wikilinks:
        rewrites = _rewrite_wikilinks(vault, src_rel, dest_rel)
        result["updatedFiles"] = rewrites["files"]
        result["replacementCount"] = rewrites["count"]
    return result
```

- [ ] **Step 5: Run all new tests to verify they pass**

```
python -m pytest tests/test_obsidian_vault_mcp.py::ObsidianVaultMcpTests::test_move_file_relocates_file tests/test_obsidian_vault_mcp.py::ObsidianVaultMcpTests::test_move_file_dry_run tests/test_obsidian_vault_mcp.py::ObsidianVaultMcpTests::test_move_file_updates_wikilinks tests/test_obsidian_vault_mcp.py::ObsidianVaultMcpTests::test_rename_file_renames_in_place tests/test_obsidian_vault_mcp.py::ObsidianVaultMcpTests::test_rename_file_updates_wikilinks -v
```

Expected: 5 passed

- [ ] **Step 6: Run full suite**

```
python -m pytest tests/ -v
```

Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add scripts/obsidian_vault_mcp/helpers.py scripts/obsidian_vault_mcp/tools.py tests/test_obsidian_vault_mcp.py
git commit -m "feat: add obsidian_move_file, obsidian_rename_file with optional wikilink rewriting"
```

---

## Task 7: `obsidian_search` regex support

**Files:**
- Modify: `scripts/obsidian_vault_mcp/tools.py` (`obsidian_search`, lines 56–87)

- [ ] **Step 1: Write the failing tests**

Add to `ObsidianVaultMcpTests`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```
python -m pytest tests/test_obsidian_vault_mcp.py::ObsidianVaultMcpTests::test_search_regex_matches_pattern tests/test_obsidian_vault_mcp.py::ObsidianVaultMcpTests::test_search_regex_invalid_pattern_returns_error -v
```

Expected: FAIL (TypeError: unexpected keyword argument `use_regex`)

- [ ] **Step 3: Implement in tools.py**

Replace the entire `obsidian_search` function (lines 56–87) with:

```python
@tool()
def obsidian_search(
    query: str,
    vault_path: str = "",
    folder: str = "",
    extensions: str = ".md",
    case_sensitive: bool = False,
    use_regex: bool = False,
    limit: int = 50,
    context_chars: int = 140,
) -> list[dict[str, Any]]:
    """Search text files in a vault and return matching line snippets. Set use_regex=true for regular expression matching."""
    vault = _vault(vault_path)
    wanted = _extension_set(extensions)
    compiled: re.Pattern[str] | None = None
    needle: str = ""
    if use_regex:
        try:
            flags = 0 if case_sensitive else re.IGNORECASE
            compiled = re.compile(query, flags)
        except re.error as exc:
            return [{"error": f"Invalid regex: {exc}"}]
    else:
        needle = query if case_sensitive else query.lower()
    matches: list[dict[str, Any]] = []
    for path in _iter_files(vault, folder):
        if wanted and path.suffix.lower() not in wanted:
            continue
        try:
            lines = _read_text(path).splitlines()
        except UnicodeDecodeError:
            continue
        for number, line in enumerate(lines, start=1):
            if compiled is not None:
                m = compiled.search(line)
                if not m:
                    continue
                index = m.start()
                matched_len = m.end() - m.start()
                start = max(0, index - context_chars // 2)
                end = min(len(line), index + matched_len + context_chars // 2)
            else:
                haystack = line if case_sensitive else line.lower()
                index = haystack.find(needle)
                if index == -1:
                    continue
                start = max(0, index - context_chars // 2)
                end = min(len(line), index + len(query) + context_chars // 2)
            matches.append({"path": _rel(vault, path), "line": number, "snippet": line[start:end].strip()})
            if len(matches) >= max(1, limit):
                return matches
    return matches
```

- [ ] **Step 4: Run all new tests to verify they pass**

```
python -m pytest tests/test_obsidian_vault_mcp.py::ObsidianVaultMcpTests::test_search_regex_matches_pattern tests/test_obsidian_vault_mcp.py::ObsidianVaultMcpTests::test_search_regex_case_sensitive tests/test_obsidian_vault_mcp.py::ObsidianVaultMcpTests::test_search_regex_invalid_pattern_returns_error tests/test_obsidian_vault_mcp.py::ObsidianVaultMcpTests::test_search_regex_false_preserves_existing_behavior -v
```

Expected: 4 passed

- [ ] **Step 5: Run full suite — final check**

```
python -m pytest tests/ -v
```

Expected: all 54 original + all new tests pass (≥ 79 total)

- [ ] **Step 6: Final commit**

```bash
git add scripts/obsidian_vault_mcp/tools.py tests/test_obsidian_vault_mcp.py
git commit -m "feat: add use_regex parameter to obsidian_search"
```

---

## Self-Review Checklist

- [x] **Spec coverage:** All 6 spec requirements covered — structured annotations (Task 1–4), delete (Task 5), move+rename (Task 6), regex search (Task 7)
- [x] **No placeholders:** Every step has complete code
- [x] **Type consistency:** `_resolve_annotation_color_labels` returns `dict[str, str]` — used as `color_labels: dict[str, str]` in `_zotero_annotations_structured` ✓. `_rewrite_wikilinks` returns `dict[str, Any]` with `files` and `count` keys — consumed correctly in both tools ✓
- [x] **Backward compatibility:** All new parameters have defaults that preserve existing behavior. `obsidian_search` rewrite preserves the original code path when `use_regex=False`
- [x] **Zero new dependencies:** `datetime`, `timezone`, `shutil`, `re` already available via the helpers import chain
