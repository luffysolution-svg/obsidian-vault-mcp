# Wiki Stale Pages Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `obsidian_wiki_stale_pages` tool that scans `wiki/` for pages superseded by new vault content, returning a ranked list for LLM-driven regeneration decisions.

**Architecture:** Single `@tool()` function in `tools.py` delegating to `_stale_wiki_pages_scan` in `helpers.py`. Two staleness signals: (1) `related` frontmatter links with `st_mtime` after page creation and within `since_days` window; (2) vault notes matching title keywords with the same mtime condition. Three small private helpers handle timestamp parsing and keyword tokenisation.

**Tech Stack:** Python stdlib only — `time`, `datetime`, `re`, `pathlib`. No new dependencies. All helpers reuse existing `_read_text`, `_iter_files`, `_split_frontmatter`, `_safe_path`, `_rel`, `_ensure_md_path`.

---

## File Map

| File | Change |
|---|---|
| `scripts/obsidian_vault_mcp/helpers.py` | Append 3 helpers: `_parse_created_ts`, `_title_keywords`, `_stale_wiki_pages_scan` |
| `scripts/obsidian_vault_mcp/tools.py` | Append 1 tool: `obsidian_wiki_stale_pages` |
| `tests/test_obsidian_vault_mcp.py` | Append 6 tests inside `ObsidianVaultMcpTests` |
| `pyproject.toml` | Bump `version` from `1.0.24` → `1.0.25` |

---

## Task 1: Helper `_parse_created_ts` + `_title_keywords`

**Files:**
- Modify: `scripts/obsidian_vault_mcp/helpers.py` (append after line 2910)
- Test: `tests/test_obsidian_vault_mcp.py` (no direct test — covered via integration tests in Task 2)

- [ ] **Step 1: Append the two helpers to the end of `helpers.py`**

```python
def _parse_created_ts(props: "dict[str, Any]", path: "Path") -> float:
    """Return Unix timestamp for when a wiki page was created.

    Prefers the ISO ``created`` frontmatter field written by
    ``obsidian_write_wiki_page``; falls back to ``st_birthtime`` (Windows /
    macOS) then ``st_mtime``.
    """
    created = _s(props.get("created")).strip()
    if created:
        try:
            ts = datetime.fromisoformat(created.replace("Z", "+00:00"))
            return ts.timestamp()
        except Exception:
            pass
    try:
        stat = path.stat()
        return getattr(stat, "st_birthtime", stat.st_mtime)
    except Exception:
        return 0.0


def _title_keywords(title: str) -> list[str]:
    """Tokenise *title* into lowercase search keywords.

    Splits on whitespace and common punctuation.  Keeps tokens that are either
    2+ characters long OR a single CJK ideograph (U+4E00–U+9FFF), because a
    single Chinese character is a meaningful unit while a single Latin letter
    is not.
    """
    tokens = re.split(r"[\s/\-_,;:。，、　！？.!?]+", title.lower())
    result: list[str] = []
    for t in tokens:
        if not t:
            continue
        if len(t) >= 2 or ("一" <= t <= "鿿"):
            result.append(t)
    return result
```

- [ ] **Step 2: Verify the file ends cleanly**

```bash
python -c "
import importlib.util, pathlib
spec = importlib.util.spec_from_file_location('h', 'scripts/obsidian_vault_mcp/helpers.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
print('_parse_created_ts' in dir(m), '_title_keywords' in dir(m))
"
```

Expected output: `True True`

---

## Task 2: Helper `_stale_wiki_pages_scan`

**Files:**
- Modify: `scripts/obsidian_vault_mcp/helpers.py` (append after `_title_keywords`)
- Test: `tests/test_obsidian_vault_mcp.py`

- [ ] **Step 1: Write the 6 failing tests** — append inside `ObsidianVaultMcpTests` before the final `if __name__ == "__main__":` block

```python
    # ------------------------------------------------------- #
    # obsidian_wiki_stale_pages                               #
    # ------------------------------------------------------- #

    def test_stale_pages_related_modified(self):
        import os, time
        from datetime import datetime, timezone, timedelta

        def iso_ago(days):
            return (
                (datetime.now(timezone.utc) - timedelta(days=days))
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z")
            )

        now = time.time()
        # Wiki page created 10 days ago
        self.write_note(
            "wiki/reactor.md",
            f"---\ntitle: Reactor\ntype: wiki\ncreated: {iso_ago(10)}\nrelated:\n  - entities/agitator.md\n---\n\n## Overview\n\nContent.\n",
        )
        os.utime(self.vault / "wiki" / "reactor.md", (now - 10 * 86400, now - 10 * 86400))

        # Related note modified 2 days ago (within since_days=7, after page created)
        self.write_note("entities/agitator.md", "---\ntitle: Agitator\n---\n\n# Agitator\n")
        os.utime(self.vault / "entities" / "agitator.md", (now - 2 * 86400, now - 2 * 86400))

        result = self.module.obsidian_wiki_stale_pages(
            vault_path=str(self.vault), min_age_days=7, since_days=7
        )

        self.assertEqual(result["staleCount"], 1)
        page = result["stalePages"][0]
        self.assertIn("related_modified", page["reasons"])
        self.assertIn("entities/agitator.md", page["modifiedRelated"])
        self.assertEqual(page["title"], "Reactor")
        self.assertGreaterEqual(page["daysSinceCreated"], 9)

    def test_stale_pages_new_notes_keyword(self):
        import os, time
        from datetime import datetime, timezone, timedelta

        def iso_ago(days):
            return (
                (datetime.now(timezone.utc) - timedelta(days=days))
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z")
            )

        now = time.time()
        # Wiki page created 10 days ago, no related field
        self.write_note(
            "wiki/reactor.md",
            f"---\ntitle: Reactor\ntype: wiki\ncreated: {iso_ago(10)}\n---\n\n## Overview\n\nContent.\n",
        )
        os.utime(self.vault / "wiki" / "reactor.md", (now - 10 * 86400, now - 10 * 86400))

        # New source note modified 2 days ago containing title keyword "reactor"
        self.write_note("sources/new_paper.md", "---\ntitle: New Paper\n---\n\n# About reactor design\n")
        os.utime(self.vault / "sources" / "new_paper.md", (now - 2 * 86400, now - 2 * 86400))

        result = self.module.obsidian_wiki_stale_pages(
            vault_path=str(self.vault), min_age_days=7, since_days=7
        )

        self.assertEqual(result["staleCount"], 1)
        page = result["stalePages"][0]
        self.assertIn("new_notes", page["reasons"])
        paths = [n["path"] for n in page["newNotes"]]
        self.assertIn("sources/new_paper.md", paths)

    def test_stale_pages_min_age_filters_new_pages(self):
        import os, time
        from datetime import datetime, timezone, timedelta

        def iso_ago(days):
            return (
                (datetime.now(timezone.utc) - timedelta(days=days))
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z")
            )

        now = time.time()
        # Wiki page created only 3 days ago (< min_age_days=7) — should be skipped
        self.write_note(
            "wiki/fresh.md",
            f"---\ntitle: Fresh\ntype: wiki\ncreated: {iso_ago(3)}\nrelated:\n  - entities/agitator.md\n---\n\n## Overview\n",
        )
        os.utime(self.vault / "wiki" / "fresh.md", (now - 3 * 86400, now - 3 * 86400))

        self.write_note("entities/agitator.md", "---\ntitle: Agitator\n---\n\n# Agitator\n")
        os.utime(self.vault / "entities" / "agitator.md", (now - 1 * 86400, now - 1 * 86400))

        result = self.module.obsidian_wiki_stale_pages(
            vault_path=str(self.vault), min_age_days=7, since_days=7
        )

        self.assertEqual(result["staleCount"], 0)
        self.assertEqual(result["checkedCount"], 0)

    def test_stale_pages_since_days_window(self):
        import os, time
        from datetime import datetime, timezone, timedelta

        def iso_ago(days):
            return (
                (datetime.now(timezone.utc) - timedelta(days=days))
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z")
            )

        now = time.time()
        # Wiki page created 30 days ago
        self.write_note(
            "wiki/old.md",
            f"---\ntitle: OldPage\ntype: wiki\ncreated: {iso_ago(30)}\nrelated:\n  - entities/thing.md\n---\n\n## Overview\n",
        )
        os.utime(self.vault / "wiki" / "old.md", (now - 30 * 86400, now - 30 * 86400))

        # Related note modified 10 days ago — OUTSIDE since_days=7 window
        self.write_note("entities/thing.md", "---\ntitle: Thing\n---\n\n# Thing\n")
        os.utime(self.vault / "entities" / "thing.md", (now - 10 * 86400, now - 10 * 86400))

        result = self.module.obsidian_wiki_stale_pages(
            vault_path=str(self.vault), min_age_days=7, since_days=7
        )

        # Signal 1 should NOT fire because related note was modified 10 days ago (outside 7-day window)
        stale_paths = [p["path"] for p in result["stalePages"]]
        self.assertNotIn("wiki/old.md", stale_paths)

    def test_stale_pages_no_related_field(self):
        import os, time
        from datetime import datetime, timezone, timedelta

        def iso_ago(days):
            return (
                (datetime.now(timezone.utc) - timedelta(days=days))
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z")
            )

        now = time.time()
        # Wiki page with no 'related' field — Signal 1 skipped, should not crash
        self.write_note(
            "wiki/no_related.md",
            f"---\ntitle: NoRelated\ntype: wiki\ncreated: {iso_ago(10)}\n---\n\n## Overview\n",
        )
        os.utime(self.vault / "wiki" / "no_related.md", (now - 10 * 86400, now - 10 * 86400))

        # No matching vault notes either
        result = self.module.obsidian_wiki_stale_pages(
            vault_path=str(self.vault), min_age_days=7, since_days=7
        )

        # Should complete without error; no false positives
        self.assertIsInstance(result["stalePages"], list)
        self.assertEqual(result["staleCount"], 0)

    def test_stale_pages_top_n_limit(self):
        import os, time
        from datetime import datetime, timezone, timedelta

        def iso_ago(days):
            return (
                (datetime.now(timezone.utc) - timedelta(days=days))
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z")
            )

        now = time.time()
        # Create 3 stale wiki pages all with a modified related note
        for i in range(3):
            slug = f"page{i}"
            self.write_note(
                f"wiki/{slug}.md",
                f"---\ntitle: Page{i}\ntype: wiki\ncreated: {iso_ago(10)}\nrelated:\n  - entities/e{i}.md\n---\n\n## Overview\n",
            )
            os.utime(self.vault / "wiki" / f"{slug}.md", (now - 10 * 86400, now - 10 * 86400))
            self.write_note(f"entities/e{i}.md", f"---\ntitle: E{i}\n---\n\n# E{i}\n")
            os.utime(self.vault / "entities" / f"e{i}.md", (now - 2 * 86400, now - 2 * 86400))

        result = self.module.obsidian_wiki_stale_pages(
            vault_path=str(self.vault), min_age_days=7, since_days=7, top_n=2
        )

        self.assertLessEqual(len(result["stalePages"]), 2)
        self.assertEqual(result["staleCount"], 2)
```

- [ ] **Step 2: Run tests to confirm they all fail**

```bash
cd "F:\化工设计比赛\plugins\obsidian-vault"
python -m pytest tests/test_obsidian_vault_mcp.py -k "stale_pages" -v 2>&1 | tail -20
```

Expected: 6 failures — `AttributeError: module ... has no attribute 'obsidian_wiki_stale_pages'`

- [ ] **Step 3: Append `_stale_wiki_pages_scan` to `helpers.py`** (after `_title_keywords`)

```python
def _stale_wiki_pages_scan(
    vault: "Path",
    wiki_folder: str,
    min_age_days: int,
    since_days: int,
    max_new_notes: int,
    top_n: int,
) -> "tuple[list[dict[str, Any]], int]":
    """Scan *wiki_folder* for pages with stale content.

    Returns ``(stale_pages, checked_count)`` where *checked_count* is the
    number of wiki pages that were old enough to inspect (passed
    *min_age_days*).
    """
    import time as _time

    now = _time.time()
    age_cutoff = now - min_age_days * 86400     # page must be OLDER than this
    change_cutoff = now - since_days * 86400    # changes must be NEWER than this

    wiki_root = _safe_path(vault, wiki_folder) if wiki_folder else vault / "wiki"
    if not wiki_root.exists():
        return [], 0

    stale: list[dict[str, Any]] = []
    checked = 0

    for path in sorted(wiki_root.rglob("*.md")):
        try:
            text = _read_text(path)
        except Exception:
            continue

        props, _ = _split_frontmatter(text)
        page_created = _parse_created_ts(props, path)

        if page_created > age_cutoff:
            continue  # page too new — skip without incrementing checked
        checked += 1

        title = str(props.get("title") or path.stem)
        rel = _rel(vault, path)

        # ── Signal 1: related notes modified within window ──────────────
        modified_related: list[str] = []
        related_raw = props.get("related") or []
        if isinstance(related_raw, list):
            for r in related_raw:
                r_str = _s(r).strip()
                if not r_str:
                    continue
                r_rel = _ensure_md_path(r_str)
                try:
                    r_full = _safe_path(vault, r_rel)
                    if r_full.exists():
                        r_mtime = r_full.stat().st_mtime
                        if page_created < r_mtime and r_mtime >= change_cutoff:
                            modified_related.append(r_rel)
                except Exception:
                    continue

        # ── Signal 2: new vault notes matching title keywords ────────────
        new_notes: list[dict[str, Any]] = []
        keywords = _title_keywords(title)
        if keywords:
            for f in _iter_files(vault):
                if f.suffix.lower() != ".md":
                    continue
                # Exclude files inside the wiki folder itself
                try:
                    f.relative_to(wiki_root)
                    continue
                except ValueError:
                    pass
                try:
                    f_mtime = f.stat().st_mtime
                    if page_created < f_mtime and f_mtime >= change_cutoff:
                        content = _read_text(f).lower()
                        if any(kw in content for kw in keywords):
                            days_ago = int((now - f_mtime) / 86400)
                            new_notes.append({"path": _rel(vault, f), "mtimeDays": days_ago})
                            if len(new_notes) >= max_new_notes:
                                break
                except Exception:
                    continue

        if not modified_related and not new_notes:
            continue

        reasons: list[str] = []
        if modified_related:
            reasons.append("related_modified")
        if new_notes:
            reasons.append("new_notes")

        stale.append({
            "path": rel,
            "title": title,
            "daysSinceCreated": int((now - page_created) / 86400),
            "reasons": reasons,
            "modifiedRelated": modified_related,
            "newNotes": new_notes,
            "newNeighborCount": len(modified_related) + len(new_notes),
        })

    stale.sort(key=lambda x: x["newNeighborCount"], reverse=True)
    return stale[:top_n], checked
```

- [ ] **Step 4: Verify helpers load cleanly**

```bash
python -c "
import importlib.util
spec = importlib.util.spec_from_file_location('h', 'scripts/obsidian_vault_mcp/helpers.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
print('_stale_wiki_pages_scan' in dir(m))
"
```

Expected: `True`

---

## Task 3: Tool `obsidian_wiki_stale_pages`

**Files:**
- Modify: `scripts/obsidian_vault_mcp/tools.py` (append after last `@tool()` at line 3989)

- [ ] **Step 1: Append the tool to the end of `tools.py`**

```python


@tool()
def obsidian_wiki_stale_pages(
    vault_path: str = "",
    wiki_folder: str = "wiki",
    min_age_days: int = 7,
    since_days: int = 7,
    max_new_notes: int = 5,
    top_n: int = 50,
) -> dict[str, Any]:
    """Scan the wiki folder for pages that may need regeneration.

    Returns pages where at least one of these signals fires within the
    last since_days days AND after the page was originally created:

    - ``related_modified``: a note listed in the page's ``related``
      frontmatter field has been modified.
    - ``new_notes``: a vault note (outside wiki_folder) whose content
      contains the page's title keywords has been modified.

    Only pages whose ``created`` timestamp is at least min_age_days old
    are examined.  Results are sorted by newNeighborCount descending
    (most stale first) and capped at top_n.

    Use the returned stalePages list to decide which wiki pages to
    regenerate via obsidian_wiki_context + obsidian_write_wiki_page.
    """
    vault = _vault(vault_path)
    stale_pages, checked_count = _stale_wiki_pages_scan(
        vault, wiki_folder, min_age_days, since_days, max_new_notes, top_n
    )
    return {
        "stalePages": stale_pages,
        "checkedCount": checked_count,
        "staleCount": len(stale_pages),
        "wikiFolder": wiki_folder,
        "minAgeDays": min_age_days,
        "sinceDays": since_days,
    }
```

- [ ] **Step 2: Run the 6 stale-pages tests**

```bash
python -m pytest tests/test_obsidian_vault_mcp.py -k "stale_pages" -v 2>&1 | tail -15
```

Expected: 6 passed

- [ ] **Step 3: Run the full test suite**

```bash
python -m pytest tests/test_obsidian_vault_mcp.py -v 2>&1 | tail -10
```

Expected: all 152 existing tests + 6 new = **158 passed, 0 failed**

- [ ] **Step 4: Commit**

```bash
git add scripts/obsidian_vault_mcp/helpers.py scripts/obsidian_vault_mcp/tools.py tests/test_obsidian_vault_mcp.py
git commit -m "feat: add obsidian_wiki_stale_pages for wiki page staleness detection"
```

---

## Task 4: Version Bump

**Files:**
- Modify: `pyproject.toml` line 7

- [ ] **Step 1: Bump version**

In `pyproject.toml`, change:
```toml
version = "1.0.24"
```
to:
```toml
version = "1.0.25"
```

- [ ] **Step 2: Commit**

```bash
git add pyproject.toml
git commit -m "chore: bump version to 1.0.25"
```

---

## Task 5: Real-World Test Against Live Vault

- [ ] **Step 1: Find the real vault path**

Check the Obsidian vault path (usually `C:\Users\Administrator\...` or similar). The MCP server's `vault_path` defaults to the active CLI vault if unset.

- [ ] **Step 2: Call the tool via the MCP server**

```python
# Run in a Python shell or via MCP client
import sys
sys.path.insert(0, "scripts")
import obsidian_vault_mcp as m

result = m.obsidian_wiki_stale_pages(
    vault_path=r"<REAL_VAULT_PATH>",
    since_days=30,
    min_age_days=3,
)
import json
print(json.dumps(result, indent=2, ensure_ascii=False))
```

- [ ] **Step 3: Validate results**

Check that:
- `checkedCount` > 0 if there are wiki pages older than 3 days
- `stalePages` entries have correct `path`, `title`, `reasons` fields
- No Python errors or tracebacks

- [ ] **Step 4: Report outcome** — if results look correct, proceed to Task 6. If unexpected output, investigate before continuing.

---

## Task 6: Push to GitHub and Publish to PyPI

- [ ] **Step 1: Push to GitHub**

```bash
"F:\化工设计比赛\tools\gh\gh.exe" repo view  # confirm correct repo
git push origin main
```

- [ ] **Step 2: Build the package**

```bash
python -m build
```

Expected: `dist/zotero_obsidian_mcp-1.0.25-py3-none-any.whl` and `.tar.gz` created.

- [ ] **Step 3: Publish to PyPI**

```bash
python -m twine upload dist/zotero_obsidian_mcp-1.0.25* --username __token__ --password pypi-AgEIcHlwaS5vcmcCJGQ0YmM0YmU1LWZjZTQtNDVjNC1iODRhLWNjMTI4MTNjMjNhMwACG1sxLFsiem90ZXJvLW9ic2lkaWFuLW1jcCJdXQ ACLFsyLFsiYTgyYjcwMDctNTY3Zi00N2I0LWIzYzgtYzk3Yjc2Yzg0MmRiIl1dAAAGIA1TghyWJK66oz8i4wDCaYRP4sQofaopqN1nCHhDQn4Q
```

- [ ] **Step 4: Verify on PyPI**

Check that `zotero-obsidian-mcp 1.0.25` appears on PyPI (wait ~60 seconds for index update).

---

## Self-Review Notes

- **Spec coverage:** All 4 spec sections implemented. Three helpers + one tool. Six tests match the testing strategy table exactly.
- **Placeholder scan:** No TBD/TODO. All code blocks contain complete implementations.
- **Type consistency:**
  - `_parse_created_ts(props, path) → float` used consistently in `_stale_wiki_pages_scan`
  - `_title_keywords(title) → list[str]` used consistently in `_stale_wiki_pages_scan`
  - `_stale_wiki_pages_scan(...) → tuple[list[dict], int]` unpacked correctly in `obsidian_wiki_stale_pages`
  - Return field `staleCount` = `len(stale_pages)` (not `checkedCount`) — consistent with spec
