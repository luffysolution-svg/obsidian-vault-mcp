---
layout: default
title: Analysis and Skills
lang: en
---
# Analysis and Skills

## Five Analysis types

| Type | Use | Output directory |
|---|---|---|
| `full_read` | Complete reading of one paper | `Analysis/full-reads/` |
| `literature_review` | Multi-paper review or comparison | `Analysis/reviews/` |
| `passage_qa` | A question answered at a located passage | `Analysis/qa/passages/` |
| `figure_qa` | Figure, table, scheme, or equation interpretation | `Analysis/qa/figures/` |
| `concept` | Cross-paper concept learning | `Analysis/concepts/` |

`Literature/Analysis/Analysis.base` is the single deterministic Base view over these notes. Profiles are `general`, `medicine`, `chemistry`, `materials`, `catalysis`, `physics`, and `mathematics`; statuses are `draft`, `ready`, `reviewed`, `needs_update`, and `archived`. Stable `analysisId`, source fingerprints, and source keys power duplicate detection and updates. Source changes mark `needs_update`; they never silently replace user-owned content.

## Seven Skills

| Skill | Typical prompt |
|---|---|
| `paper-qa` | “What are this paper's key findings?” |
| `full-read` | “Read this paper completely” |
| `passage-qa` | “How do these experimental conditions support the claim?” |
| `figure-qa` | “Explain Figure 3 / this equation” |
| `compare-papers` | “Compare the methods and results of these papers” |
| `literature-review` | “Prepare a literature review on this topic” |
| `concept-learning` | “Learn this concept across papers” |

Skills orchestrate research workflows. Official MCP Tools execute reads, retrievals, and writes; Skills are neither an independent database nor an independent Agent.
