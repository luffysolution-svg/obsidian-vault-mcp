---
name: obsidian-zotero
description: "Import Zotero literature into Obsidian, read/compare papers, and write literature reviews. Zotero 文献导入、单篇阅读、多篇对比或综述撰写时使用。"
---

- **Before import**: `obsidian_zotero_ping` → if fails, ask user to open Zotero Desktop.
- **Single item**: `obsidian_pipeline_ingest_item` (copies PDF, writes frontmatter, preserves user fields on re-ingest).
- **Batch**: `obsidian_pipeline_ingest_collection` (continues after per-item failures, returns full report).
- **Read a paper**: check `mineruStatus` in frontmatter → if `parsed`, read `attachments/mineru/<key>/paper.md`; else read the literature note. Use `obsidian_search` for targeted questions (≤ 3 tool calls).
- **Compare papers**: batch-read first ~60 lines of each note → agree on axis (method/result/dataset) → `obsidian_search` for detail → emit Markdown table + synthesis paragraph.
- **Literature review**: Phase 1 — `obsidian_search` by topic, filter `type: literature`; Phase 2 — deep-read MinerU markdown or note, extract claims by theme; Phase 3 — draft by theme, `obsidian_write_file` to `reviews/` with `status: draft`.
- Always preserve user's `## Reading Notes` as primary evidence in any synthesis.
