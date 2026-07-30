---
layout: default
title: Quick start
lang: en
---
# Quick start

After release, install 3.0.0 and confirm the runtime contract:

```bash
uv tool install "zotero-obsidian-mcp==3.0.0"
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

Continue with [full installation]({{ '/en/installation/' | relative_url }}) and [configuration]({{ '/en/configuration/' | relative_url }}).
