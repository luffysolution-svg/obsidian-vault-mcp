# Obsidian Vault

面向 Codex 的本地 MCP 插件，将本地 Obsidian vault 维护成可持续增长的双链知识库。

[English README](./README.en.md) | [技术文档](./docs/TECHNICAL_GUIDE.md) | [文档站](./docs/index.md)

## 快速开始

在插件目录中运行：

```bash
python -m pip install -r requirements.txt
python scripts/obsidian_vault_mcp.py --doctor --doctor-format text --vault /path/to/your-vault
```

将本目录注册为 Codex 本地插件，然后重启或重新加载 MCP 客户端。个人 vault 路径、Zotero 存储路径、API token 和私有笔记内容只保存在本地配置中，不要提交到仓库。

## 功能概览

- vault 文件列出、搜索、读取、写入和笔记创建，支持 YAML property 更新。
- 写入前提供 `dry_run=true` unified diff 预览。
- 批量编辑计划支持多文件预览、应用、vault 内备份和回滚。
- 自动添加 wikilink，并基于别名、标签、未解析链接和歧义链接构建图谱。
- 检查孤立笔记、死链、重复 key、空笔记、缺失标题和 frontmatter 一致性。
- 校验 Markdown frontmatter、Canvas JSON 和 Base YAML 格式。
- 建议未解析链接、互链、可能重复页面、Markdown 链接和附件嵌入的图谱改进。
- Karpathy 风格 wiki 工作流：刷新 `index.md`、追加 `log.md`、将来源整理进 source/entity/concept 页面。
- 从 BibTeX、参考文献元数据、MinerU Markdown、PDF 附件和 Zotero 条目导入文献。
- 可选调用 MinerU Open API CLI 直接解析 PDF/文档后导入。
- 直接访问 Zotero Desktop 本地 API：搜索、元数据、子笔记、标注、PDF 附件、PDF 文本提取和一步导入。
- Zotero `zotero://` 链接、重复检测（key/DOI/citekey/标题）和可配置 PDF 附件命名策略。
- 从 Obsidian Templates、Templater 和插件配置发现用户模板。
- vault 内 `.obsidian-vault-mcp.json` 支持输出目录、模板目录、索引/日志路径和 Zotero 附件命名默认值。
- `--doctor` 就绪检查和只读 smoke 检查脚本。
- JSON Canvas 创建，包括从 vault wikilink 自动生成 grid、radial、grouped、layered 布局。
- Obsidian Bases 创建，内置文献、项目任务、设备、公用工程、经济性和来源材料模板。
- Dataview 查询笔记模板。
- 封装本地官方 `obsidian` CLI，提供 read/open、backlinks、Base query、properties、tasks、截图、plugin reload、move/rename dry-run 等结构化工具。
- 随插件发布的 `skills/obsidian-vault/SKILL.md`，让 Codex 知道何时、如何调用这些工具。

## 配置

在本地 MCP 配置中设置 `OBSIDIAN_VAULT_PATH`，或在每次工具调用时传入 `vault_path`。`.mcp.json` 默认使用 `auto`，会通过本地 Obsidian CLI 获取当前活动 vault，CLI 不可用时回退到进程工作目录。

```json
{
  "OBSIDIAN_VAULT_PATH": "auto",
  "OBSIDIAN_CLI_COMMAND": "obsidian"
}
```

CLI 封装需要 Obsidian 1.12.7 或更高版本，且 `obsidian` 命令在 PATH 中。

Zotero 工具需要 Zotero Desktop 本地 API 运行在 `http://127.0.0.1:23119/api`，可通过 `ZOTERO_LOCAL_API` 覆盖。

MinerU 支持是可选的。已有 MinerU Markdown 可直接导入，无需安装 MinerU。如需直接解析文档，安装 `mineru-open-api` 并使用 `obsidian_mineru_*` 工具。`flash-extract` 无需 token；精确 `extract` 可能需要 MinerU token。本插件不会自动安装 MinerU CLI、MinerU MCP、Zotero Desktop 或 Obsidian CLI。

MinerU 提取会调用多个 MinerU/OpenXLab 端点。使用 VPN、代理或 fake-IP DNS 时，请确保以下域名可直连：

- `mineru.net`
- `mineru.oss-cn-shanghai.aliyuncs.com`
- `cdn-mineru.openxlab.org.cn`
- `*.openxlab.org.cn`

常见失败场景：解析任务和 OSS 上传成功，但从 `cdn-mineru.openxlab.org.cn` 下载 `full.md` 时出现 TLS/EOF 错误。遇到此问题请先检查代理/DNS 规则。

默认要求路径解析到包含 `.obsidian` 的文件夹。只有在明确使用普通 Markdown 文件夹时才设置 `OBSIDIAN_ALLOW_NON_VAULT=true`。

## Vault 内默认配置

可在 vault 根目录的 `.obsidian-vault-mcp.json` 或 `.obsidian/obsidian-vault-mcp.json` 中保存可复用的默认值。工具参数显式传入时优先级更高。

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

Zotero 附件命名策略：`original`、`zotero_key`、`citekey`、`title_year`、`parent_key`。

## 用户模板

`obsidian_list_user_templates` 从以下位置发现 Markdown 模板：

- Obsidian Templates 核心插件配置 `.obsidian/templates.json`；
- Templater 插件配置 `.obsidian/plugins/templater-obsidian/data.json`；
- 上述插件默认配置中的 `templateFolder` 和 `defaultTemplate`。

`obsidian_create_note` 支持通过 `template_path`、`template_name`、`use_template=true` 或配置的 `defaultTemplate` 应用模板。支持 `{{title}}`、`{{body}}`、`{{date}}`、`{{time}}` 等变量的安全文本替换，不执行 Templater JavaScript。

## Doctor 检查

不启动 MCP 服务器，直接运行本地就绪检查：

```bash
python scripts/obsidian_vault_mcp.py --doctor --doctor-format text --vault /path/to/your-vault
```

Zotero Desktop、Obsidian CLI、MinerU、PDF 文本提取等可选集成会作为检查项报告，不可用时不影响核心 vault 工具。去掉 `--doctor-format text` 可获得 JSON 输出，适合自动化或提交 bug 报告。

## 批量编辑计划

批量编辑工具接受 JSON 数组或带 `operations` 数组的对象。每个操作可用 `op`、`operation` 或 `type` 指定动作名。支持的动作：`write`、`update_properties`、`append`、`replace`、`delete`。

```json
{
  "operations": [
    {
      "operation": "update_properties",
      "path": "Projects/Alpha.md",
      "properties": { "status": "draft" }
    },
    {
      "operation": "append",
      "path": "Projects/Alpha.md",
      "content": "\n\n已由 Codex 审阅。"
    }
  ]
}
```

先运行 `obsidian_preview_edit_plan`，确认后再运行 `obsidian_apply_edit_plan`。应用后会在 `.obsidian-vault-backups/` 创建备份，可通过 `obsidian_rollback_edit_plan` 恢复。

## 安装依赖

MCP 服务器基于 Python：

```bash
python -m pip install -r requirements.txt
```

开发模式安装（同时提供 `obsidian-vault-mcp` 命令行工具）：

```bash
python -m pip install -e ".[dev]"
obsidian-vault-mcp --doctor --doctor-format text --vault /path/to/your-vault
```

打开 Obsidian 和 Zotero Desktop 后，可运行只读集成检查：

```bash
python scripts/smoke_integrations.py --vault /path/to/your-vault
```

smoke 脚本只读，仅做 dry-run 写入预览。检查内容包括 vault 解析、dry-run 笔记创建、Zotero 本地 API 访问和 Obsidian CLI。

详细安装和配置说明见 [技术文档](./docs/TECHNICAL_GUIDE.md)。

## 代码架构

MCP 入口保持在 `scripts/obsidian_vault_mcp.py`，确保现有 `.mcp.json` 安装继续可用。该文件是薄封装：将 `scripts/` 加入 `sys.path`，导入包，启动服务器。

实现包在 `scripts/obsidian_vault_mcp/`：

- `common.py`：共享导入、常量和 MCP 工具注册元数据。
- `helpers.py`：vault 安全路径、frontmatter/YAML 处理、图谱工具、Canvas/Base/schema 工具、编辑计划支持、Zotero/MinerU 工具等非工具实现细节。
- `tools.py`：公开的 MCP 工具函数和 CLI 封装。
- `server.py`：FastMCP 服务器构建和工具注册。
- `__init__.py`：供测试和直接导入使用的包导出。

### 可选外部工具

- Zotero Desktop：仅在使用 Zotero 文库搜索/导入时需要。
- Obsidian CLI：仅在使用 app-backed read/open/backlinks/Base/property/task/截图操作时需要。
- MinerU CLI（`mineru-open-api`）：仅在使用 `obsidian_mineru_extract` 和 `obsidian_mineru_extract_and_ingest` 时需要。
- MinerU MCP：可选伴随服务器。Codex 可用 MinerU MCP 解析文档，再用本插件导入生成的 Markdown。本插件不在内部调用 MinerU MCP。

CLI 封装的可选 `vault` 参数是 Obsidian 已知的 vault 名称，不是文件系统路径。省略时 CLI 使用当前活动 vault。`obsidian_read_file`、`obsidian_create_note` 等直接文件工具仍接受 `vault_path` 文件系统路径。

Windows MinerU 连通性快速检查：

```powershell
mineru-open-api version
curl.exe -I https://mineru.net
curl.exe -I https://cdn-mineru.openxlab.org.cn
Resolve-DnsName cdn-mineru.openxlab.org.cn
```

如果 `cdn-mineru.openxlab.org.cn` 解析到 `198.18.x.x` 等 fake-IP 地址，请配置代理/VPN DNS 规则，确保 MinerU/OpenXLab 域名使用可用路由。

## 通过 Codex 部署

可以让 Codex 帮你安装和配置本插件。将以下提示词复制到 Codex：

```text
Install and configure the open-source Obsidian Vault MCP plugin from
https://github.com/luffysolution-svg/obsidian-vault-mcp.

Please:
1. Clone the repository to a suitable local plugins folder.
2. Install its Python dependencies with `python -m pip install -r requirements.txt`.
3. Register it as a local Codex plugin/MCP server using the checked-in `.mcp.json`.
4. Keep the portable `${CLAUDE_PLUGIN_ROOT}` script path; do not hard-code the repository path into files that will be committed.
5. Use `OBSIDIAN_VAULT_PATH=auto` by default. If auto-detection fails, ask me for my local Obsidian vault path and configure it only in my local MCP/plugin settings.
6. Do not modify or publish my Obsidian vault contents.
7. Verify the server can start, then run `python -m unittest discover -s tests`.
8. Tell me how to restart/reload Codex so the new MCP tools become available.

Optional: if I want Zotero features, remind me to open Zotero Desktop so its
local API at `http://127.0.0.1:23119/api` is reachable.

Optional: if I want MinerU document parsing, check whether `mineru-open-api`
is installed. If it is not installed, tell me how to install it. Do not store
or commit MinerU tokens in the repository. Use `flash-extract` when I do not
have a token, and use precision `extract` only when I have configured MinerU
authentication locally.
```

## 发布安全说明

本仓库设计为可被其他用户复用，默认配置具有可移植性：

- `.mcp.json` 使用 `${CLAUDE_PLUGIN_ROOT}` 而非绝对脚本路径。
- `OBSIDIAN_VAULT_PATH` 默认 `auto`，用户可在本地设置自己的 vault 路径而无需提交。
- Zotero 集成指向用户自己的本地 Zotero Desktop API。
- 文件工具默认拒绝非 vault 文件夹，除非用户显式设置 `OBSIDIAN_ALLOW_NON_VAULT=true`。
- 单元测试创建临时 vault，不写入真实 vault。

## 可移植性说明

- 插件不硬编码 vault 路径。`auto` 跟随本地 Obsidian CLI 当前活动的 vault。
- 所有文件操作限制在解析后的 vault 根目录内。
- 现有文件不会被覆盖，除非工具调用传入 `overwrite=true`。
- 写入工具支持 `dry_run=true`，返回 unified diff 而不修改文件。
- Wiki 工作流工具将生成内容保存在标记注释内，手写笔记内容可保留在托管块之外。
- Obsidian CLI 功能需要 Obsidian Desktop 正在运行。设置了 `OBSIDIAN_VAULT_PATH` 时，直接文件工具在 CLI 不可用时仍可正常工作。

## 贡献与发布

完整发布检查清单和 GitHub 发布流程见 [部署指南](./docs/DEPLOYMENT.md)。

## 常用提示词

- "展示这个 Obsidian vault 的结构。"
- "创建一条带 YAML properties 的双链笔记。"
- "在这些笔记之间添加 wikilink，并报告孤立笔记。"
- "预览并应用批量编辑计划，如有需要可回滚。"
- "检查这个 vault，显示未解析链接、死链和缺失的 index/log 文件。"
- "校验整个 vault 的 frontmatter、Canvas 和 Base schema。"
- "预览缺失 frontmatter 的 schema 默认值修复。"
- "为未解析和弱链接页面建议图谱改进。"
- "刷新 wiki 索引并追加一条日志。"
- "将这个来源整理进关联的 source、entity 和 concept 笔记。"
- "将这条 BibTeX 条目或 MinerU 提取结果导入文献知识库。"
- "检查 MinerU CLI 是否对这个 vault 可用。"
- "用 MinerU flash-extract 解析这个 PDF 并导入 Obsidian。"
- "搜索 Zotero 并将该条目导入 Obsidian。"
- "为这个 PDF 附件创建来源笔记。"
- "为这个项目创建设备或经济性 Base 模板。"
- "创建 Dataview 设备表格笔记。"
- "创建这个主题群的 Canvas 知识图谱。"
- "从这个 vault 的 wikilink 生成 Canvas 知识图谱。"
- "用 Obsidian CLI 读取 backlinks 或查询 Base。"

## 参考资料

- Kepano 的 Obsidian Skills 将领域拆分为 Markdown、Bases、Canvas、CLI 和提取技能：https://github.com/kepano/obsidian-skills
- Karpathy 的 LLM Wiki 模式将 Obsidian 视为持久化 LLM 维护 wiki 的 IDE：https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f
- Obsidian CLI 文档：https://help.obsidian.md/cli
- Codex Skills 文档：https://developers.openai.com/codex/skills
- Codex Plugins 文档：https://developers.openai.com/codex/plugins
- Zotero 本地连接器 HTTP 服务器文档：https://www.zotero.org/support/dev/client_coding/connector_http_server
- Zotero Web API v3 基础：https://www.zotero.org/support/dev/web_api/v3/basics
- MinerU Open API CLI 文档：https://pkg.go.dev/github.com/opendatalab/MinerU-Ecosystem/cli
