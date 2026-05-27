---
title: Obsidian Vault MCP 文档
lang: zh-CN
---

# Obsidian Vault MCP

Obsidian Vault MCP 是一个面向 Codex 的本地插件，用 MCP 工具和 Codex skill 把本地 Obsidian vault 维护成可持续增长的双链知识库。

## 文档

- [安装配置教程](./SETUP_GUIDE.zh-CN.md) — 面向普通用户的 step-by-step 安装配置指南（中文）
- [技术文档 / Technical Guide](./TECHNICAL_GUIDE.md) — 完整功能说明、全部 70 个工具、安装部署、配置、集成指南（中英双语）
- [部署与发布指南](./DEPLOYMENT.md) / [Deployment Guide](./DEPLOYMENT.md) — 发布前检查清单、GitHub 发布流程
- [隐私说明](./PRIVACY.zh-CN.md) / [Privacy](./PRIVACY.md)
- [参考与致谢](./REFERENCES.zh-CN.md) / [References](./REFERENCES.md)

## 快速安装

```bash
pip install zotero-obsidian-mcp
obsidian-vault-mcp --doctor --doctor-format text --vault /path/to/your-vault
```

Claude Code 用户可直接添加：

```bash
claude mcp add obsidian-vault obsidian-vault-mcp
```

详细配置见 [技术文档](./TECHNICAL_GUIDE.md)。

## 源码仓库

<https://github.com/luffysolution-svg/obsidian-vault-mcp>
