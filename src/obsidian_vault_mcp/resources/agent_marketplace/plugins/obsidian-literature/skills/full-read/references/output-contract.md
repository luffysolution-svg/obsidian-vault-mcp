# Full-read output contract

Use this contract only when the user asks to persist a complete analysis.

## Write call

Call `literature_analysis_write` with `fields`, `managed_content`, `vault_path`, and `dry_run: true`. Inspect the preview, then repeat the same fields and managed content with `dry_run: false`.

The client supplies every field in this canonical example:

<!-- ovm:analysis-fields-example:start -->
```yaml
analysisType: full_read
analysisProfile: general
secondaryProfiles: []
title: Complete reading of ABCD1234
status: ready
analysisFocus: Explain the main mechanism and its evidence.
primarySourceKey: ABCD1234
primarySource: "[[Literature/ABCD1234]]"
sourceKeys:
  - ABCD1234
sourceCount: 1
summary: The paper reports a bounded mechanism supported by its main experiment.
skillName: full-read
skillVersion: "1.0.0"
tags:
  - analysis
paperTitle: Example paper
year: 2026
journal: Example Journal
paperKind: experimental
researchQuestion: Which mechanism explains the reported result?
coreContribution: The study connects one mechanism to a measurable outcome.
methodSummary: The authors combine a controlled experiment with characterization.
mainFinding: The reported result supports the proposed mechanism under the tested conditions.
limitationSummary: The evidence does not establish behavior outside the tested conditions.
```
<!-- ovm:analysis-fields-example:end -->

The service derives and persists `analysisSchemaVersion`, `analysisId`, `sourceFingerprint`, `createdAt`, and `updatedAt`; do not guess them. Keep `status: ready` unless the user explicitly confirms review. `paperKind` is one of `experimental`, `theoretical`, `computational`, `methodological`, `clinical`, `observational`, `review`, `dataset`, `benchmark`, `mixed`, or `other`.

Obtain `primarySource` from `literature_paper_read.metadata.notePath`: remove the trailing `.md` and wrap the remaining Vault-relative path in `[[...]]`. The example uses the default layout only; never hard-code `Literature/{zoteroKey}` for a configurable Vault.

`analysisFocus` preserves the user's natural-language priority. `summary` is a separately written Base summary, not a truncated body. A summary field may contain at most 180 characters when it contains CJK text, otherwise 300 characters.

## Managed content

Pass only the Markdown owned by this analysis through `managed_content`, for example:

```markdown
# Paper title

## Quick read
## Research object and core question
## Background, prior work, and gap
## Core claim and contribution
## Research design or theoretical framework
## Discipline-specific analysis
## Main results, theorems, or observations
## Mechanism, interpretation, or proof logic
## Key figures, tables, and equations
## Robustness and controls
## Difference from related work
## Limitations, applicable boundary, and open questions
## Reusable implications
## Items requiring further checking
```

Do not include managed-block markers, `## User Notes`, or any user-owned section in `managed_content`. The service adds its own markers and preserves user notes, unknown sections, and unknown frontmatter fields.

Before updating an existing note, call `literature_analysis_get`. If the source changed, surface that state and do not silently replace the old analysis. Distinguish source results, author interpretation, and agent synthesis.
