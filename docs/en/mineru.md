---
layout: default
title: MinerU parsing
lang: en
---
# MinerU parsing

After configuring the MinerU Open API CLI, parsing starts in hidden staging. Formal files are committed only after Markdown selection, image renaming, and relative-link validation all succeed in one transaction.

```bash
obsidian-vault-mcp mineru parse ABCD1234 --vault-path "<VAULT_PATH>" --dry-run
obsidian-vault-mcp mineru parse-batch ABCD1234 EFGH5678 --vault-path "<VAULT_PATH>" --dry-run
```

```text
Literature/attachment/MinerU/{zoteroKey}.md
Literature/attachment/MinerU/image/{zoteroKey}/{zoteroKey}-figNN.ext
```

Markdown uses relative links such as `![](image/ABCD1234/ABCD1234-fig01.png)`. A failed paper does not publish partial output.
