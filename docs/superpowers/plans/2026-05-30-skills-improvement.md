# Skills Improvement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade Canvas layout docs, add obsidian-ai-summary skill, fix cross-skill AI Summary references, and publish v1.1.3.

**Architecture:** Edit authoritative `skills/<name>/SKILL.md` first, then mechanically sync to `scripts/obsidian_vault_mcp/skills/<name>/SKILL.md` (full copy) and `.claude/skills/<name>.md` (bullet-point summary). New skill needs all three locations created. Version bump across 4 files before PyPI build.

**Tech Stack:** Markdown skill files, Python/pyproject.toml, JSON plugin manifests, PyPI (twine), GitHub Release (gh CLI).

**Note:** MCP server bugs (`Path.rename` → `Path.replace`, try/except around rename) are already committed in `68380e3`. This plan covers skills and publishing only.

---

## File Map

| Action | Path |
|--------|------|
| Modify | `skills/obsidian-views/SKILL.md` |
| Sync   | `scripts/obsidian_vault_mcp/skills/obsidian-views/SKILL.md` |
| Sync   | `.claude/skills/obsidian-views.md` |
| Modify | `skills/obsidian-zotero/SKILL.md` |
| Sync   | `scripts/obsidian_vault_mcp/skills/obsidian-zotero/SKILL.md` |
| Sync   | `.claude/skills/obsidian-zotero.md` |
| Modify | `skills/obsidian-mineru/SKILL.md` |
| Sync   | `scripts/obsidian_vault_mcp/skills/obsidian-mineru/SKILL.md` |
| Sync   | `.claude/skills/obsidian-mineru.md` |
| Modify | `skills/obsidian-vault/SKILL.md` |
| Sync   | `scripts/obsidian_vault_mcp/skills/obsidian-vault/SKILL.md` |
| Sync   | `.claude/skills/obsidian-vault.md` |
| Create | `skills/obsidian-ai-summary/SKILL.md` |
| Create | `scripts/obsidian_vault_mcp/skills/obsidian-ai-summary/SKILL.md` |
| Create | `.claude/skills/obsidian-ai-summary.md` |
| Modify | `pyproject.toml` |
| Modify | `.codex-plugin/plugin.json` |
| Modify | `.claude-plugin/plugin.json` |

---

## Task 1: Upgrade obsidian-views Canvas section

**Files:**
- Modify: `skills/obsidian-views/SKILL.md`

- [ ] **Step 1: Replace the sparse Layouts block with complete content**

In `skills/obsidian-views/SKILL.md`, replace:

```
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
```

With:

```
**Kepano detection:** Before generating any Canvas, check whether `skills/json-canvas/SKILL.md` (project) or `.claude/skills/json-canvas.md` (user) exists. If found, invoke that skill instead of the built-in section below.

**Layouts — coordinate formulas:**
- **Grid:** `x = col * (nodeWidth + 60)`, `y = row * (nodeHeight + 40)`. Fill columns first, max 4 nodes per row.
- **Radial:** `x = cx + r * cos(2π * i / n)`, `y = cy + r * sin(2π * i / n)`. Radius `r = max(200, n * 60)`.
- **Layered (DAG):** Topological sort to get depth `d`; `x = d * 320`; nodes at same depth share `y` evenly. Recommended for 5+ nodes with a clear dependency direction.
- **Grouped:** Place group nodes first; constrain member coordinates within group bounds with 30 px inner padding.

**Overlap detection:** After placing all nodes, check every pair for bounding-box intersection:
`overlap = !(ax+aw ≤ bx || bx+bw ≤ ax || ay+ah ≤ by || by+bh ≤ ay)`
If overlap found, shift the later node right by `overlapWidth + 40`.

**Colors:**

| Preset | Color | Preset | Color |
|--------|-------|--------|-------|
| `"1"` | Red | `"4"` | Green |
| `"2"` | Orange | `"5"` | Cyan |
| `"3"` | Yellow | `"6"` | Purple |

Omit the `color` field entirely when no colour is needed.

**Node size guidelines:**

| Type | width | height |
|------|-------|--------|
| Small text / label | 200–300 | 80–150 |
| Normal note card | 250–400 | 150–250 |
| Large card / file preview | 400–500 | 250–400 |

**ID generation:** 16-character lowercase hex string, e.g. `"6f0ad84f44ce9c17"`. Never reuse an existing node or edge id.

**Steps to create a Canvas from vault links:**
1. `obsidian_search` with `query=""` to get all notes.
2. `obsidian_read_file` each note to extract `[[wikilinks]]`.
3. Build node list (one node per note) and edge list (one edge per link).
4. Apply layout using the coordinate formulas above.
5. Run overlap detection; adjust positions if needed.
6. `obsidian_write_file` the JSON to `<path>.canvas`.

**Visual validation (pure JSON — after writing the file):**
1. `obsidian_read_file` the written `.canvas` file.
2. Output a position summary table for quick scan:
   ```
   id       type   x     y     w    h
   ──────────────────────────────────
   a1b2c3   file     0     0   300  150
   d4e5f6   file   360     0   300  150
   ```
3. Run bounding-box overlap check on all node pairs; report any overlapping pairs.
4. Check total canvas span: `(max_x − min_x)` and `(max_y − min_y)` should be < 3000 px.
5. Verify every edge `fromNode`/`toNode` exists in the node list.

**Validation checklist:**
1. All `id` values unique across nodes and edges.
2. Every `fromNode`/`toNode` references an existing node id.
3. `type` is one of `text`, `file`, `link`, `group`.
4. `fromSide`/`toSide` is one of `top`, `right`, `bottom`, `left`.
5. `fromEnd`/`toEnd` is one of `none`, `arrow`.
6. Color presets are `"1"`–`"6"` or valid hex (e.g. `"#FF0000"`).
7. JSON is valid and parseable.
```

- [ ] **Step 2: Verify the edit**

Run: `python -c "f=open('skills/obsidian-views/SKILL.md').read(); assert 'Kepano detection' in f; assert 'Overlap detection' in f; assert 'Visual validation' in f; assert 'Validation checklist' in f; print('ok')"`

Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add skills/obsidian-views/SKILL.md
git commit -m "docs(skill): upgrade obsidian-views Canvas with layout formulas, visual validation, kepano detection"
```

---

## Task 2: Sync obsidian-views to mirror locations

**Files:**
- Modify: `scripts/obsidian_vault_mcp/skills/obsidian-views/SKILL.md`
- Modify: `.claude/skills/obsidian-views.md`

- [ ] **Step 1: Copy authoritative file to PyPI mirror**

```bash
cp skills/obsidian-views/SKILL.md scripts/obsidian_vault_mcp/skills/obsidian-views/SKILL.md
```

- [ ] **Step 2: Update `.claude/skills/obsidian-views.md` summary**

Replace the entire content of `.claude/skills/obsidian-views.md` with:

```markdown
---
name: obsidian-views
description: "Create Canvas maps, Obsidian Bases, or Dataview notes. 创建 Canvas、Bases 或 Dataview 视图时使用。"
---

Use `obsidian_write_file` to write views. Use `obsidian_search` + `obsidian_read_file` first to gather vault data.

- **Canvas**: write JSON `{nodes:[...], edges:[...]}` to `<name>.canvas`. **Kepano detection first**: if `skills/json-canvas/SKILL.md` or `.claude/skills/json-canvas.md` exists, invoke that skill. Built-in fallback: Grid `x=col*(w+60), y=row*(h+40)`; Radial `x=cx+r*cos(2πi/n), y=cy+r*sin(2πi/n)` r=max(200,n*60); Layered (DAG) topo-sort → `x=d*320`; Grouped 30px padding. Overlap check: `!(ax+aw≤bx||bx+bw≤ax||ay+ah≤by||by+bh≤ay)`, shift right by `overlapW+40`. Colors: "1"=Red "2"=Orange "3"=Yellow "4"=Green "5"=Cyan "6"=Purple. Node sizes: small 200–300×80–150, card 250–400×150–250, large 400–500×250–400. IDs: 16-char lowercase hex. After writing: read back → position table → overlap check → span < 3000px → edge refs valid.
- **Bases**: write YAML `{filters:{and:[...]}, views:[{type:table, columns:[...]}]}` to `<name>.base`.
- **Dataview**: write a `.md` file with ` ```dataview TABLE ... FROM ... ``` ` blocks.
```

- [ ] **Step 3: Verify mirrors match authoritative**

```bash
diff skills/obsidian-views/SKILL.md scripts/obsidian_vault_mcp/skills/obsidian-views/SKILL.md
```

Expected: no output (files identical).

- [ ] **Step 4: Commit**

```bash
git add scripts/obsidian_vault_mcp/skills/obsidian-views/SKILL.md .claude/skills/obsidian-views.md
git commit -m "chore(sync): sync obsidian-views skill to PyPI mirror and Claude summary"
```

---

## Task 3: Update obsidian-zotero cross-reference

**Files:**
- Modify: `skills/obsidian-zotero/SKILL.md`

- [ ] **Step 1: Update Re-ingest Behavior section**

In `skills/obsidian-zotero/SKILL.md`, replace:

```
- The plugin does not generate AI summaries; skills may write that section later.
```

With:

```
- The plugin does not generate AI summaries. Use the `obsidian-ai-summary` skill to generate or update that section — it can be triggered after import or via `obsidian_pipeline_ingest_item(write_ai_summary=true)`.
```

- [ ] **Step 2: Verify**

```bash
python -c "f=open('skills/obsidian-zotero/SKILL.md').read(); assert 'obsidian-ai-summary' in f; assert 'write_ai_summary=true' in f; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add skills/obsidian-zotero/SKILL.md
git commit -m "docs(skill): point obsidian-zotero AI Summary ref to obsidian-ai-summary skill"
```

---

## Task 4: Sync obsidian-zotero to mirror locations

**Files:**
- Modify: `scripts/obsidian_vault_mcp/skills/obsidian-zotero/SKILL.md`
- Modify: `.claude/skills/obsidian-zotero.md`

- [ ] **Step 1: Copy authoritative file to PyPI mirror**

```bash
cp skills/obsidian-zotero/SKILL.md scripts/obsidian_vault_mcp/skills/obsidian-zotero/SKILL.md
```

- [ ] **Step 2: Update `.claude/skills/obsidian-zotero.md` summary**

In `.claude/skills/obsidian-zotero.md`, append this line after the `Always preserve user's ## Reading Notes` line:

```markdown
- **AI Summary**: use `obsidian-ai-summary` skill after import, or pass `write_ai_summary=true` to `obsidian_pipeline_ingest_item`.
```

- [ ] **Step 3: Verify mirror**

```bash
diff skills/obsidian-zotero/SKILL.md scripts/obsidian_vault_mcp/skills/obsidian-zotero/SKILL.md
```

Expected: no output.

- [ ] **Step 4: Commit**

```bash
git add scripts/obsidian_vault_mcp/skills/obsidian-zotero/SKILL.md .claude/skills/obsidian-zotero.md
git commit -m "chore(sync): sync obsidian-zotero skill to mirrors"
```

---

## Task 5: Update obsidian-mineru cross-reference

**Files:**
- Modify: `skills/obsidian-mineru/SKILL.md`

- [ ] **Step 1: Update Output Expectations section**

In `skills/obsidian-mineru/SKILL.md`, replace:

```
- Literature notes are stable user workspaces; preserve custom YAML, `Reading Notes`, and `AI Summary`.
```

With:

```
- Literature notes are stable user workspaces; preserve custom YAML, `Reading Notes`, and `AI Summary`. To generate or update `## AI Summary` after parsing, use the `obsidian-ai-summary` skill. It can also be triggered via `obsidian_pipeline_parse_with_mineru(write_ai_summary=true)`.
```

- [ ] **Step 2: Verify**

```bash
python -c "f=open('skills/obsidian-mineru/SKILL.md').read(); assert 'obsidian-ai-summary' in f; assert 'parse_with_mineru(write_ai_summary=true)' in f; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add skills/obsidian-mineru/SKILL.md
git commit -m "docs(skill): point obsidian-mineru AI Summary ref to obsidian-ai-summary skill"
```

---

## Task 6: Sync obsidian-mineru to mirror locations

**Files:**
- Modify: `scripts/obsidian_vault_mcp/skills/obsidian-mineru/SKILL.md`
- Modify: `.claude/skills/obsidian-mineru.md`

- [ ] **Step 1: Copy authoritative file to PyPI mirror**

```bash
cp skills/obsidian-mineru/SKILL.md scripts/obsidian_vault_mcp/skills/obsidian-mineru/SKILL.md
```

- [ ] **Step 2: Update `.claude/skills/obsidian-mineru.md` summary**

In `.claude/skills/obsidian-mineru.md`, append after the last bullet point:

```markdown
- **AI Summary**: after parsing, use `obsidian-ai-summary` skill, or pass `write_ai_summary=true` to `obsidian_pipeline_parse_with_mineru`.
```

- [ ] **Step 3: Verify mirror**

```bash
diff skills/obsidian-mineru/SKILL.md scripts/obsidian_vault_mcp/skills/obsidian-mineru/SKILL.md
```

Expected: no output.

- [ ] **Step 4: Commit**

```bash
git add scripts/obsidian_vault_mcp/skills/obsidian-mineru/SKILL.md .claude/skills/obsidian-mineru.md
git commit -m "chore(sync): sync obsidian-mineru skill to mirrors"
```

---

## Task 7: Update obsidian-vault Safety section

**Files:**
- Modify: `skills/obsidian-vault/SKILL.md`

- [ ] **Step 1: Add AI Summary line to Safety section**

In `skills/obsidian-vault/SKILL.md`, replace:

```
- When Obsidian desktop is open, prefer the `obsidian-cli` skill for moves and renames.
```

With:

```
- When Obsidian desktop is open, prefer the `obsidian-cli` skill for moves and renames.
- To generate AI summaries for literature notes, use the `obsidian-ai-summary` skill.
```

- [ ] **Step 2: Verify**

```bash
python -c "f=open('skills/obsidian-vault/SKILL.md').read(); assert 'obsidian-ai-summary' in f; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add skills/obsidian-vault/SKILL.md
git commit -m "docs(skill): add AI Summary pointer to obsidian-vault Safety section"
```

---

## Task 8: Sync obsidian-vault to mirror locations

**Files:**
- Modify: `scripts/obsidian_vault_mcp/skills/obsidian-vault/SKILL.md`
- Modify: `.claude/skills/obsidian-vault.md`

- [ ] **Step 1: Copy authoritative file to PyPI mirror**

```bash
cp skills/obsidian-vault/SKILL.md scripts/obsidian_vault_mcp/skills/obsidian-vault/SKILL.md
```

- [ ] **Step 2: Update `.claude/skills/obsidian-vault.md` summary**

In `.claude/skills/obsidian-vault.md`, append after the last bullet point:

```markdown
- **AI Summary**: use `obsidian-ai-summary` skill to generate summaries for literature notes
```

- [ ] **Step 3: Verify mirror**

```bash
diff skills/obsidian-vault/SKILL.md scripts/obsidian_vault_mcp/skills/obsidian-vault/SKILL.md
```

Expected: no output.

- [ ] **Step 4: Commit**

```bash
git add scripts/obsidian_vault_mcp/skills/obsidian-vault/SKILL.md .claude/skills/obsidian-vault.md
git commit -m "chore(sync): sync obsidian-vault skill to mirrors"
```

---

## Task 9: Create obsidian-ai-summary skill (all 3 locations)

**Files:**
- Create: `skills/obsidian-ai-summary/SKILL.md`
- Create: `scripts/obsidian_vault_mcp/skills/obsidian-ai-summary/SKILL.md`
- Create: `.claude/skills/obsidian-ai-summary.md`

- [ ] **Step 1: Create authoritative SKILL.md**

Create `skills/obsidian-ai-summary/SKILL.md` with content:

````markdown
---
name: obsidian-ai-summary
description: "Generate and write AI Summary sections for Obsidian literature notes. Use when the user asks to summarize a paper, or when prompted after Zotero import or MinerU parsing. 当用户请求总结论文、Zotero 导入或 MinerU 解析完成后有 AI Summary 空白时使用。"
---

# Obsidian AI Summary

Generate and write `## AI Summary` sections in Obsidian literature notes.
处理文献笔记 AI 摘要的生成和写入时优先使用。

## Trigger Conditions

Run this skill when **any** of the following apply:

1. **Explicit request:** user says "write AI Summary", "summarize this paper", "fill in the summary".
2. **Post-import prompt:** after `obsidian-zotero` or `obsidian-mineru` completes, detect whether `## AI Summary` is absent or empty in the literature note → ask "Want to generate an AI Summary?".
3. **Pipeline flag:** `obsidian_pipeline_ingest_item(write_ai_summary=true)` or `obsidian_pipeline_parse_with_mineru(write_ai_summary=true)` triggers automatic execution (skill-level convention; server-side implementation is a separate task).

## Source Reading Priority

1. Check `mineruStatus` in note frontmatter via `obsidian_read_file`.
2. If `mineruStatus: parsed` → read `attachments/mineru/<zoteroKey>/paper.md` (richest source: full structured text + figure captions).
3. Otherwise → read the literature note body directly.
4. Always include existing `## Reading Notes` content as primary evidence.

**Budget:** ≤ 4 tool calls total (read note → optionally read MinerU md → write back → confirm).

## Standard Summary Template

Write exactly this structure into `## AI Summary`:

```markdown
## AI Summary

**Core Finding:** [One-sentence core conclusion.]

**Method:** [Methods, models, or experimental design used.]

**Dataset / Scope:** [Dataset name, scale, domain.]

**Limitations:** [Acknowledged or inferable limitations.]

**My Assessment:** [Relevance to current research direction, credibility, follow-up worth.]
```

## Write-back Procedure

1. `obsidian_read_file` the full literature note.
2. Locate `## AI Summary` section:
   - If present and non-empty → ask user before overwriting (unless triggered by pipeline flag).
   - If absent or empty → insert before `## Reading Notes` (or at end of note if no Reading Notes section exists).
3. Replace only the `## AI Summary` section content; leave all other sections untouched.
4. `obsidian_write_file` the updated note.
5. On re-ingest via `obsidian-zotero`, the `## AI Summary` section is preserved automatically.

## 中文说明

检测触发条件（显式请求 / 导入后提示 / 管道 flag），优先读取 MinerU 全文，按标准五节模板写入 `## AI Summary`，不触碰其他节内容。
````

- [ ] **Step 2: Verify authoritative file**

```bash
python -c "f=open('skills/obsidian-ai-summary/SKILL.md').read(); assert 'Trigger Conditions' in f; assert 'Standard Summary Template' in f; assert 'Write-back Procedure' in f; assert 'write_ai_summary=true' in f; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Copy to PyPI mirror**

```bash
cp skills/obsidian-ai-summary/SKILL.md scripts/obsidian_vault_mcp/skills/obsidian-ai-summary/SKILL.md
```

- [ ] **Step 4: Create Claude summary**

Create `.claude/skills/obsidian-ai-summary.md` with content:

```markdown
---
name: obsidian-ai-summary
description: "Generate and write ## AI Summary for literature notes. Use after Zotero import, MinerU parse, or explicit user request. 导入或解析后生成 AI Summary 时使用。"
---

- **Trigger**: user asks for summary; OR `## AI Summary` absent/empty after import/parse → prompt user
- **Pipeline flag**: `obsidian_pipeline_ingest_item(write_ai_summary=true)` or `obsidian_pipeline_parse_with_mineru(write_ai_summary=true)` → run automatically
- **Source priority**: `mineruStatus: parsed` → read `attachments/mineru/<key>/paper.md`; else read literature note body
- **Template** (5 sections): **Core Finding** / **Method** / **Dataset / Scope** / **Limitations** / **My Assessment**
- **Write-back**: `obsidian_read_file` → find/insert `## AI Summary` before `## Reading Notes` → replace only that section → `obsidian_write_file`
- Do not overwrite existing non-empty AI Summary unless triggered by pipeline flag or user confirms
- Budget: ≤ 4 tool calls
```

- [ ] **Step 5: Verify all 3 locations exist**

```bash
python -c "import os; [print('ok:', p) for p in ['skills/obsidian-ai-summary/SKILL.md','scripts/obsidian_vault_mcp/skills/obsidian-ai-summary/SKILL.md','.claude/skills/obsidian-ai-summary.md'] if os.path.exists(p)]"
```

Expected: three `ok:` lines.

- [ ] **Step 6: Commit**

```bash
git add skills/obsidian-ai-summary/ scripts/obsidian_vault_mcp/skills/obsidian-ai-summary/ .claude/skills/obsidian-ai-summary.md
git commit -m "feat(skill): add obsidian-ai-summary skill with trigger conditions, template, write-back procedure"
```

---

## Task 10: Version bump (1.1.2 → 1.1.3)

**Files:**
- Modify: `pyproject.toml`
- Modify: `.codex-plugin/plugin.json`
- Modify: `.claude-plugin/plugin.json`

- [ ] **Step 1: Bump pyproject.toml**

In `pyproject.toml`, replace:

```
version = "1.1.2"
```

With:

```
version = "1.1.3"
```

- [ ] **Step 2: Bump .codex-plugin/plugin.json**

In `.codex-plugin/plugin.json`, replace:

```
  "version": "1.1.2",
```

With:

```
  "version": "1.1.3",
```

- [ ] **Step 3: Bump .claude-plugin/plugin.json**

In `.claude-plugin/plugin.json`, replace:

```
  "version": "1.1.2",
```

With:

```
  "version": "1.1.3",
```

- [ ] **Step 4: Verify all four version fields agree**

```bash
python -c "
import tomllib, json
v_pyproject = tomllib.load(open('pyproject.toml','rb'))['project']['version']
v_codex = json.load(open('.codex-plugin/plugin.json'))['version']
v_claude = json.load(open('.claude-plugin/plugin.json'))['version']
assert v_pyproject == v_codex == v_claude == '1.1.3', f'mismatch: {v_pyproject} {v_codex} {v_claude}'
print('all versions == 1.1.3')
"
```

Expected: `all versions == 1.1.3`

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml .codex-plugin/plugin.json .claude-plugin/plugin.json
git commit -m "chore: bump to v1.1.3"
```

---

## Task 11: Build and upload to PyPI

- [ ] **Step 1: Clean previous build artifacts**

```bash
rm -rf dist/ build/ *.egg-info
```

(Windows PowerShell: `Remove-Item -Recurse -Force dist,build -ErrorAction SilentlyContinue`)

- [ ] **Step 2: Build wheel and sdist**

```bash
python -m build
```

Expected output ends with: `Successfully built obsidian_vault_mcp-1.1.3.tar.gz and obsidian_vault_mcp-1.1.3-py3-none-any.whl`

- [ ] **Step 3: Verify skills are included in the wheel**

```bash
python -c "
import zipfile, glob
whl = glob.glob('dist/*.whl')[0]
with zipfile.ZipFile(whl) as z:
    skills = [n for n in z.namelist() if 'skills' in n and 'SKILL.md' in n]
    print('\n'.join(sorted(skills)))
    assert any('obsidian-ai-summary' in s for s in skills), 'obsidian-ai-summary missing from wheel'
    print('wheel ok')
"
```

Expected: lists all SKILL.md paths including `obsidian-ai-summary`, ends with `wheel ok`.

- [ ] **Step 4: Upload to PyPI**

```bash
twine upload dist/*
```

Enter credentials when prompted (or use `~/.pypirc` / `TWINE_PASSWORD` env var).

Expected: `View at: https://pypi.org/project/obsidian-vault-mcp/1.1.3/`

---

## Task 12: Create GitHub Release

- [ ] **Step 1: Tag the commit**

```bash
git tag v1.1.3
git push origin main --tags
```

- [ ] **Step 2: Create the release zip**

```bash
git archive --format=zip --prefix=obsidian-vault-skills-1.1.3/ HEAD skills/ -o obsidian-vault-skills-1.1.3.zip
```

- [ ] **Step 3: Create GitHub Release**

```bash
gh release create v1.1.3 obsidian-vault-skills-1.1.3.zip \
  --title "v1.1.3 — Canvas layout algorithms, obsidian-ai-summary skill, MinerU rename fix" \
  --notes "## Changes

### New skill: obsidian-ai-summary
- Three trigger modes: explicit request, post-import prompt, pipeline flag \`write_ai_summary=true\`
- Source priority: MinerU full-text > literature note
- Standard 5-section template: Core Finding / Method / Dataset / Limitations / My Assessment
- Non-destructive write-back (preserves all other sections)

### obsidian-views — Canvas upgrade
- Kepano json-canvas skill detection (reference-first with built-in fallback)
- Concrete layout formulas: Grid, Radial, Layered (DAG topological sort), Grouped
- Bounding-box overlap detection algorithm
- Color table, node size guidelines, ID generation rules
- Pure-JSON visual validation steps (no MCP required)

### Cross-skill references
- obsidian-zotero, obsidian-mineru, obsidian-vault now point to obsidian-ai-summary skill

### Bug fixes (MCP server)
- \`Path.rename()\` → \`Path.replace()\`: idempotent, overwrite-safe on Windows (no WinError 183)
- \`parse_with_mineru\`: wrap rename call in try/except so extraction status is always persisted"
```

- [ ] **Step 4: Verify release**

```bash
gh release view v1.1.3
```

Expected: shows release title, notes, and attached zip asset.

- [ ] **Step 5: Clean up local zip**

```bash
rm obsidian-vault-skills-1.1.3.zip
```

(Windows: `Remove-Item obsidian-vault-skills-1.1.3.zip`)

---

## Self-Review

**Spec coverage check:**

| Spec section | Covered by |
|---|---|
| Canvas kepano detection | Task 1 |
| Canvas coordinate formulas | Task 1 |
| Canvas overlap detection | Task 1 |
| Canvas colors / sizes / IDs | Task 1 |
| Canvas visual validation (pure JSON) | Task 1 |
| Canvas validation checklist | Task 1 |
| obsidian-views sync | Task 2 |
| obsidian-zotero cross-ref | Task 3–4 |
| obsidian-mineru cross-ref | Task 5–6 |
| obsidian-vault cross-ref | Task 7–8 |
| obsidian-ai-summary skill (all 3 dirs) | Task 9 |
| AI Summary trigger conditions (3 modes) | Task 9 |
| AI Summary source priority | Task 9 |
| AI Summary standard template | Task 9 |
| AI Summary write-back procedure | Task 9 |
| Version bump (4 files) | Task 10 |
| PyPI wheel includes new skill | Task 11 |
| GitHub Release with zip + notes | Task 12 |
| MCP bug fixes | Already committed (68380e3) |
