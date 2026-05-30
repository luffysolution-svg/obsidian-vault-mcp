---
name: obsidian-ai-summary
description: "Generate and write AI Summary sections for Obsidian literature notes. Use when the user asks to summarize a paper, or when prompted after Zotero import or MinerU parsing. 当用户请求总结论文、Zotero 导入或 MinerU 解析完成后有 AI Summary 空白时使用。"
---

# Obsidian AI Summary

Generate and write `## AI Summary` sections in Obsidian literature notes.
处理文献笔记 AI 摘要的生成和写入时优先使用。

## Trigger Conditions

Run this skill when **any** of the following apply:

1. **Explicit request:** user says "write AI Summary", "summarize this paper", "fill in the summary".
2. **Post-import prompt:** after `obsidian-zotero` or `obsidian-mineru` completes, detect whether `## AI Summary` is absent or empty in the literature note → ask "Want to generate an AI Summary?".
3. **Pipeline flag:** `obsidian_pipeline_ingest_item(write_ai_summary=true)` or `obsidian_pipeline_parse_with_mineru(write_ai_summary=true)` triggers automatic execution (skill-level convention; server-side implementation is a separate task).

## Source Reading Priority

1. Check `mineruStatus` in note frontmatter via `obsidian_read_file`.
2. If `mineruStatus: parsed` → read `attachments/mineru/<zoteroKey>/paper.md` (richest source: full structured text + figure captions).
3. Otherwise → read the literature note body directly.
4. Always include existing `## Reading Notes` content as primary evidence.

**Budget:** ≤ 4 tool calls total (read note → optionally read MinerU md → write back → confirm).

## Standard Summary Template

Write exactly this structure into `## AI Summary`:

```markdown
## AI Summary

**Core Finding:** [One-sentence core conclusion.]

**Method:** [Methods, models, or experimental design used.]

**Dataset / Scope:** [Dataset name, scale, domain.]

**Limitations:** [Acknowledged or inferable limitations.]

**My Assessment:** [Relevance to current research direction, credibility, follow-up worth.]
```

## Write-back Procedure

1. `obsidian_read_file` the full literature note.
2. Locate `## AI Summary` section:
   - If present and non-empty → ask user before overwriting (unless triggered by pipeline flag).
   - If absent or empty → insert before `## Reading Notes` (or at end of note if no Reading Notes section exists).
3. Replace only the `## AI Summary` section content; leave all other sections untouched.
4. `obsidian_write_file` the updated note.
5. On re-ingest via `obsidian-zotero`, the `## AI Summary` section is preserved automatically.

## 中文说明

检测触发条件（显式请求 / 导入后提示 / 管道 flag），优先读取 MinerU 全文，按标准五节模板写入 `## AI Summary`，不触碰其他节内容。
