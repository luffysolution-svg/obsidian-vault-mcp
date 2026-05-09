---
name: obsidian-vault
description: Use this skill when the user asks to inspect, edit, organize, or maintain a local Obsidian vault, including vault files, YAML properties, tags, wikilinks, backlinks, graph structure, JSON Canvas, Bases, or the Obsidian CLI.
---

# Obsidian Vault

Use the bundled `obsidian-vault` MCP tools for local vault operations, and combine them with the workspace skills `obsidian-markdown`, `json-canvas`, and `obsidian-bases` when creating Obsidian-native content.

## Setup

The plugin reads `OBSIDIAN_VAULT_PATH` from `.mcp.json` when set. The default value is `auto`, which resolves the currently active Obsidian CLI vault. If `auto` cannot resolve a vault, pass `vault_path` explicitly to tools or set `OBSIDIAN_VAULT_PATH` to the vault root. The path should usually contain `.obsidian`.

Vault-local defaults can be stored in `.obsidian-vault-mcp.json` or `.obsidian/obsidian-vault-mcp.json` for folders such as `literatureFolder`, `mineruSourceFolder`, `pdfSourceFolder`, `zoteroAttachmentsFolder`, `entitiesFolder`, `conceptsFolder`, plus `indexPath`, `logPath`, `templateFolder`, `defaultTemplate`, and `zoteroAttachmentNameStrategy`.

If Obsidian Desktop 1.12.7 or newer is installed and running, the tool `obsidian_cli` can call the local `obsidian` command. The CLI is useful for app-backed actions such as opening notes, querying Bases, listing backlinks, setting properties through Obsidian, taking screenshots, and running developer commands.

## Core Workflow

1. Inspect the vault with `obsidian_vault_status`, `obsidian_list_files`, and `obsidian_search`.
2. Read candidate notes with `obsidian_read_file`.
3. Edit Markdown using Obsidian-flavored syntax:
   - YAML properties at the top of notes.
   - Wikilinks like `[[Topic]]`, `[[Topic|label]]`, and embeds like `![[Diagram.canvas]]`.
   - Stable tags in frontmatter, using nested tags when they clarify structure.
4. Update properties with `obsidian_update_properties` instead of manually rewriting frontmatter when possible.
5. For bulk edits, use `obsidian_preview_edit_plan` first, then `obsidian_apply_edit_plan`; keep the returned transaction id for `obsidian_rollback_edit_plan`.
6. For single-file edits, call write tools with `dry_run=true` first and review the returned unified diff.
7. Add controlled links with `obsidian_add_wikilinks` and then run `obsidian_build_graph`, `obsidian_lint_vault`, or `obsidian_suggest_graph_improvements` to check backlinks, dead ends, orphan notes, unresolved links, and improvement suggestions.
8. Run `obsidian_validate_vault_schema` before publishing or after large edits to check frontmatter, Canvas JSON, and Base YAML. Use `obsidian_apply_schema_defaults` with its default dry-run behavior when missing frontmatter fields should be filled from schema presets.
9. Create Canvas files with `obsidian_create_canvas` for custom JSON or `obsidian_create_canvas_from_graph` to lay out vault wikilinks automatically.
10. Create Bases files with `obsidian_create_base` for custom YAML or `obsidian_create_base_template` for built-in literature, project task, equipment, utilities, economics, and sources templates.
11. Create Dataview notes with `obsidian_create_dataview_note` when the user wants Dataview/DQL query blocks instead of Bases.
12. Use structured CLI wrappers such as `obsidian_cli_read`, `obsidian_cli_backlinks`, `obsidian_cli_base_query`, `obsidian_cli_properties`, and `obsidian_cli_tasks` for common app-backed operations. Use generic `obsidian_cli` only when no structured wrapper exists.

## Persistent Wiki Pattern

For LLM-maintained wiki work:

- Keep raw sources separate from generated wiki notes.
- Maintain an `index.md` with each important page, one-line summaries, and major categories.
- Maintain a chronological `log.md` with entries for ingest, query, and lint passes.
- When ingesting a source, update the source summary, touched entity pages, concept pages, index, and log in the same pass.
- Prefer durable cross-references over one-off summaries. New insights should be filed back into the vault when they are likely to matter later.
- Periodically run graph checks for orphan pages, dead ends, unresolved links, missing backlinks, stale claims, and concepts that deserve their own pages.

Use `obsidian_ingest_source_note` for the source/entity/concept/index/log pass when the user gives source content or extracted notes. Use `obsidian_update_wiki_index` and `obsidian_append_wiki_log` directly for smaller maintenance passes.

Use `obsidian_ingest_bibtex`, `obsidian_ingest_reference`, `obsidian_ingest_mineru_markdown`, or `obsidian_ingest_pdf_attachment` when the source comes from Zotero exports, BibTeX, existing MinerU Markdown, or a vault PDF attachment. These tools create literature/source notes and can still update entity/concept pages, `index.md`, and `log.md`.

When the user wants MinerU to parse a document directly, first call `obsidian_mineru_status`. If `mineru-open-api` is available, use `obsidian_mineru_extract` for extraction or `obsidian_mineru_extract_and_ingest` for the full extract-and-import workflow. Prefer `flash-extract` when no token is configured. Precision `extract` may require MinerU authentication. If the user already has a separate MinerU MCP server, let Codex use that MCP directly and then ingest the generated Markdown with this plugin; this plugin does not call another MCP server internally.

If MinerU task creation succeeds but Markdown download fails, check network
routes for `mineru.net`, `mineru.oss-cn-shanghai.aliyuncs.com`,
`cdn-mineru.openxlab.org.cn`, and `*.openxlab.org.cn`. VPN/proxy fake-IP DNS
can break result downloads even when the main API is reachable.

Use `obsidian_zotero_ping` before direct Zotero work. If it fails, ask the user to open Zotero Desktop and enable local API access. Once reachable, use `obsidian_zotero_search_items`, `obsidian_zotero_get_item`, `obsidian_zotero_get_children`, and `obsidian_ingest_zotero_item`. Imported Zotero notes include `zoteroKey`, `zoteroSelect`, `zoteroLinks`, and PDF links when PDF children exist. Attachment copy naming can use `original`, `zotero_key`, `citekey`, `title_year`, or `parent_key`.

## Tool Hints

- `obsidian_list_files`: scan Markdown, Canvas, Bases, and attachments.
- `obsidian_search`: search note contents with line snippets.
- `obsidian_read_file` / `obsidian_write_file`: read or create any vault-relative file.
- `obsidian_create_note`: create a Markdown note with title and frontmatter; can apply a user template by `template_path`, `template_name`, `use_template=true`, or configured `defaultTemplate`.
- `obsidian_list_user_templates`: list Markdown templates discovered from Obsidian Templates, Templater, and plugin defaults.
- `obsidian_update_properties`: merge, replace, or remove YAML properties.
- `obsidian_preview_edit_plan`: preview a multi-file edit plan with unified diffs.
- `obsidian_apply_edit_plan`: apply a multi-file edit plan and save backups under `.obsidian-vault-backups/<transaction_id>/`.
- `obsidian_rollback_edit_plan`: restore files from an applied transaction backup.
- `obsidian_add_wikilinks`: append related links or replace exact phrases with wikilinks.
- `obsidian_build_graph`: parse `[[wikilinks]]`, embeds, aliases, backlinks, tags, orphans, dead ends, ambiguous links, and unresolved links.
- `obsidian_lint_vault`: report graph health, missing `index.md`/`log.md`, duplicate keys, empty notes, missing titles, missing tags, and invalid tag property types.
- `obsidian_suggest_graph_improvements`: suggest unresolved-note creation, reciprocal links, duplicate-page candidates, Markdown-link conversion, and attachment modeling.
- `obsidian_validate_vault_schema`: validate Markdown frontmatter schemas plus Canvas JSON and Base YAML structure.
- `obsidian_list_schema_presets`: list built-in note type schemas.
- `obsidian_doctor`: report vault resolution, template discovery, dependencies, and optional integrations.
- `obsidian_apply_schema_defaults`: preview or apply missing frontmatter defaults inferred from built-in/custom schemas.
- `obsidian_update_wiki_index`: create or refresh a managed catalogue block in `index.md`.
- `obsidian_append_wiki_log`: append timestamped maintenance, ingest, or query entries to `log.md`.
- `obsidian_ingest_source_note`: create a source note, generate/update linked entity and concept pages, then refresh index/log.
- `obsidian_parse_bibtex`: parse BibTeX into normalized reference metadata.
- `obsidian_ingest_reference`: ingest one reference metadata object as a literature source note.
- `obsidian_ingest_bibtex`: ingest one or more BibTeX entries as literature source notes.
- `obsidian_ingest_mineru_markdown`: ingest MinerU Markdown output and optional PDF attachment as a source note.
- `obsidian_mineru_status`: check optional MinerU CLI availability and token environment variables.
- `obsidian_mineru_extract`: run optional MinerU CLI extraction and save Markdown output under the vault.
- `obsidian_mineru_extract_and_ingest`: run MinerU CLI, find the generated Markdown, and ingest it as a source note.
- `obsidian_ingest_pdf_attachment`: create a source note for a PDF attachment already in the vault.
- `obsidian_zotero_ping`: check whether Zotero Desktop local API is reachable.
- `obsidian_zotero_search_items`: search local Zotero items.
- `obsidian_zotero_get_item`: fetch one Zotero item metadata record.
- `obsidian_zotero_get_children`: fetch child notes, annotations, attachments, and other child items.
- `obsidian_zotero_list_pdf_attachments`: list Zotero PDF attachments.
- `obsidian_zotero_extract_pdf_text`: extract text from a Zotero PDF attachment when `pypdf` or `PyPDF2` is installed.
- `obsidian_ingest_zotero_item`: fetch a Zotero item, optionally copy PDF attachments into the vault, include child notes/annotations/PDF text, and ingest it as a literature note.
- `obsidian_create_canvas`: write valid JSON Canvas from node and edge JSON.
- `obsidian_create_canvas_from_graph`: create a Canvas map from the vault graph with `grid`, `radial`, `grouped`, or `layered` layout, optional folder/tag filtering, group nodes, orphan control, and dry-run diff support.
- `obsidian_create_base`: write valid Obsidian Bases YAML from JSON.
- `obsidian_list_base_templates`: list built-in Base templates.
- `obsidian_create_base_template`: create a built-in Base template; accepts `options_json` with `folder`, `tag`, `title`, and `limit`.
- `obsidian_list_dataview_templates`: list built-in Dataview note templates.
- `obsidian_create_dataview_note`: create a Markdown note with a Dataview query block; accepts `options_json` with `folder`, `tag`, `title`, `sort`, and `limit`.
- `obsidian_cli`: call commands such as `files`, `read`, `search`, `property:set`, `base:query`, `links`, `backlinks`, `orphans`, `open`, `dev:screenshot`, and `eval`.
- `obsidian_cli_read` / `obsidian_cli_open`: read or open a note through Obsidian.
- `obsidian_cli_backlinks`: list backlinks and parse JSON output when available.
- `obsidian_cli_base_query`: query a Base through the Obsidian CLI and parse JSON output when requested.
- `obsidian_cli_properties`, `obsidian_cli_property_read`, `obsidian_cli_property_set`, `obsidian_cli_property_remove`: inspect and edit Obsidian properties through the app.
- `obsidian_cli_tasks`: list tasks, normalizing "No tasks found." to an empty list.
- `obsidian_cli_screenshot`: take an app-backed screenshot.
- `obsidian_cli_plugin_reload`: reload an Obsidian plugin.
- `obsidian_cli_move_or_rename`: move or rename notes through Obsidian; defaults to `dry_run=true`.

Write tools including `obsidian_write_file`, `obsidian_create_note`, `obsidian_update_properties`, `obsidian_add_wikilinks`, `obsidian_create_canvas`, and `obsidian_create_base` accept `dry_run=true` to return a diff without writing. Batch edit plans support operations `write`, `update_properties`, `append`, `replace`, and `delete`.

## Safety Rules

- Treat all file paths as vault-relative unless the tool explicitly asks for `vault_path`.
- Do not write outside the vault root.
- Do not use a plain Markdown folder unless `OBSIDIAN_ALLOW_NON_VAULT=true` was set intentionally.
- Preserve existing note body content and unrelated properties.
- For bulk changes, read the graph first, use `dry_run=true`, make focused edits, then run `obsidian_lint_vault` to confirm the shape changed as intended.
- Prefer Obsidian CLI `move` or `rename` for note moves when Obsidian is running, because it can update internal links according to vault settings.
