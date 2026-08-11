---
layout: default
title: 完整安装教程
lang: zh-CN
---
# 完整安装教程

## 系统与包

需要 Python 3.10+；Obsidian 应至少打开过一次目标 Vault；Zotero Desktop 需运行并开启本地 API。MinerU 是可选的外部解析服务。

```bash
python -m pip install --upgrade "zotero-obsidian-mcp==3.0.2"
pipx install "zotero-obsidian-mcp==3.0.2"
uv tool install "zotero-obsidian-mcp==3.0.2"
uvx --from "zotero-obsidian-mcp==3.0.2" obsidian-vault-mcp --help
```

兼容 CLI `zotero-obsidian-mcp` 与主 CLI `obsidian-vault-mcp` 指向同一程序。发布后也可从正式 tag 安装源码：`git checkout v3.0.2` 后运行 `python -m pip install -e ".[dev]"`。

## 初始化、导入与同步

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

必须使用 Zotero **父条目**的 `zoteroKey`，而不是附件 key。详见 [Zotero](https://luffysolution-svg.github.io/obsidian-vault-mcp/zotero/)。

## MinerU、索引与 Analysis

```bash
obsidian-vault-mcp mineru parse ABCD1234 --vault-path "<VAULT_PATH>" --dry-run
obsidian-vault-mcp index rebuild --vault-path "<VAULT_PATH>" --dry-run
obsidian-vault-mcp base rebuild --vault-path "<VAULT_PATH>" --dry-run
obsidian-vault-mcp verify --vault-path "<VAULT_PATH>"
obsidian-vault-mcp agent install codex --dry-run
```

Analysis 通过 MCP Tools 与 Skills 协作；见 [Analysis 与 Skills](https://luffysolution-svg.github.io/obsidian-vault-mcp/analysis/) 和 [Agent](https://luffysolution-svg.github.io/obsidian-vault-mcp/agents/)。

## Codex 与 Claude Code 插件

安装好上面的 Python 包后，可分别运行以下命令安装原生插件、MCP Server 和 7 个 Skills：

```bash
obsidian-vault-mcp agent install codex --dry-run
obsidian-vault-mcp agent install codex

obsidian-vault-mcp agent install claude --dry-run
obsidian-vault-mcp agent install claude
```

完整的验证、升级与卸载命令见 [Agent 客户端安装](https://luffysolution-svg.github.io/obsidian-vault-mcp/agents/)。

## 安全、升级与卸载

每次写入先预览；保存返回的 `transactionId`，并可用 `preview`、`rollback` 检查或恢复事务。升级包不会删除 Vault 文献、PDF、MinerU、Wiki、Analysis 或备份。按原安装器卸载 Python 包；再按 Agent installer 返回的 `uninstall_instructions` 移除其管理的客户端配置。不要将 token、绝对 Vault 路径或 `linkedAttachmentBaseDir` 提交进仓库。

MinerU 可能将 PDF 发送至外部服务，请先确认文献权利与组织政策。
