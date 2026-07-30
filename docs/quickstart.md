---
layout: default
title: 快速开始
lang: zh-CN
---
# 快速开始

安装 3.0.1，并验证运行时契约：

```bash
uv tool install "zotero-obsidian-mcp==3.0.1"
obsidian-vault-mcp call literature_version --json '{}'
```

初始化目标 Vault；所有可写命令先使用 `--dry-run`：

```bash
obsidian-vault-mcp config init --vault-path "<VAULT_PATH>" --dry-run
obsidian-vault-mcp config init --vault-path "<VAULT_PATH>"
obsidian-vault-mcp doctor --vault-path "<VAULT_PATH>"
```

从 Zotero 搜索并导入一个**父条目** key：

```bash
obsidian-vault-mcp call zotero_search_items --json '{"query":"catalysis"}'
obsidian-vault-mcp import item ABCD1234 --vault-path "<VAULT_PATH>" --dry-run
```

继续阅读[完整安装](https://luffysolution-svg.github.io/obsidian-vault-mcp/installation/)和[配置](https://luffysolution-svg.github.io/obsidian-vault-mcp/configuration/)。
