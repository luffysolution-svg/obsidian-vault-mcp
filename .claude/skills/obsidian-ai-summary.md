---
name: obsidian-ai-summary
description: "Generate and write ## AI Summary for literature notes. Use after Zotero import, MinerU parse, or explicit user request. 导入或解析后生成 AI Summary 时使用。"
---

- **Trigger**: user asks for summary; OR `## AI Summary` absent/empty after import/parse → prompt user
- **Pipeline flag**: `obsidian_pipeline_ingest_item(write_ai_summary=true)` or `obsidian_pipeline_parse_with_mineru(write_ai_summary=true)` → run automatically
- **Source priority**: `mineruStatus: parsed` → read `attachments/mineru/<key>/paper.md`; else read literature note body
- **Template** (5 sections): **Core Finding** / **Method** / **Dataset / Scope** / **Limitations** / **My Assessment**
- **Write-back**: `obsidian_read_file` → find/insert `## AI Summary` before `## Reading Notes` → replace only that section → `obsidian_write_file`
- Do not overwrite existing non-empty AI Summary unless triggered by pipeline flag or user confirms
- Budget: ≤ 4 tool calls
