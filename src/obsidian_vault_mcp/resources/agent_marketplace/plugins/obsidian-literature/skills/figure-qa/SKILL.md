---
name: figure-qa
description: Locate and explain a paper's figure, table, scheme, equation, or named panel using its caption, nearby text, and real image or structured content when available. Use for visual or numbered-target questions; not for general paper summaries.
---

# Figure Q&A

<!-- ovm:skill-managed:start -->

Read [the figure-analysis contract](references/figure-analysis.md) before interpreting or saving a target.

1. Resolve one source paper and the explicit target label or description.
2. Call `literature_paper_read` in figures mode to locate the target, full caption, nearby text, and available file.
3. Confirm labels from the caption or explicit prose, never from filenames or file order.
4. For a compound figure, inspect the whole figure before focusing on a panel.
5. Prefer structured Markdown for tables and source LaTeX or equation text for formulas.
6. Use visual observations only when the image file exists; otherwise answer from caption and context and say so.
7. Explain direct observations separately from scientific interpretation and relation to the paper's claim.
8. Answer in chat unless persistence is requested; then preview and commit through `literature_analysis_write`.

Do not install image-processing dependencies or use OCR as an automatic fallback.

<!-- ovm:skill-managed:end -->

## User Customizations

Add local figure conventions below this line.
