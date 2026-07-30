---
layout: default
title: 故障排查
lang: zh-CN
---
# 故障排查

| 现象 | 处理 |
|---|---|
| `doctor` 成功但 Zotero 失败 | 启动 Zotero、开启本地 API，并查看独立的 Zotero 结果。 |
| 导入元数据却没有 PDF | 分别检查 `ZOTERO_STORAGE_DIR` 与 linked attachment base。 |
| MinerU 解析失败 | 命令可用不代表认证或网络就绪；只在隔离副本做真实解析。 |
| Analysis 为 `needs_update` | 源指纹变了；复核后显式更新。 |
| Analysis Base 缺失 | 调用 `literature_rebuild_analysis_base`。 |
| 客户端看不到 31 工具 | 核对实际包与启动命令、重启客户端并重新 handshake。 |

```bash
obsidian-vault-mcp doctor --vault-path "<VAULT_PATH>"
obsidian-vault-mcp verify --vault-path "<VAULT_PATH>"
obsidian-vault-mcp preview <transaction-id> --vault-path "<VAULT_PATH>"
obsidian-vault-mcp rollback <transaction-id> --vault-path "<VAULT_PATH>" --dry-run
```
