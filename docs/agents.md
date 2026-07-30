---
layout: default
title: Agent 客户端安装
lang: zh-CN
---
# Agent 客户端安装

实际 installer 支持 Codex、Claude Code、OpenCode、Pi、Hermes、WorkBuddy：

```bash
obsidian-vault-mcp agent install <client> --dry-run
obsidian-vault-mcp agent install <client>
```

| 客户端 | 安装内容 |
|---|---|
| Codex | 原生 marketplace plugin、MCP、7 Skills |
| Claude Code | 原生 marketplace plugin、MCP、7 Skills |
| OpenCode | 项目本地 MCP 与 7 Skills |
| Pi | 共享 JSON CLI 的 TypeScript Extension |
| Hermes | MCP 配置（不自动安装 Skills） |
| WorkBuddy | MCP 配置（不自动安装 Skills） |

## Codex 插件安装

先安装 Python 包，并确认 `codex` 已在 `PATH` 中。以下命令会注册随 Python 包提供的 `obsidian-vault-mcp` marketplace，然后安装 `obsidian-literature@obsidian-vault-mcp` 原生插件、MCP Server 和 7 个 Skills：

```bash
obsidian-vault-mcp agent install codex --dry-run
obsidian-vault-mcp agent install codex
codex plugin marketplace list --json
codex plugin list --json
```

升级 Python 包后，执行 `codex plugin add obsidian-literature@obsidian-vault-mcp --json`。卸载时执行 `codex plugin remove obsidian-literature@obsidian-vault-mcp --json`；若不再使用该 marketplace，再执行 `codex plugin marketplace remove obsidian-vault-mcp --json`。

## Claude Code 插件安装

先安装 Python 包，并确认 `claude` 已在 `PATH` 中。安装器会以用户范围注册同一个 marketplace，并安装原生插件、MCP Server 和 7 个 Skills：

```bash
obsidian-vault-mcp agent install claude --dry-run
obsidian-vault-mcp agent install claude
claude plugin marketplace list --json
claude plugin list --json
```

升级 Python 包后，依次执行：

```bash
claude plugin marketplace update obsidian-vault-mcp
claude plugin update obsidian-literature@obsidian-vault-mcp --scope user
```

然后重启 Claude Code。卸载时执行 `claude plugin uninstall obsidian-literature@obsidian-vault-mcp --scope user`；若不再使用该 marketplace，再执行 `claude plugin marketplace remove obsidian-vault-mcp --scope user`。

Codex/Claude 使用选择器 `obsidian-literature@obsidian-vault-mcp`。OpenCode、Pi、Hermes、WorkBuddy 以当前项目或 `--project-dir` 为目标。配置型 installer 会备份、合并、验证并 handshake；失败时回滚本次新增状态。若提示同名 marketplace 来自另一个安装路径，请先确认要切换的版本，再按报错中的卸载提示移除旧 marketplace；安装器不会自动删除已有配置。
