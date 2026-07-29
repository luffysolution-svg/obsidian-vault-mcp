---
name: evidence-based-qa
description: Answer literature questions with original passages and explicit coverage limits.
version: 1.0.0
---

<!-- ovm:skill-managed:start -->
# Evidence-based literature Q&A

- For a broad single-paper question, call `literature_paper_read` with `mode=overview` and `record_coverage=true`.
- For a precise single-paper question, call `literature_paper_read` with `mode=targeted` and `record_coverage=true`.
- For multiple papers, call `literature_retrieve` with an explicit scope, bounded budgets, and `record_coverage=true`.
- Cite each important factual answer with `[[evidence:...]]`, then explain exactly what the passage supports.
- Preserve the original language for quotations. Mark translations and paraphrases.
- Use `queryVariants` only to expand recall. Treat metadata, Zotero notes, Analysis notes, query variants, and Coverage Ledger entries as context, never as original-paper evidence or facts.
- A returned image with any `visualStatus` other than `visual_verified` cannot support a visual conclusion.
- If the returned evidence is partial, sampled, abstract-only, or missing, state that boundary in the answer.

Do not manufacture evidence IDs, pages, figure numbers, sections, units, or causality.
<!-- ovm:skill-managed:end -->

## User Customizations

Add preferred answer formats here.
