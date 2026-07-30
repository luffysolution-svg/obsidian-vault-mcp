---
name: compare-papers
description: Compare a user-selected set of papers across explicit methods, mechanisms, results, conditions, assumptions, or limitations. Use for bounded multi-paper comparisons, not open-ended corpus discovery or a general literature review.
---

# Compare papers

<!-- ovm:skill-managed:start -->

Read [comparison dimensions](references/comparison-dimensions.md) before building the matrix. When the user asks to save the comparison, also read the complete [literature-review output contract](../literature-review/references/output-contract.md) before constructing the write call.

1. Confirm the paper set and preserve any set supplied by the user.
2. Extract the requested comparison dimensions; do not replace them with defaults.
3. Use `literature_retrieve` across the set, then call `literature_paper_read` in targeted mode only for unresolved cells.
4. Normalize terms, units, baselines, conditions, sample definitions, and assumptions.
5. Mark every matrix cell as directly comparable, qualitatively comparable, not comparable, or missing.
6. Synthesize agreements, differences, conflicts, and gaps across papers instead of stacking summaries.
7. Answer in chat unless the user requests persistence.
8. When saving, use `literature_analysis_write` with review mode `comparative`, `skillName: compare-papers`, and `skillVersion: "1.0.0"`; preview with dry-run, inspect it, then commit the same fields and managed content.

Never infer comparability from similar terminology alone. Do not invent missing values, conditions, citations, or causal explanations.

<!-- ovm:skill-managed:end -->

## User Customizations

Add local comparison conventions below this line.
