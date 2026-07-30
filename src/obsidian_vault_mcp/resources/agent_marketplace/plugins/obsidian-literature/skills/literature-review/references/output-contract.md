# Literature-review output contract

Use this contract for a bounded multi-paper synthesis or an explicit comparison that the user asks to persist.

## Write call

Call `literature_analysis_write` with `fields`, `managed_content`, `vault_path`, and `dry_run: true`. Inspect the preview, then repeat the same fields and managed content with `dry_run: false`.

The client supplies every field in this canonical example:

<!-- ovm:analysis-fields-example:start -->
```yaml
analysisType: literature_review
analysisProfile: general
secondaryProfiles: []
title: Bounded review of two example papers
status: ready
analysisFocus: Compare the mechanisms and evidence boundaries.
primarySourceKey: ""
primarySource: ""
sourceKeys:
  - ABCD1234
  - EFGH5678
sourceCount: 2
summary: Both papers address the question with different methods and non-identical evidence.
skillName: literature-review
skillVersion: "1.0.0"
tags:
  - analysis
  - review
reviewMode: comparative
reviewQuestion: How do the two reported mechanisms compare?
scopeSummary: Two user-selected papers with available full text.
timeRange: 2024-2026
taxonomySummary: The evidence separates into experimental and interpretive claims.
consensusSummary: Both studies support directed transfer under their tested conditions.
controversySummary: The proposed rate-limiting steps differ and are not directly comparable.
gapSummary: A shared benchmark and matched operating conditions are absent.
conclusionSummary: The common trend is supported, while the mechanistic difference remains conditional.
```
<!-- ovm:analysis-fields-example:end -->

The service derives and persists `analysisSchemaVersion`, `analysisId`, `sourceFingerprint`, `createdAt`, and `updatedAt`; do not guess them. A review requires at least two unique, existing `sourceKeys`, and `sourceCount` must match. Keep both primary-source fields empty for a review.

Use `thematic` for ordinary multi-paper synthesis, `comparative` for an explicit comparison, `narrative` for a general narrative account, and `scoping` for mapping a field. Use `systematic` only when the search, inclusion, exclusion, and reporting process actually meets that standard.

When `compare-papers` saves through this contract, set `skillName: compare-papers`, `skillVersion: "1.0.0"`, and `reviewMode: comparative`.

## Managed content

Pass only the review-owned Markdown through `managed_content`, for example:

```markdown
# Review title

## Executive summary
## Review question and scope
## Source pool and inclusion boundary
## Conceptual framework and taxonomy
## Thematic synthesis
### Question-driven theme
## Cross-study comparison matrix
## Consensus, disagreement, and non-comparability
## Methodological limits
## Research gaps and open questions
## Implications
## Integrated conclusion
## Included papers
```

Do not include managed-block markers, `## User Notes`, or any user-owned section in `managed_content`. The service adds its own markers and preserves user-owned content. Build themes from the question rather than using one section per paper, and distinguish reported facts, author explanations, and cross-paper synthesis.
