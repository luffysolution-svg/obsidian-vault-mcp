# Figure, table, scheme, and equation analysis

## Location and interpretation

Confirm `targetLabel` from a caption or explicit body text. Do not derive it from an image filename, numerical order, or extraction order. Confirm a panel label independently.

Read the complete caption and nearby paragraphs first. For a compound figure, inspect the whole item before the requested panel. Separate direct observations from scientific interpretation and relation to the paper's claim.

`targetType` is `figure`, `table`, `scheme`, or `equation`. `visualMode` is `image`, `table_text`, `caption_context`, or `equation_text`. Use `image` only after checking the real Vault-relative file. If the file is missing, set `imageExists: false`, use `caption_context`, embed nothing, and state that the answer relies on caption and prose.

## Write call

When persistence is requested, call `literature_analysis_write` with `fields`, `managed_content`, `vault_path`, and `dry_run: true`. Inspect the preview, then repeat the same fields and managed content with `dry_run: false`.

The client supplies every field in this canonical example:

<!-- ovm:analysis-fields-example:start -->
```yaml
analysisType: figure_qa
analysisProfile: general
secondaryProfiles: []
title: Figure answer for ABCD1234
status: ready
analysisFocus: Interpret Figure 2 panel b from the caption and image.
primarySourceKey: ABCD1234
primarySource: "[[Literature/ABCD1234]]"
sourceKeys:
  - ABCD1234
sourceCount: 1
summary: Figure 2b supplies bounded visual evidence for the reported mechanism.
skillName: figure-qa
skillVersion: "1.0.0"
tags:
  - analysis
  - figure
question: What does Figure 2 panel b show?
answerSummary: The panel shows the measured contrast under the reported conditions.
targetType: figure
targetLabel: Fig. 2
targetPanel: b
page: 6
imagePath: Literature/attachment/MinerU/image/ABCD1234/ABCD1234-fig02.jpg
imageExists: true
visualMode: image
sourceLink: "[[Literature/attachment/MinerU/ABCD1234#Figure 2]]"
captionSummary: The caption defines the samples, measurement, and panel assignment.
```
<!-- ovm:analysis-fields-example:end -->

The service derives and persists `analysisSchemaVersion`, `analysisId`, `sourceFingerprint`, `createdAt`, and `updatedAt`; do not guess them. Obtain `primarySource` from `literature_paper_read.metadata.notePath`: remove `.md` and wrap the Vault-relative path in `[[...]]`. The example uses the default layout only.

Set `imagePath` from the path returned by `literature_paper_read` in figures mode. `imageExists` must match the actual filesystem state. Do not use `visualMode: image` or embed an image when it is missing.

## Managed content

Pass only the answer-owned Markdown through `managed_content`, for example:

```markdown
# Figure 2b

## Direct conclusion
## Source location and caption
## Direct observations
## Scientific interpretation
## Relation to the paper's claim
## Limitations and missing context
```

Include the real Vault-relative image embed only when `imageExists` is true. Do not include managed-block markers, `## User Notes`, or any user-owned section in `managed_content`; the service adds markers and preserves user-owned content. Do not install image-processing dependencies or use OCR as an automatic fallback.
