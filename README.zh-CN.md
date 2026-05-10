# Obsidian Vault

面向 Codex 的本地 Obsidian Vault MCP 插件，用来把本地 Obsidian 仓库维护成可持续增长的双链知识库。

[English README](./README.md) | [中文文档站](./docs/index.md)

## 快速开始

详细配置请看 [配置指南](./docs/CONFIGURATION.zh-CN.md)。

在插件目录中运行：

```bash
python -m pip install -r requirements.txt
python scripts/obsidian_vault_mcp.py --doctor --doctor-format text --vault /path/to/your-vault
```

然后把本目录注册为 Codex 本地插件，或通过 Codex 本地 marketplace 暴露给 Codex。不要把个人 vault 路径、Zotero 存储路径、API token 或私有笔记内容提交到仓库。

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

- [安装指南](./docs/INSTALL.zh-CN.md)
- [配置指南](./docs/CONFIGURATION.zh-CN.md)
- [部署指南](./docs/DEPLOYMENT.zh-CN.md)
- [隐私说明](./docs/PRIVACY.zh-CN.md)
- [参考与致谢](./docs/REFERENCES.zh-CN.md)

## 可选外部工具

- Zotero Desktop：只有使用 Zotero 搜索、导入、PDF 附件和标注时需要。
- Obsidian CLI：只有使用 app-backed 读写、打开、backlinks、Base query、properties、tasks、截图、插件 reload、移动/重命名时需要。
- MinerU Open API CLI：只有希望本插件直接解析 PDF/文档时需要。已有 MinerU Markdown 可以直接导入，不需要 CLI。
- MinerU MCP：可作为独立伴随服务使用。本插件不会在内部调用另一个 MCP server，但 Codex 可以先用 MinerU MCP 解析，再用本插件导入 Markdown。

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

- “Show me the structure of this Obsidian vault.”
- “Create a linked wiki note with YAML properties.”
- “Add wikilinks between these notes and report orphans.”
- “Preview and apply a batch edit plan, then rollback if needed.”
- “Lint this vault and show unresolved links, dead ends, and missing index/log files.”
- “Ingest this BibTeX entry or MinerU extraction into the literature wiki.”
- “Search Zotero and ingest this Zotero item into Obsidian.”
- “Create a Canvas knowledge map from this vault's wikilinks.”
- “Use the Obsidian CLI to read backlinks or query a Base.”

## 官方参考

- Obsidian CLI: https://obsidian.md/help/cli
- Codex Skills: https://developers.openai.com/codex/skills
- Codex Plugins: https://developers.openai.com/codex/plugins
- Zotero Connector HTTP Server: https://www.zotero.org/support/dev/client_coding/connector_http_server
- Zotero Web API v3: https://www.zotero.org/support/dev/web_api/v3/basics
- MinerU Open API CLI: https://pkg.go.dev/github.com/opendatalab/MinerU-Ecosystem/cli
