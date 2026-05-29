# Design: Docs & Skills Improvement — v1.1.0

**Date:** 2026-05-30  
**Scope:** Fix documentation errors, rewrite AI install prompt (zh + en), expand 3 skill files

---

## 1. Documentation Fixes

### 1.1 `.claude-plugin/plugin.json` version mismatch

- **Problem:** `.claude-plugin/plugin.json` still reads `"version": "1.0.27"` while `.codex-plugin/plugin.json` and `pyproject.toml` are both at `1.1.0`.
- **Fix:** Change `"version"` to `"1.1.0"`.

### 1.2 AI install prompt — Claude Code skills path error

- **Problem:** Both READMEs say:  
  > "If skills are not auto-loaded, copy the packaged `skills/` directory into `~/.claude/skills/`."  
  This path is wrong. Claude Code loads skills from codex-plugin packages, not from `~/.claude/skills/`.
- **Fix:** Replace the erroneous note with the correct instruction:  
  > "Skills are bundled in the installed package and loaded automatically by Codex. For Claude Code, run `claude mcp add obsidian-vault obsidian-vault-mcp` — no manual skill copying needed."

---

## 2. AI Install Prompt Rewrite

The install prompt block (identical in both README.md and README.en.md) is rewritten to:

1. Remove the incorrect skills-copy instruction.
2. Add setup steps for **Cursor**, **Windsurf**, and **VS Code + Copilot**.
3. Make step 6 (MinerU check) concrete with an actual command.

### New prompt (both languages use the same English text block):

```text
Install and configure the Obsidian Vault MCP plugin from
https://github.com/luffysolution-svg/obsidian-vault-mcp.

1. Install: `pip install zotero-obsidian-mcp`
   (Do NOT install the unrelated `obsidian-vault-mcp` package;
   `obsidian-vault-mcp` is only the executable name.)
2. Keep `OBSIDIAN_VAULT_PATH=auto` unless auto-detection fails.
3. Wire up the client I am using:
   - Codex: point plugin root at this repo; `.codex-plugin/plugin.json` and
     `.mcp.json` are already in place.
   - Claude Code: run `claude mcp add obsidian-vault obsidian-vault-mcp`.
     Skills are bundled in the package — no manual copying needed.
   - OpenCode: copy `opencode.json` into the project, or merge its `mcp`
     block into `~/.config/opencode/opencode.json`.
   - Cursor: add the server block from `.mcp.json` to
     `<project>/.cursor/mcp.json` (or global `~/.cursor/mcp.json`).
   - Windsurf: add the same server block to
     `~/.codeium/windsurf/mcp_config.json`.
   - VS Code + Copilot: add the server block to
     `.vscode/mcp.json` in the workspace (requires GitHub Copilot Chat ≥ 1.256).
4. Keep vault paths, Zotero storage paths, and API tokens in local config only
   — never commit them.
5. Run: `obsidian-vault-mcp --doctor --doctor-format text --vault /path/to/vault`
6. If I need Zotero features, remind me to start Zotero Desktop with the local
   API enabled (port 23119). If I need MinerU parsing, run
   `mineru-open-api --version` first; install with `pip install mineru-open-api`
   if missing.
```

The **Chinese README** keeps the same English text block inside the code fence (AI prompts are conventionally kept in English), but the surrounding paragraph is updated in Chinese to mention Cursor / Windsurf / VS Code.

---

## 3. Skills Expansion

Three files are modified. No new files are created.

### 3.1 `skills/obsidian-zotero/SKILL.md`

Add three new workflow sections after "Re-ingest Behavior":

#### § Reading a Single Paper (Q&A / Evidence Search)

- Check `mineruStatus` in the literature note frontmatter.
- If `mineruStatus: parsed`, read `attachments/mineru/<key>/paper.md` via `obsidian_read_file` — this is the richest source.
- Otherwise fall back to reading the literature note itself with `obsidian_read_file`.
- For targeted questions: use `obsidian_search` with a focused keyword before reading the full file.
- Max 3 tool calls to answer a typical question; escalate to full-file read only if search is insufficient.

#### § Comparing Multiple Papers

1. Batch-read each paper's literature note frontmatter + abstract section (first ~60 lines via `obsidian_read_file`).
2. Identify the comparison axis (method / result / dataset / limitation).
3. For each axis requiring more detail, use `obsidian_search` with a targeted query scoped to the relevant paper's attachment folder.
4. Emit a structured comparison table in Markdown.

#### § Writing a Literature Review

Three phases:

1. **Collect** — `obsidian_search` with topic keywords to gather candidate notes; filter by `type: literature` in frontmatter.
2. **Deep-read** — for each selected paper, read MinerU Markdown if available, else literature note; extract key claims per theme.
3. **Synthesize** — draft the review section by section, grouping papers by theme; use `obsidian_write_file` to save the draft.

Preservation rule: user's existing `## Reading Notes` content is primary evidence — always include it in synthesis.

---

### 3.2 `skills/obsidian-mineru/SKILL.md`

Add one new section after "Zotero PDF Text Extraction":

#### § Figure & Table Analysis

1. Read `attachments/mineru/<key>/images-index.md` to enumerate all figures and their semantic filenames.
2. To answer a question about a specific figure, locate it in the images-index, then read the corresponding section of `paper.md` using `obsidian_search` with the figure filename as the query.
3. The images-index contains the original caption context alongside the renamed slug — use this to confirm which figure answers the user's question before retrieving full context.
4. Do NOT attempt to decode image binary data; work from extracted caption text and surrounding paragraphs in `paper.md`.

---

### 3.3 `skills/obsidian-graph/SKILL.md`

Add two new analysis modes after "Graph Improvement Suggestions":

#### § Knowledge Gap Detection

After building the graph:

```python
import networkx as nx

# Isolated nodes (no edges at all)
gaps = [n for n in G.nodes if G.degree(n) == 0]

# Sparse communities (size == 1 or 2 after community detection)
sparse = [c for c in communities if len(c) <= 2]

# Bridge nodes (removal disconnects the graph)
bridges = list(nx.bridges(G.to_undirected()))
```

Report:
- Isolated notes with suggestions to link or delete.
- Sparse single-paper communities that have no topical neighbors.
- Bridge notes that hold two clusters together — candidates for expansion into index notes.

#### § Surprising Connections

```python
# Cross-community edges: edges where source and target belong to different communities
node_to_community = {}
for i, c in enumerate(communities):
    for n in c:
        node_to_community[n] = i

cross_edges = [
    (u, v) for u, v in G.edges()
    if node_to_community.get(u) != node_to_community.get(v)
]
# Sort by combined degree (high-degree cross-community links are most surprising)
cross_edges.sort(key=lambda e: G.degree(e[0]) + G.degree(e[1]), reverse=True)
print(cross_edges[:10])
```

Report the top 10 cross-community connections as potential interdisciplinary insights. For each, suggest whether a new bridge note or explicit wikilink annotation would reinforce the connection.

---

## 4. Out of Scope

- No new skill files.
- No changes to `pyproject.toml`, `server.py`, `tools.py`, or any Python source.
- No changes to TECHNICAL_GUIDE.md (verified clean of legacy references).
- No changes to `.codex-plugin/plugin.json` (already at 1.1.0).

---

## 5. File Change Summary

| File | Change |
|------|--------|
| `.claude-plugin/plugin.json` | `version` → `"1.1.0"` |
| `README.md` | Rewrite AI 安装提示词 block + update surrounding paragraph |
| `README.en.md` | Rewrite AI-Assisted Setup prompt block |
| `skills/obsidian-zotero/SKILL.md` | Add §Reading, §Comparing, §Literature Review |
| `skills/obsidian-mineru/SKILL.md` | Add §Figure & Table Analysis |
| `skills/obsidian-graph/SKILL.md` | Add §Knowledge Gap Detection + §Surprising Connections |
