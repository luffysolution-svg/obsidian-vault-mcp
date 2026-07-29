---
name: verify-paper-claims
description: Resolve pending paper claims against targeted text and image evidence.
version: 1.0.0
---

<!-- ovm:skill-managed:start -->
# Verify paper claims

1. List pending uncertainty items for the paper.
2. For each verification target, call `literature_paper_read` with `mode=targeted` and `record_coverage=true`.
3. If the matching section is needed, call `literature_paper_read` with `mode=sections` and `record_coverage=true`.
4. For a figure-related item, call `literature_paper_read` with `mode=figures`, `include_images=true`, and `record_coverage=true`; inspect its caption, surrounding text, asset status, and PDF crop availability.
5. Choose `confirmed`, `rejected`, `revised`, or `unresolved` and provide evidence IDs, asset IDs, and a concise resolution note.
6. Use `revised` with a preserved original claim and an explicit revised claim.
7. Submit the structured resolution before editing prose. Preview writes first.
8. Use `queryVariants` only to expand recall. Coverage Ledger records describe coverage and are not evidence or paper facts.

Do not confirm a text claim without valid text evidence or any visual claim unless `visualStatus=visual_verified`. Use `unresolved` when verification remains impossible.
<!-- ovm:skill-managed:end -->

## User Customizations

Add preferred verification queues here.
