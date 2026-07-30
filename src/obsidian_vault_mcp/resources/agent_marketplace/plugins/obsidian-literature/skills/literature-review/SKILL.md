---
name: literature-review
description: Synthesize a bounded paper pool or Zotero collection by themes, mechanisms, methods, consensus, conflicts, and research gaps. Use for literature reviews, research-state summaries, and multi-paper thematic synthesis; do not use for one paper or a narrow pairwise comparison.
---

# Literature review

<!-- ovm:skill-managed:start -->

Read [discipline profiles](references/discipline-profiles.md) to select default synthesis axes and [the output contract](references/output-contract.md) before saving.

1. State the review question, source pool, time or topic boundary, and inclusion limits.
2. Preserve a user-specified pool. Use `literature_retrieve` for the initial cross-paper map.
3. Select the primary discipline profile from the question and sources; user priorities override profile defaults.
4. Deep-read only pivotal papers and unresolved themes with targeted `literature_paper_read` calls.
5. Organize the review by themes, mechanisms, methods, theories, or another question-driven taxonomy.
6. Build a cross-study matrix and distinguish consensus, conflict, non-comparability, and missing information.
7. Do not describe search candidates as deeply read sources or call a selective review systematic.
8. Generate a concise summary and source boundary.
9. Use `literature_analysis_get` to avoid duplicates, then `literature_analysis_write` in dry-run mode; inspect before committing the review.

Never organize the main synthesis as one summary per paper or imply exhaustive coverage without an exhaustive process.

<!-- ovm:skill-managed:end -->

## User Customizations

Add local review conventions below this line.
