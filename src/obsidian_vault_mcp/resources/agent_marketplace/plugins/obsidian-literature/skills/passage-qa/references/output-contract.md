# Passage Q&A output contract

Persist only when the user asks. The normal response remains in chat.

## Write call

Call `literature_analysis_write` with `fields`, `managed_content`, `vault_path`, and `dry_run: true`. Inspect the preview, then repeat the same fields and managed content with `dry_run: false`.

The client supplies every field in this canonical example:

<!-- ovm:analysis-fields-example:start -->
```yaml
analysisType: passage_qa
analysisProfile: general
secondaryProfiles: []
title: Passage answer for ABCD1234
status: ready
analysisFocus: Locate the exact mechanism statement.
primarySourceKey: ABCD1234
primarySource: "[[Literature/ABCD1234]]"
sourceKeys:
  - ABCD1234
sourceCount: 1
summary: The selected passage directly states the mechanism under discussion.
skillName: passage-qa
skillVersion: "1.0.0"
tags:
  - analysis
  - question
question: Where does the paper explain the mechanism?
answerSummary: The Results section states the mechanism and its immediate consequence.
sourceSection: Results
sourceSubsection: Mechanism
sourceParagraph: 6
sourceLink: "[[Literature/attachment/MinerU/ABCD1234#Mechanism]]"
locatorQuality: exact
quoteFingerprint: "sha256:1111111111111111111111111111111111111111111111111111111111111111"
```
<!-- ovm:analysis-fields-example:end -->

The service derives and persists `analysisSchemaVersion`, `analysisId`, `sourceFingerprint`, `createdAt`, and `updatedAt`; do not guess them. Obtain `primarySource` from `literature_paper_read.metadata.notePath`: remove `.md` and wrap the Vault-relative path in `[[...]]`. The example uses the default layout only.

`locatorQuality` is:

- `exact`: the section and specific paragraph are reliable.
- `section_only`: only the section can be located reliably.
- `approximate`: nearby text supports the match but exact placement is not reliable.

Never use line numbers as the only permanent locator. Prefer a link to the relevant MinerU heading. Fingerprint the exact quoted source text so a later source change can be detected.

## Managed content

Pass only the answer-owned Markdown through `managed_content`, for example:

```markdown
# Question

## Direct answer
## Source location
- Paper:
- Section:
- Subsection:
- Paragraph:
- Full-text link:
- Location quality:

## Key source text
> A necessary short quotation in the source language

## Interpretation
## What this passage can support
## What this passage cannot support
## Relevant context
```

Do not include managed-block markers, `## User Notes`, or any user-owned section in `managed_content`. The service adds its own markers and preserves user-owned content. Do not fabricate a page, heading, paragraph, quotation, or precision level.
