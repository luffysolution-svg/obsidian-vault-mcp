---
name: obsidian-cli
description: "Drive Obsidian desktop via CLI — open notes, backlinks, property CRUD, Base queries, tasks, screenshots, plugin reload, wikilink-safe move/rename. 控制 Obsidian 桌面应用、读写属性、查询 Bases、列出任务时使用。"
---

All commands: `obsidian <command> [params]`. Use `Bash` tool to run.

- Read: `obsidian read --path "note.md"`
- Open: `obsidian open --path "note.md"`
- Backlinks: `obsidian backlinks --path "note.md" --format json`
- Properties: `obsidian properties --path "note.md" --format json`
- Set property: `obsidian property:set --name "status" --value "done" --type "text" --path "note.md"`
- Base query: `obsidian base:query --path "bases/lit.base" --view "Main" --format json`
- Tasks: `obsidian tasks --path "note.md" --format json --todo`
- Move: `obsidian move --path "old.md" --to "new.md"` (updates wikilinks)
- Rename: `obsidian rename --path "note.md" --name "new-name.md"`
- Screenshot: `obsidian screenshot --output "shot.png"`
- Plugin reload: `obsidian plugin:reload --id "plugin-id"`
- Evals: open note is read-only; rename/move must preserve wikilinks; tasks output must be parsed as JSON and stdout error text still counts as failure.
