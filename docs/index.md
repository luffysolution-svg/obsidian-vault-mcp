---
title: Obsidian Vault MCP 中文文档
lang: zh-CN
---

# Obsidian Vault MCP

Obsidian Vault MCP 是一个面向 Codex 的本地插件，用 MCP 工具和 Codex skill 把本地 Obsidian vault 维护成可持续增长的双链知识库。

它适合这些场景：

- 让 Codex 安全读写本地 Obsidian vault。
- 通过 dry-run diff 预览笔记修改。
- 批量编辑、备份和回滚 vault 文件。
- 管理 YAML properties、tags、wikilinks、backlinks 和图谱健康。
- 创建 JSON Canvas、Obsidian Bases 和 Dataview 查询笔记。
- 把 Zotero、BibTeX、PDF、MinerU Markdown 导入文献知识库。
- 调用官方 Obsidian CLI 执行 app-backed 操作。

## 文档入口

- [项目 README 中文版](../README.zh-CN.md)
- [安装指南](./INSTALL.zh-CN.md)
- [完整配置指南](./CONFIGURATION.zh-CN.md)
- [部署与发布指南](./DEPLOYMENT.zh-CN.md)
- [隐私说明](./PRIVACY.zh-CN.md)
- [参考与致谢](./REFERENCES.zh-CN.md)
- [GitHub 展示 README 中文版](./GITHUB_REFERENCE_README.zh-CN.md)

英文文档仍保留在同一目录中：

- [Install](./INSTALL.md)
- [Configuration](./CONFIGURATION.md)
- [Deployment](./DEPLOYMENT.md)
- [Privacy](./PRIVACY.md)
- [References](./REFERENCES.md)

## 快速安装

```bash
python -m pip install -r requirements.txt
python scripts/obsidian_vault_mcp.py --doctor --doctor-format text --vault /path/to/your-vault
```

然后在 Codex 中安装或启用该本地插件。插件根目录必须包含：

```text
.codex-plugin/plugin.json
.mcp.json
skills/obsidian-vault/SKILL.md
scripts/obsidian_vault_mcp.py
```

## GitHub 仓库

源码仓库：<https://github.com/luffysolution-svg/obsidian-vault-mcp>
