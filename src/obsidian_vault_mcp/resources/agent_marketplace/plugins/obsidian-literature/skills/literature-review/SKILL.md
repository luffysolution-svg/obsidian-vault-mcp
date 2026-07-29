---
name: literature-review
description: Synthesize a bounded literature set by themes, methods, findings, and gaps.
version: 1.0.0
---

<!-- ovm:skill-managed:start -->
# Literature review

1. Define the discovery source and the exact paper pool.
2. Call `literature_retrieve` with `intent=enumerate`, `depth=metadata`, an explicit scope, bounded budgets, and `record_coverage=true`; then screen abstracts without describing that as full-text review.
3. Call `literature_retrieve` with `depth=evidence`, the same explicit scope, bounded budgets, and `record_coverage=true`; selectively deepen only the papers needed for the review question.
4. Organize the synthesis by themes, mechanisms, methods, findings, disagreements, and gaps—not one summary per paper.
5. Preserve evidence anchors for consequential claims and comparisons.
6. Report how many papers had metadata, abstracts, MinerU full text, evidence snippets, image assets, and reliable PDF crops.
7. Keep unread frontier papers outside analysed conclusions and label externally discovered papers separately.
8. Save a Topic note only after the user approves the bounded synthesis.
9. Use `queryVariants` only to expand recall. Coverage Ledger records are coverage boundaries, not original-paper facts or evidence.
10. Do not draw a visual conclusion from an image unless its `visualStatus` is `visual_verified`.

Never write “all studies” or “no paper” unless the returned coverage is genuinely exhaustive.
<!-- ovm:skill-managed:end -->

## User Customizations

Add review-specific inclusion criteria here.
