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

Codex/Claude 使用选择器 `obsidian-literature@obsidian-vault-mcp`。OpenCode、Pi、Hermes、WorkBuddy 以当前项目或 `--project-dir` 为目标。配置型 installer 会备份、合并、验证并 handshake；失败时回滚本次新增状态。请以返回的路径与卸载说明为准。
