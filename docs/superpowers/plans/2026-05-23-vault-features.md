# Vault Features Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 9 new features to the Obsidian Vault MCP server covering dead-link detection, orphan notes, batch file ops, vault stats, Zotero incremental sync, MinerU batch PDF, search context lines, citation network, and reading digest.

**Architecture:** All tool functions live in `scripts/obsidian_vault_mcp/tools.py` (imported via the glob-update pattern from `helpers.py`); tests live in `tests/test_obsidian_vault_mcp.py` using `unittest.TestCase` with a temp-vault fixture. Each section below (A–D) is independently shippable.

**Tech Stack:** Python 3.10+, FastMCP, PyYAML, `unittest`, `re`, `pathlib`, `shutil`, `json`

---

## File Structure

**Modified files:**
- `scripts/obsidian_vault_mcp/tools.py` — all new tools added here; `obsidian_search` and `obsidian_ingest_zotero_collection` modified
- `tests/test_obsidian_vault_mcp.py` — all new tests appended

**No new files required.** Every tool follows the existing `@tool()` decorator pattern.

---

## Section A — Quick Wins (Features 8, 9, 3)

### Task 1: obsidian_search — add `context_lines` parameter

**Files:**
- Modify: `scripts/obsidian_vault_mcp/tools.py:56-107`
- Test: `tests/test_obsidian_vault_mcp.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_obsidian_vault_mcp.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```
python -m unittest tests.test_obsidian_vault_mcp -v -k "test_search_context_lines"
```

Expected: FAIL — `obsidian_search()` takes no keyword argument `context_lines`

- [ ] **Step 3: Modify `obsidian_search` in tools.py**

Change the function signature (line 56) from:
```python
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
```
To:
```python
def obsidian_search(
    query: str,
    vault_path: str = "",
    folder: str = "",
    extensions: str = ".md",
    case_sensitive: bool = False,
    use_regex: bool = False,
    limit: int = 50,
    context_chars: int = 140,
    context_lines: int = 0,
) -> list[dict[str, Any]]:
```

Then, inside the loop where matches are built, replace the `matches.append(...)` calls (both the `compiled` branch and the `needle` branch) to include context lines when `context_lines > 0`.

The current structure (both branches append the same shape):
```python
matches.append({"path": _rel(vault, path), "line": number, "snippet": line[start:end].strip()})
```

Change both branches to call a shared helper right after setting `index`/`matched_len`:

```python
# At the top of the for-path loop, store all lines for context use:
try:
    lines = _read_text(path).splitlines()
except UnicodeDecodeError:
    continue
```
(This is already in the code. Now add context logic.)

After computing `start`/`end` for each match, build the match dict:
```python
match_dict: dict[str, Any] = {
    "path": _rel(vault, path),
    "line": number,
    "snippet": line[start:end].strip(),
}
if context_lines > 0:
    line_idx = number - 1  # 0-based
    before_start = max(0, line_idx - context_lines)
    after_end = min(len(lines), line_idx + context_lines + 1)
    match_dict["contextBefore"] = lines[before_start:line_idx]
    match_dict["contextAfter"] = lines[line_idx + 1:after_end]
matches.append(match_dict)
```

Apply this change to **both** the `compiled is not None` branch and the `needle` branch.

- [ ] **Step 4: Run tests to verify they pass**

```
python -m unittest tests.test_obsidian_vault_mcp -v -k "test_search_context_lines"
```

Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```
git add scripts/obsidian_vault_mcp/tools.py tests/test_obsidian_vault_mcp.py
git commit -m "feat: add context_lines parameter to obsidian_search"
```

---

### Task 2: obsidian_vault_stats — new tool for folder, tag, and hub stats

**Files:**
- Modify: `scripts/obsidian_vault_mcp/tools.py` — insert after `obsidian_vault_status` (line ~22)
- Test: `tests/test_obsidian_vault_mcp.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_vault_stats_groups_notes_by_top_level_folder(self):
    self.write_note("papers/A.md", "---\ntitle: A\ntags: [science]\n---\n[[B]]\n")
    self.write_note("notes/B.md", "---\ntitle: B\ntags: [math]\n---\n")
    result = self.module.obsidian_vault_stats(str(self.vault))
    self.assertEqual(result["byFolder"].get("papers"), 1)
    self.assertEqual(result["byFolder"].get("notes"), 1)

def test_vault_stats_returns_tag_frequency(self):
    self.write_note("A.md", "---\ntitle: A\ntags: [alpha, beta]\n---\n")
    self.write_note("B.md", "---\ntitle: B\ntags: [alpha]\n---\n")
    result = self.module.obsidian_vault_stats(str(self.vault))
    tags = {t["tag"]: t["count"] for t in result["topTags"]}
    self.assertEqual(tags.get("alpha"), 2)
    self.assertEqual(tags.get("beta"), 1)

def test_vault_stats_finds_knowledge_hub_nodes(self):
    self.write_note("hub.md", "---\ntitle: Hub\n---\n")
    self.write_note("A.md", "---\ntitle: A\n---\n[[hub]]\n")
    self.write_note("B.md", "---\ntitle: B\n---\n[[hub]]\n")
    result = self.module.obsidian_vault_stats(str(self.vault))
    hub = next((e for e in result["topLinked"] if e["path"] == "hub.md"), None)
    self.assertIsNotNone(hub)
    self.assertEqual(hub["incomingLinks"], 2)
```

- [ ] **Step 2: Run tests to verify they fail**

```
python -m unittest tests.test_obsidian_vault_mcp -v -k "test_vault_stats"
```

Expected: FAIL — `module` has no attribute `obsidian_vault_stats`

- [ ] **Step 3: Add `obsidian_vault_stats` to tools.py**

Insert after the closing brace of `obsidian_vault_status` (approximately after line 22):

```python
@tool()
def obsidian_vault_stats(
    vault_path: str = "",
    top_tags: int = 20,
    top_linked: int = 10,
) -> dict[str, Any]:
    """Return per-folder note counts, top tags by frequency, and most-linked notes."""
    vault = _vault(vault_path)
    graph = obsidian_build_graph(vault_path=str(vault), include_tags=True)

    by_folder: dict[str, int] = {}
    for path in _iter_files(vault):
        if path.suffix.lower() != ".md":
            continue
        parts = path.relative_to(vault).parts
        folder_key = parts[0] if len(parts) > 1 else "/"
        by_folder[folder_key] = by_folder.get(folder_key, 0) + 1

    sorted_tags = sorted(graph.get("tags", []), key=lambda x: x["count"], reverse=True)
    top_tag_list = sorted_tags[:max(1, top_tags)]

    nodes_by_id = {n["id"]: n for n in graph["nodes"]}
    backlinks = graph.get("backlinks", {})
    hub_candidates = [
        {
            "path": node_id,
            "title": nodes_by_id.get(node_id, {}).get("title") or Path(node_id).stem,
            "incomingLinks": len(sources),
        }
        for node_id, sources in backlinks.items()
        if sources
    ]
    top_linked_list = sorted(hub_candidates, key=lambda x: x["incomingLinks"], reverse=True)[:max(1, top_linked)]

    return {
        "vaultPath": str(vault),
        "markdownCount": graph["nodeCount"],
        "edgeCount": graph["edgeCount"],
        "orphanCount": len(graph["orphans"]),
        "byFolder": by_folder,
        "topTags": top_tag_list,
        "topLinked": top_linked_list,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```
python -m unittest tests.test_obsidian_vault_mcp -v -k "test_vault_stats"
```

Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```
git add scripts/obsidian_vault_mcp/tools.py tests/test_obsidian_vault_mcp.py
git commit -m "feat: add obsidian_vault_stats with folder counts, top tags, and hub nodes"
```

---

### Task 3: obsidian_find_orphans — dedicated orphan query tool

**Files:**
- Modify: `scripts/obsidian_vault_mcp/tools.py` — insert after `obsidian_lint_vault` (line ~571)
- Test: `tests/test_obsidian_vault_mcp.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_find_orphans_returns_notes_with_no_incoming_links(self):
    self.write_note("linked.md", "---\ntitle: Linked\n---\n")
    self.write_note("orphan.md", "---\ntitle: Orphan\n---\n")
    self.write_note("hub.md", "---\ntitle: Hub\n---\n[[linked]]\n")
    result = self.module.obsidian_find_orphans(str(self.vault))
    paths = [o["path"] for o in result["orphans"]]
    self.assertIn("orphan.md", paths)
    self.assertNotIn("linked.md", paths)
    self.assertIn("orphanCount", result)
    self.assertIn("totalNotes", result)

def test_find_orphans_excludes_index_and_log_by_default(self):
    self.write_note("index.md", "# Index\n")
    self.write_note("log.md", "# Log\n")
    self.write_note("regular.md", "---\ntitle: R\n---\n")
    result = self.module.obsidian_find_orphans(str(self.vault), exclude_index=True)
    paths = [o["path"] for o in result["orphans"]]
    self.assertNotIn("index.md", paths)
    self.assertNotIn("log.md", paths)
    self.assertIn("regular.md", paths)

def test_find_orphans_includes_file_metadata(self):
    self.write_note("alone.md", "---\ntitle: Alone Note\ntags: [solo]\n---\n")
    result = self.module.obsidian_find_orphans(str(self.vault))
    orphan = next((o for o in result["orphans"] if o["path"] == "alone.md"), None)
    self.assertIsNotNone(orphan)
    self.assertEqual(orphan["title"], "Alone Note")
    self.assertIn("solo", orphan["tags"])
    self.assertIn("size", orphan)
    self.assertIn("modified", orphan)
```

- [ ] **Step 2: Run tests to verify they fail**

```
python -m unittest tests.test_obsidian_vault_mcp -v -k "test_find_orphans"
```

Expected: FAIL — `module` has no attribute `obsidian_find_orphans`

- [ ] **Step 3: Add `obsidian_find_orphans` to tools.py**

Insert after `obsidian_lint_vault` (after approximately line 571):

```python
@tool()
def obsidian_find_orphans(
    vault_path: str = "",
    folder: str = "",
    exclude_index: bool = True,
) -> dict[str, Any]:
    """Return all Markdown notes that have no incoming wikilinks, with file metadata."""
    vault = _vault(vault_path)
    graph = obsidian_build_graph(vault_path=str(vault), folder=folder, include_tags=True)

    excluded: set[str] = set()
    if exclude_index:
        index_path = _configured_path(vault, "indexPath", "index.md", "index.md")
        log_path = _configured_path(vault, "logPath", "log.md", "log.md")
        excluded = {index_path.lower(), log_path.lower()}

    nodes_by_id = {n["id"]: n for n in graph["nodes"]}
    orphan_details: list[dict[str, Any]] = []
    for orphan_id in graph["orphans"]:
        if orphan_id.lower() in excluded:
            continue
        node = nodes_by_id.get(orphan_id, {})
        full = _safe_path(vault, orphan_id)
        stat = full.stat() if full.exists() else None
        orphan_details.append(
            {
                "path": orphan_id,
                "title": node.get("title") or Path(orphan_id).stem,
                "tags": node.get("tags", []),
                "size": stat.st_size if stat else 0,
                "modified": int(stat.st_mtime) if stat else 0,
            }
        )

    return {
        "vaultPath": str(vault),
        "orphanCount": len(orphan_details),
        "totalNotes": graph["nodeCount"],
        "orphans": orphan_details,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```
python -m unittest tests.test_obsidian_vault_mcp -v -k "test_find_orphans"
```

Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```
git add scripts/obsidian_vault_mcp/tools.py tests/test_obsidian_vault_mcp.py
git commit -m "feat: add obsidian_find_orphans tool with file metadata"
```

---

## Section B — Core Link & File Health (Features 1, 4)

### Task 4: obsidian_find_broken_links — dead wikilink + markdown link detection with optional fix

**Files:**
- Modify: `scripts/obsidian_vault_mcp/tools.py` — insert after `obsidian_find_orphans`
- Test: `tests/test_obsidian_vault_mcp.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_find_broken_links_detects_unresolved_wikilinks(self):
    self.write_note("A.md", "---\ntitle: A\n---\nSee [[NonExistent]].\n")
    result = self.module.obsidian_find_broken_links(str(self.vault))
    self.assertGreater(result["totalBroken"], 0)
    targets = [e["target"] for e in result["brokenWikilinks"]]
    self.assertIn("NonExistent", targets)

def test_find_broken_links_detects_dead_local_markdown_links(self):
    self.write_note("A.md", "See [label](missing_file.md).\n")
    result = self.module.obsidian_find_broken_links(str(self.vault))
    targets = [e["target"] for e in result["brokenMarkdownLinks"]]
    self.assertIn("missing_file.md", targets)

def test_find_broken_links_skips_external_urls(self):
    self.write_note("A.md", "See [Google](https://google.com) and [Mail](mailto:x@y.com).\n")
    result = self.module.obsidian_find_broken_links(str(self.vault))
    self.assertEqual(len(result["brokenMarkdownLinks"]), 0)

def test_find_broken_links_skips_existing_local_links(self):
    self.write_note("A.md", "See [B](B.md).\n")
    self.write_note("B.md", "# B\n")
    result = self.module.obsidian_find_broken_links(str(self.vault))
    self.assertEqual(len(result["brokenMarkdownLinks"]), 0)

def test_find_broken_links_fix_replaces_dead_wikilink_with_text(self):
    self.write_note("A.md", "---\ntitle: A\n---\nSee [[Ghost]] here.\n")
    result = self.module.obsidian_find_broken_links(
        str(self.vault), fix=True, dry_run=False
    )
    content = (self.vault / "A.md").read_text(encoding="utf-8")
    self.assertNotIn("[[Ghost]]", content)
    self.assertIn("Ghost", content)

def test_find_broken_links_fix_keeps_alias_text(self):
    self.write_note("A.md", "---\ntitle: A\n---\nSee [[Ghost|Haunted]] here.\n")
    self.module.obsidian_find_broken_links(
        str(self.vault), fix=True, dry_run=False
    )
    content = (self.vault / "A.md").read_text(encoding="utf-8")
    self.assertNotIn("[[Ghost|Haunted]]", content)
    self.assertIn("Haunted", content)
    self.assertNotIn("Ghost", content)
```

- [ ] **Step 2: Run tests to verify they fail**

```
python -m unittest tests.test_obsidian_vault_mcp -v -k "test_find_broken_links"
```

Expected: FAIL — `module` has no attribute `obsidian_find_broken_links`

- [ ] **Step 3: Add `obsidian_find_broken_links` to tools.py**

Insert after `obsidian_find_orphans`:

```python
@tool()
def obsidian_find_broken_links(
    vault_path: str = "",
    folder: str = "",
    fix: bool = False,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Scan for broken [[wikilinks]] and [markdown](links), with optional fix to strip dead links.

    fix=True: replace [[DeadTarget]] with DeadTarget and [[DeadTarget|Label]] with Label.
    dry_run=True (default): report only, do not write files.
    """
    vault = _vault(vault_path)
    graph = obsidian_build_graph(vault_path=str(vault), folder=folder)

    # Broken wikilinks from graph
    broken_wikilinks: list[dict[str, Any]] = [
        {"file": source, "target": target, "type": "wikilink"}
        for target, sources in graph["unresolved"].items()
        for source in sources
    ]

    # Broken local markdown links: scan files for [label](path) that don't exist
    broken_md_links: list[dict[str, Any]] = []
    _url_schemes = ("http://", "https://", "ftp://", "mailto:", "zotero:", "#", "obsidian://")
    for path in _iter_files(vault, folder):
        if path.suffix.lower() != ".md":
            continue
        rel = _rel(vault, path)
        text = _read_text(path)
        for m in MARKDOWN_LINK_RE.finditer(text):
            raw_target = m.group(1)
            if any(raw_target.startswith(scheme) for scheme in _url_schemes):
                continue
            target_clean = unquote(raw_target.split("#")[0].split("?")[0])
            if not target_clean:
                continue
            candidate_rel = path.parent / target_clean
            candidate_abs = vault / target_clean
            if not candidate_rel.exists() and not candidate_abs.exists():
                broken_md_links.append({"file": rel, "target": raw_target, "type": "markdown"})

    all_broken = broken_wikilinks + broken_md_links
    fixed_count = 0

    if fix:
        # Build per-file set of broken wikilink targets (normalized)
        broken_targets: set[str] = set()
        for entry in broken_wikilinks:
            broken_targets.add(_normalize_note_key(entry["target"]))

        files_with_dead_wikilinks: set[str] = {e["file"] for e in broken_wikilinks}
        for rel_path in files_with_dead_wikilinks:
            full = _safe_path(vault, rel_path)
            if not full.exists():
                continue
            original = _read_text(full)

            def _replacer(m: re.Match) -> str:
                inner = m.group(1)
                raw = _target_from_link(inner)
                if _normalize_note_key(raw) in broken_targets:
                    # Use alias if present, otherwise use the target name
                    parts = inner.split("|", 1)
                    return parts[1].strip() if len(parts) > 1 else raw
                return m.group(0)

            new_text = WIKILINK_RE.sub(_replacer, original)
            if new_text != original:
                if not dry_run:
                    _write_text(full, new_text)
                fixed_count += 1

    return {
        "vaultPath": str(vault),
        "totalBroken": len(all_broken),
        "brokenWikilinks": broken_wikilinks,
        "brokenMarkdownLinks": broken_md_links,
        "fixed": fixed_count,
        "dryRun": dry_run,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```
python -m unittest tests.test_obsidian_vault_mcp -v -k "test_find_broken_links"
```

Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```
git add scripts/obsidian_vault_mcp/tools.py tests/test_obsidian_vault_mcp.py
git commit -m "feat: add obsidian_find_broken_links with wikilink and markdown link detection"
```

---

### Task 5: obsidian_batch_move_files — batch move by path list, glob, tag, or folder

**Files:**
- Modify: `scripts/obsidian_vault_mcp/tools.py` — insert after `obsidian_rename_file` (line ~238)
- Test: `tests/test_obsidian_vault_mcp.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_batch_move_dry_run_reports_without_moving(self):
    self.write_note("inbox/A.md", "# A")
    self.write_note("inbox/B.md", "# B")
    result = self.module.obsidian_batch_move_files(
        "archive", str(self.vault), folder="inbox", dry_run=True
    )
    self.assertTrue(result["dryRun"])
    self.assertEqual(result["total"], 2)
    self.assertTrue((self.vault / "inbox" / "A.md").exists())

def test_batch_move_by_tag_moves_matching_only(self):
    self.write_note("A.md", "---\ntags: [archive]\n---\n")
    self.write_note("B.md", "---\ntags: [keep]\n---\n")
    result = self.module.obsidian_batch_move_files(
        "archived", str(self.vault), tag="archive", dry_run=False
    )
    self.assertEqual(result["movedCount"], 1)
    self.assertTrue((self.vault / "archived" / "A.md").exists())
    self.assertTrue((self.vault / "B.md").exists())

def test_batch_move_by_paths_json(self):
    import json
    self.write_note("X.md", "# X")
    self.write_note("Y.md", "# Y")
    self.write_note("Z.md", "# Z")
    result = self.module.obsidian_batch_move_files(
        "done", str(self.vault),
        paths_json=json.dumps(["X.md", "Y.md"]),
        dry_run=False,
    )
    self.assertEqual(result["movedCount"], 2)
    self.assertTrue((self.vault / "done" / "X.md").exists())
    self.assertTrue((self.vault / "Z.md").exists())

def test_batch_move_reports_errors_on_missing_files(self):
    result = self.module.obsidian_batch_move_files(
        "dest", str(self.vault),
        paths_json='["does_not_exist.md"]',
        dry_run=False,
    )
    self.assertFalse(result["ok"])
    self.assertEqual(result["errorCount"], 1)
```

- [ ] **Step 2: Run tests to verify they fail**

```
python -m unittest tests.test_obsidian_vault_mcp -v -k "test_batch_move"
```

Expected: FAIL — `module` has no attribute `obsidian_batch_move_files`

- [ ] **Step 3: Add `obsidian_batch_move_files` to tools.py**

Insert after `obsidian_rename_file` (after approximately line 238):

```python
@tool()
def obsidian_batch_move_files(
    to: str,
    vault_path: str = "",
    paths_json: str = "[]",
    glob_pattern: str = "",
    tag: str = "",
    folder: str = "",
    update_wikilinks: bool = False,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Move multiple vault files to a target directory.

    Specify which files to move via at least one of:
      paths_json: JSON array of vault-relative paths, e.g. '["papers/A.md","papers/B.md"]'
      glob_pattern: shell glob matched against each file's name, e.g. "*.md"
      tag: move all .md files that carry this frontmatter or inline tag
      folder: move all files found in this vault-relative folder

    update_wikilinks=true rewrites [[links]] after each move (slow for large vaults).
    dry_run=true (default): report planned moves without executing them.
    """
    vault = _vault(vault_path)
    files_to_move: list[str] = []

    if paths_json and paths_json != "[]":
        try:
            parsed = json.loads(paths_json)
        except json.JSONDecodeError as exc:
            return {"ok": False, "error": f"Invalid paths_json: {exc}", "total": 0, "movedCount": 0, "errorCount": 0, "moved": [], "errors": [], "dryRun": dry_run}
        files_to_move.extend(str(p) for p in parsed)

    if glob_pattern:
        import fnmatch
        for path in _iter_files(vault, folder):
            if fnmatch.fnmatch(path.name, glob_pattern) or fnmatch.fnmatch(_rel(vault, path), glob_pattern):
                rel = _rel(vault, path)
                if rel not in files_to_move:
                    files_to_move.append(rel)

    if tag:
        for path in _iter_files(vault, folder):
            if path.suffix.lower() != ".md":
                continue
            props, body = _split_frontmatter(_read_text(path))
            all_tags = _frontmatter_tags(props) + _inline_tags(body)
            if tag in all_tags:
                rel = _rel(vault, path)
                if rel not in files_to_move:
                    files_to_move.append(rel)

    if folder and not glob_pattern and not tag and not (paths_json and paths_json != "[]"):
        for path in _iter_files(vault, folder):
            rel = _rel(vault, path)
            if rel not in files_to_move:
                files_to_move.append(rel)

    moved: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for file_path in files_to_move:
        res = obsidian_move_file(
            path=file_path,
            to=to,
            vault_path=str(vault),
            update_wikilinks=update_wikilinks,
            dry_run=dry_run,
        )
        if res.get("ok"):
            moved.append({"from": res["from"], "to": res["to"]})
        else:
            errors.append({"path": file_path, "error": res.get("error", "unknown error")})

    return {
        "ok": len(errors) == 0,
        "total": len(files_to_move),
        "movedCount": len(moved),
        "errorCount": len(errors),
        "moved": moved,
        "errors": errors,
        "dryRun": dry_run,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```
python -m unittest tests.test_obsidian_vault_mcp -v -k "test_batch_move"
```

Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```
git add scripts/obsidian_vault_mcp/tools.py tests/test_obsidian_vault_mcp.py
git commit -m "feat: add obsidian_batch_move_files with glob, tag, and path-list selectors"
```

---

## Section C — Performance & Batch (Features 2, 6)

### Task 6: Zotero incremental sync — pre-filter using collection list versions

**Files:**
- Modify: `scripts/obsidian_vault_mcp/tools.py:1656-1768` (obsidian_ingest_zotero_collection)
- Test: `tests/test_obsidian_vault_mcp.py`

**Problem:** `obsidian_ingest_zotero_collection` calls `obsidian_ingest_zotero_item` for every item in the collection. Each `obsidian_ingest_zotero_item` call makes a Zotero API request to fetch full item data before it can check `zoteroVersion`. For a 100-item collection that's already synced, this makes 100 unnecessary API calls.

**Fix:** Build a `zoteroKey → (path, stored_version)` index from the vault once, then use the `version` field already present in the collection list response to pre-skip unchanged items before making any item-level API calls.

- [ ] **Step 1: Write the failing test**

```python
def test_zotero_incremental_skips_unchanged_items_without_api_call(self):
    """Items already at the current version must be skipped before obsidian_ingest_zotero_item is called."""
    import unittest.mock as mock

    # Create an existing note that looks like it was ingested at version 7
    self.write_note(
        "literature/Paper One.md",
        "---\ntitle: Paper One\nzoteroKey: AAABBB\nzoteroVersion: 7\ntags: [zotero]\n---\n",
    )

    fake_items = [
        {"key": "AAABBB", "version": 7, "data": {"itemType": "journalArticle", "title": "Paper One"}},
    ]

    with mock.patch.object(
        self.module, "_zotero_api", return_value=fake_items
    ) as mock_api, mock.patch.object(
        self.module, "obsidian_ingest_zotero_item"
    ) as mock_ingest:
        result = self.module.obsidian_ingest_zotero_collection(
            query="paper", vault_path=str(self.vault), skip_up_to_date=True
        )

    mock_ingest.assert_not_called()
    self.assertEqual(result["skipped"], 1)
    self.assertEqual(result["total"], 1)
```

- [ ] **Step 2: Run test to verify it fails**

```
python -m unittest tests.test_obsidian_vault_mcp -v -k "test_zotero_incremental"
```

Expected: FAIL — `mock_ingest` IS called (the optimization is not yet in place)

- [ ] **Step 3: Modify `obsidian_ingest_zotero_collection` in tools.py**

In `obsidian_ingest_zotero_collection` (around line 1656), after the `raw_items` fetch and before the per-key loop, add a pre-filtering step.

Replace:
```python
# Filter to real parent items (exclude attachments/notes/annotations)
skip_types = {"attachment", "note", "annotation"}
keys = [
    item.get("key")
    for item in raw_items
    if item.get("key") and item.get("data", {}).get("itemType") not in skip_types
]
```

With:
```python
# Filter to real parent items (exclude attachments/notes/annotations)
skip_types = {"attachment", "note", "annotation"}
items_by_key = {
    item["key"]: item
    for item in raw_items
    if item.get("key") and item.get("data", {}).get("itemType") not in skip_types
}
```

Then replace:
```python
results: list[dict[str, Any]] = []
skipped = 0
updated = 0
created = 0
errors = 0

for item_key in keys:
    try:
        res = obsidian_ingest_zotero_item(
```

With:
```python
# Build a zoteroKey → (path, stored_version) index from vault notes once.
# This avoids O(N*M) _find_existing_reference calls for large collections.
_key_to_stored: dict[str, tuple[Path, Any]] = {}
if skip_up_to_date and not overwrite:
    _lit_root = _safe_path(vault, source_folder) if source_folder else vault
    if _lit_root.exists():
        for _p in _lit_root.rglob("*.md"):
            if any(part in DEFAULT_EXCLUDES or part.startswith(".") for part in _p.relative_to(vault).parts):
                continue
            _props, _ = _split_frontmatter(_read_text(_p))
            _zk = str(_props.get("zoteroKey") or "").strip()
            if _zk:
                _key_to_stored[_zk] = (_p, _props.get("zoteroVersion"))

results: list[dict[str, Any]] = []
skipped = 0
updated = 0
created = 0
errors = 0

for item_key, raw_item in items_by_key.items():
    try:
        # Fast pre-check: if version matches stored note, skip without any API call.
        if skip_up_to_date and not overwrite and item_key in _key_to_stored:
            _stored_path, _stored_version = _key_to_stored[item_key]
            if _stored_version == raw_item.get("version") and raw_item.get("version") is not None:
                skipped += 1
                results.append({"key": item_key, "ok": True, "upToDate": True, "referencePath": _rel(vault, _stored_path)})
                continue

        res = obsidian_ingest_zotero_item(
```

- [ ] **Step 4: Run test to verify it passes**

```
python -m unittest tests.test_obsidian_vault_mcp -v -k "test_zotero_incremental"
```

Expected: PASS

- [ ] **Step 5: Commit**

```
git add scripts/obsidian_vault_mcp/tools.py tests/test_obsidian_vault_mcp.py
git commit -m "perf: skip unchanged Zotero items in collection sync without API calls"
```

---

### Task 7: obsidian_mineru_extract_folder — batch MinerU extraction for a PDF folder

**Files:**
- Modify: `scripts/obsidian_vault_mcp/tools.py` — insert after `obsidian_mineru_extract_and_ingest` (line ~1226)
- Test: `tests/test_obsidian_vault_mcp.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_mineru_extract_folder_dry_run_lists_pdfs(self):
    (self.vault / "pdfs").mkdir()
    (self.vault / "pdfs" / "paper1.pdf").write_bytes(b"%PDF-1.4\n")
    (self.vault / "pdfs" / "paper2.pdf").write_bytes(b"%PDF-1.4\n")
    result = self.module.obsidian_mineru_extract_folder(
        "pdfs", str(self.vault), dry_run=True
    )
    self.assertTrue(result["dryRun"])
    self.assertEqual(result["total"], 2)
    statuses = [r["status"] for r in result["results"]]
    self.assertIn("would_extract", statuses)

def test_mineru_extract_folder_skips_already_extracted(self):
    (self.vault / "pdfs").mkdir()
    (self.vault / "pdfs" / "paper.pdf").write_bytes(b"%PDF-1.4\n")
    # Simulate an already-extracted output marker
    out_dir = self.vault / "mineru" / "paper"
    out_dir.mkdir(parents=True)
    (out_dir / "paper.md").write_text("# Extracted\n", encoding="utf-8")
    result = self.module.obsidian_mineru_extract_folder(
        "pdfs", str(self.vault), output_folder="mineru",
        skip_extracted=True, dry_run=True
    )
    self.assertEqual(result["skipped"], 1)
    self.assertEqual(result["total"], 1)

def test_mineru_extract_folder_returns_error_on_missing_dir(self):
    result = self.module.obsidian_mineru_extract_folder(
        "nonexistent_folder", str(self.vault)
    )
    self.assertFalse(result["ok"])
    self.assertIn("error", result)
```

- [ ] **Step 2: Run tests to verify they fail**

```
python -m unittest tests.test_obsidian_vault_mcp -v -k "test_mineru_extract_folder"
```

Expected: FAIL — `module` has no attribute `obsidian_mineru_extract_folder`

- [ ] **Step 3: Add `obsidian_mineru_extract_folder` to tools.py**

Insert after `obsidian_mineru_extract_and_ingest`:

```python
@tool()
def obsidian_mineru_extract_folder(
    input_folder: str,
    vault_path: str = "",
    output_folder: str = "mineru",
    mode: str = "",
    language: str = "ch",
    skip_extracted: bool = True,
    ingest: bool = False,
    token: str = "",
    dry_run: bool = False,
) -> dict[str, Any]:
    """Batch-extract all PDF files in a folder using MinerU.

    skip_extracted=true (default): skip any PDF whose output directory already contains a .md file.
    ingest=true: automatically call obsidian_ingest_mineru_markdown after each successful extraction.
    dry_run=true: enumerate PDFs and show skip/extract decisions without running MinerU.
    """
    vault = _vault(vault_path)
    if Path(input_folder).is_absolute():
        input_full = Path(input_folder)
    else:
        input_full = _safe_path(vault, input_folder)

    if not input_full.is_dir():
        return {"ok": False, "error": f"Not a directory: {input_folder}", "total": 0, "extracted": 0, "skipped": 0, "errors": 0, "dryRun": dry_run, "results": []}

    pdf_files = sorted(input_full.rglob("*.pdf")) + sorted(input_full.rglob("*.PDF"))
    pdf_files = sorted(set(pdf_files), key=lambda p: str(p).lower())

    output_base = vault / output_folder if output_folder else vault / "mineru"
    results: list[dict[str, Any]] = []
    extracted = 0
    skipped = 0
    errors = 0

    for pdf_path in pdf_files:
        pdf_rel = _rel(vault, pdf_path) if pdf_path.is_relative_to(vault) else str(pdf_path)
        stem = pdf_path.stem

        if skip_extracted:
            expected_md = output_base / stem / f"{stem}.md"
            if expected_md.exists():
                skipped += 1
                results.append({"input": pdf_rel, "status": "skipped", "reason": "already_extracted", "outputPath": _rel(vault, expected_md)})
                continue

        if dry_run:
            results.append({"input": pdf_rel, "status": "would_extract"})
            continue

        try:
            res = obsidian_mineru_extract(
                input_path=str(pdf_path),
                vault_path=str(vault),
                output_path=output_folder,
                mode=mode,
                language=language,
                token=token,
                dry_run=False,
            )
            if res.get("ok"):
                extracted += 1
                entry: dict[str, Any] = {"input": pdf_rel, "status": "extracted", "outputPath": res.get("markdownPath", "")}
                if ingest and res.get("markdownPath"):
                    ingest_res = obsidian_ingest_mineru_markdown(
                        markdown_path=res["markdownPath"],
                        vault_path=str(vault),
                    )
                    entry["ingested"] = ingest_res.get("ok", False)
                results.append(entry)
            else:
                errors += 1
                results.append({"input": pdf_rel, "status": "error", "error": res.get("error", "MinerU extraction failed")})
        except Exception as exc:
            errors += 1
            results.append({"input": pdf_rel, "status": "error", "error": str(exc)})

    return {
        "ok": errors == 0,
        "total": len(pdf_files),
        "extracted": extracted,
        "skipped": skipped,
        "errors": errors,
        "dryRun": dry_run,
        "results": results,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```
python -m unittest tests.test_obsidian_vault_mcp -v -k "test_mineru_extract_folder"
```

Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```
git add scripts/obsidian_vault_mcp/tools.py tests/test_obsidian_vault_mcp.py
git commit -m "feat: add obsidian_mineru_extract_folder for batch PDF extraction"
```

---

## Section D — Advanced Academic Workflow (Features 5, 7)

### Task 8: obsidian_build_citation_network — extract Zotero relations and write cites wikilinks

**Files:**
- Modify: `scripts/obsidian_vault_mcp/tools.py` — insert after `obsidian_ingest_zotero_collection` (line ~1769)
- Test: `tests/test_obsidian_vault_mcp.py`

**Approach:** Scan literature notes for `relations` frontmatter (Zotero `zotero://select/library/items/KEY` URIs). Build a vault-wide `zoteroKey → note_path` index. For each note with relations, resolve the related keys to vault paths and add wikilinks to the `cites` frontmatter list.

- [ ] **Step 1: Write the failing tests**

```python
def test_build_citation_network_resolves_zotero_uri_relations(self):
    self.write_note(
        "lit/paper1.md",
        "---\ntitle: Paper 1\nzoteroKey: AAAAAA\n---\n",
    )
    self.write_note(
        "lit/paper2.md",
        "---\ntitle: Paper 2\nzoteroKey: BBBBBB\nrelations:\n  - 'zotero://select/library/items/AAAAAA'\n---\n",
    )
    result = self.module.obsidian_build_citation_network(
        str(self.vault), source_folder="lit", dry_run=False
    )
    self.assertEqual(result["updatedCount"], 1)
    content = (self.vault / "lit" / "paper2.md").read_text(encoding="utf-8")
    self.assertIn("lit/paper1.md", content)

def test_build_citation_network_dry_run_does_not_write(self):
    self.write_note("lit/A.md", "---\nzoteroKey: KEY1\n---\n")
    self.write_note("lit/B.md", "---\nzoteroKey: KEY2\nrelations:\n  - 'zotero://select/library/items/KEY1'\n---\n")
    original = (self.vault / "lit" / "B.md").read_text(encoding="utf-8")
    result = self.module.obsidian_build_citation_network(
        str(self.vault), source_folder="lit", dry_run=True
    )
    self.assertEqual(result["updatedCount"], 1)
    self.assertEqual((self.vault / "lit" / "B.md").read_text(encoding="utf-8"), original)

def test_build_citation_network_skips_self_references(self):
    self.write_note(
        "lit/self.md",
        "---\nzoteroKey: SELFKEY\nrelations:\n  - 'zotero://select/library/items/SELFKEY'\n---\n",
    )
    result = self.module.obsidian_build_citation_network(
        str(self.vault), source_folder="lit", dry_run=False
    )
    self.assertEqual(result["updatedCount"], 0)

def test_build_citation_network_preserves_existing_cites(self):
    self.write_note("lit/A.md", "---\nzoteroKey: AAAA\n---\n")
    self.write_note("lit/B.md", "---\nzoteroKey: BBBB\n---\n")
    self.write_note(
        "lit/C.md",
        "---\nzoteroKey: CCCC\ncites:\n  - '[[lit/A.md]]'\nrelations:\n  - 'zotero://select/library/items/BBBB'\n---\n",
    )
    self.module.obsidian_build_citation_network(
        str(self.vault), source_folder="lit", dry_run=False
    )
    content = (self.vault / "lit" / "C.md").read_text(encoding="utf-8")
    self.assertIn("lit/A.md", content)
    self.assertIn("lit/B.md", content)
```

- [ ] **Step 2: Run tests to verify they fail**

```
python -m unittest tests.test_obsidian_vault_mcp -v -k "test_build_citation_network"
```

Expected: FAIL — `module` has no attribute `obsidian_build_citation_network`

- [ ] **Step 3: Add `obsidian_build_citation_network` to tools.py**

Insert after `obsidian_ingest_zotero_collection`:

```python
@tool()
def obsidian_build_citation_network(
    vault_path: str = "",
    source_folder: str = "literature",
    dry_run: bool = True,
) -> dict[str, Any]:
    """Scan literature notes for Zotero relations and write [[wikilinks]] into the cites frontmatter field.

    Reads the 'relations' frontmatter list (values may be zotero://select/library/items/KEY URIs).
    Resolves each relation key to a vault note via the zoteroKey index.
    Adds unresolved targets as [[path]] entries to the note's 'cites' list.
    dry_run=true (default): report planned updates without writing.
    """
    vault = _vault(vault_path)
    root = _safe_path(vault, source_folder) if source_folder else vault

    # Build zoteroKey → vault-relative-path index from all notes in source_folder
    key_to_path: dict[str, str] = {}
    if root.exists():
        for path in root.rglob("*.md"):
            if any(part in DEFAULT_EXCLUDES or part.startswith(".") for part in path.relative_to(vault).parts):
                continue
            props, _ = _split_frontmatter(_read_text(path))
            zk = str(props.get("zoteroKey") or "").strip()
            if zk:
                key_to_path[zk.upper()] = _rel(vault, path)

    _ZOTERO_KEY_RE = re.compile(r"items/([A-Z0-9]+)", re.IGNORECASE)

    updated_notes: list[dict[str, Any]] = []

    if root.exists():
        for path in root.rglob("*.md"):
            if any(part in DEFAULT_EXCLUDES or part.startswith(".") for part in path.relative_to(vault).parts):
                continue
            rel = _rel(vault, path)
            props, body = _split_frontmatter(_read_text(path))

            # Collect referenced keys from 'relations' field
            relation_keys: set[str] = set()
            for val in _listify(props.get("relations")):
                val_str = str(val).strip()
                m = _ZOTERO_KEY_RE.search(val_str)
                if m:
                    relation_keys.add(m.group(1).upper())
                elif val_str:
                    relation_keys.add(val_str.upper())

            # Resolve keys to vault paths (skip self)
            new_wikilinks: list[str] = []
            for key in relation_keys:
                resolved = key_to_path.get(key)
                if resolved and resolved != rel:
                    new_wikilinks.append(f"[[{resolved}]]")

            if not new_wikilinks:
                continue

            # Merge with existing 'cites' list, avoiding duplicates
            existing_cites: list[str] = [str(v) for v in _listify(props.get("cites")) if v]
            existing_set = set(existing_cites)
            added = [link for link in new_wikilinks if link not in existing_set]
            if not added:
                continue

            props["cites"] = existing_cites + added
            new_text = _join_frontmatter(props, body)
            if not dry_run:
                _write_text(path, new_text)
            updated_notes.append({"path": rel, "addedLinks": added})

    return {
        "ok": True,
        "updatedCount": len(updated_notes),
        "dryRun": dry_run,
        "updatedNotes": updated_notes,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```
python -m unittest tests.test_obsidian_vault_mcp -v -k "test_build_citation_network"
```

Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```
git add scripts/obsidian_vault_mcp/tools.py tests/test_obsidian_vault_mcp.py
git commit -m "feat: add obsidian_build_citation_network to link literature notes via Zotero relations"
```

---

### Task 9: obsidian_build_reading_digest — aggregate callout blocks into a weekly digest note

**Files:**
- Modify: `scripts/obsidian_vault_mcp/tools.py` — insert at end of file
- Test: `tests/test_obsidian_vault_mcp.py`

**Approach:** Scan all `.md` files modified within `since_days`, find Obsidian callout blocks (`> [!quote]`, `> [!highlight]`, `> [!important]`, `> [!note]`), group by tag or callout type, and write a digest note.

- [ ] **Step 1: Write the failing tests**

```python
def test_reading_digest_extracts_quote_callout(self):
    self.write_note(
        "lit/paper.md",
        "---\ntitle: Paper\ntags: [science]\n---\n\n> [!quote]\n> Important finding here.\n\n",
    )
    result = self.module.obsidian_build_reading_digest(
        str(self.vault), folder="lit", since_days=9999, dry_run=False
    )
    self.assertEqual(result["excerptCount"], 1)
    digest_path = self.vault / "reading-digest.md"
    self.assertTrue(digest_path.exists())
    digest = digest_path.read_text(encoding="utf-8")
    self.assertIn("Important finding here.", digest)

def test_reading_digest_dry_run_does_not_write(self):
    self.write_note(
        "lit/p.md",
        "---\ntitle: P\n---\n\n> [!quote]\n> Quote text.\n\n",
    )
    result = self.module.obsidian_build_reading_digest(
        str(self.vault), folder="lit", since_days=9999, dry_run=True
    )
    self.assertFalse((self.vault / "reading-digest.md").exists())
    self.assertIn("preview", result)

def test_reading_digest_skips_files_outside_since_days(self):
    self.write_note("lit/old.md", "---\ntitle: Old\n---\n\n> [!quote]\n> Old quote.\n\n")
    import os, time
    # Backdate the file by 30 days
    old_mtime = time.time() - 30 * 86400
    os.utime(self.vault / "lit" / "old.md", (old_mtime, old_mtime))
    result = self.module.obsidian_build_reading_digest(
        str(self.vault), folder="lit", since_days=7, dry_run=True
    )
    self.assertEqual(result["excerptCount"], 0)

def test_reading_digest_includes_source_wikilink(self):
    self.write_note(
        "lit/source.md",
        "---\ntitle: My Source\n---\n\n> [!highlight]\n> A highlight.\n\n",
    )
    result = self.module.obsidian_build_reading_digest(
        str(self.vault), folder="lit", since_days=9999, dry_run=False
    )
    digest = (self.vault / "reading-digest.md").read_text(encoding="utf-8")
    self.assertIn("lit/source.md", digest)
```

- [ ] **Step 2: Run tests to verify they fail**

```
python -m unittest tests.test_obsidian_vault_mcp -v -k "test_reading_digest"
```

Expected: FAIL — `module` has no attribute `obsidian_build_reading_digest`

- [ ] **Step 3: Add `obsidian_build_reading_digest` to tools.py**

Append at the end of tools.py:

```python
@tool()
def obsidian_build_reading_digest(
    vault_path: str = "",
    folder: str = "literature",
    output_path: str = "reading-digest.md",
    since_days: int = 7,
    group_by: str = "tag",
    dry_run: bool = False,
) -> dict[str, Any]:
    """Aggregate [!quote], [!highlight], [!important], and [!note] callout blocks from recently
    modified notes into a digest file grouped by tag or callout type.

    since_days: only scan notes modified within the last N days.
    group_by: "tag" groups by frontmatter/inline tags; "type" groups by callout type.
    dry_run=True: return a preview without writing the output file.
    """
    import time as _time

    vault = _vault(vault_path)
    cutoff = _time.time() - since_days * 86400

    _CALLOUT_BLOCK_RE = re.compile(
        r"(^> \[!(?:quote|highlight|important|note)[^\]]*\][ \t]*.*?(?:\n(?:> .*|>))*)",
        re.IGNORECASE | re.MULTILINE,
    )
    _CALLOUT_TYPE_RE = re.compile(r"\[!([^\]]+)\]", re.IGNORECASE)

    excerpts: list[dict[str, Any]] = []

    for path in _iter_files(vault, folder):
        if path.suffix.lower() != ".md":
            continue
        if path.stat().st_mtime < cutoff:
            continue
        rel = _rel(vault, path)
        props, body = _split_frontmatter(_read_text(path))
        title = str(props.get("title") or path.stem)
        tags = _frontmatter_tags(props) + _inline_tags(body)

        for m in _CALLOUT_BLOCK_RE.finditer(body):
            block = m.group(0)
            type_match = _CALLOUT_TYPE_RE.search(block)
            callout_type = type_match.group(1).lower() if type_match else "note"
            content_lines = []
            for raw_line in block.split("\n"):
                stripped = raw_line.lstrip(">").strip()
                if stripped and not _CALLOUT_TYPE_RE.search(stripped):
                    content_lines.append(stripped)
            content = "\n".join(content_lines).strip()
            if content:
                excerpts.append(
                    {
                        "source": rel,
                        "title": title,
                        "tags": tags,
                        "type": callout_type,
                        "content": content,
                    }
                )

    result: dict[str, Any] = {
        "ok": True,
        "excerptCount": len(excerpts),
        "outputPath": output_path,
        "dryRun": dry_run,
    }

    if not excerpts:
        result["message"] = "No callout excerpts found in the specified date range."
        return result

    # Group excerpts
    groups: dict[str, list[dict[str, Any]]] = {}
    if group_by == "tag":
        for exc in excerpts:
            for tag in (exc["tags"] or ["untagged"]):
                groups.setdefault(tag, []).append(exc)
    else:
        for exc in excerpts:
            groups.setdefault(exc["type"], []).append(exc)

    # Build digest Markdown
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines: list[str] = [
        "---",
        "title: Reading Digest",
        f"generated: {now_iso}",
        "tags: [digest]",
        "---",
        "",
        f"# Reading Digest — Last {since_days} day{'s' if since_days != 1 else ''}",
        "",
    ]
    for group_name in sorted(groups):
        lines.append(f"## {group_name}")
        lines.append("")
        for exc in groups[group_name]:
            lines.append(f"**From** [[{exc['source']}|{exc['title']}]]")
            lines.append("")
            lines.append(f"> [!{exc['type']}]")
            for content_line in exc["content"].split("\n"):
                lines.append(f"> {content_line}")
            lines.append("")

    content = "\n".join(lines)

    if dry_run:
        result["preview"] = content[:600]
        return result

    output_full = _safe_path(vault, output_path)
    output_full.parent.mkdir(parents=True, exist_ok=True)
    _write_text(output_full, content)
    result["writtenTo"] = output_path
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

```
python -m unittest tests.test_obsidian_vault_mcp -v -k "test_reading_digest"
```

Expected: PASS (4 tests)

- [ ] **Step 5: Run the full test suite to ensure no regressions**

```
python -m unittest tests.test_obsidian_vault_mcp -v
```

Expected: all tests PASS

- [ ] **Step 6: Run linter**

```
python -m ruff check scripts/obsidian_vault_mcp/tools.py
```

Expected: no errors (E501 line-length is ignored per pyproject.toml)

- [ ] **Step 7: Commit**

```
git add scripts/obsidian_vault_mcp/tools.py tests/test_obsidian_vault_mcp.py
git commit -m "feat: add obsidian_build_reading_digest to aggregate callout blocks by tag or type"
```

---

## Self-Review

**Spec coverage check:**

| Feature | Task | Status |
|---------|------|--------|
| 1. Dead link detection + fix | Task 4 `obsidian_find_broken_links` | ✓ |
| 2. Zotero incremental sync | Task 6 modify `obsidian_ingest_zotero_collection` | ✓ |
| 3. Orphan note detection | Task 3 `obsidian_find_orphans` | ✓ |
| 4. Batch file operations | Task 5 `obsidian_batch_move_files` | ✓ |
| 5. Citation network | Task 8 `obsidian_build_citation_network` | ✓ |
| 6. MinerU batch PDF | Task 7 `obsidian_mineru_extract_folder` | ✓ |
| 7. Annotation stats view | Task 9 `obsidian_build_reading_digest` | ✓ |
| 8. Search context lines | Task 1 `obsidian_search context_lines` | ✓ |
| 9. Vault statistics | Task 2 `obsidian_vault_stats` | ✓ |

**Placeholder scan:** No TBD, TODO, or "similar to Task N" patterns. All code blocks are complete.

**Type consistency check:**
- `obsidian_find_broken_links` uses `WIKILINK_RE` (defined in common.py ✓), `MARKDOWN_LINK_RE` (defined in common.py ✓), `_normalize_note_key` (helpers.py ✓), `_target_from_link` (helpers.py ✓), `unquote` (common.py imports `from urllib.parse import unquote` ✓)
- `obsidian_batch_move_files` calls `obsidian_move_file` (tools.py ✓), uses `_frontmatter_tags` and `_inline_tags` (helpers.py ✓)
- `obsidian_vault_stats` calls `obsidian_build_graph` (tools.py ✓), uses `_iter_files` (helpers.py ✓)
- `obsidian_find_orphans` calls `obsidian_build_graph` (tools.py ✓), uses `_configured_path` (helpers.py ✓)
- `obsidian_build_citation_network` uses `_listify` (helpers.py ✓), `DEFAULT_EXCLUDES` (common.py ✓), `_join_frontmatter` (helpers.py ✓)
- `obsidian_build_reading_digest` uses `_frontmatter_tags`, `_inline_tags`, `_iter_files`, `_split_frontmatter`, `_write_text`, `_safe_path` — all helpers.py ✓; `datetime`, `timezone` imported in common.py ✓
- `obsidian_mineru_extract_folder` calls `obsidian_mineru_extract` and `obsidian_ingest_mineru_markdown` — both defined in tools.py ✓

**Edge cases confirmed in tests:**
- `test_search_context_lines_clips_at_file_boundaries` — start-of-file and end-of-file ✓
- `test_find_broken_links_fix_keeps_alias_text` — `[[Ghost|Label]]` → `Label` ✓
- `test_build_citation_network_skips_self_references` — self-citing note ✓
- `test_reading_digest_skips_files_outside_since_days` — time filtering ✓
