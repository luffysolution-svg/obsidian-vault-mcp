---
name: uncertainty-audit
description: Convert unsupported or overstated analysis claims into structured review items.
version: 1.0.0
---

<!-- ovm:skill-managed:start -->
# Uncertainty audit

Audit the draft for claims without original evidence; correlation written as causation; author interpretation mixed with Agent inference; user notes presented as paper findings; altered definitions; missing units or conditions; abstract-only support presented as full-text support; hypotheses presented as results; single-paper or sampled findings generalized to a field; and unverifiable page, section, or figure labels.

For figures, flag caption-less interpretations, unlinked candidates treated as official figures, and visual observations made without a reliable PDF crop.

Return structured items containing claim, reason, verification target, evidence IDs, asset IDs, and `pending` status. Preserve uncertainty instead of completing absent details.
<!-- ovm:skill-managed:end -->

## User Customizations

Add local review thresholds here.
