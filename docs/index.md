# Obsidian Vault MCP 3.0.0 完整安装教程

[English](./index.en.md) · [项目首页](../README.md) · [开发文档](../DEVELOPMENT.md) · [更新日志](../CHANGELOG.md)

本教程覆盖正式安装、Zotero、MinerU、Obsidian、Analysis、Skills、Agent 插件和发布验收。

## 1. 系统要求

| 组件 | 要求 | 用途 |
|---|---|---|
| Python | 3.10–3.13 | CLI 与 MCP Server |
| Obsidian | 已打开目标 Vault | 创建 `.obsidian/` 并查看 Markdown/Base |
| Zotero Desktop | 运行中并启用本地 API | 文献、附件、notes、annotations、BibTeX |
| MinerU Open API CLI | 可选 | PDF 全文、图片与公式解析 |
| AI 客户端 | 可选 | Codex、Claude Code、OpenCode、Pi、Hermes、WorkBuddy |

推荐本地 `stdio`。MinerU 可能上传 PDF，使用前确认授权和组织政策。

## 2. 安装

### uv（推荐）

```powershell
uv tool install "zotero-obsidian-mcp==3.0.0"
obsidian-vault-mcp --help
```

临时执行：

```powershell
uvx --from "zotero-obsidian-mcp==3.0.0" obsidian-vault-mcp --help
```

### pipx / pip

```powershell
pipx install "zotero-obsidian-mcp==3.0.0"
# 或
python -m pip install "zotero-obsidian-mcp==3.0.0"
```

### 从 Tag 安装源码

```powershell
git clone https://github.com/luffysolution-svg/obsidian-vault-mcp.git
cd obsidian-vault-mcp
git checkout v3.0.0
uv sync --locked --all-extras
uv run obsidian-vault-mcp --help
```

验证：

```powershell
python -c "from importlib.metadata import version; print(version('zotero-obsidian-mcp'))"
obsidian-vault-mcp call literature_version --json '{}'
```

输出版本应为 `3.0.0`，工具数为 31，Skills 数为 7。

## 3. 初始化 Vault

目标目录必须包含 `.obsidian/`：

```powershell
$env:OBSIDIAN_VAULT_PATH = "<VAULT_PATH>"
obsidian-vault-mcp config init --vault-path "$env:OBSIDIAN_VAULT_PATH" --dry-run
obsidian-vault-mcp config init --vault-path "$env:OBSIDIAN_VAULT_PATH"
obsidian-vault-mcp config validate --vault-path "$env:OBSIDIAN_VAULT_PATH"
obsidian-vault-mcp doctor --vault-path "$env:OBSIDIAN_VAULT_PATH"
```

配置文件是 `<Vault>/.obsidian-vault-mcp.json`。不要提交本机绝对路径或凭据。

## 4. Zotero

1. 启动 Zotero Desktop。
2. 启用本地 HTTP API。
3. 检查连接并搜索父条目：

```powershell
obsidian-vault-mcp call zotero_ping --json '{}'
obsidian-vault-mcp call zotero_search_items --json '{"query":"photocatalysis"}'
```

不要使用 PDF 子附件 key 作为文献身份。

链接附件配置：

```json
{
  "zotero": {
    "linkedAttachmentBaseDir": "<ZOTERO_LINKED_ATTACHMENT_BASE_DIR>"
  }
}
```

也可以设置 `ZOTERO_LINKED_ATTACHMENT_BASE_DIR`。越出基础目录的路径会被拒绝。

## 5. 导入与同步

```powershell
obsidian-vault-mcp import item ABCD1234 --dry-run
obsidian-vault-mcp import item ABCD1234

obsidian-vault-mcp import collection COLLECTION_KEY --dry-run
obsidian-vault-mcp import collection COLLECTION_KEY

obsidian-vault-mcp sync item ABCD1234 --dry-run
obsidian-vault-mcp sync item ABCD1234
```

产物：

```text
Literature/ABCD1234.md
Literature/attachment/ABCD1234.pdf
Literature/index.md
Literature/Literature.base
```

`zoteroKey` 是稳定主键，元数据变化不会生成重复主笔记。

## 6. MinerU

按照 MinerU 官方说明安装并认证 `mineru-open-api`。不要在聊天、Vault 或 Git 中保存 token。

```powershell
obsidian-vault-mcp mineru parse ABCD1234 --dry-run
obsidian-vault-mcp mineru parse ABCD1234
obsidian-vault-mcp mineru parse-batch ABCD1234 EFGH5678 --dry-run
obsidian-vault-mcp mineru parse-batch ABCD1234 EFGH5678
```

规范产物：

```text
Literature/attachment/MinerU/ABCD1234.md
Literature/attachment/MinerU/image/ABCD1234/ABCD1234-fig01.png
```

Markdown 使用相对链接。解析先进入 staging，全部校验通过后才提交。

## 7. Analysis 与 Skills

| Analysis | 用途 | Skill |
|---|---|---|
| `full_read` | 单篇完整精读 | `full-read` |
| `literature_review` | 多篇综述或比较 | `literature-review`、`compare-papers` |
| `passage_qa` | 段落、方法、数值或结论定位 | `passage-qa` |
| `figure_qa` | 图、表、Scheme、方程解读 | `figure-qa` |
| `concept` | 跨文献概念学习 | `concept-learning` |

`paper-qa` 用于默认不落盘的快速问答。支持 `general`、`medicine`、`chemistry`、`materials`、`catalysis`、`physics`、`mathematics` 学科 Profile。

```powershell
obsidian-vault-mcp call literature_paper_read --json '{"zotero_key":"ABCD1234","mode":"overview"}'
obsidian-vault-mcp call literature_retrieve --json '{"query":"催化活性位点","intent":"compare","depth":"evidence"}'
```

持久化 Analysis 时，Skill 应先调用 `literature_analysis_get` 去重，再 dry-run `literature_analysis_write`，检查后正式提交。

```powershell
obsidian-vault-mcp call literature_rebuild_analysis_base --json '{"dry_run":true}'
obsidian-vault-mcp call literature_rebuild_analysis_base --json '{"dry_run":false}'
```

`Analysis.base` 包含 9 个视图：Dashboard、Full Reads、Reviews、Passage Q&A、Figure Q&A、Concepts、Needs Attention、By Discipline、Recently Updated。

## 8. MCP Registry

Registry 名称：

```text
io.github.luffysolution-svg/obsidian-vault-mcp
```

`uvx` stdio 配置：

```json
{
  "mcpServers": {
    "obsidian-literature": {
      "command": "uvx",
      "args": [
        "--from",
        "zotero-obsidian-mcp==3.0.0",
        "obsidian-vault-mcp",
        "serve",
        "--transport",
        "stdio"
      ],
      "env": {
        "OBSIDIAN_VAULT_PATH": "<VAULT_PATH>"
      }
    }
  }
}
```

## 9. Agent 插件

```powershell
obsidian-vault-mcp agent install <client> --dry-run
obsidian-vault-mcp agent install <client>
```

客户端：`codex`、`claude`、`opencode`、`pi`、`hermes`、`workbuddy`。

| 客户端 | 安装结果 |
|---|---|
| Codex | 原生 marketplace 插件、MCP、7 Skills |
| Claude Code | 原生 marketplace 插件、MCP、7 Skills |
| OpenCode | 项目本地 MCP、7 Skills |
| Pi | TypeScript Extension |
| Hermes | MCP 配置 |
| WorkBuddy | MCP 配置 |

Codex / Claude 离线包：`obsidian-vault-mcp-3.0.0-plugins.zip`。

## 10. 31 个 MCP Tools

| 分组 | 数量 | 能力 |
|---|---:|---|
| 版本、系统与配置 | 5 | version、doctor、读取、校验、初始化 |
| Zotero | 6 | ping、搜索、Collection、条目、子项、BibTeX |
| 导入与同步 | 4 | 单篇和 Collection 导入/同步 |
| MinerU | 3 | 单篇、批量、删除派生产物 |
| 导航与校验 | 3 | Index、Base、Verify |
| Analysis | 5 | 单篇读取、跨篇检索、查询、写入、Base |
| Wiki | 3 | 上下文、写入、列表 |
| 事务 | 2 | 预览、回滚 |

## 11. 效果展示

<img src="assets/screenshots/v2/vault-structure.png" alt="Vault 文献结构" width="320">

<img src="assets/screenshots/v2/literature-index.png" alt="Literature Index" width="760">

<img src="assets/screenshots/v2/wiki-synthesis.png" alt="可追溯 Wiki" width="780">

## 12. 校验与故障排查

```powershell
obsidian-vault-mcp call literature_version --json '{}'
obsidian-vault-mcp doctor
obsidian-vault-mcp verify
obsidian-vault-mcp index rebuild --dry-run
obsidian-vault-mcp base rebuild --dry-run
```

| 现象 | 检查 |
|---|---|
| Zotero 调用失败 | Zotero 是否运行、本地 API 是否启用 |
| PDF 未复制 | Zotero storage 或链接附件基础目录 |
| MinerU 失败 | CLI、认证、网络、PDF 权限 |
| Analysis 为 `needs_update` | 来源 fingerprint 已变化，需要重新核查 |
| 客户端看不到工具 | 包版本、PATH、环境变量和客户端重启 |

## 13. 发布验收

- `pyproject.toml`、`__version__`、`server.json`、插件 manifests、Pi package 均为 `3.0.0`。
- Tag 为 `v3.0.0`，指向 `main` 上的发布提交。
- wheel、sdist、插件 ZIP 和 `SHA256SUMS` 通过验证。
- Python 测试、Ruff、Pi 类型检查、wheel smoke、31 工具检查、7 Skills 检查和 MCP handshake 全部通过。
- PyPI、MCP Registry 和 GitHub Release 的版本与产物一致。

## 14. 安全规则

- 写操作先 dry-run，并保存 `transactionId`。
- 回滚前同样先 dry-run。
- 自动写测试只使用隔离 Vault。
- 独立备份 Vault。
- 不公开暴露无认证的 SSE/HTTP。
