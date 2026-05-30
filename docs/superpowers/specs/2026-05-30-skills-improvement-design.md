# Skills Improvement Design

**Date:** 2026-05-30
**Scope:** obsidian-views (Canvas), new obsidian-ai-summary skill, cross-skill reference updates

---

## Background

Three gaps were identified in the current skills:

1. **Canvas layout algorithms missing** — `obsidian-views` lists four layout names (Grid/Radial/Grouped/Layered) but provides no coordinate formulas, overlap detection, color table, node size guidelines, or visual validation steps.
2. **AI Summary workflow gap** — `obsidian-zotero` and `obsidian-mineru` both note that `## AI Summary` exists but neither defines when or how to fill it. `obsidian-vault` does not mention it at all.
3. **kepano/obsidian-skills integration** — the upstream `json-canvas` skill has richer Canvas content; we should reference it when available and fall back to built-in content when not.

---

## Section 1 — Canvas Upgrade (obsidian-views)

### Kepano Detection

At the top of the `## Canvas` section, add a detection block:

> Before generating any Canvas, check whether `skills/json-canvas/SKILL.md` (project) or `.claude/skills/json-canvas.md` (user) exists. If found, invoke that skill instead of the built-in section below.

### Built-in Fallback — New Content

**Coordinate formulas:**

- **Grid:** `x = col * (nodeWidth + 60)`, `y = row * (nodeHeight + 40)`; fill columns first, max 4 nodes per row.
- **Radial:** `x = cx + r * cos(2π * i / n)`, `y = cy + r * sin(2π * i / n)`; radius `r = max(200, n * 60)`.
- **Layered (DAG):** topological sort first to get depth `d`; `x = d * 320`; nodes at same depth share `y` evenly. Recommended for 5+ nodes with clear dependency direction.
- **Grouped:** place group nodes first; constrain member node coordinates within group bounds with 30px inner padding.

**Overlap detection (after all nodes are placed):**

Check every pair of nodes for bounding-box intersection:
```
overlap = !(ax+aw ≤ bx || bx+bw ≤ ax || ay+ah ≤ by || by+bh ≤ ay)
```
If overlap found, shift the later node right by `overlapWidth + 40`.

**Color table (per JSON Canvas spec):**

| Preset | Color  |
|--------|--------|
| `"1"`  | Red    |
| `"2"`  | Orange |
| `"3"`  | Yellow |
| `"4"`  | Green  |
| `"5"`  | Cyan   |
| `"6"`  | Purple |

Omit the `color` field entirely when no color is needed.

**Node size guidelines:**

| Type              | width   | height  |
|-------------------|---------|---------|
| Small text/label  | 200–300 | 80–150  |
| Normal note card  | 250–400 | 150–250 |
| Large card/file   | 400–500 | 250–400 |

**ID generation:** 16-character lowercase hex string, e.g. `"6f0ad84f44ce9c17"`. Never reuse an existing node or edge id.

### Visual Validation (pure JSON, no MCP)

After writing the canvas file:

1. `obsidian_read_file` the written file to confirm it was saved.
2. Output a position summary table for quick scan:
   ```
   id       type   x     y     w    h
   ──────────────────────────────────
   a1b2c3   file   0     0     300  150
   ```
3. Run bounding-box overlap check on all node pairs; report any overlapping pairs.
4. Check total canvas span (max_x − min_x, max_y − min_y) stays under 3000px.
5. Verify every edge `fromNode`/`toNode` exists in the node list.

### Validation Checklist

1. All `id` values unique across nodes and edges.
2. Every `fromNode`/`toNode` references an existing node id.
3. `type` is one of `text`, `file`, `link`, `group`.
4. `fromSide`/`toSide` is one of `top`, `right`, `bottom`, `left`.
5. `fromEnd`/`toEnd` is one of `none`, `arrow`.
6. Color presets are `"1"`–`"6"` or valid hex (e.g. `"#FF0000"`).
7. JSON is valid and parseable.

---

## Section 2 — New Skill: obsidian-ai-summary

### File location

`skills/obsidian-ai-summary/SKILL.md` (and synced to the two mirror locations per CLAUDE.md rules).

### Trigger Conditions

Three entry points:

1. **Explicit call:** user says "write AI Summary" / "summarize this paper".
2. **Post-import prompt:** after `obsidian-zotero` or `obsidian-mineru` completes, detect whether `## AI Summary` is absent or empty in the literature note; if so, ask "Want to generate an AI Summary?".
3. **Pipeline flag:** `obsidian_pipeline_ingest_item(write_ai_summary=true)` or `obsidian_pipeline_parse_with_mineru(write_ai_summary=true)` triggers automatic execution.

### Source Reading Priority

1. If `mineruStatus: parsed` → read `attachments/mineru/<zoteroKey>/paper.md` (richest source).
2. Otherwise → read the literature note body.
3. Always include existing `## Reading Notes` content as primary evidence.

### Standard Summary Template

```markdown
## AI Summary

**Core Finding:** One-sentence core conclusion.

**Method:** Methods, models, or experimental design used.

**Dataset / Scope:** Dataset name, scale, domain.

**Limitations:** Acknowledged or inferable limitations.

**My Assessment:** Relevance to current research direction, credibility, follow-up worth.
```

### Write-back Rules

1. `obsidian_read_file` the full note.
2. Locate `## AI Summary` section; if absent, insert it before `## Reading Notes`.
3. Replace only that section's content; leave all other sections untouched.
4. `obsidian_write_file` the updated note.
5. On re-ingest, preserve existing AI Summary (do not overwrite).

**Tool budget:** ≤ 4 calls (read note → optionally read MinerU md → write back → confirm).

---

## Section 3 — Cross-skill Reference Updates

### obsidian-zotero (Re-ingest Behavior section)

Replace:
> The plugin does not generate AI summaries; skills may write that section later.

With:
> The plugin does not generate AI summaries. Use the `obsidian-ai-summary` skill to generate or update that section — it can be triggered after import or via `obsidian_pipeline_ingest_item(write_ai_summary=true)`.

### obsidian-mineru (Output Expectations section)

Append to the line about preserving AI Summary:
> To generate or update `## AI Summary` after parsing, use the `obsidian-ai-summary` skill. It can also be triggered via `obsidian_pipeline_parse_with_mineru(write_ai_summary=true)`.

### obsidian-vault (Safety section)

Add line:
> To generate AI summaries for literature notes, use the `obsidian-ai-summary` skill.

---

## Section 4 — Publishing & Sync Checklist

Per CLAUDE.md rules, every skill change requires:

### Skills sync (3 directories)

| Directory | Action |
|-----------|--------|
| `skills/<name>/SKILL.md` | Authoritative source — edit here first |
| `scripts/obsidian_vault_mcp/skills/<name>/SKILL.md` | Mechanical copy |
| `.claude/skills/<name>.md` | Manual bullet-point summary |

New skill `obsidian-ai-summary` needs all three created.
Modified skills (`obsidian-views`, `obsidian-zotero`, `obsidian-mineru`, `obsidian-vault`) need all three synced.

### Version bump (4 files, must be identical)

- `pyproject.toml`
- `.codex-plugin/plugin.json`
- `.claude-plugin/plugin.json`
- `scripts/obsidian_vault_mcp/skills/` (carried via wheel, no separate version field)

Bump patch version (e.g. `1.1.2` → `1.1.3`).

### PyPI upload

```bash
python -m build
twine upload dist/*
```

### GitHub Release

Create a new GitHub Release tagged with the new version; attach the zip of `skills/`.

---

## Out of Scope

- Changes to MCP server Python code (pipeline flag `write_ai_summary` is documented as a skill-level convention; actual server implementation is a separate task).
- Defuddle, obsidian-markdown, or obsidian-cli skill content changes.
- Automated CI for skill sync.
