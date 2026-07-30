---
layout: default
title: Troubleshooting
lang: en
---
# Troubleshooting

| Symptom | Action |
|---|---|
| `doctor` passes but Zotero fails | Start Zotero, enable its local API, and inspect the separate Zotero result. |
| Metadata imports but no PDF | Check `ZOTERO_STORAGE_DIR` and the linked attachment base separately. |
| MinerU parse fails | A present command does not prove authentication or network readiness; use an isolated copy for a real parse. |
| Analysis is `needs_update` | Its source fingerprint changed; review and explicitly update it. |
| Analysis Base is absent | Call `literature_rebuild_analysis_base`. |
| Client does not show 31 tools | Verify the actual package and launch command, restart it, then redo the handshake. |

```bash
obsidian-vault-mcp doctor --vault-path "<VAULT_PATH>"
obsidian-vault-mcp verify --vault-path "<VAULT_PATH>"
obsidian-vault-mcp preview <transaction-id> --vault-path "<VAULT_PATH>"
obsidian-vault-mcp rollback <transaction-id> --vault-path "<VAULT_PATH>" --dry-run
```
