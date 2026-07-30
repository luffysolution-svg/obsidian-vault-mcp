---
layout: default
title: Full installation
lang: en
---
# Full installation

## Requirements and packages

Use Python 3.10+. Open the target Vault in Obsidian at least once. Run Zotero Desktop with its local API enabled. MinerU is optional external parsing software.

{% include release-notice.html %}

```bash
python -m pip install --upgrade "zotero-obsidian-mcp==3.0.1"
pipx install "zotero-obsidian-mcp==3.0.1"
uv tool install "zotero-obsidian-mcp==3.0.1"
uvx --from "zotero-obsidian-mcp==3.0.1" obsidian-vault-mcp --help
```

The compatible `zotero-obsidian-mcp` CLI and primary `obsidian-vault-mcp` CLI start the same program. After release, source installation is possible from the official tag: `git checkout v3.0.1`, then `python -m pip install -e ".[dev]"`.

## Initialize, import, and sync

```bash
obsidian-vault-mcp config init --vault-path "<VAULT_PATH>" --dry-run
obsidian-vault-mcp config init --vault-path "<VAULT_PATH>"
obsidian-vault-mcp config validate --vault-path "<VAULT_PATH>"
obsidian-vault-mcp doctor --vault-path "<VAULT_PATH>"
obsidian-vault-mcp import item ABCD1234 --vault-path "<VAULT_PATH>" --dry-run
obsidian-vault-mcp import collection COLLECTION_KEY --vault-path "<VAULT_PATH>" --dry-run
obsidian-vault-mcp sync item ABCD1234 --vault-path "<VAULT_PATH>" --dry-run
obsidian-vault-mcp sync collection COLLECTION_KEY --vault-path "<VAULT_PATH>" --dry-run
```

Always provide a Zotero **parent item** `zoteroKey`, never an attachment key. See [Zotero]({{ '/en/zotero/' | relative_url }}).

## MinerU, indexes, and Analysis

```bash
obsidian-vault-mcp mineru parse ABCD1234 --vault-path "<VAULT_PATH>" --dry-run
obsidian-vault-mcp index rebuild --vault-path "<VAULT_PATH>" --dry-run
obsidian-vault-mcp base rebuild --vault-path "<VAULT_PATH>" --dry-run
obsidian-vault-mcp verify --vault-path "<VAULT_PATH>"
obsidian-vault-mcp agent install codex --dry-run
```

Analysis uses MCP Tools and Skills together; see [Analysis and Skills]({{ '/en/analysis/' | relative_url }}) and [Agents]({{ '/en/agents/' | relative_url }}).

## Safety, upgrade, and uninstall

Preview every write. Retain the returned `transactionId`, then use `preview` and `rollback` to inspect or restore a transaction. Package upgrades do not delete Vault literature, PDFs, MinerU output, Wiki, Analysis, or backups. Uninstall with the original package manager, then follow the Agent installer's returned `uninstall_instructions`. Never commit tokens, absolute Vault paths, or `linkedAttachmentBaseDir`.

MinerU can transmit PDFs to an external service; confirm document rights and organizational policy first.
