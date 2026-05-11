# Obsidian Vault

面向 Codex 的本地 Obsidian Vault MCP 插件，用来把本地 Obsidian 仓库维护成可持续增长的双链知识库。

[English README](./README.md) | [中文文档站](./docs/index.md)

## 快速开始

详细配置请看 [技术文档](./docs/TECHNICAL_GUIDE.md)。

在插件目录中运行：

```bash
python -m pip install -r requirements.txt
python scripts/obsidian_vault_mcp.py --doctor --doctor-format text --vault /path/to/your-vault
```

然后把本目录注册为 Codex 本地插件，或通过 Codex 本地 marketplace 暴露给 Codex。

## 功能概览

- 列出、搜索、读取、写入 Obsidian vault 文件。
- 创建带 YAML properties 的 Markdown 笔记。
- 写入前提供 `dry_run=true` 统一 diff 预览。
- 批量编辑计划支持预览、应用、vault 内备份和回滚。
- 自动添加 wikilinks，并基于别名、标签、未解析链接和歧义链接构建图谱。
- 检查孤立笔记、死端笔记、重复 key、空笔记、缺失标题和 frontmatter 类型问题。
- 校验 Markdown frontmatter、JSON Canvas 和 Obsidian Bases YAML。
- 根据图谱建议创建未解析页面、补充反向链接、合并可能重复页面、转换普通 Markdown 链接。
- 支持 Karpathy 风格的 LLM wiki 工作流：刷新 `index.md`、追加 `log.md`、把来源材料整理进 source/entity/concept 页面。
- 支持 BibTeX、参考文献元数据、已有 MinerU Markdown、PDF 附件和 Zotero 条目的文献导入。
- 可选调用 MinerU Open API CLI 解析 PDF/文档，再导入 Obsidian。
- 直接访问 Zotero Desktop 本地 API，支持搜索条目、读取元数据、子笔记、标注、PDF 附件和 PDF 文本。
- 支持 Zotero `zotero://` 链接、重复检测和 PDF 附件命名策略。
- 发现 Obsidian Templates、Templater 和插件配置里的用户模板。
- 支持 vault 内 `.obsidian-vault-mcp.json` 默认输出目录、模板目录、索引/日志路径和 Zotero 附件命名。
- 提供 `--doctor` 就绪检查和只读 smoke 检查脚本。
- 创建 JSON Canvas，包括从 wikilinks 图谱自动生成 grid、radial、grouped、layered 布局。
- 创建 Obsidian Bases，包括文献、项目任务、设备、公用工程、经济性和来源材料模板。
- 创建 Dataview 查询笔记。
- 包装本地官方 `obsidian` CLI，并提供 read/open、backlinks、Base query、properties、tasks、screenshots、plugin reload、move/rename dry-run 等结构化工具。
- 附带 `skills/obsidian-vault/SKILL.md`，让 Codex 知道什么时候、怎样调用这些工具。

## 安装与配置

核心依赖是 Python：

```bash
python -m pip install -r requirements.txt
```

开发模式：

```bash
python -m pip install -e ".[dev]"
obsidian-vault-mcp --doctor --doctor-format text --vault /path/to/your-vault
```

`.mcp.json` 默认使用可移植配置：

```json
{
  "mcpServers": {
    "obsidian-vault": {
      "type": "stdio",
      "command": "python",
      "args": ["${CLAUDE_PLUGIN_ROOT}/scripts/obsidian_vault_mcp.py"],
      "env": {
        "OBSIDIAN_VAULT_PATH": "auto",
        "OBSIDIAN_CLI_COMMAND": "obsidian"
      }
    }
  }
}
```

`OBSIDIAN_VAULT_PATH=auto` 会尝试通过 Obsidian CLI 获取当前活动 vault。如果失败，可以只在本地 MCP/插件配置中设置显式 vault 路径。

更多细节：

- [技术文档 / Technical Guide](./docs/TECHNICAL_GUIDE.md)
- [部署指南](./docs/DEPLOYMENT.zh-CN.md)
- [隐私说明](./docs/PRIVACY.zh-CN.md)
- [参考与致谢](./docs/REFERENCES.zh-CN.md)

## 可选外部工具

- **Zotero Desktop**（[下载](https://www.zotero.org/download/)，当前版本 9.x）：只有使用 Zotero 搜索、导入、PDF 附件和标注时需要。
- **Obsidian CLI**：Obsidian 1.12.7+ 内置，在 设置 → 高级 → 启用 Obsidian CLI 中开启，只有使用 app-backed 读写、打开、backlinks、Base query、properties、tasks、截图、插件 reload、移动/重命名时需要。
- **MinerU**（[GitHub](https://github.com/opendatalab/MinerU)）：只有希望本插件直接解析 PDF/文档时需要，安装命令：`pip install -U "mineru[full]"`。已有 MinerU Markdown 可以直接导入，不需要安装。
- **MinerU MCP**：可作为独立伴随服务使用。本插件不会在内部调用另一个 MCP server，但 Codex 可以先用 MinerU MCP 解析，再用本插件导入 Markdown。

### Zotero 插件依赖

> 以下插件均支持 Zotero 8 / 9。从 Releases 页面下载 `.xpi` 文件，在 Zotero 中通过 工具 → 附加组件 → 从文件安装 完成安装。

| 插件 | 作用 | 必要性 | 安装地址 |
|------|------|--------|----------|
| **Better BibTeX for Zotero** | 为每条文献生成稳定的 `citekey`（如 `chenLowvalence2024`），用于笔记命名、去重和 PDF 附件命名策略 `citekey` | 强烈推荐；缺少时回退到 Zotero key | [GitHub Releases](https://github.com/retorquere/zotero-better-bibtex/releases) |
| **Ethereal Style (ZoteroStyle)** | 为标注颜色设置自定义名称（如背景/实验/结果/方法），导入 Obsidian 后 callout 标签显示用户定义名称 | 可选；缺少时显示英文颜色名 | [GitHub Releases](https://github.com/MuiseDestiny/zotero-style/releases) |
| **Zotero PDF Translate** | 自动翻译 PDF 标注内容，翻译结果写入 `annotationComment`，本插件会将其导入 Obsidian 笔记的 **Note:** 字段 | 可选；有翻译需求时推荐 | [GitHub Releases](https://github.com/windingwind/zotero-pdf-translate/releases) |

Zotero Desktop 本身的本地 HTTP 服务（端口 `23119`）是内置功能，无需额外插件即可使用。

### Obsidian 插件推荐

以下 Obsidian 社区插件与本 MCP 插件的工作流配合使用效果更佳，均可在 Obsidian 设置 → 社区插件中搜索安装：

| 插件 | 作用 | GitHub |
|------|------|--------|
| **Dataview** | 查询 vault 中的 frontmatter 属性，本插件可生成 Dataview 查询笔记 | [GitHub](https://github.com/blacksmithgu/obsidian-dataview) |
| **Templater** | 高级模板引擎，本插件支持发现并应用 Templater 模板 | [GitHub](https://github.com/SilentVoid13/Templater) |
| **Zotero Integration** | 在 Obsidian 内直接从 Zotero 导入文献笔记（与本插件功能互补，可并行使用） | [GitHub](https://github.com/mgmeyers/obsidian-zotero-integration) |

## Vault 内默认配置

可以在 vault 根目录放：

```text
.obsidian-vault-mcp.json
```

或：

```text
.obsidian/obsidian-vault-mcp.json
```

示例：

```json
{
  "literatureFolder": "01-literature",
  "mineruSourceFolder": "02-sources/mineru",
  "pdfSourceFolder": "02-sources/pdf",
  "entitiesFolder": "entities",
  "conceptsFolder": "concepts",
  "zoteroAttachmentsFolder": "assets/zotero",
  "zoteroAttachmentNameStrategy": "zotero_key",
  "indexPath": "index.md",
  "logPath": "log.md",
  "templateFolder": "Templates",
  "defaultTemplate": "Literature"
}
```

显式工具参数优先级高于 vault 默认配置。

## 本地检查

```bash
python scripts/obsidian_vault_mcp.py --doctor --doctor-format text --vault /path/to/your-vault
python -m unittest discover -s tests
```

打开 Obsidian 和 Zotero Desktop 后，可运行只读集成检查：

```bash
python scripts/smoke_integrations.py --vault /path/to/your-vault
```

## 常用提示词

- “展示这个 Obsidian vault 的结构。”
- “创建一条带 YAML properties 的双链笔记。”
- “在这些笔记之间添加 wikilinks，并报告孤立笔记。”
- “预览并应用批量编辑计划，如有需要可回滚。”
- “检查这个 vault，显示未解析链接、死端笔记和缺失的 index/log 文件。”
- “把这条 BibTeX 条目或 MinerU 提取结果导入文献知识库。”
- “搜索 Zotero 并把该条目导入 Obsidian。”
- “从这个 vault 的 wikilinks 生成 Canvas 知识图谱。”
- “用 Obsidian CLI 读取 backlinks 或查询 Base。”

## 官方参考

- Obsidian CLI: https://help.obsidian.md/cli
- Codex Skills: https://developers.openai.com/codex/skills
- Codex Plugins: https://developers.openai.com/codex/plugins
- Zotero Connector HTTP Server: https://www.zotero.org/support/dev/client_coding/connector_http_server
- Zotero Web API v3: https://www.zotero.org/support/dev/web_api/v3/basics
- MinerU Open API CLI: https://pkg.go.dev/github.com/opendatalab/MinerU-Ecosystem/cli
