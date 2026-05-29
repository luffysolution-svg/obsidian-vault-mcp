---
name: obsidian-zotero
description: "Import and synchronize Zotero literature with an Obsidian vault. Use when Codex needs to search the local Zotero library, inspect Zotero items or collections, import Zotero items into Obsidian literature notes, include child notes or annotations, copy or link PDF attachments, extract PDF text, or batch-ingest a Zotero collection. 当用户提到 Zotero 文献库、参考文献导入、批注、附件、PDF、合集批量导入或文献笔记同步时使用。"
---

# Obsidian Zotero

Use the Zotero tools in this plugin when the request starts from the user's local Zotero library and the destination is an Obsidian vault.
处理 Zotero 到 Obsidian 的导入、同步、附件和批注时优先使用。

## Start

1. Call `obsidian_zotero_ping` before direct Zotero work.
2. If the ping fails, ask the user to open Zotero Desktop and enable the local API.
3. Use `obsidian_zotero_search_items`, `obsidian_zotero_list_collections`, `obsidian_zotero_get_item`, and `obsidian_zotero_get_children` to find the correct source record before importing.

## Import Workflow

1. Prefer `obsidian_pipeline_ingest_item` for a single parent item.
2. Prefer `obsidian_pipeline_ingest_collection` for collection batch import; it continues after per-item failures and returns a full report.
3. The pipeline always copies PDFs into the configured vault attachment folder, preserves Zotero source paths, and writes `zotero://select` plus `zotero://open-pdf` links.
4. Use the older `obsidian_ingest_zotero_item` and `obsidian_ingest_zotero_collection` only when running the `full` or `legacy` tool profile for compatibility/debugging.

## Imported Note Shape

- Pipeline frontmatter includes Zotero identity fields such as `zoteroKey`, `zoteroVersion`, `zoteroSelect`, `zoteroPdfKeys`, `zoteroPdfLinks`, original attachment paths, copied attachment paths, and Obsidian wikilinks.
- Collection names are stored as human-readable names in `collections`, not raw collection keys.
- The note body can include citation details, embedded attachments, abstract text, child notes, annotations, related-item links, attachment warnings, and optional extracted PDF text.

## Re-ingest Behavior

- Repeated pipeline runs preserve user-owned YAML fields, unknown custom fields, `## Reading Notes`, and `## AI Summary`.
- The plugin does not generate AI summaries; skills may write that section later.

## Related Tools

- Use `obsidian_zotero_list_pdf_attachments` to inspect attachment inventory before import.
- Use `obsidian_zotero_extract_pdf_text` when the user wants raw text from a Zotero PDF attachment without a full note import.
- Use the `obsidian-mineru` skill when the request is about parsing a Zotero-linked PDF into full Markdown.
