---
layout: default
title: User configuration
lang: en
---
# User configuration

The only runtime configuration is `<Vault>/.obsidian-vault-mcp.json`. Its `schemaVersion` is an independent data-format version, not package version 3.0.2.

`config init` creates it, `config get` reads it, and `config validate` validates it. Its top-level domains are:

```text
literature  identity  naming  attachments  frontmatter  note
zotero  bibtex  mineru  analysis  index  base  safety
```

```json
{"analysis":{"folder":"Literature/Analysis","base":"Literature/Analysis/Analysis.base","fullReadsFolder":"Literature/Analysis/full-reads","reviewsFolder":"Literature/Analysis/reviews","passageQaFolder":"Literature/Analysis/qa/passages","figureQaFolder":"Literature/Analysis/qa/figures","conceptsFolder":"Literature/Analysis/concepts"}}
```

Every Vault-visible path is relative and stays inside the Vault. There is no `defaultDryRunForMigration` field.

## Analysis intent

Express the focus naturally, for example: “Focus on catalytic mechanism, characterization evidence, and experimental conditions; do not repeat the introduction at length.” Workflow outputs such as `analysisFocus` are written by the workflow; users do not maintain complex custom templates.

## Skill customizations

Each `SKILL.md` has a `## User Customizations` area for lasting preferences. The installer replaces only its managed section, preserving that area. It stores hashes for managed text and references, refusing to overwrite modified user content. The actual OpenCode target is `<project>/.opencode/skills/`; other targets are returned by their installer and must not be guessed from documentation.
