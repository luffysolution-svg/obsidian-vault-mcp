---
name: obsidian-views
description: "Build research views for Obsidian literature notes. Use when the user asks for Canvas maps, Bases tables, Dataview notes, paper maps, literature dashboards, or visual/query views over a vault. 当用户提到 Canvas、Bases、Dataview、文献视图、研究图谱或查询表时使用。"
---

# Obsidian Views

This skill turns literature notes and MinerU outputs into research views. It delegates format-specific syntax to dedicated Obsidian format skills whenever available.

## Format Skill Discovery

Before generating a view, check for specialized Kepano / Obsidian Skills:

- JSON Canvas: `skills/json-canvas/SKILL.md` or `.claude/skills/json-canvas.md`
- Obsidian Bases: `skills/obsidian-bases/SKILL.md` or `.claude/skills/obsidian-bases.md`
- Obsidian Markdown/Dataview: `skills/obsidian-markdown/SKILL.md` or `.claude/skills/obsidian-markdown.md`

If a needed format skill is missing and network access is allowed, install it into the AGENTS-declared summary skill directory (`.claude/skills` in this repository):

```powershell
$tmp = Join-Path $env:TEMP "obsidian-skills-kepano"
if (Test-Path $tmp) { Remove-Item -Recurse -Force -LiteralPath $tmp }
git clone https://github.com/kepano/obsidian-skills $tmp
New-Item -ItemType Directory -Force .claude\skills | Out-Null
Copy-Item "$tmp\skills\json-canvas\SKILL.md" ".claude\skills\json-canvas.md" -Force
Copy-Item "$tmp\skills\obsidian-bases\SKILL.md" ".claude\skills\obsidian-bases.md" -Force
Copy-Item "$tmp\skills\obsidian-markdown\SKILL.md" ".claude\skills\obsidian-markdown.md" -Force
```

Use the built-in fallback below only when the dedicated format skill cannot be installed or loaded.

## Research View Workflow

1. Gather candidates with `obsidian_search`:
   - Literature dashboard: search folder `literature` or query `type: literature`.
   - Topic map: search topic keywords, then filter notes with `type: literature`.
   - Figure map: search `mineruImagesIndex` or read `attachments/mineru/<zoteroKey>/images-index.md`.
2. Read only the needed notes with `obsidian_read_file`:
   - Frontmatter: title, authors, year, tags, collections, DOI, MinerU links.
   - Body: abstract, `## Reading Notes`, and `## AI Summary`.
3. Choose the output:
   - `.canvas` for relationships, clusters, paper flow, and visual synthesis.
   - `.base` for sortable literature tables.
   - `.md` Dataview note for query dashboards inside Markdown.
4. Generate the file through the specialized format skill when available, then write with `obsidian_write_file`.
5. Read the result back with `obsidian_read_file` and validate the file references existing notes.

## Built-in Fallback

- Canvas fallback: create JSON with `nodes` and `edges`. Use stable file nodes for papers, text nodes for themes, and group nodes for clusters. Keep node ids unique, 16-character lowercase hex. Avoid overlaps with a simple grid (`x = col * 360`, `y = row * 220`).
- Bases fallback: create YAML with `filters` and `views`, using table columns such as `title`, `authors`, `year`, `tags`, `doi`, `mineruStatus`.
- Dataview fallback: create Markdown containing a `dataview` code fence scoped to the relevant folder or tag.

## Validation

- For Canvas: JSON parses, all ids are unique, every edge references an existing node id, and all file nodes point to vault-relative paths.
- For Bases: YAML parses and has top-level `filters` and `views`.
- For Dataview: code fence exists and the query is scoped to the requested folder/tag.
- Do not invent paper metadata. If a field is missing, leave it blank or omit the column.

## Eval Scenarios

- **Trigger:** "Make a Canvas map of literature about CO2 absorption." Expected: search literature notes, read selected metadata, use JSON Canvas skill if present or install it, then write a `.canvas`. Must not generate a marketing diagram detached from vault files.
- **Trigger:** "Create a sortable literature Base." Expected: use Obsidian Bases skill if present or install it, then write a `.base` with columns from existing frontmatter. Must not invent DOI/year/authors.
- **Trigger:** "Create a Dataview dashboard for papers missing MinerU." Expected: write a Markdown Dataview query scoped to literature notes. Must only write the requested dashboard file.

## 中文说明

本 skill 只负责把本项目的文献笔记、MinerU 输出和 YAML 字段组织成研究视图。Canvas、Bases 和 Markdown/Dataview 的底层格式规则优先交给 Kepano / Obsidian Skills；缺失时先下载安装到 `.claude/skills`，不可用时才使用内置 fallback。
