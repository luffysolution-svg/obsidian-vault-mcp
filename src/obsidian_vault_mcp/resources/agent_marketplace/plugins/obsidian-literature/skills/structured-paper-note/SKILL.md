---
name: structured-paper-note
description: Build a traceable 13-part Chinese paper analysis from local evidence.
version: 1.0.0
---

<!-- ovm:skill-managed:start -->
# Structured paper note

1. Call `literature_analysis_context` with the paper's `zotero_key`.
2. Inspect section, evidence, image, and coverage gaps before drafting.
3. If a gap requires an overview or targeted read, call `literature_paper_read` with the appropriate `mode` and `record_coverage=true`.
4. Draft all 13 requested sections; use “证据不足” instead of filling gaps.
5. Label source facts, author interpretation, Agent inference, and user notes separately.
6. Attach an `[[evidence:...]]` anchor to important facts, numbers, conditions, methods, findings, and limitations.
7. A figure claim needs both `[[asset:...]]` and relevant text evidence. A visual conclusion additionally requires `visualStatus=visual_verified`; no other image status qualifies.
8. Turn unsupported claims into structured uncertainty items.
9. Run an uncertainty audit, then call `literature_analysis_write` with `dry_run=true`.
10. Review the preview before the committed call and report its transaction ID.

Use `queryVariants` only to expand recall. Coverage Ledger records describe reading coverage and are not original-paper evidence or facts.

Never invent authors, DOI, year, page, section, figure label, data, or causal language. Keep direct quotations in their source language and identify translations or paraphrases.
<!-- ovm:skill-managed:end -->

## User Customizations

Add project-specific preferences here. This section is never replaced by a managed upgrade.
