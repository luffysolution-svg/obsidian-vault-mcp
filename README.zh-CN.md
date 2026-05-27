# Obsidian Vault

面向 Codex、Claude Code 和 OpenCode 的本地 MCP 插件，将本地 Obsidian vault 维护成可持续增长的双链知识库。

[![PyPI](https://img.shields.io/pypi/v/zotero-obsidian-mcp?label=PyPI)](https://pypi.org/project/zotero-obsidian-mcp/)
[![Python](https://img.shields.io/pypi/pyversions/zotero-obsidian-mcp)](https://pypi.org/project/zotero-obsidian-mcp/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](./LICENSE)

> 完整中文文档见 [README.md](./README.md)，含快速开始、完整功能列表、配置说明、客户端部署和常用提示词。

[English README](./README.en.md) | [安装配置教程](./docs/SETUP_GUIDE.zh-CN.md) | [技术文档](./docs/TECHNICAL_GUIDE.md)

## 快速开始

**PyPI 安装（推荐）：**

```bash
pip install zotero-obsidian-mcp
obsidian-vault-mcp --doctor --doctor-format text --vault /path/to/your-vault
```

**Claude Code：**

```bash
pip install zotero-obsidian-mcp
claude mcp add obsidian-vault obsidian-vault-mcp
```

**Codex：** 将仓库根目录注册为本地插件，并确保 PyPI 包已安装。

**OpenCode：** 将仓库根目录的 `.opencode.json` 复制到项目目录，或合并到 `~/.opencode.json`。

## 主要功能

- vault 文件读写、搜索、笔记创建，支持 YAML property 批量更新。
- 写入前 `dry_run=true` diff 预览；批量编辑计划支持预览、应用、备份、回滚。
- 自动添加 wikilink，构建别名/标签/引用边图谱，结果按 mtime 缓存。
- 从 Zotero `relations` 构建引用网络；将 callout 块聚合为阅读摘要。
- lint 检查孤立笔记、死链、frontmatter 一致性；schema 校验 Canvas/Base/Markdown。
- 图谱改进建议：未解析链接、互链、可能重复页面、Markdown 链接转 wikilink。
- Karpathy 风格 wiki 工作流：`index.md` / `log.md`、source/entity/concept 页面整理。
- BibTeX、Zotero 条目、MinerU Markdown、PDF 附件一步导入文献。
- MinerU 批量解析整个 PDF 文件夹；图片按图注自动重命名为语义文件名（中文直通）。
- 直接访问 Zotero Desktop 本地 API：搜索、元数据、标注、PDF 附件、一步导入。
- JSON Canvas 自动布局（grid / radial / grouped / layered）、Obsidian Bases 创建、Dataview 查询笔记。
- 本地官方 `obsidian` CLI 封装：read/open、backlinks、Base query、properties、tasks、截图、plugin reload、move/rename。
- 附带 5 套标准 skill，帮助 AI 编程助手自动命中合适工作流。

完整功能列表和配置说明见 [README.md](./README.md)。
