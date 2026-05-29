# Obsidian Vault MCP — Technical Guide / 技术文档

> Version 1.0.26 | Python 3.10+ | MIT License

## Literature Pipeline Profile

The default MCP tool profile is `literature`. It exposes only the focused Zotero + MinerU + Obsidian literature pipeline surface plus a few basic file/YAML and Zotero query tools. Set `OBSIDIAN_VAULT_TOOL_PROFILE=full` or `OBSIDIAN_VAULT_TOOL_PROFILE=legacy` to expose the historical graph, wiki, Canvas, Bases, Dataview, schema, and CLI tools.

Default high-level pipeline tools: `obsidian_pipeline_doctor`, `obsidian_pipeline_config`, `obsidian_pipeline_migrate_layout`, `obsidian_pipeline_ingest_item`, `obsidian_pipeline_ingest_collection`, `obsidian_pipeline_parse_with_mineru`, and `obsidian_pipeline_rename_mineru_images`.

Vault-local pipeline configuration is read from `.obsidian-vault-pipeline.json`. Defaults place literature notes in `literature/`, copied Zotero PDFs in `attachments/zotero/<zoteroKey>/`, and MinerU machine outputs in `attachments/mineru/<zoteroKey>/paper.md`, `images-index.md`, and `images/`.
>
> [English](#english) | [中文](#chinese)

---

<a name="english"></a>

# English

## Overview

**Obsidian Vault MCP** is a local [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server that exposes your Obsidian vault as a structured, LLM-accessible knowledge base. It follows two design patterns:

- **Kepano's Obsidian Skills** — domain split into Markdown, Canvas, Bases, CLI, and extraction workflows.
- **Karpathy's LLM Wiki** — vault treated as a persistent, compounding wiki maintained by an LLM.

The server runs as a `stdio` MCP process launched by Codex, Claude Code, OpenCode, or any MCP-compatible host. It provides **74 tools** covering vault file I/O, wikilink management, schema validation, wiki workflows, literature ingestion, Zotero integration, MinerU document extraction and image renaming, Canvas/Bases creation, batch editing, Obsidian CLI wrappers, graph intelligence (Louvain community detection, 4-signal link scoring, bridge/hub/cluster insights), and LLM-driven wiki page generation.

---

## Architecture

```
obsidian-vault/
├── .mcp.json                        # Portable MCP server config
├── .codex-plugin/plugin.json        # Codex plugin manifest
├── pyproject.toml                   # Python package metadata
├── requirements.txt                 # Runtime dependencies
├── scripts/
│   ├── obsidian_vault_mcp.py        # MCP entrypoint (thin wrapper)
│   ├── smoke_integrations.py        # Read-only integration tests
│   └── obsidian_vault_mcp/          # Implementation package
│       ├── __init__.py
│       ├── cli.py                   # CLI entry point
│       ├── common.py                # Constants, tool registry
│       ├── helpers.py               # Core logic
│       ├── tools.py                 # 72 MCP tool functions
│       └── server.py                # FastMCP server setup
├── skills/
│   ├── obsidian-vault/SKILL.md      # General vault workflow skill
│   ├── obsidian-zotero/SKILL.md     # Zotero import workflow skill
│   ├── obsidian-mineru/SKILL.md     # MinerU extraction workflow skill
│   ├── obsidian-views/SKILL.md      # Canvas/Bases/Dataview skill
│   └── obsidian-cli/SKILL.md        # Obsidian CLI workflow skill
├── docs/                            # Documentation (EN + zh-CN)
└── tests/                           # Unit tests
```

### Key Design Principles

| Principle | Implementation |
|-----------|---------------|
| Vault safety | All paths constrained to vault root; rejects non-vault folders by default |
| Dry-run first | All write tools support `dry_run=true` returning a unified diff |
| Managed blocks | Wiki workflow uses marker comments to preserve hand-written content |
| Transaction backups | Batch edits create `.obsidian-vault-backups/` for rollback |
| Portable config | `.mcp.json` uses `${CLAUDE_PLUGIN_ROOT}`; vault path defaults to `auto` |

---

## Dependencies

### Runtime (required)

| Package | Purpose |
|---------|---------|
| `mcp` | Model Context Protocol framework (FastMCP) |
| `PyYAML` | Full YAML compatibility for frontmatter parsing |
| `pypdf` | PDF text extraction (falls back to `PyPDF2` if present) |
| `networkx>=3.0` | Graph algorithms: Louvain community detection, Adamic-Adar index, betweenness centrality |

### Development (optional)

| Package | Purpose |
|---------|---------|
| `ruff==0.13.2` | Linter (line length 160, Python 3.10+) |

### External Tools (optional, not auto-installed)

| Tool | Required For |
|------|-------------|
| Obsidian Desktop 1.12.7+ with CLI enabled | App-backed CLI tools (backlinks, properties, tasks, screenshots) |
| Zotero Desktop | Zotero library search, metadata fetch, PDF import |
| MinerU Open API CLI (`mineru-open-api`) | Direct PDF/document parsing before ingestion |

---

## All 72 MCP Tools

### Vault Core (6 tools)

| Tool | Description |
|------|-------------|
| `obsidian_vault_status` | Vault info: file counts, CLI availability, config summary |
| `obsidian_list_files` | List vault files filtered by folder and/or extension |
| `obsidian_search` | Full-text search with line-level snippets |
| `obsidian_read_file` | Read file content with parsed YAML frontmatter |
| `obsidian_write_file` | Write file; supports `dry_run=true` for diff preview |
| `obsidian_create_note` | Create Markdown note with YAML properties and optional template |

### Note Management (4 tools)

| Tool | Description |
|------|-------------|
| `obsidian_list_user_templates` | Discover templates from Obsidian Templates / Templater plugins |
| `obsidian_update_properties` | Merge, replace, or remove YAML frontmatter properties |
| `obsidian_add_wikilinks` | Add or replace wikilinks with surrounding context |
| `obsidian_build_graph` | Parse wikilinks, embeds, aliases, tags; detect orphans and dead ends |

### Vault Linting & Validation (7 tools)

| Tool | Description |
|------|-------------|
| `obsidian_lint_vault` | Check orphans, dead ends, duplicates, empty notes, missing titles |
| `obsidian_validate_vault_schema` | Validate Markdown frontmatter, Canvas JSON, Base YAML |
| `obsidian_apply_schema_defaults` | Fill missing frontmatter from built-in schema presets |
| `obsidian_list_schema_presets` | List available note-type schema presets |
| `obsidian_suggest_graph_improvements` | Suggest reciprocal links, unresolved links, duplicate pages; `use_scoring=True` adds 4-signal ranked suggestions (source overlap × 4.0, Adamic-Adar × 1.5, type affinity × 1.0) |
| `obsidian_build_graph_communities` | Louvain community detection; returns communities with label, top nodes, dominant tags, and modularity score; optionally writes `community:` to note frontmatter |
| `obsidian_graph_insights` | Detects bridge nodes, surprising cross-community links, sparse clusters, and isolated hubs using betweenness centrality and source-overlap scoring |

### Wiki Workflow — Karpathy Pattern (8 tools)

| Tool | Description |
|------|-------------|
| `obsidian_update_wiki_index` | Create or refresh managed `index.md` catalogue |
| `obsidian_append_wiki_log` | Append timestamped entry to `log.md` |
| `obsidian_ingest_source_note` | Ingest source → update entities/concepts/index/log in one pass |
| `obsidian_doctor` | Readiness check: vault, templates, dependencies, integrations |
| `obsidian_build_citation_network` | Read Zotero `relations` fields and insert wikilink citation edges between literature notes |
| `obsidian_build_reading_digest` | Aggregate callout blocks (highlights, notes, annotations) across a folder, grouped by tag or type |
| `obsidian_wiki_context` | Collect vault context for LLM-driven wiki generation: returns wikilink neighbours, full-text search results, Zotero literature items, and entity/concept nodes as a structured JSON bundle |
| `obsidian_write_wiki_page` | Write LLM-generated Markdown to `wiki/<slug>.md` with standard frontmatter (type=wiki, tags=[wiki]); optionally updates index and log |
| `obsidian_wiki_stale_pages` | Scan the wiki folder for pages that may need regeneration: detects pages whose `related` notes were modified or new vault notes matching title keywords appeared within a configurable time window |

### Literature & Reference Ingestion (6 tools)

| Tool | Description |
|------|-------------|
| `obsidian_parse_bibtex` | Parse BibTeX string into normalized metadata |
| `obsidian_ingest_reference` | Ingest reference metadata as a literature note |
| `obsidian_ingest_bibtex` | Ingest one or more BibTeX entries |
| `obsidian_ingest_mineru_markdown` | Ingest MinerU-generated Markdown + optional PDF |
| `obsidian_ingest_pdf_attachment` | Create source note for a vault PDF attachment |
| `obsidian_ingest_zotero_item` | Fetch Zotero item, copy PDFs, and ingest as literature note |

### MinerU Integration (5 tools)

| Tool | Description |
|------|-------------|
| `obsidian_mineru_status` | Check MinerU CLI availability and token configuration |
| `obsidian_mineru_extract` | Run MinerU extraction and save Markdown to vault |
| `obsidian_mineru_extract_and_ingest` | Extract with MinerU then ingest result in one pass; accepts `rename_images=True` |
| `obsidian_mineru_extract_folder` | Batch-extract all PDFs in a folder; forwards `rename_images` to each extraction |
| `obsidian_mineru_rename_images` | Rename MinerU-extracted images using figure captions; Chinese characters preserved verbatim |

### Zotero Integration (7 tools)

| Tool | Description |
|------|-------------|
| `obsidian_zotero_ping` | Check Zotero Desktop local API reachability |
| `obsidian_zotero_list_collections` | List all Zotero collections with key, name, parent, and item count |
| `obsidian_zotero_search_items` | Search local Zotero library |
| `obsidian_zotero_get_item` | Fetch Zotero item metadata by key |
| `obsidian_zotero_get_children` | Fetch child notes, annotations, attachments |
| `obsidian_zotero_list_pdf_attachments` | List PDF attachments for a Zotero item |
| `obsidian_zotero_extract_pdf_text` | Extract text from a Zotero PDF attachment |

### Canvas & Bases (7 tools)

| Tool | Description |
|------|-------------|
| `obsidian_create_canvas` | Write valid JSON Canvas from nodes and edges |
| `obsidian_create_canvas_from_graph` | Auto-layout vault wikilinks: grid / radial / grouped / layered |
| `obsidian_create_base` | Write valid Obsidian Bases YAML |
| `obsidian_list_base_templates` | List built-in Base templates |
| `obsidian_create_base_template` | Create Base from template (literature/tasks/equipment/utilities/economics/sources) |
| `obsidian_list_dataview_templates` | List Dataview query templates |
| `obsidian_create_dataview_note` | Create a Dataview query note |

### Batch Editing (3 tools)

| Tool | Description |
|------|-------------|
| `obsidian_preview_edit_plan` | Preview multi-file edits as unified diffs |
| `obsidian_apply_edit_plan` | Apply edits and create vault-local backups |
| `obsidian_rollback_edit_plan` | Restore files from transaction backup |

### Obsidian CLI Wrappers (14 tools)

| Tool | Description |
|------|-------------|
| `obsidian_cli` | Generic CLI wrapper |
| `obsidian_cli_read` | Read note via Obsidian app |
| `obsidian_cli_open` | Open note in Obsidian app |
| `obsidian_cli_backlinks` | Query backlinks for a note |
| `obsidian_cli_base_query` | Query an Obsidian Base view |
| `obsidian_cli_properties` | List all properties of a note |
| `obsidian_cli_property_read` | Read a single property value |
| `obsidian_cli_property_set` | Set a property value |
| `obsidian_cli_property_remove` | Remove a property |
| `obsidian_cli_tasks` | List tasks in a note |
| `obsidian_cli_screenshot` | Take a screenshot of the Obsidian window |
| `obsidian_cli_plugin_reload` | Reload an Obsidian plugin |
| `obsidian_cli_move_or_rename` | Move or rename a note (supports dry-run) |

---

## Installation

### Prerequisites

- Python 3.10 or newer
- Obsidian Desktop with at least one local vault
- Codex, Claude Code, OpenCode, or another MCP-compatible host

### Option A — Install from PyPI (recommended)

```bash
pip install zotero-obsidian-mcp
obsidian-vault-mcp --doctor --doctor-format text --vault /path/to/your-vault
```

**Claude Code:**

```bash
pip install zotero-obsidian-mcp
claude mcp add obsidian-vault obsidian-vault-mcp
```

**Codex / OpenCode:** register via local marketplace (see Step 3 below) after installing the package.

### Option B — Install from Source (developers / latest commits)

```bash
git clone https://github.com/luffysolution-svg/obsidian-vault-mcp.git obsidian-vault
cd obsidian-vault
python -m pip install -e ".[dev]"
obsidian-vault-mcp --doctor --doctor-format text --vault /path/to/your-vault
```

### Step 3 — Register as a Codex Plugin (Codex only)

The plugin ships with `.codex-plugin/plugin.json` and `.mcp.json`. Register it via a local marketplace.

**Repo-scoped marketplace** — create `$REPO_ROOT/.agents/plugins/marketplace.json`:

```json
{
  "name": "local-repo",
  "interface": { "displayName": "Local Repo Plugins" },
  "plugins": [
    {
      "name": "obsidian-vault",
      "source": { "source": "local", "path": "./plugins/obsidian-vault" },
      "policy": { "installation": "AVAILABLE", "authentication": "ON_INSTALL" },
      "category": "Productivity"
    }
  ]
}
```

**Personal marketplace** — create `~/.agents/plugins/marketplace.json` pointing to your local copy.

### Step 4 — Restart Your MCP Client

After registration (or after `claude mcp add`), restart or reload your MCP client so the 74 tools become available.

### Step 5 — Run Smoke Checks (Optional)

With Obsidian and Zotero Desktop open:

```bash
python scripts/smoke_integrations.py --vault /path/to/your-vault
```

This is read-only and verifies vault status, dry-run note creation, Zotero API, and Obsidian CLI.

---

## Configuration

### MCP Server Config (`.mcp.json`)

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

Do **not** replace `${CLAUDE_PLUGIN_ROOT}` with a personal absolute path in committed files.

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OBSIDIAN_VAULT_PATH` | `auto` | Vault root path. `auto` asks Obsidian CLI, falls back to CWD |
| `OBSIDIAN_CLI_COMMAND` | `obsidian` | Obsidian CLI executable name |
| `OBSIDIAN_ALLOW_NON_VAULT` | `false` | Allow plain Markdown folders without `.obsidian` |
| `ZOTERO_LOCAL_API` | `http://127.0.0.1:23119/api` | Zotero Desktop local API base URL |
| `ZOTERO_STORAGE_DIR` | `~/Zotero/storage` | Zotero attachment storage directory |
| `MINERU_TOKEN` | — | MinerU API token — auto-enables precise `extract` mode (get one at [mineru.net](https://mineru.net/apiManage/token)) |
| `MINERU_API_TOKEN` | — | Alias for `MINERU_TOKEN` (either name is accepted) |
| `MINERU_CLI_COMMAND` | `mineru-open-api` | MinerU CLI executable name |

### Vault-Local Defaults

Create `.obsidian-vault-mcp.json` at the vault root (or `.obsidian/obsidian-vault-mcp.json`):

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

Tool arguments always take precedence over these defaults.

**Zotero attachment naming strategies:** `original` | `zotero_key` | `citekey` | `title_year` | `parent_key`

---

## Integration Guides

### Obsidian CLI

Required for app-backed tools (backlinks, properties, tasks, screenshots, Base queries).

1. Install Obsidian 1.12.7+ using the official installer.
2. Open Obsidian → **Settings** → **General** → enable **Command line interface**.
3. Follow the registration prompt, then restart your terminal.

```bash
obsidian version
obsidian vault info=path
```

The `vault` parameter in CLI wrapper tools is an Obsidian vault **name**, not a filesystem path.

### Zotero Desktop

Required for Zotero search/import tools. Open Zotero Desktop before using these tools.

```bash
# Windows
curl.exe "http://127.0.0.1:23119/connector/ping"
```

Zotero 7+: enable local API access in **Zotero → Edit → Preferences → Advanced**.

Imported notes include `zoteroKey`, `zoteroSelect`, `zoteroLinks`, and PDF attachment links.

#### Frontmatter Field Behavior

Only fields with actual values are written to YAML frontmatter. Type-specific fields (`university`, `thesisType`, `patentNumber`, `assignee`, `country`, `journalAbbreviation`, `conferenceName`, `proceedingsTitle`, `bookTitle`, `reportNumber`, `institution`, `place`, `edition`, `numPages`, `series`, `repository`, `doi`, `publisher`, `ISBN`) are omitted when empty, so a patent note will not contain `university: null` and a thesis note will not contain `patentNumber: null`.

The `collections` field stores human-readable Zotero collection names (e.g. `苯乙烯优化`) resolved from the Zotero API at import time, not raw internal keys (e.g. `HXSD675W`). Collection names are refreshed on every smart update.

`relations` and `annotationPosition` are never written to literature note frontmatter.

### Annotation Color Label Resolution

When importing Zotero annotations, the plugin resolves each annotation's hex color to a human-readable label using a three-step priority chain (implemented in `helpers.py: _annotation_color_label`):

1. **Exact match** against the user's Ethereal Style (ZoteroStyle) config read from `prefs.js` (`extensions.zotero.zoterostyle.annotationColors`).
2. **Nearest-color match** within the ZoteroStyle config using RGB Euclidean distance (threshold ≤ 15). This handles minor hex rounding introduced by the ZoteroStyle color picker UI.
3. **Fallback** to the built-in Zotero standard English color names (`_ANNOTATION_COLOR_NAMES` in `helpers.py`).

The `prefs.js` is re-read automatically whenever its modification time changes — no MCP server restart needed after renaming labels.

**Changing label names** (keeping hex values): safe, takes effect on the next tool call.

**Changing hex values**: old annotations in `itemAnnotations` still store the old hex. The nearest-color match (step 2) covers small deviations (≤ 15 RGB distance). For larger changes, update the `color` column in `zotero.sqlite → itemAnnotations` to the new hex value before re-importing. Zotero must be closed during any direct database edits.

**Recommended hex values** — use Zotero's 8 native standard colors to avoid mismatches:

| Color | Hex |
|-------|-----|
| yellow | `#ffd400` |
| red | `#ff6666` |
| green | `#5fb236` |
| blue | `#2ea8e5` |
| purple | `#a28ae5` |
| magenta | `#e56eee` |
| orange | `#f19837` |
| gray | `#aaaaaa` |

To modify the built-in fallback English names, edit `_ANNOTATION_COLOR_NAMES` in `scripts/obsidian_vault_mcp/helpers.py`.

### MinerU Document Extraction

Optional. Install only when you need direct PDF/document parsing.

**Windows:**
```powershell
irm https://cdn-mineru.openxlab.org.cn/open-api-cli/install.ps1 | iex
mineru-open-api version
```

**Linux/macOS:**
```bash
curl -fsSL https://cdn-mineru.openxlab.org.cn/open-api-cli/install.sh | sh
mineru-open-api version
```

**Modes:**
- `flash-extract` — free, no token, best for small/simple documents
- `extract` — requires token, supports OCR, tables, formulas, larger files

**Get a token:** https://mineru.net/apiManage/token

```bash
mineru-open-api auth          # interactive token setup
mineru-open-api flash-extract report.pdf -o ./out/
mineru-open-api extract report.pdf -f md,docx -o ./results/
```

**Network requirements** (ensure these domains are reachable, not fake-IP routed):
- `mineru.net`
- `mineru.oss-cn-shanghai.aliyuncs.com`
- `cdn-mineru.openxlab.org.cn`
- `*.openxlab.org.cn`

---

## Batch Edit Plans

```json
{
  "operations": [
    { "operation": "update_properties", "path": "Projects/Alpha.md", "properties": { "status": "draft" } },
    { "operation": "append", "path": "Projects/Alpha.md", "content": "\n\nReviewed." },
    { "operation": "replace", "path": "Notes/Draft.md", "old": "TODO", "new": "DONE" },
    { "operation": "write", "path": "Inbox/New.md", "content": "# New\n", "overwrite": false },
    { "operation": "delete", "path": "Trash/Old.md" }
  ]
}
```

Workflow: `obsidian_preview_edit_plan` → review diff → `obsidian_apply_edit_plan` → `obsidian_rollback_edit_plan` if needed.

Backups are stored under `.obsidian-vault-backups/` inside the vault.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `python` not recognized | Python missing or not on PATH | Install Python; enable "Add Python to PATH" |
| `No module named mcp` | Dependencies not installed | `pip install zotero-obsidian-mcp` or `pip install -e ".[dev]"` |
| `Could not resolve an Obsidian vault` | `auto` cannot find vault | Open Obsidian or set `OBSIDIAN_VAULT_PATH` explicitly |
| `Path does not look like an Obsidian vault root` | Path lacks `.obsidian` | Point to the vault root folder |
| `Obsidian CLI command not found` | CLI not enabled or not on PATH | Enable CLI in Obsidian Settings → General; restart terminal |
| Zotero API check fails | Zotero closed or local API disabled | Open Zotero; check `127.0.0.1:23119` |
| MinerU check fails | CLI not installed | Install `mineru-open-api` only if direct extraction is needed |
| MinerU Markdown download fails | Proxy/DNS routing issue | Check MinerU/OpenXLab domains; fix fake-IP rules |
| MCP tools do not appear | Codex has not reloaded the plugin | Restart Codex or reload MCP/plugin state |
| Write rejected (file exists) | Existing files are protected | Pass `overwrite=true` after reviewing the target |

---

## Running Tests

```bash
# Unit tests (no real vault needed)
python -m unittest discover -s tests

# Doctor check
python scripts/obsidian_vault_mcp.py --doctor --doctor-format text --vault /path/to/vault

# Read-only integration smoke checks (Obsidian + Zotero must be open)
python scripts/smoke_integrations.py --vault /path/to/vault
```

---

## Useful Prompts

```
Show me the structure of this Obsidian vault.
Create a linked wiki note with YAML properties.
Lint this vault and show unresolved links, dead ends, and missing index/log files.
Validate frontmatter, Canvas, and Base schemas across this vault.
Suggest graph improvements for unresolved and weakly linked pages.
Suggest scored graph improvements using the 4-signal model (use_scoring=True).
Detect Louvain communities in this vault and label each cluster.
Find bridge nodes, isolated hubs, and surprising cross-community links.
Refresh the wiki index and append a log entry.
Ingest this BibTeX entry into the literature wiki.
Search Zotero and ingest this item into Obsidian.
Use MinerU flash-extract on this PDF and ingest the result.
Batch extract all PDFs in this folder with MinerU and ingest them.
Rename MinerU-extracted images in this Markdown file using figure captions.
Build a citation network from Zotero relations across my literature notes.
Generate a reading digest of all highlights and notes in this literature folder.
Create a Canvas map of this topic cluster from vault wikilinks.
Preview and apply a batch edit plan, then rollback if needed.
```

---

<a name="chinese"></a>

# 中文

## 概述

**Obsidian Vault MCP** 是一个本地 [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) 服务器，将你的 Obsidian vault 作为结构化、LLM 可访问的知识库对外暴露。它遵循两种设计模式：

- **Kepano 的 Obsidian Skills** — 领域拆分为 Markdown、Canvas、Bases、CLI 和文档提取工作流。
- **Karpathy 的 LLM Wiki** — 将 vault 视为由 LLM 持续维护的、不断积累的 wiki。

服务器以 `stdio` MCP 进程方式运行，由 Codex、Claude Code、OpenCode 或任何兼容 MCP 的 host 启动。提供 **74 个工具**，覆盖 vault 文件读写、wikilink 管理、schema 验证、wiki 工作流、文献导入、Zotero 集成、MinerU 文档提取与图片重命名、Canvas/Bases 创建、批量编辑、Obsidian CLI 封装、图谱智能（Louvain 社区检测、4 信号链接评分、桥接节点/孤立枢纽/稀疏社区洞察），以及 LLM 驱动的 wiki 页面生成。

---

## 架构

```
obsidian-vault/
├── .mcp.json                        # 可移植 MCP 服务器配置
├── .codex-plugin/plugin.json        # Codex 插件 manifest
├── pyproject.toml                   # Python 包元数据
├── requirements.txt                 # 运行时依赖
├── scripts/
│   ├── obsidian_vault_mcp.py        # MCP 入口（薄封装）
│   ├── smoke_integrations.py        # 只读集成测试
│   └── obsidian_vault_mcp/          # 实现包
│       ├── cli.py                   # CLI 入口
│       ├── common.py                # 常量、工具注册表
│       ├── helpers.py               # 核心逻辑
│       ├── tools.py                 # 72 个 MCP 工具函数
│       └── server.py                # FastMCP 服务器设置
├── skills/
│   ├── obsidian-vault/SKILL.md      # 通用 vault 工作流 skill
│   ├── obsidian-zotero/SKILL.md     # Zotero 导入工作流 skill
│   ├── obsidian-mineru/SKILL.md     # MinerU 提取工作流 skill
│   ├── obsidian-views/SKILL.md      # Canvas/Bases/Dataview skill
│   └── obsidian-cli/SKILL.md        # Obsidian CLI 工作流 skill
├── docs/                            # 文档（EN + zh-CN）
└── tests/                           # 单元测试
```

### 核心设计原则

| 原则 | 实现方式 |
|------|---------|
| Vault 安全 | 所有路径限制在 vault 根目录内；默认拒绝非 vault 文件夹 |
| 先预览再写入 | 所有写入工具支持 `dry_run=true`，返回 unified diff |
| 托管块 | Wiki 工作流使用标记注释保护手写内容 |
| 事务备份 | 批量编辑在 `.obsidian-vault-backups/` 创建备份以支持回滚 |
| 可移植配置 | `.mcp.json` 使用 `${CLAUDE_PLUGIN_ROOT}`；vault 路径默认 `auto` |

---

## 依赖

### 运行时（必需）

| 包 | 用途 |
|----|------|
| `mcp` | Model Context Protocol 框架（FastMCP） |
| `PyYAML` | 完整 YAML 兼容性，用于 frontmatter 解析 |
| `pypdf` | PDF 文本提取（已安装 `PyPDF2` 时自动回退） |
| `networkx>=3.0` | 图算法：Louvain 社区检测、Adamic-Adar 指数、介数中心性 |

### 外部工具（可选，不自动安装）

| 工具 | 用途 |
|------|------|
| Obsidian Desktop 1.12.7+（启用 CLI） | App-backed CLI 工具（backlinks、properties、tasks、截图） |
| Zotero Desktop | Zotero 文库搜索、元数据获取、PDF 导入 |
| MinerU Open API CLI (`mineru-open-api`) | 直接解析 PDF/文档后导入 |

---

## 全部 72 个 MCP 工具

### Vault 核心（6 个）

| 工具 | 说明 |
|------|------|
| `obsidian_vault_status` | Vault 信息：文件数量、CLI 可用性、配置摘要 |
| `obsidian_list_files` | 按文件夹和/或扩展名过滤列出 vault 文件 |
| `obsidian_search` | 全文搜索，返回行级片段 |
| `obsidian_read_file` | 读取文件内容，解析 YAML frontmatter |
| `obsidian_write_file` | 写入文件；支持 `dry_run=true` 预览 diff |
| `obsidian_create_note` | 创建带 YAML 属性和可选模板的 Markdown 笔记 |

### 笔记管理（4 个）

| 工具 | 说明 |
|------|------|
| `obsidian_list_user_templates` | 从 Obsidian Templates / Templater 插件发现模板 |
| `obsidian_update_properties` | 合并、替换或删除 YAML frontmatter 属性 |
| `obsidian_add_wikilinks` | 添加或替换带上下文的 wikilink |
| `obsidian_build_graph` | 解析 wikilink、嵌入、别名、标签；检测孤立笔记和死链 |

### Vault 检查与验证（7 个）

| 工具 | 说明 |
|------|------|
| `obsidian_lint_vault` | 检查孤立笔记、死链、重复键、空笔记、缺失标题 |
| `obsidian_validate_vault_schema` | 验证 Markdown frontmatter、Canvas JSON、Base YAML |
| `obsidian_apply_schema_defaults` | 从内置 schema 预设填充缺失的 frontmatter |
| `obsidian_list_schema_presets` | 列出可用的笔记类型 schema 预设 |
| `obsidian_suggest_graph_improvements` | 建议互链、未解析链接、重复页面；`use_scoring=True` 启用 4 信号评分（来源重叠 × 4.0、Adamic-Adar × 1.5、类型亲和 × 1.0） |
| `obsidian_build_graph_communities` | Louvain 社区检测；返回带标签、核心节点、主导标签和模块度分值的社区列表；可选将 `community:` 写入笔记 frontmatter |
| `obsidian_graph_insights` | 基于介数中心性和来源重叠评分，检测桥接节点、跨社区惊喜链接、稀疏社区和孤立枢纽 |

### Wiki 工作流（8 个）

| 工具 | 说明 |
|------|------|
| `obsidian_update_wiki_index` | 创建或刷新托管的 `index.md` 目录 |
| `obsidian_append_wiki_log` | 向 `log.md` 追加带时间戳的条目 |
| `obsidian_ingest_source_note` | 导入来源 → 一次性更新实体/概念/索引/日志 |
| `obsidian_doctor` | 就绪检查：vault、模板、依赖、集成 |
| `obsidian_build_citation_network` | 读取 Zotero `relations` 字段，在文献笔记之间插入 wikilink 引用边 |
| `obsidian_build_reading_digest` | 将文件夹内 callout 块（高亮、笔记、批注）按标签或类型聚合为阅读摘要 |
| `obsidian_wiki_context` | 为 LLM 驱动的 wiki 生成收集 vault 上下文：返回 wikilink 邻居、全文搜索结果、Zotero 文献、实体/概念节点的结构化 JSON bundle |
| `obsidian_write_wiki_page` | 将 LLM 生成的 Markdown 写入 `wiki/<slug>.md`，附标准 frontmatter（type=wiki, tags=[wiki]）；可选更新索引和日志 |
| `obsidian_wiki_stale_pages` | 扫描 wiki 文件夹，检测哪些页面可能需要重新生成：检查 `related` 笔记是否被修改，或 vault 中是否出现包含页面标题关键词的新笔记 |

### 文献导入（6 个）

| 工具 | 说明 |
|------|------|
| `obsidian_parse_bibtex` | 将 BibTeX 字符串解析为规范化元数据 |
| `obsidian_ingest_reference` | 将参考文献元数据导入为文献笔记 |
| `obsidian_ingest_bibtex` | 导入一个或多个 BibTeX 条目 |
| `obsidian_ingest_mineru_markdown` | 导入 MinerU 生成的 Markdown + 可选 PDF |
| `obsidian_ingest_pdf_attachment` | 为 vault PDF 附件创建来源笔记 |
| `obsidian_ingest_zotero_item` | 获取 Zotero 条目、复制 PDF、导入为文献笔记 |

### MinerU 集成（5 个）

| 工具 | 说明 |
|------|------|
| `obsidian_mineru_status` | 检查 MinerU CLI 可用性和 token 配置 |
| `obsidian_mineru_extract` | 运行 MinerU 提取，将 Markdown 保存到 vault |
| `obsidian_mineru_extract_and_ingest` | MinerU 提取后一步导入；接受 `rename_images=True` |
| `obsidian_mineru_extract_folder` | 批量提取文件夹内所有 PDF；`rename_images` 标志转发给每次提取 |
| `obsidian_mineru_rename_images` | 用正文图注重命名 MinerU 提取图片；中文字符直通保留 |

### Zotero 集成（7 个）、Canvas/Bases（7 个）、批量编辑（3 个）、CLI 封装（14 个）

详见英文部分工具表格，工具名称与英文完全一致。

---

## 安装部署

### 前置条件

- Python 3.10 或更高版本
- Obsidian Desktop，至少有一个本地 vault
- Codex、Claude Code、OpenCode 或其他兼容 MCP 的 host

### 方式 A — PyPI 安装（推荐）

```bash
pip install zotero-obsidian-mcp
obsidian-vault-mcp --doctor --doctor-format text --vault /path/to/your-vault
```

**Claude Code：**

```bash
pip install zotero-obsidian-mcp
claude mcp add obsidian-vault obsidian-vault-mcp
```

**Codex / OpenCode：** 安装包后，通过 local marketplace 注册（见第三步）。

### 方式 B — 源码安装（开发者 / 跟进最新提交）

```bash
git clone https://github.com/luffysolution-svg/obsidian-vault-mcp.git obsidian-vault
cd obsidian-vault
python -m pip install -e ".[dev]"
obsidian-vault-mcp --doctor --doctor-format text --vault /path/to/your-vault
```

### 第三步 — 注册为 Codex 插件（仅 Codex）

**Repo marketplace** — 创建 `$REPO_ROOT/.agents/plugins/marketplace.json`：

```json
{
  "name": "local-repo",
  "interface": { "displayName": "Local Repo Plugins" },
  "plugins": [
    {
      "name": "obsidian-vault",
      "source": { "source": "local", "path": "./plugins/obsidian-vault" },
      "policy": { "installation": "AVAILABLE", "authentication": "ON_INSTALL" },
      "category": "Productivity"
    }
  ]
}
```

**个人 marketplace** — 创建 `~/.agents/plugins/marketplace.json`，`source.path` 指向你的本地副本。

### 第四步 — 重启 MCP 客户端

注册后（或 `claude mcp add` 后）重启或重新加载客户端，74 个工具即可使用。

---

## 配置说明

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `OBSIDIAN_VAULT_PATH` | `auto` | Vault 根目录路径。`auto` 询问 Obsidian CLI，回退到当前目录 |
| `OBSIDIAN_CLI_COMMAND` | `obsidian` | Obsidian CLI 可执行文件名 |
| `OBSIDIAN_ALLOW_NON_VAULT` | `false` | 允许不含 `.obsidian` 的普通 Markdown 文件夹 |
| `ZOTERO_LOCAL_API` | `http://127.0.0.1:23119/api` | Zotero Desktop 本地 API 基础 URL |
| `ZOTERO_STORAGE_DIR` | `~/Zotero/storage` | Zotero 附件存储目录 |
| `MINERU_TOKEN` | — | MinerU API token — 自动启用精准 `extract` 模式（在 [mineru.net](https://mineru.net/apiManage/token) 获取） |
| `MINERU_API_TOKEN` | — | `MINERU_TOKEN` 的别名，两者均可使用 |
| `MINERU_CLI_COMMAND` | `mineru-open-api` | MinerU CLI 可执行文件名 |

### Vault 内配置文件

在 vault 根目录创建 `.obsidian-vault-mcp.json`：

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

**Zotero 附件命名策略：** `original` | `zotero_key` | `citekey` | `title_year` | `parent_key`

---

## 集成配置

### Obsidian CLI

1. 安装 Obsidian 1.12.7+ 官方安装包。
2. 打开 Obsidian → **设置** → **通用** → 启用**命令行界面**。
3. 按提示注册 `obsidian` 命令，然后重启终端。

```bash
obsidian version && obsidian vault info=path
```

### Zotero Desktop

使用前打开 Zotero Desktop。Zotero 7+ 需在**编辑 → 首选项 → 高级**中允许本地 API 访问。

```powershell
curl.exe "http://127.0.0.1:23119/connector/ping"
```

#### 导入笔记的 frontmatter 字段行为

只有有实际值的字段才会写入 YAML frontmatter。类型专用字段（`university`、`thesisType`、`patentNumber`、`assignee`、`country`、`journalAbbreviation`、`conferenceName`、`proceedingsTitle`、`bookTitle`、`reportNumber`、`institution`、`place`、`edition`、`numPages`、`series`、`repository`、`doi`、`publisher`、`ISBN`）为空时不写入，因此专利笔记不会出现 `university: null`，学位论文笔记不会出现 `patentNumber: null`。

`collections` 字段存储从 Zotero API 解析的可读集合名称（如 `苯乙烯优化`），而非原始内部 key（如 `HXSD675W`）。每次 smart update 时集合名称会自动刷新。

`relations` 和 `annotationPosition` 不会写入文献笔记的 frontmatter。

### MinerU 文档提取

**Windows：**
```powershell
irm https://cdn-mineru.openxlab.org.cn/open-api-cli/install.ps1 | iex
mineru-open-api version
mineru-open-api auth   # 配置 token（精确模式需要）
```

**Linux/macOS：**
```bash
curl -fsSL https://cdn-mineru.openxlab.org.cn/open-api-cli/install.sh | sh
```

需要可达的域名：`mineru.net`、`mineru.oss-cn-shanghai.aliyuncs.com`、`cdn-mineru.openxlab.org.cn`、`*.openxlab.org.cn`

---

## 常见问题排查

| 现象 | 可能原因 | 处理方式 |
|------|---------|---------|
| `python` 无法识别 | Python 未安装或不在 PATH | 安装 Python 并启用 "Add Python to PATH" |
| `No module named mcp` | 依赖未安装 | `pip install zotero-obsidian-mcp` 或 `pip install -e ".[dev]"` |
| `Could not resolve an Obsidian vault` | `auto` 找不到 vault | 打开 Obsidian 或显式设置 `OBSIDIAN_VAULT_PATH` |
| `Path does not look like an Obsidian vault root` | 路径缺少 `.obsidian` | 指向 vault 根目录 |
| `Obsidian CLI command not found` | CLI 未启用或不在 PATH | 在 Obsidian 设置中启用 CLI；重启终端 |
| Zotero API 检查失败 | Zotero 未打开或本地 API 被禁用 | 打开 Zotero；检查 `127.0.0.1:23119` |
| MinerU Markdown 下载失败 | 代理/DNS 路由问题 | 检查 MinerU/OpenXLab 域名；修复 fake-IP 规则 |
| MCP 工具不出现 | Codex 尚未重新加载插件 | 重启 Codex 或重新加载 MCP/plugin 状态 |
| 写入提示文件已存在 | 默认保护已有文件 | 确认无误后传入 `overwrite=true` |

---

## 常用提示词

```
展示这个 Obsidian vault 的结构。
创建一条带 YAML properties 的双链笔记。
检查这个 vault，显示未解析链接、死链和缺失的 index/log 文件。
校验整个 vault 的 frontmatter、Canvas 和 Base schema。
建议图谱改进：补充互链、合并可能重复的页面。
用 4 信号评分模型给出链接建议（use_scoring=True）。
检测 vault 的 Louvain 社区并为每个社区打上标签。
查找桥接节点、孤立枢纽和跨社区惊喜链接。
刷新 wiki 索引并追加一条日志。
把这条 BibTeX 条目导入文献知识库。
搜索 Zotero 并将该条目导入 Obsidian。
用 MinerU flash-extract 解析这个 PDF 并导入 Obsidian。
批量解析这个文件夹内所有 PDF 并导入 Obsidian。
用图注重命名这个 Markdown 文件里的 MinerU 提取图片。
根据 Zotero relations 构建文献引用网络。
生成这个文献文件夹的阅读摘要（高亮 + 笔记）。
从 vault wikilinks 生成 Canvas 知识图谱。
预览并应用批量编辑计划，如有需要可回滚。
```

---

## 参考资料

- [Kepano's Obsidian Skills](https://github.com/kepano/obsidian-skills)
- [Karpathy's LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
- [Obsidian CLI 文档](https://help.obsidian.md/cli)
- [Zotero 本地连接器 HTTP 服务器](https://www.zotero.org/support/dev/client_coding/connector_http_server)
- [MinerU Open API CLI](https://pkg.go.dev/github.com/opendatalab/MinerU-Ecosystem/cli)
