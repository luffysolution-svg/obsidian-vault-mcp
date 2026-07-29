---
name: analyze-figures
description: Interpret figure and table evidence without overstating MinerU image reliability.
version: 1.0.0
---

<!-- ovm:skill-managed:start -->
# Analyze figures and tables

1. Call `literature_paper_read` with `mode=figures`, `include_images=true`, and `record_coverage=true`.
2. Inspect asset `status`, `visualStatus`, caption evidence, context evidence, page, and PDF crop path.
3. Prefer structured Markdown table text for numerical values.
4. Read the complete caption and nearby body passages before interpreting a figure.
5. Make visual conclusions only when `visualStatus=visual_verified`; `pdf_crop_available` permits inspection but is not itself visual verification. Otherwise provide only a text-based caption/context interpretation and state the limitation.
6. Embed only allowed formal assets. Never embed an unlinked candidate automatically.
7. Treat `queryVariants` as recall aids and Coverage Ledger records as coverage context, never as paper evidence or facts.

Do not infer figure labels from filenames, panels from file order, or visual detail from a candidate's mere existence. Do not install OCR or image dependencies from this Skill.
<!-- ovm:skill-managed:end -->

## User Customizations

Add domain-specific plotting terminology here.
