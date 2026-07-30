---
name: concept-learning
description: Build a reusable concept model from one or more papers for a theory, mechanism, method, metric, material, equation, model, or phenomenon. Use when the user wants to learn how a concept works, its prerequisites, boundaries, relations, and applications; not for a dictionary definition.
---

# Concept learning

<!-- ovm:skill-managed:start -->

Read [the concept-model contract](references/concept-model.md) before structuring or saving the result.

1. Define the concept name, kind, source pool, and the user's learning goal.
2. Use `literature_retrieve` to find definitions, mechanisms, measurements, examples, and boundary cases.
3. Use targeted `literature_paper_read` calls only where the cross-paper map lacks decisive context.
4. Keep the load-bearing concepts rather than collecting every term.
5. Explain what the concept distinguishes, what it is not, and which prerequisites it depends on.
6. Build a relationship chain from conditions through mechanism to observable consequences.
7. Add representative paper cases, counterexamples, boundary conditions, neighboring concepts, and a minimal equation or decision rule when justified.
8. End with transfer guidance and self-check questions.
9. Use `literature_analysis_get` to detect an existing concept note, then preview and commit with `literature_analysis_write`.

Do not reduce the result to a glossary or invent a relation that the sources cannot support.

<!-- ovm:skill-managed:end -->

## User Customizations

Add local concept-learning conventions below this line.
