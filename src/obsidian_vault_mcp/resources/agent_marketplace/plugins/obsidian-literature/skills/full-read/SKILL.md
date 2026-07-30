---
name: full-read
description: Produce and optionally save a complete structured reading of one paper, adapting depth to the user's natural-language focus and discipline. Use for deep reading, full-text analysis, or a complete paper note; not for one passage, one figure, or multiple papers.
---

# Full read

<!-- ovm:skill-managed:start -->

Read [discipline profiles](references/discipline-profiles.md) before selecting default analysis axes and [the output contract](references/output-contract.md) before writing.

1. Resolve exactly one source paper and capture the user's analysis focus verbatim.
2. Infer a primary profile and optional secondary profiles; user priorities override defaults.
3. Call `literature_paper_read` once in overview mode.
4. Read missing sections in targeted mode according to the focus and selected profiles.
5. Read figures only when they materially support the requested analysis.
6. Separate reported results, author interpretation, and your synthesis.
7. Generate concise metadata plus a coherent full analysis; do not translate the abstract section by section.
8. Use `literature_analysis_get` to detect an existing full read and source changes.
9. Call `literature_analysis_write` with dry-run enabled, inspect the complete preview, then commit only if it is valid.

Preserve source-language short quotations. Never invent bibliographic facts, locations, figure labels, numerical values, mechanisms, or causal claims.

<!-- ovm:skill-managed:end -->

## User Customizations

Add local full-read conventions below this line.
