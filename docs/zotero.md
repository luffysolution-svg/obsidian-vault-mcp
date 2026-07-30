---
layout: default
title: Zotero 导入与同步
lang: zh-CN
---
# Zotero 导入与同步

启动 Zotero Desktop 本地 API 后先探测：

```bash
obsidian-vault-mcp call zotero_ping --json '{}'
obsidian-vault-mcp call zotero_search_items --json '{"query":"catalysis"}'
```

父条目的 `zoteroKey` 是笔记稳定身份；即使标题、作者、年份或 citekey 变化，也会更新同一笔记。默认路径：

```text
Literature/{zoteroKey}.md
Literature/attachment/{zoteroKey}.pdf
Literature/index.md
Literature/Literature.base
```

对于 Zotero “Link to File”附件，在 Zotero 中设置 Linked Attachment Base Directory，并在配置中设置相同的绝对 `zotero.linkedAttachmentBaseDir`（或环境变量 `ZOTERO_LINKED_ATTACHMENT_BASE_DIR`）。`ZOTERO_STORAGE_DIR` 只用于 `storage:` 附件；linked base 只用于 `attachments:` 附件。解析会拒绝穿越路径、盘符相对值和 base 外结果。
