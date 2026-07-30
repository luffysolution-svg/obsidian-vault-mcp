---
name: paper-qa
description: Answer broad questions about one paper in chat, such as what it says, its main contribution, or how to understand it. Use for single-paper overview and general explanation; route deep saved notes, exact passages, figures, and multi-paper work to their dedicated skills.
---

# Paper Q&A

<!-- ovm:skill-managed:start -->

1. Resolve exactly one source paper.
2. Preserve the user's question and stated focus.
3. Call `literature_paper_read` once in overview mode.
4. If the overview leaves a specific gap, make one focused targeted read; do not read every section or figure by default.
5. Explain the research problem, core approach, main result, contribution, and important boundary in your own words.
6. Use only a few decisive short quotations and keep them in the source language.
7. State what the available text does and does not support.
8. Answer in chat by default.

Do not call `literature_analysis_write` from this chat-only skill. If the user asks for persistence, switch to the matching dedicated skill and read its linked output contract before constructing any write call. Route a durable complete note to `full-read`, and route an exact paragraph, figure, comparison, review, or concept request to its matching skill.

<!-- ovm:skill-managed:end -->

## User Customizations

Add local answer conventions below this line.
