---
layout: default
title: Zotero import and sync
lang: en
---
# Zotero import and sync

Start with the local Zotero Desktop API:

```bash
obsidian-vault-mcp call zotero_ping --json '{}'
obsidian-vault-mcp call zotero_search_items --json '{"query":"catalysis"}'
```

The parent item's `zoteroKey` is the stable note identity, so a title, author, year, or citekey change still updates the same note. Default paths:

```text
Literature/{zoteroKey}.md
Literature/attachment/{zoteroKey}.pdf
Literature/index.md
Literature/Literature.base
```

For a Zotero “Link to File” attachment, set Zotero's Linked Attachment Base Directory and the same absolute `zotero.linkedAttachmentBaseDir` (or `ZOTERO_LINKED_ATTACHMENT_BASE_DIR`). `ZOTERO_STORAGE_DIR` resolves only `storage:` attachments; the linked base resolves only `attachments:` paths. Traversal, drive-relative values, and results outside the base are refused.
