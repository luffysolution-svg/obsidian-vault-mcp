# Obsidian Vault

## Literature pipeline default

The default MCP profile is now `literature`: a focused Zotero + MinerU + Obsidian pipeline for importing stable literature notes, copying Zotero PDFs, preserving `zotero://select` and `zotero://open-pdf` links, optionally parsing PDFs with MinerU, renaming extracted images as English semantic slugs, and generating `images-index.md`.

Use `OBSIDIAN_VAULT_TOOL_PROFILE=full` or `OBSIDIAN_VAULT_TOOL_PROFILE=legacy` to expose the older broad Obsidian toolbox for wiki, graph, Canvas, Bases, Dataview, schema, and CLI workflows.

Default pipeline tools:

- `obsidian_pipeline_doctor`
- `obsidian_pipeline_config`
- `obsidian_pipeline_migrate_layout`
- `obsidian_pipeline_ingest_item`
- `obsidian_pipeline_ingest_collection`
- `obsidian_pipeline_parse_with_mineru`
- `obsidian_pipeline_rename_mineru_images`

Vault-local pipeline config lives in `.obsidian-vault-pipeline.json`:

```json
{
  "literatureFolder": "literature",
  "zoteroAttachmentsFolder": "attachments/zotero",
  "mineruAttachmentsFolder": "attachments/mineru",
  "noteFilenamePattern": "{firstAuthor} {year} - {shortTitle}",
  "pdfFilenamePattern": "{shortTitle}",
  "mineruMarkdownName": "paper.md",
  "mineruImagesIndexName": "images-index.md"
}
```

面向 Codex、Claude Code 和 OpenCode 的本地 MCP 插件，将本地 Obsidian vault 维护成可持续增长的双链知识库。

[![PyPI](https://img.shields.io/pypi/v/zotero-obsidian-mcp?label=PyPI)](https://pypi.org/project/zotero-obsidian-mcp/)
[![Python](https://img.shields.io/pypi/pyversions/zotero-obsidian-mcp)](https://pypi.org/project/zotero-obsidian-mcp/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](./LICENSE)

[English README](./README.en.md) | [安装配置教程](./docs/SETUP_GUIDE.zh-CN.md) | [技术文档](./docs/TECHNICAL_GUIDE.md) | [文档站](./docs/index.md)

## 快速开始

**方式一：PyPI 安装（推荐）**

```bash
pip install zotero-obsidian-mcp
obsidian-vault-mcp --doctor --doctor-format text --vault /path/to/your-vault
```

**方式二：源码安装（开发者 / 跟进最新提交）**

```bash
git clone https://github.com/luffysolution-svg/obsidian-vault-mcp.git
cd obsidian-vault-mcp
pip install -e .
obsidian-vault-mcp --doctor --doctor-format text --vault /path/to/your-vault
```

将本目录注册为 Codex 本地插件，或将 MCP server 添加到 Claude Code 或 OpenCode，然后重启或重新加载 MCP 客户端。个人 vault 路径、Zotero 存储路径、API token 和私有笔记内容只保存在本地配置中，不要提交到仓库。

## 功能概览

- vault 文件列出、搜索、读取、写入和笔记创建，支持 YAML property 更新。
- 写入前提供 `dry_run=true` unified diff 预览。
- 批量编辑计划支持多文件预览、应用、vault 内备份和回滚。
- 自动添加 wikilink，并基于别名、标签、未解析链接和歧义链接构建图谱。
- 图谱构建仅扫描正文 wikilink/embed，frontmatter 中的 `related`、`cites`、`references`、`entities`、`concepts`、`sources` 字段单独提取为带类型标签的引用边，不与正文链接混淆。
- 图谱结果基于文件 mtime 缓存，vault 无变更时重复调用直接返回缓存，大型文献库性能显著提升。
- 检查孤立笔记、死链、重复 key、空笔记、缺失标题和 frontmatter 一致性。
- 校验 Markdown frontmatter、Canvas JSON 和 Base YAML 格式。
- 建议未解析链接、互链（可通过 `max_reciprocal` 限制数量）、可能重复页面（词边界感知，避免 "My Note" 与 "MyNote" 误判）、Markdown 链接和附件嵌入的图谱改进。
- Karpathy 风格 wiki 工作流：刷新 `index.md`、追加 `log.md`、将来源整理进 source/entity/concept 页面。
- 从 Zotero `relations` 字段构建文献引用网络，自动生成笔记间引用边（`obsidian_build_citation_network`）。
- 将 vault callout 块（高亮、笔记、批注等）按标签或类型聚合为可读阅读摘要（`obsidian_build_reading_digest`）。
- 从 BibTeX、参考文献元数据、MinerU Markdown、PDF 附件和 Zotero 条目导入文献。
- 可选调用 MinerU Open API CLI 直接解析 PDF/文档后导入；支持 `obsidian_mineru_extract_folder` 批量处理整个 PDF 目录。
- MinerU 解析图片按正文图注自动重命名为语义文件名，保留中文字符，便于知识图谱节点索引（`obsidian_mineru_rename_images`）。
- 直接访问 Zotero Desktop 本地 API：列出文库分类、搜索、元数据、子笔记、标注、PDF 附件、PDF 文本提取和一步导入。
- Zotero `zotero://` 链接、重复检测（key/DOI/citekey/标题）和可配置 PDF 附件命名策略。
- 导入时自动解析 Zotero 集合名称（`collections` 字段存储可读名称而非内部 key），仅写入有值的类型专用字段，空字段不写入 frontmatter。
- 从 Obsidian Templates、Templater 和插件配置发现用户模板。
- vault 内 `.obsidian-vault-mcp.json` 支持输出目录、模板目录、索引/日志路径和 Zotero 附件命名默认值。
- `--doctor` 就绪检查和只读 smoke 检查脚本。
- JSON Canvas 创建，包括从 vault wikilink 自动生成 grid、radial、grouped、layered 布局；layered 布局支持通过 `layer_order_json` 传入自定义层级顺序。
- Obsidian Bases 创建，内置文献、项目任务、设备、公用工程、经济性和来源材料模板。
- Dataview 查询笔记模板。
- 封装本地官方 `obsidian` CLI，提供 read/open、backlinks、Base query、properties、tasks、截图、plugin reload、move/rename dry-run 等结构化工具。
- 随插件发布一组标准 skills，帮助 Codex 自动命中合适的工作流。`pip install` 安装后 skills 位于 Python 包目录内（`<site-packages>/obsidian_vault_mcp/skills/`）；clone 源码安装后位于仓库根目录 `skills/`。

## 内置 Skills

- `obsidian-vault`：通用 vault 维护、frontmatter、双链、图谱检查、批量编辑计划、index/log 维护。
- `obsidian-zotero`：Zotero 搜索、单条导入、合集批量导入、附件、批注与重导入同步。
- `obsidian-mineru`：MinerU 文档解析、批量文件夹提取、图片语义重命名、Markdown 导入、vault PDF 来源笔记、Zotero 全文挂接。
- `obsidian-views`：JSON Canvas、Obsidian Bases、内置 Base 模板和 Dataview 查询笔记。
- `obsidian-cli`：backlinks、properties、tasks、截图、plugin reload、带链接更新的 move/rename 等 Obsidian CLI 操作。

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

与 Zotero 联动的推荐三步工作流：

1. `obsidian_ingest_zotero_item` → 将文献导入 `literature/`，生成完整 YAML、笔记和批注。
2. `obsidian_mineru_extract_and_ingest`（传入 `zotero_key`）→ 解析 PDF，在 `sources/mineru/` 生成全文笔记，同时向文献 note 的 YAML 追加 `mineru_markdown: [[...]]` 跳转链接。
3. 文献 note 的正文和其他 YAML 字段完全不变，仅新增一个可点击的 MinerU 全文链接。

MinerU 提取会调用多个 MinerU/OpenXLab 端点。使用 VPN、代理或 fake-IP DNS 时，请确保以下域名可直连：

- `mineru.net`
- `mineru.oss-cn-shanghai.aliyuncs.com`
- `cdn-mineru.openxlab.org.cn`
- `*.openxlab.org.cn`

常见失败场景：解析任务和 OSS 上传成功，但从 `cdn-mineru.openxlab.org.cn` 下载 `full.md` 时出现 TLS/EOF 错误。遇到此问题请先检查代理/DNS 规则。
`NO_PROXY` 在显式 HTTP 代理场景下可能有帮助，但在全局代理、TUN 或 fake-IP 路由模式下经常不会生效。这种情况下通常需要直接在代理客户端里配置直连或 DNS bypass 规则。

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

**PyPI 安装（推荐）：**

```bash
pip install zotero-obsidian-mcp
```

**源码开发模式安装：**

```bash
python -m pip install -e ".[dev]"
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

- **Zotero Desktop**（[下载](https://www.zotero.org/download/)，当前版本 9.x）：仅在使用 Zotero 文库搜索/导入时需要。
- **Obsidian CLI**：Obsidian 1.12.7+ 内置，在 设置 → 高级 → 启用 Obsidian CLI 中开启，仅在使用 app-backed read/open/backlinks/Base/property/task/截图操作时需要。
- **MinerU**（[GitHub](https://github.com/opendatalab/MinerU)）：仅在使用 `obsidian_mineru_extract` 和 `obsidian_mineru_extract_and_ingest` 时需要。安装命令：`pip install -U "mineru[full]"`。已有 MinerU Markdown 可直接导入，无需安装。
- **MinerU MCP**：可选伴随服务器。Codex 可用 MinerU MCP 解析文档，再用本插件导入生成的 Markdown。本插件不在内部调用 MinerU MCP。

### Zotero 插件依赖

> 以下插件均支持 Zotero 8 / 9。从 Releases 页面下载 `.xpi` 文件，在 Zotero 中通过 工具 → 附加组件 → 从文件安装 完成安装。

| 插件 | 作用 | 必要性 | 安装地址 |
|------|------|--------|----------|
| **Better BibTeX for Zotero** | 为每条文献生成稳定的 `citekey`（如 `chenLowvalence2024`），用于笔记命名、去重和 PDF 附件命名策略 `citekey` | 强烈推荐；缺少时回退到 Zotero key | [GitHub Releases](https://github.com/retorquere/zotero-better-bibtex/releases) |
| **Ethereal Style (ZoteroStyle)** | 为标注颜色设置自定义名称（如背景/实验/结论），导入 Obsidian 后 callout 标签显示用户定义名称。插件优先精确匹配 ZoteroStyle 配置的 hex 值，其次按 RGB 距离最近色匹配（容差 ≤ 15），最后回退英文颜色名。建议颜色 hex 与 Zotero 8 种标准色保持一致以避免旧标注识别问题。 | 可选；缺少时显示英文颜色名 | [GitHub Releases](https://github.com/MuiseDestiny/zotero-style/releases) |
| **Zotero PDF Translate** | 自动翻译 PDF 标注内容，翻译结果写入 `annotationComment`，本插件会将其导入 Obsidian 笔记的 **Note:** 字段 | 可选；有翻译需求时推荐 | [GitHub Releases](https://github.com/windingwind/zotero-pdf-translate/releases) |

Zotero Desktop 本身的本地 HTTP 服务（端口 `23119`）是内置功能，无需额外插件即可使用。

### Obsidian 插件推荐

以下 Obsidian 社区插件与本 MCP 插件的工作流配合使用效果更佳，均可在 Obsidian 设置 → 社区插件中搜索安装：

| 插件 | 作用 | GitHub |
|------|------|--------|
| **Dataview** | 查询 vault 中的 frontmatter 属性，本插件可生成 Dataview 查询笔记 | [GitHub](https://github.com/blacksmithgu/obsidian-dataview) |
| **Templater** | 高级模板引擎，本插件支持发现并应用 Templater 模板 | [GitHub](https://github.com/SilentVoid13/Templater) |
| **Zotero Integration** | 在 Obsidian 内直接从 Zotero 导入文献笔记（与本插件功能互补，可并行使用） | [GitHub](https://github.com/mgmeyers/obsidian-zotero-integration) |

CLI 封装的可选 `vault` 参数是 Obsidian 已知的 vault 名称，不是文件系统路径。省略时 CLI 使用当前活动 vault。`obsidian_read_file`、`obsidian_create_note` 等直接文件工具仍接受 `vault_path` 文件系统路径。

Windows MinerU 连通性快速检查：

```powershell
mineru-open-api version
curl.exe -I https://mineru.net
curl.exe -I https://cdn-mineru.openxlab.org.cn
Resolve-DnsName cdn-mineru.openxlab.org.cn
```

如果 `cdn-mineru.openxlab.org.cn` 解析到 `198.18.x.x` 等 fake-IP 地址，请配置代理/VPN DNS 规则，确保 MinerU/OpenXLab 域名使用可用路由。

## AI 辅助安装

将以下提示词粘贴给任意 AI 编程助手（Codex、Claude Code、OpenCode 等）：

```text
Install and configure the Obsidian Vault MCP plugin from
https://github.com/luffysolution-svg/obsidian-vault-mcp.

1. Install the PyPI package `zotero-obsidian-mcp` with `pip install zotero-obsidian-mcp`, or use `pip install -e .` for a source checkout. Do not install the unrelated PyPI package `obsidian-vault-mcp`; `obsidian-vault-mcp` is the executable command, not the package name.
2. Keep `OBSIDIAN_VAULT_PATH=auto` unless auto-detection fails.
3. Set up the client I am using:
   - Codex: use `.codex-plugin/plugin.json` and `.mcp.json`.
   - Claude Code: first install `zotero-obsidian-mcp`, then run `claude mcp add obsidian-vault obsidian-vault-mcp`, or add the `.mcp.json` server block manually. If skills are not auto-loaded, copy the packaged `skills/` directory into `~/.claude/skills/`.
   - OpenCode: copy `opencode.json` into the project, or merge its `mcp` block into `~/.config/opencode/opencode.json`.
4. Keep vault paths, Zotero storage paths, and tokens in local config only.
5. Run `obsidian-vault-mcp --doctor --doctor-format text --vault /path/to/your-vault`.
6. If I need Zotero features, remind me to open Zotero Desktop. If I need MinerU parsing, check whether `mineru-open-api` is installed.
```

## 客户端部署

### Codex

- 将仓库作为本地插件目录使用，保留 `.codex-plugin/plugin.json`、`.mcp.json` 和 `skills/` 在根目录。
- 推荐先安装 PyPI 包：

```bash
pip install zotero-obsidian-mcp
```

- 如果你直接使用源码仓库：

```bash
git clone https://github.com/luffysolution-svg/obsidian-vault-mcp.git
cd obsidian-vault-mcp
pip install -e .
```

### Claude Code

**PyPI 安装后直接添加：**

```bash
pip install zotero-obsidian-mcp
claude mcp add obsidian-vault obsidian-vault-mcp
```

注意：PyPI 包名是 `zotero-obsidian-mcp`，不是 `obsidian-vault-mcp`。`obsidian-vault-mcp` 是安装后生成的命令行工具名称。

**源码安装后添加：**

```bash
git clone https://github.com/luffysolution-svg/obsidian-vault-mcp.git
cd obsidian-vault-mcp
pip install -e .
claude mcp add obsidian-vault obsidian-vault-mcp
```

或手动添加到 `~/.claude/settings.json`：

```json
{
  "mcpServers": {
    "obsidian-vault": {
      "type": "stdio",
      "command": "obsidian-vault-mcp",
      "env": {
        "OBSIDIAN_VAULT_PATH": "auto",
        "OBSIDIAN_CLI_COMMAND": "obsidian"
      }
    }
  }
}
```

- `.claude-plugin/plugin.json` 供 Claude Code 插件系统使用。
- 如果 Claude Code 没有自动加载 skills，可将包内 `skills/` 复制到 `~/.claude/skills/`。

### OpenCode

- 将仓库根目录的 `opencode.json` 复制到你的项目目录，或将 `mcp` 块合并到全局 `~/.config/opencode/opencode.json`。

```json
{
  "mcp": {
    "obsidian-vault": {
      "type": "local",
      "command": ["obsidian-vault-mcp"],
      "environment": {
        "OBSIDIAN_VAULT_PATH": "auto",
        "OBSIDIAN_CLI_COMMAND": "obsidian"
      }
    }
  }
}
```

## 可移植性与安全说明

- `.mcp.json` 使用已安装的 `obsidian-vault-mcp` 入口命令；对多数用户来说，`pip install zotero-obsidian-mcp` 是最稳的部署方式。
- `.codex-plugin/plugin.json`、`.claude-plugin/plugin.json` 和 `opencode.json` 分别服务于三种客户端，建议一起保留在仓库根目录。
- 插件不硬编码 vault 路径；`auto` 会跟随本地 Obsidian CLI 当前活动的 vault。
- 所有文件操作限制在解析后的 vault 根目录内，现有文件不会被覆盖，除非工具调用显式传入 `overwrite=true`。
- 写入工具支持 `dry_run=true`，Wiki 工作流将生成内容保存在标记注释内，方便保留手写内容。
- 本地路径、Zotero 存储路径、token 和私有 vault 内容应始终保存在本地配置中，不要提交。

## 贡献与发布

完整发布检查清单和 GitHub 发布流程见 [部署指南](./docs/DEPLOYMENT.md)。

## 常用提示词

- "展示这个 Obsidian vault 的结构。"
- "创建一条带 YAML properties 的双链笔记。"
- "在这些笔记之间添加 wikilink，并报告孤立笔记。"
- "检查这个 vault，显示未解析链接、死链和缺失的 index/log 文件。"
- "将这条 BibTeX 条目或 Zotero 条目导入 Obsidian。"
- "用 MinerU flash-extract 解析这个 PDF 并导入 Obsidian。"
- "批量解析这个文件夹内所有 PDF 并导入 Obsidian。"
- "用图注重命名这个 Markdown 文件里的 MinerU 提取图片。"
- "根据 Zotero relations 构建文献引用网络。"
- "生成这个文献文件夹的阅读摘要（高亮 + 笔记）。"
- "为这个项目创建 Base 视图或 Dataview 笔记。"
- "用 Obsidian CLI 读取 backlinks 或查询 Base。"

## 参考资料

- Kepano 的 Obsidian Skills 将领域拆分为 Markdown、Bases、Canvas、CLI 和提取技能：https://github.com/kepano/obsidian-skills
- Karpathy 的 LLM Wiki 模式将 Obsidian 视为持久化 LLM 维护 wiki 的 IDE：https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f
- Obsidian CLI 文档：https://help.obsidian.md/cli
- Codex Skills 文档：https://developers.openai.com/codex/skills
- Codex Plugins 文档：https://developers.openai.com/codex/plugins
- OpenCode MCP 文档：https://docs.opencode.ai/docs/mcp-servers
- OpenCode 配置参考：https://opencode-ai-opencode.mintlify.app/core-concepts/configuration
- Zotero 本地连接器 HTTP 服务器文档：https://www.zotero.org/support/dev/client_coding/connector_http_server
- Zotero Web API v3 基础：https://www.zotero.org/support/dev/web_api/v3/basics
- MinerU Open API CLI 文档：https://pkg.go.dev/github.com/opendatalab/MinerU-Ecosystem/cli
