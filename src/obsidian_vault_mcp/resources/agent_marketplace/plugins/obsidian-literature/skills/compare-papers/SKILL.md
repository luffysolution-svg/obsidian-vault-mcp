---
name: compare-papers
description: Compare papers on explicit, evidence-backed dimensions.
version: 1.0.0
---

<!-- ovm:skill-managed:start -->
# Compare papers

1. Declare the paper set and comparison dimensions.
2. Call `literature_retrieve` for targeted cross-paper evidence with an explicit scope, bounded budgets, `depth=evidence`, and `record_coverage=true` instead of producing generic paper summaries first.
3. Normalize terminology, units, experimental conditions, baselines, and measurement definitions before comparing values.
4. Report agreements, differences, conflicts, missing dimensions, and whether the data are actually comparable.
5. Cite the original passage behind each material comparison.
6. Report abstract-only and missing-full-text papers separately.
7. For figures, report `visualStatus`; only `visualStatus=visual_verified` can support visual morphology comparisons.
8. Use `queryVariants` only to expand recall. Coverage Ledger records describe reading coverage, not paper facts; neither is evidence.

Do not generalize sampled matches into an exhaustive corpus claim.
<!-- ovm:skill-managed:end -->

## User Customizations

Add recurring comparison dimensions here.
