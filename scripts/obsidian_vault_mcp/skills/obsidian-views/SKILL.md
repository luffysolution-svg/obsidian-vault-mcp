---
name: obsidian-views
description: "Build visual and query views for an Obsidian vault. Use when Codex needs to create or update JSON Canvas maps, Obsidian Bases files, built-in Base templates, or Dataview notes from vault content, graph structure, folders, tags, or frontmatter-driven collections. 当用户提到 Canvas、Bases、Dataview、视图、图谱布局、表格卡片视图或查询笔记时使用。"
---

# Obsidian Views

Use this skill when the goal is to present or query vault content rather than merely edit notes.
处理 Canvas、Bases 和 Dataview 视图构建时优先使用。

## Start

1. Inspect relevant notes, folders, tags, or graph structure first.
2. Decide whether the user needs a Canvas map, a Base, or a Dataview note.
3. Use `dry_run=true` when the generated file may overwrite an existing artifact.

## Choose the Output

### Canvas

- Use `obsidian_create_canvas` for custom node and edge payloads.
- Use `obsidian_create_canvas_from_graph` when the view should be derived from vault wikilinks.
- Choose a layout such as `grid`, `radial`, `grouped`, or `layered`.

### Bases

- Use `obsidian_create_base` when you already know the YAML structure.
- Use `obsidian_list_base_templates` and `obsidian_create_base_template` when a built-in literature, project, equipment, utilities, economics, or sources view is a good fit.

### Dataview

- Use `obsidian_list_dataview_templates` and `obsidian_create_dataview_note` when the user wants DQL blocks in Markdown rather than a `.base` file.

## Validation

- Run `obsidian_validate_vault_schema` when the generated view depends on stable frontmatter.
- Run `obsidian_build_graph` or `obsidian_lint_vault` after large graph-derived Canvas work to confirm the vault structure still matches expectations.
