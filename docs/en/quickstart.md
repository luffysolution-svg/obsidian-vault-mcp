---
layout: default
title: Quick start
lang: en
---
# Quick start

Install 3.0.1 and confirm the runtime contract:

```bash
uv tool install "zotero-obsidian-mcp==3.0.1"
obsidian-vault-mcp call literature_version --json '{}'
```

Initialize the target Vault; preview every write first:

```bash
obsidian-vault-mcp config init --vault-path "<VAULT_PATH>" --dry-run
obsidian-vault-mcp config init --vault-path "<VAULT_PATH>"
obsidian-vault-mcp doctor --vault-path "<VAULT_PATH>"
```

Search Zotero and import a **parent-item** key:

```bash
obsidian-vault-mcp call zotero_search_items --json '{"query":"catalysis"}'
obsidian-vault-mcp import item ABCD1234 --vault-path "<VAULT_PATH>" --dry-run
```

Continue with [full installation](https://luffysolution-svg.github.io/obsidian-vault-mcp/en/installation/) and [configuration](https://luffysolution-svg.github.io/obsidian-vault-mcp/en/configuration/).
