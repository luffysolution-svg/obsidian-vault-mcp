# Docs & Skills Improvement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 2 documentation errors, rewrite the AI install prompt in both READMEs to cover 6 clients, and expand 3 skill files with literature-reading, comparison, review, figure-analysis, and graph-gap workflows.

**Architecture:** Pure documentation edits — no Python source changes. Six files modified, one new file already committed (the spec). Each task is one file edit + one commit.

**Tech Stack:** Markdown, YAML front-matter, Python snippets (inline in skill files)

---

## File Map

| File | Action |
|------|--------|
| `.claude-plugin/plugin.json` | Fix `"version"` field `1.0.27` → `1.1.0` |
| `README.en.md` | Rewrite AI-Assisted Setup prompt block (lines 281–294) |
| `README.md` | Rewrite AI 辅助安装 prompt block (lines 238–251) + update surrounding sentence |
| `skills/obsidian-zotero/SKILL.md` | Add §Reading, §Comparing, §Literature Review after "Re-ingest Behavior" |
| `skills/obsidian-mineru/SKILL.md` | Add §Figure & Table Analysis after "Zotero PDF Text Extraction" |
| `skills/obsidian-graph/SKILL.md` | Add §Knowledge Gap Detection + §Surprising Connections after "Graph Improvement Suggestions" |

---

## Task 1: Fix `.claude-plugin/plugin.json` version

**Files:**
- Modify: `.claude-plugin/plugin.json` line 3

- [ ] **Step 1: Make the edit**

Change:
```json
"version": "1.0.27",
```
To:
```json
"version": "1.1.0",
```

- [ ] **Step 2: Verify**

Run: `python -c "import json; d=json.load(open('.claude-plugin/plugin.json')); assert d['version']=='1.1.0', d['version']"`

Expected: no output (assertion passes).

- [ ] **Step 3: Commit**

```bash
git add .claude-plugin/plugin.json
git commit -m "chore: sync .claude-plugin/plugin.json version to 1.1.0"
```

---

## Task 2: Rewrite AI install prompt — README.en.md

**Files:**
- Modify: `README.en.md` (the `\`\`\`text` block inside "## AI-Assisted Setup")

- [ ] **Step 1: Replace the prompt block**

Find the exact block (between the two ` ```text ` / ` ``` ` fences inside "## AI-Assisted Setup") and replace with:

````markdown
```text
Install and configure the Obsidian Vault MCP plugin from
https://github.com/luffysolution-svg/obsidian-vault-mcp.

1. Install: `pip install zotero-obsidian-mcp`
   (Do NOT install the unrelated `obsidian-vault-mcp` package;
   `obsidian-vault-mcp` is only the executable name.)
2. Keep `OBSIDIAN_VAULT_PATH=auto` unless auto-detection fails.
3. Wire up the client I am using:
   - Codex: point the plugin root at this repo; `.codex-plugin/plugin.json`
     and `.mcp.json` are already in place.
   - Claude Code: run `claude mcp add obsidian-vault obsidian-vault-mcp`.
     Skills are bundled in the package — no manual copying needed.
   - OpenCode: copy `opencode.json` into the project, or merge its `mcp`
     block into `~/.config/opencode/opencode.json`.
   - Cursor: add the server block from `.mcp.json` to
     `<project>/.cursor/mcp.json` (or global `~/.cursor/mcp.json`).
   - Windsurf: add the same server block to
     `~/.codeium/windsurf/mcp_config.json`.
   - VS Code + Copilot: add the server block to `.vscode/mcp.json`
     in the workspace (requires GitHub Copilot Chat ≥ 1.256).
4. Keep vault paths, Zotero storage paths, and API tokens in local config
   only — never commit them.
5. Run: `obsidian-vault-mcp --doctor --doctor-format text --vault /path/to/vault`
6. If I need Zotero features, remind me to start Zotero Desktop with the
   local API enabled (port 23119). If I need MinerU parsing, run
   `mineru-open-api --version` first; install with
   `pip install mineru-open-api` if missing.
```
````

Also update the surrounding paragraph (the line containing "Paste this prompt into any AI coding assistant") to include the new clients:

Old:
```
Paste this prompt into any AI coding assistant (Codex, Claude Code, OpenCode,
etc.):
```

New:
```
Paste this prompt into any AI coding assistant (Codex, Claude Code, OpenCode,
Cursor, Windsurf, VS Code + Copilot, etc.):
```

- [ ] **Step 2: Commit**

```bash
git add README.en.md
git commit -m "docs: rewrite AI-Assisted Setup prompt, add Cursor/Windsurf/VS Code"
```

---

## Task 3: Rewrite AI install prompt — README.md

**Files:**
- Modify: `README.md` (the `\`\`\`text` block inside "## AI 辅助安装")

- [ ] **Step 1: Replace the prompt block**

Find the exact block (between the two ` ```text ` / ` ``` ` fences inside "## AI 辅助安装") and replace with **the same English text block** as Task 2 above (AI prompts stay in English):

````markdown
```text
Install and configure the Obsidian Vault MCP plugin from
https://github.com/luffysolution-svg/obsidian-vault-mcp.

1. Install: `pip install zotero-obsidian-mcp`
   (Do NOT install the unrelated `obsidian-vault-mcp` package;
   `obsidian-vault-mcp` is only the executable name.)
2. Keep `OBSIDIAN_VAULT_PATH=auto` unless auto-detection fails.
3. Wire up the client I am using:
   - Codex: point the plugin root at this repo; `.codex-plugin/plugin.json`
     and `.mcp.json` are already in place.
   - Claude Code: run `claude mcp add obsidian-vault obsidian-vault-mcp`.
     Skills are bundled in the package — no manual copying needed.
   - OpenCode: copy `opencode.json` into the project, or merge its `mcp`
     block into `~/.config/opencode/opencode.json`.
   - Cursor: add the server block from `.mcp.json` to
     `<project>/.cursor/mcp.json` (or global `~/.cursor/mcp.json`).
   - Windsurf: add the same server block to
     `~/.codeium/windsurf/mcp_config.json`.
   - VS Code + Copilot: add the server block to `.vscode/mcp.json`
     in the workspace (requires GitHub Copilot Chat ≥ 1.256).
4. Keep vault paths, Zotero storage paths, and API tokens in local config
   only — never commit them.
5. Run: `obsidian-vault-mcp --doctor --doctor-format text --vault /path/to/vault`
6. If I need Zotero features, remind me to start Zotero Desktop with the
   local API enabled (port 23119). If I need MinerU parsing, run
   `mineru-open-api --version` first; install with
   `pip install mineru-open-api` if missing.
```
````

Also update the Chinese surrounding paragraph:

Old:
```
将以下提示词粘贴给任意 AI 编程助手（Codex、Claude Code、OpenCode 等）：
```

New:
```
将以下提示词粘贴给任意 AI 编程助手（Codex、Claude Code、OpenCode、Cursor、Windsurf、VS Code + Copilot 等）：
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: rewrite AI 辅助安装提示词，新增 Cursor/Windsurf/VS Code"
```

---

## Task 4: Expand `skills/obsidian-zotero/SKILL.md`

**Files:**
- Modify: `skills/obsidian-zotero/SKILL.md`

Append the three new sections **after the last line** of the current file (after "Use `obsidian_zotero_extract_pdf_text` when...").

- [ ] **Step 1: Append new sections**

Add to the end of the file:

````markdown

## Reading a Single Paper

Use when the user asks a question about a specific literature note or wants a summary, key findings, methods, or evidence from one paper.

1. Read the literature note frontmatter with `obsidian_read_file`.
2. Check `mineruStatus`:
   - If `mineruStatus: parsed` → read `attachments/mineru/<zoteroKey>/paper.md` via `obsidian_read_file`. This is the richest source (full structured text + figure captions).
   - Otherwise → read the literature note body directly.
3. For targeted questions (e.g. "what dataset did they use?"), use `obsidian_search` with a focused keyword **before** reading the full file — this often answers the question in ≤ 2 tool calls.
4. Preserve and surface the user's `## Reading Notes` content as primary evidence when answering.

**Budget:** ≤ 3 tool calls for a typical factual question. Escalate to full-file read only if search is insufficient.

## Comparing Multiple Papers

Use when the user wants a structured comparison across 2–10 literature notes (methods, results, datasets, limitations, etc.).

1. Batch-read each paper's literature note (first ~60 lines) to get frontmatter + abstract via `obsidian_read_file`. This covers most comparisons.
2. Agree on the comparison axis with the user (method / result / dataset / limitation / year).
3. For axes requiring deeper detail, run `obsidian_search` with a targeted keyword. Scope the search by including the paper title or zoteroKey in the query to avoid cross-paper noise.
4. Emit a structured Markdown table:

```markdown
| Paper | Method | Dataset | Key Result | Limitation |
|-------|--------|---------|------------|------------|
| Author YYYY | … | … | … | … |
```

5. Append a 2–3 sentence synthesis paragraph below the table.

## Writing a Literature Review

Use when the user wants to draft or scaffold a review section covering multiple papers on a topic.

**Three phases:**

### Phase 1 — Collect
1. Run `obsidian_search` with the review topic as query; set `extensions=".md"`.
2. Filter results to notes with `type: literature` in frontmatter.
3. Present the candidate list to the user and confirm scope before proceeding.

### Phase 2 — Deep-read
1. For each selected paper:
   - If `mineruStatus: parsed` → read MinerU Markdown (`attachments/mineru/<key>/paper.md`).
   - Otherwise → read the literature note.
2. Extract key claims grouped by review theme (background / methods / results / gaps).
3. Always include the user's existing `## Reading Notes` content — it is primary evidence.

### Phase 3 — Synthesize
1. Draft the review section by section, grouping papers under each theme.
2. Use inline wikilinks `[[Lovelace 2024 - Zotero Article]]` to cite papers.
3. Save the draft with `obsidian_write_file` to a path agreed with the user (e.g. `reviews/Topic Review Draft.md`).
4. Mark the draft with `status: draft` in frontmatter.
````

- [ ] **Step 2: Commit**

```bash
git add skills/obsidian-zotero/SKILL.md
git commit -m "docs(skill): add reading, comparison, literature-review workflows to obsidian-zotero"
```

---

## Task 5: Expand `skills/obsidian-mineru/SKILL.md`

**Files:**
- Modify: `skills/obsidian-mineru/SKILL.md`

Append one new section **after the last line** of the current file (after the `python extract_text.py` line).

- [ ] **Step 1: Append new section**

Add to the end of the file:

````markdown

## Figure & Table Analysis

Use when the user asks a specific question about a figure, chart, or table in a parsed paper.

1. Read `attachments/mineru/<zoteroKey>/images-index.md` with `obsidian_read_file`.
   The index lists every figure with its semantic slug filename and the original caption context, e.g.:
   ```
   - fig-01-process-flow-diagram.png (was: image-a.png)
     Caption context: "Figure 1 Process flow diagram showing…"
   ```
2. Identify which figure matches the user's question from the slug name and caption.
3. Run `obsidian_search` using the slug filename (e.g. `fig-01-process-flow-diagram`) as query to locate the surrounding paragraph in `paper.md`. The search snippet will include the figure's Markdown image tag and adjacent text.
4. Read that section of `paper.md` with `obsidian_read_file` if the search snippet is insufficient.
5. Answer using the extracted caption and surrounding text only. Do **not** attempt to decode image binary data — the image files are not readable as text.

**Typical budget:** 2–3 tool calls (read index → search → answer, or read index → read section → answer).
````

- [ ] **Step 2: Commit**

```bash
git add skills/obsidian-mineru/SKILL.md
git commit -m "docs(skill): add figure & table analysis workflow to obsidian-mineru"
```

---

## Task 6: Expand `skills/obsidian-graph/SKILL.md`

**Files:**
- Modify: `skills/obsidian-graph/SKILL.md`

Append two new sections **after the last line** of the current file (after the Chinese summary paragraph).

- [ ] **Step 1: Append new sections**

Add to the end of the file:

````markdown

## Knowledge Gap Detection

Run after building the graph (see "Citation Network" above). Identifies notes and clusters that are under-connected.

```python
import networkx as nx

# 1. Isolated nodes — no edges at all
gaps = [n for n in G.nodes if G.degree(n) == 0]
print(f"Isolated notes ({len(gaps)}):", gaps[:20])

# 2. Sparse communities — single-node or two-node clusters after community detection
sparse = [list(c) for c in communities if len(c) <= 2]
print(f"Sparse communities ({len(sparse)}):", sparse)

# 3. Bridge nodes — their removal would disconnect the graph
bridges = list(nx.bridges(G.to_undirected()))
bridge_nodes = {u for u, v in bridges} | {v for u, v in bridges}
print(f"Bridge nodes ({len(bridge_nodes)}):", list(bridge_nodes)[:10])
```

**Report to the user:**
- **Isolated notes** → suggest `obsidian_search` by tag overlap to find candidate notes to link, or ask whether to delete.
- **Sparse single-paper communities** → these topics have no neighbors; suggest importing related Zotero items.
- **Bridge notes** → held two clusters together; flag as candidates to expand into proper index notes with `obsidian_write_file`.

## Surprising Connections

Run after community detection. Finds high-value cross-community edges that may represent unexpected interdisciplinary links.

```python
# Map each node to its community index
node_to_community = {}
for i, c in enumerate(communities):
    for n in c:
        node_to_community[n] = i

# Cross-community edges
cross_edges = [
    (u, v) for u, v in G.edges()
    if node_to_community.get(u) != node_to_community.get(v)
]

# Rank by combined degree — high-degree cross-community links are most surprising
cross_edges.sort(
    key=lambda e: G.degree(e[0]) + G.degree(e[1]),
    reverse=True
)

print("Top surprising connections:")
for u, v in cross_edges[:10]:
    print(f"  [{node_to_community[u]}] {u}  →  [{node_to_community[v]}] {v}")
```

**Report to the user:** For each of the top 10 cross-community connections, describe which two thematic clusters they bridge (using community member note names as cluster labels). Suggest:
- Adding a wikilink annotation explaining the connection, or
- Creating a new bridge note that synthesizes the two lines of work.
````

- [ ] **Step 2: Commit**

```bash
git add skills/obsidian-graph/SKILL.md
git commit -m "docs(skill): add knowledge gap detection and surprising connections to obsidian-graph"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Covered by task |
|------------------|-----------------|
| `.claude-plugin/plugin.json` version fix | Task 1 ✓ |
| Remove erroneous skills-copy instruction | Task 2 & 3 ✓ (new prompt has no such line) |
| Add Cursor / Windsurf / VS Code+Copilot | Task 2 & 3 ✓ |
| MinerU step → concrete command | Task 2 & 3 ✓ (`mineru-open-api --version`) |
| Update surrounding paragraph (en) | Task 2 ✓ |
| Update surrounding paragraph (zh) | Task 3 ✓ |
| obsidian-zotero: reading workflow | Task 4 ✓ |
| obsidian-zotero: comparison workflow | Task 4 ✓ |
| obsidian-zotero: literature review | Task 4 ✓ |
| obsidian-mineru: figure analysis | Task 5 ✓ |
| obsidian-graph: knowledge gap detection | Task 6 ✓ |
| obsidian-graph: surprising connections | Task 6 ✓ |
| No Python source changes | All tasks ✓ (markdown only) |
| No new skill files | All tasks ✓ |

**Placeholder scan:** No TBD, TODO, or vague instructions present. All code blocks are complete.

**Consistency check:** `zoteroKey` used consistently across Tasks 4 and 5. `communities` variable referenced in Task 6 is defined by the community detection snippet already in the skill file.
