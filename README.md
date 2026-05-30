# Obsidian Vault

## 工具列表（17个核心工具）

默认只提供 17 个专注于 Zotero→MinerU→Obsidian 文献管道的 MCP 工具：

| 类别 | 工具 |
|------|------|
| Pipeline | `obsidian_pipeline_doctor`、`obsidian_pipeline_config`、`obsidian_pipeline_migrate_layout` |
| 文献导入 | `obsidian_pipeline_ingest_item`、`obsidian_pipeline_ingest_collection` |
| MinerU | `obsidian_pipeline_parse_with_mineru`、`obsidian_pipeline_rename_mineru_images` |
| Zotero | `obsidian_zotero_ping`、`obsidian_zotero_search_items`、`obsidian_zotero_list_collections`、`obsidian_zotero_get_item`、`obsidian_zotero_get_children`、`obsidian_zotero_list_pdf_attachments` |
| Vault 基础 | `obsidian_read_file`、`obsidian_write_file`、`obsidian_search`、`obsidian_update_properties` |

## Skills（技能）

图谱分析、Wiki 维护、Canvas/Bases/Dataview 视图、Obsidian CLI 控制等高级工作流已转为 Skills，通过 Claude Code 或 Codex 调用：

| Skill | 功能 |
|-------|------|
| `obsidian-vault` | 图谱、lint、wiki、schema、批量编辑、文件管理 |
| `obsidian-cli` | Obsidian 桌面 CLI 控制 |
| `obsidian-views` | Canvas、Bases、Dataview |
| `obsidian-graph` | 引用网络、社区检测、连通性分析 |
| `obsidian-mineru` | MinerU 直接解析、批量处理 |
| `obsidian-zotero` | Zotero 搜索与文献导入 |

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

- Vault 文件搜索、读取、写入和 YAML property 更新。
- Zotero Desktop 本地 API 集成：搜索、元数据获取、子条目、PDF 附件。
- 从 Zotero 条目一步导入文献笔记，复制 PDF 到 vault，保留 `zotero://` 链接。
- 可选调用 MinerU Open API CLI 直接解析 PDF/文档后导入，支持批量处理。
- MinerU 解析图片按正文图注自动重命名为语义文件名，保留中文字符。
- 导入时自动解析 Zotero 集合名称，空字段不写入 frontmatter。
- `--doctor` 就绪检查脚本（Zotero、MinerU、vault 配置）。
- 随插件发布一组标准 skills，帮助 Codex/Claude Code 自动命中合适的工作流。`pip install` 安装后 skills 位于 Python 包目录内；clone 源码安装后位于仓库根目录 `skills/`。

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

1. `obsidian_pipeline_ingest_item`（传入 `zotero_key`）→ 将文献导入 `literature/`，生成完整 YAML、笔记和批注。
2. `obsidian_pipeline_parse_with_mineru`（传入 `zotero_key`）→ 解析 PDF，在 `attachments/mineru/` 生成全文笔记，同时向文献 note 的 YAML 追加 MinerU 跳转链接。
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

模板发现和笔记创建等高级功能已转为 `obsidian-vault` Skill，通过 Claude Code 或 Codex 调用。

## Doctor 检查

不启动 MCP 服务器，直接运行本地就绪检查：

```bash
python scripts/obsidian_vault_mcp.py --doctor --doctor-format text --vault /path/to/your-vault
```

Zotero Desktop、Obsidian CLI、MinerU、PDF 文本提取等可选集成会作为检查项报告，不可用时不影响核心 vault 工具。去掉 `--doctor-format text` 可获得 JSON 输出，适合自动化或提交 bug 报告。

## 批量编辑计划

批量编辑工作流（`obsidian_preview_edit_plan`、`obsidian_apply_edit_plan`、`obsidian_rollback_edit_plan`）已转为 `obsidian-vault` Skill，通过 Claude Code 或 Codex 调用。

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
- `helpers.py`：vault 安全路径、frontmatter/YAML 处理、Zotero/MinerU 工具等非工具实现细节。
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

将以下提示词粘贴给任意 AI 编程助手（Codex、Claude Code、OpenCode、Cursor、Windsurf、VS Code + Copilot 等）：

```text
Install and configure the Obsidian Vault MCP plugin from
https://github.com/luffysolution-svg/obsidian-vault-mcp.

1. Install: `pip install zotero-obsidian-mcp`
   (Do NOT install the unrelated `obsidian-vault-mcp` package;
   `obsidian-vault-mcp` is only the executable name.)
2. Keep `OBSIDIAN_VAULT_PATH=auto` unless auto-detection fails.
3. Wire up the client I am using:
   - Codex: point the plugin root at this repo; `.codex-plugin/plugin.json`
     and `.mcp.json` are already in place.
   - Claude Code: run `claude mcp add obsidian-vault obsidian-vault-mcp`.
     Skills are bundled in the package — no manual copying needed.
   - OpenCode: copy `opencode.json` into the project, or merge its `mcp`
     block into `~/.config/opencode/opencode.json`.
   - Cursor: add the server block from `.mcp.json` to
     `<project>/.cursor/mcp.json` (or global `~/.cursor/mcp.json`).
   - Windsurf: add the same server block to
     `~/.codeium/windsurf/mcp_config.json`.
   - VS Code + Copilot: add the server block to `.vscode/mcp.json`
     in the workspace (requires GitHub Copilot Chat >= 1.256).
4. Keep vault paths, Zotero storage paths, and API tokens in local config
   only — never commit them.
5. Run: `obsidian-vault-mcp --doctor --doctor-format text --vault /path/to/vault`
6. If I need Zotero features, remind me to start Zotero Desktop with the
   local API enabled (port 23119). If I need MinerU parsing, run
   `mineru-open-api --version` first; install with
   `pip install mineru-open-api` if missing.
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
- Skills 随插件/包一起提供；本仓库的 `.claude/skills/` 仅作为开发期精简摘要镜像维护。

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

- "搜索这个 Obsidian vault 中关于 X 的文献笔记。"
- "从 Zotero 导入这条文献（key: XXXXXXXX）到 Obsidian。"
- "用 MinerU flash-extract 解析这个 PDF 并导入 Obsidian。"
- "用图注重命名这个 Markdown 文件里的 MinerU 提取图片。"
- "列出 Zotero 中某集合的所有文献。"
- "运行 pipeline doctor 检查 vault 配置。"

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
