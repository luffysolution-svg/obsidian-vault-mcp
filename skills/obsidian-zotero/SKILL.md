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

1. Use `obsidian_ingest_zotero_item` for a single parent item.
2. Use `obsidian_ingest_zotero_collection` for batch import by collection, tag, item type, or query.
3. Enable `copy_pdf_attachments` only when vault-local copies are desired.
4. Choose `attachment_name_strategy` from `original`, `zotero_key`, `citekey`, `title_year`, or `parent_key`.
5. Use `folder_by_collection`, `folder_by_type`, and `tag_by_collection` only when the vault taxonomy should follow Zotero organization.

## Imported Note Shape

- Frontmatter includes Zotero identity fields such as `zoteroKey`, `zoteroVersion`, `zoteroSelect`, and, when available, PDF link fields.
- Collection names are stored as human-readable names in `collections`, not raw collection keys.
- The note body can include citation details, embedded attachments, abstract text, child notes, annotations, related-item links, attachment warnings, and optional extracted PDF text.

## Re-ingest Behavior

- If the stored `zoteroVersion` matches, the tool returns `upToDate: true` and skips rewriting by default.
- If the Zotero version changed, the note is rewritten and user-added non-Zotero fields are preserved.
- This preservation is important for fields added later, such as `mineru_markdown`.

## Related Tools

- Use `obsidian_zotero_list_pdf_attachments` to inspect attachment inventory before import.
- Use `obsidian_zotero_extract_pdf_text` when the user wants raw text from a Zotero PDF attachment without a full note import.
- Use the `obsidian-mineru` skill when the request is about parsing a Zotero-linked PDF into full Markdown.
