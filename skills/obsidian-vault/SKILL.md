---
name: obsidian-vault
description: "Work with local Obsidian vaults as linked knowledge bases. Use when Codex needs to inspect, edit, organize, or maintain vault notes, YAML frontmatter, tags, wikilinks, backlinks, graph structure, bulk edit plans, schema checks, index/log wiki files, or source notes inside an Obsidian vault. 当用户提到 Obsidian 仓库、笔记、YAML 属性、双链、图谱、批量修改、索引日志或本地知识库维护时使用。"
---

# Obsidian Vault

Default MCP profile is `literature`, focused on Zotero + MinerU + Obsidian ingestion. Use `OBSIDIAN_VAULT_TOOL_PROFILE=full` or `legacy` when a request requires the older graph, wiki, Canvas, Bases, Dataview, schema, or CLI tools.

Use the bundled `obsidian-vault` MCP tools for vault-relative work. Combine them with `obsidian-markdown`, `json-canvas`, and `obsidian-bases` when those workspace skills are available.
在处理 Obsidian vault、本地知识库、frontmatter、双链和图谱维护时优先使用。

## Start

1. Resolve the vault with `obsidian_vault_status`.
2. Inspect candidate files with `obsidian_list_files`, `obsidian_search`, and `obsidian_read_file`.
3. Prefer `obsidian_update_properties` for frontmatter changes and `obsidian_add_wikilinks` for controlled linking.
4. Preview write operations with `dry_run=true`.
5. For multi-file work, use `obsidian_preview_edit_plan` before `obsidian_apply_edit_plan`, and keep the transaction id for `obsidian_rollback_edit_plan`.

## Common Workflows

### Edit notes and frontmatter

- Use `obsidian_create_note` or `obsidian_write_file` for note creation.
- Use `obsidian_list_user_templates` when the vault relies on Obsidian Templates or Templater.
- Preserve unrelated body content and unrelated YAML fields.

### Maintain the graph

- Run `obsidian_build_graph` after link-heavy edits.
- Use `obsidian_lint_vault` and `obsidian_suggest_graph_improvements` to catch orphans, dead ends, unresolved links, and weak backlink structure.
- Run `obsidian_validate_vault_schema` or `obsidian_apply_schema_defaults` when note types depend on stable frontmatter layouts.

### Maintain a persistent wiki

- Keep raw sources separate from generated entity and concept notes.
- Update `index.md` and `log.md` as part of the same pass when ingesting important new material.
- Use `obsidian_ingest_source_note` for source plus entity plus concept plus index plus log updates.
- Use `obsidian_update_wiki_index` and `obsidian_append_wiki_log` for smaller maintenance passes.

### Ingest literature and source material

- Use `obsidian_ingest_reference` or `obsidian_ingest_bibtex` for literature metadata.
- Use `obsidian_ingest_pdf_attachment` for PDFs already inside the vault.
- Use the dedicated `obsidian-zotero` and `obsidian-mineru` skills when the request is specifically about Zotero or MinerU.

## Safety

- Treat file paths as vault-relative unless a tool explicitly asks for `vault_path`.
- Do not write outside the vault root.
- Use `dry_run=true` before mutations when the requested change is broad or destructive.
- Prefer Obsidian CLI move or rename wrappers when the desktop app is running and internal links must stay correct.
