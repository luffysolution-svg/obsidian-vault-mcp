---
name: obsidian-vault
description: "Work with local Obsidian vaults as linked knowledge bases. Use when the user needs to inspect, edit, organise, maintain, or analyse vault notes, YAML frontmatter, wikilinks, graph structure, wiki index/log, schema, or bulk edits. 当用户提到 Obsidian 仓库、笔记、YAML 属性、双链、图谱、批量修改、索引日志、模板或本地知识库维护时使用。"
---

# Obsidian Vault

Use the 17 MCP tools in the `literature` profile plus Claude's built-in tools (Read, Write, Edit, Grep, Bash, Glob) for all vault work.

## Core MCP Tools

- `obsidian_read_file` / `obsidian_write_file` — read and write vault notes
- `obsidian_search` — full-text search across the vault
- `obsidian_update_properties` — safely merge/replace YAML frontmatter

## File Management

To list files: use `obsidian_search` with an empty query, or use the `Glob` tool with the vault path.

To delete a file: use `Bash` → `Remove-Item "vault_path\relative\path.md"` (Windows) or `rm`.

To move/rename a file: use `Bash` → `Move-Item` (Windows) or `mv`. If Obsidian is open, use the `obsidian-cli` skill to preserve wikilink integrity.

To batch-move files: use `Bash` with a loop or `Get-ChildItem | Move-Item`.

## Graph Maintenance

To analyse the wikilink graph:
1. Use `obsidian_search` with `query=""` to list all `.md` files.
2. For each file, use `obsidian_read_file` to extract `[[wikilinks]]` with regex `\[\[([^\]]+)\]\]`.
3. Build an edge list and identify orphans (nodes with no in-links) and dead links (targets that don't exist as files).
4. Report findings. Suggest `obsidian_write_file` fixes for broken links.

To find orphans: collect all filenames, collect all link targets, subtract linked from all.

To find broken links: collect all link targets, subtract existing filenames.

To add wikilinks: use `obsidian_read_file` + `obsidian_write_file` with the updated content.

## Vault Health (Lint)

Run this sequence:
1. `obsidian_search` with `query=""` — get all notes.
2. Read each note with `obsidian_read_file` and check:
   - Missing required frontmatter fields (type, title, tags).
   - Dead `[[links]]` pointing to non-existent notes.
   - Notes with no outgoing or incoming links (orphans).
3. Report a structured issues list grouped by type.

## Wiki Maintenance

To update the wiki index (`index.md`):
1. Use `obsidian_search` to list notes by tag or folder.
2. Build a markdown catalogue grouped by tag.
3. Use `obsidian_write_file` to write the catalogue between `<!-- obsidian-vault:index:start -->` and `<!-- obsidian-vault:index:end -->` markers.

To append a wiki log entry (`log.md`):
1. Use `obsidian_read_file` to read existing `log.md` (or create if absent).
2. Prepend a new `## YYYY-MM-DD` entry with the summary and touched paths.
3. Use `obsidian_write_file` to save.

## Schema Validation

To validate frontmatter schema:
1. Use `obsidian_search` to find notes by folder prefix (e.g. `sources/`, `entities/`).
2. For each note, use `obsidian_read_file` and parse the YAML frontmatter block.
3. Check required fields: `sources/` → `{type, title, tags}`, `entities/` → `{type, title, sources}`.
4. Report missing or invalid fields.

To apply schema defaults:
1. For notes missing required fields, use `obsidian_update_properties` with `merge_mode="merge"` to fill in defaults.
2. Use `dry_run=true` first to preview.

## Bulk Editing (Edit Plans)

To preview a multi-file edit:
1. Collect the list of files and planned changes.
2. Use `obsidian_read_file` on each, show before/after diffs inline.
3. Ask the user to confirm before writing.

To apply:
1. For each file, use `obsidian_write_file` or `obsidian_update_properties`.
2. Keep a backup list of original content for rollback.

To rollback: restore each file from the backup content using `obsidian_write_file`.

## Note Creation with Templates

To create a note with a template:
1. Use `obsidian_search` in the templates folder (check `.obsidian/templates.json` for path).
2. Use `obsidian_read_file` to load the template.
3. Substitute `{{title}}`, `{{body}}`, `{{status}}` and Templater tokens (`<% tp.date.now(...) %>`).
4. Merge template frontmatter with supplied properties (supplied properties win).
5. Use `obsidian_write_file` to write the note.

## Safety

- Always use `dry_run=true` before broad mutations.
- Never write outside the vault root.
- Prefer `obsidian_update_properties` for frontmatter edits — it preserves body content.
- When Obsidian desktop is open, prefer the `obsidian-cli` skill for moves and renames.
- To generate AI summaries for literature notes, use the `obsidian-ai-summary` skill.

---

## 中文说明

使用 17 个 MCP 工具加上 Claude 内置工具处理所有 vault 操作。图谱分析、lint 检查、wiki 维护、schema 验证和批量编辑现在通过 `obsidian_search` + `obsidian_read_file` + `obsidian_write_file` 组合完成，不再依赖独立的 MCP 工具。
