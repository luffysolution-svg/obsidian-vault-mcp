# Concept-model contract

## Scope

Set a `conceptName`, one `conceptKind`, a bounded source pool, and the user's learning objective. Valid kinds are `theory`, `mechanism`, `method`, `metric`, `model`, `material`, `equation`, and `phenomenon`.

Keep only concepts that carry the explanation. Establish what the concept distinguishes, its prerequisites, inputs, mechanism, first observable consequence, representative cases, boundary conditions, neighboring concepts, and a minimal equation or decision rule when justified.

## Write call

When persistence is requested, call `literature_analysis_write` with `fields`, `managed_content`, `vault_path`, and `dry_run: true`. Inspect the preview, then repeat the same fields and managed content with `dry_run: false`.

The client supplies every field in this canonical example:

<!-- ovm:analysis-fields-example:start -->
```yaml
analysisType: concept
analysisProfile: general
secondaryProfiles: []
title: Concept model for directed transfer
status: ready
analysisFocus: Explain the mechanism, prerequisites, and boundaries.
primarySourceKey: ""
primarySource: ""
sourceKeys:
  - ABCD1234
  - EFGH5678
sourceCount: 2
summary: Directed transfer links energetic alignment to an observable carrier redistribution.
skillName: concept-learning
skillVersion: "1.0.0"
tags:
  - analysis
  - concept
conceptName: Directed transfer
conceptKind: mechanism
aliases:
  - interface-mediated transfer
definitionSummary: Carrier movement follows an energetically and structurally supported direction.
relationSummary: Alignment and coupling precede redistribution and the measured outcome.
useSummary: The model helps evaluate whether an interface can support the proposed pathway.
prerequisites:
  - energetic alignment
  - interfacial coupling
relatedConcepts:
  - charge separation
  - active-site utilization
```
<!-- ovm:analysis-fields-example:end -->

The service derives and persists `analysisSchemaVersion`, `analysisId`, `sourceFingerprint`, `createdAt`, and `updatedAt`; do not guess them. A concept requires at least one unique, existing source key, and `sourceCount` must match. Keep both primary-source fields empty.

## Managed content

Pass only the concept-owned Markdown through `managed_content`, for example:

```markdown
# Concept name

## Why this concept is needed
## Operational definition
## Prerequisites
## Relationship model
## How papers define, use, or measure it
## Representative cases
## Boundary conditions and counterexamples
## Neighboring concepts
## Minimal equation, diagram, or decision rule
## Transfer to the user's research
## Self-check questions
```

Do not include managed-block markers, `## User Notes`, or any user-owned section in `managed_content`; the service adds markers and preserves user-owned content. Do not produce a glossary or invent relations unsupported by the sources.
