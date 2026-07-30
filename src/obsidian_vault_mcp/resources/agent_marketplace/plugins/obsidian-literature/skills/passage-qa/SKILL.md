---
name: passage-qa
description: Locate and answer an exact question about a paper's section, paragraph, definition, method, result, number, or conclusion. Use when the user asks where or how the paper states something; do not use for broad summaries or figure interpretation.
---

# Passage Q&A

<!-- ovm:skill-managed:start -->

Read [the output contract](references/output-contract.md) when the user asks to save the answer.

1. Resolve one source paper and normalize the precise question.
2. Call `literature_paper_read` directly in targeted mode; skip a broad overview.
3. Read adjacent context only when needed to interpret the matched passage.
4. Give a direct answer, reliable section path, source link, and a short source-language quotation.
5. Distinguish what the passage supports from what it cannot establish.
6. Mark location quality honestly when only a section or approximate neighborhood is available.
7. Answer in chat by default.
8. If persistence is requested, use `literature_analysis_get` to detect a duplicate, then preview and commit with `literature_analysis_write`.

Never invent a page, heading, paragraph, quotation, or precision level.

<!-- ovm:skill-managed:end -->

## User Customizations

Add local passage conventions below this line.
