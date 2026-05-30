---
name: obsidian-vault
description: "Inspect, edit, organise, or maintain Obsidian vault notes, frontmatter, wikilinks, graph, wiki, schema, or bulk edits. 维护 Obsidian vault 笔记、属性、双链、图谱、schema 或批量编辑时使用。"
---

Use 17 MCP tools (literature profile) + Claude built-in tools. Key tools: `obsidian_read_file`, `obsidian_write_file`, `obsidian_search`, `obsidian_update_properties`.

- **Graph/lint**: search all notes → read each → extract wikilinks → report orphans/dead links
- **Wiki index**: search by tag → build catalogue → write between index markers
- **Schema**: read frontmatter → check required fields → `obsidian_update_properties` to fill defaults
- **Bulk edit**: read → show diff → confirm → write; keep backup for rollback
- **File ops**: Bash `Move-Item`/`Remove-Item` for move/delete; `obsidian-cli` skill for Obsidian-open moves
- **AI Summary**: use `obsidian-ai-summary` skill to generate summaries for literature notes
- **Evals**: audits are read-only; broad property fixes preview first; Obsidian-open moves use `obsidian-cli`
