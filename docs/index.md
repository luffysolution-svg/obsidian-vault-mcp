# Obsidian Vault MCP 3.0.0 完整教程

[English](./index.en.md) · [项目首页](../README.md) · [开发文档](../DEVELOPMENT.md)

本教程从安装开始，完成 Zotero 导入、MinerU 解析、Analysis、Agent 插件、旧数据迁移和真实 Vault 的安全验收。

## 1. 先理解 V3

数据流如下：

```text
Zotero Desktop local API
        ↓
稳定 zoteroKey → 主笔记 + PDF
        ↓
MinerU Markdown + 每篇独立图片目录
        ↓
paper_read / retrieve
        ↓
五类 Analysis → 唯一 Analysis.base
```

V3 有三条不能混淆的边界：

1. V2 的文献核心保留，包括 `Literature/index.md`、`Literature/Literature.base`、Wiki、事务与 26 个工具。
2. 结构化研究层只有五类 Analysis 和一个 `Analysis.base`。
3. Evidence、Coverage、Uncertainty、Analysis index、Topic、Theory 与 Analysis 模板已退出数据模型；旧文件仅由迁移器识别，不再是运行时资产。

## 2. 准备软件

| 软件 | 要求 | 用途 |
|---|---|---|
| Python | 3.10+ | 运行包、CLI 与 MCP server |
| Obsidian | 已打开过目标 Vault | 创建 `.obsidian` 并查看 Markdown/Base |
| Zotero Desktop | 运行中，启用本地 API | 查询父条目、附件、notes 与 BibTeX |
| MinerU Open API CLI | 可选 | 把 PDF 解析为 Markdown 与图片 |
| AI 客户端 | 可选 | Codex、Claude Code、OpenCode、Pi、Hermes、WorkBuddy |

Zotero 的本地 API 默认只访问本机。MinerU 是外部服务，即使无 token 的快速模式也可能上传 PDF；请先检查授权和组织政策。

## 3. 安装 Python 包

四种入口共享同一个 PyPI 发布包。

```powershell
# 当前 Python 环境
python -m pip install --upgrade "zotero-obsidian-mcp==3.0.0"

# 隔离命令
pipx install "zotero-obsidian-mcp==3.0.0"

# uv 持久工具
uv tool install "zotero-obsidian-mcp==3.0.0"

# uv 临时执行
uvx --from "zotero-obsidian-mcp==3.0.0" obsidian-vault-mcp --help
```

验证安装来源和版本：

```powershell
obsidian-vault-mcp --help
python -c "from importlib.metadata import version; print(version('zotero-obsidian-mcp'))"
```

开发者从源码安装时应 checkout 已发布 tag，并在独立虚拟环境执行：

```powershell
git clone https://github.com/luffysolution-svg/obsidian-vault-mcp.git
cd obsidian-vault-mcp
git checkout v3.0.0
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
```

## 4. 选择 Vault 并初始化

把示例路径替换为自己的 Vault：

```powershell
$env:OBSIDIAN_VAULT_PATH = "<VAULT_PATH>"
obsidian-vault-mcp config init --vault-path "$env:OBSIDIAN_VAULT_PATH" --dry-run
obsidian-vault-mcp config init --vault-path "$env:OBSIDIAN_VAULT_PATH"
obsidian-vault-mcp config validate --vault-path "$env:OBSIDIAN_VAULT_PATH"
obsidian-vault-mcp doctor --vault-path "$env:OBSIDIAN_VAULT_PATH"
```

`config init` 写入 `.obsidian-vault-mcp.json`。首次写入前必须检查 dry-run。`doctor` 顶层成功只表示基本配置可读取，还需分别查看 Zotero 和 MinerU 子状态。

Analysis 默认配置：

```json
{
  "analysis": {
    "folder": "Literature/Analysis",
    "base": "Literature/Analysis/Analysis.base",
    "fullReadsFolder": "Literature/Analysis/full-reads",
    "reviewsFolder": "Literature/Analysis/reviews",
    "passageQaFolder": "Literature/Analysis/qa/passages",
    "figureQaFolder": "Literature/Analysis/qa/figures",
    "conceptsFolder": "Literature/Analysis/concepts"
  }
}
```

目录必须位于 Vault 内，五个类型目录应彼此独立，Base 必须以 `.base` 结尾。

## 5. Zotero 设置与导入

在 Zotero 设置中启用本地 HTTP API。先检测连接并搜索：

```powershell
obsidian-vault-mcp call zotero_ping --json '{}'
obsidian-vault-mcp call zotero_search_items --json '{"query":"catalysis"}'
```

导入前使用返回的父条目 key，而不是附件 key：

```powershell
obsidian-vault-mcp import item ABCD1234 --vault-path "$env:OBSIDIAN_VAULT_PATH" --dry-run
obsidian-vault-mcp import item ABCD1234 --vault-path "$env:OBSIDIAN_VAULT_PATH"
```

批量导入 Zotero collection：

```powershell
obsidian-vault-mcp import collection COLLECTION_KEY --vault-path "$env:OBSIDIAN_VAULT_PATH" --dry-run
obsidian-vault-mcp import collection COLLECTION_KEY --vault-path "$env:OBSIDIAN_VAULT_PATH"
```

默认主资产：

```text
Literature/ABCD1234.md
Literature/attachment/ABCD1234.pdf
```

标题、作者、年份或 citekey 改变时，`zoteroKey` 仍指向同一主笔记。同步使用 `sync item` 或 `sync collection`，并继续遵循先 dry-run 后提交。

如果附件是 Zotero 的“链接到文件”，本地 API 会返回 `attachments:` 相对路径。请在 Zotero 的 **设置 → 高级 → 文件和文件夹 → 链接附件基础目录** 中选择固定目录，并在 Vault 的 `.obsidian-vault-mcp.json` 中填写同一目录：

```json
{
  "zotero": {
    "linkedAttachmentBaseDir": "<ZOTERO_LINKED_ATTACHMENT_BASE_DIR>"
  }
}
```

也可以在启动 CLI/MCP server 前设置环境变量；非空配置值优先：

```powershell
$env:ZOTERO_LINKED_ATTACHMENT_BASE_DIR = "<ZOTERO_LINKED_ATTACHMENT_BASE_DIR>"
```

```bash
export ZOTERO_LINKED_ATTACHMENT_BASE_DIR="<ZOTERO_LINKED_ATTACHMENT_BASE_DIR>"
```

`ZOTERO_STORAGE_DIR` 只解析 Zotero 管理的 `storage:` 附件；`linkedAttachmentBaseDir`/`ZOTERO_LINKED_ATTACHMENT_BASE_DIR` 只解析 `attachments:` 链接附件。该绝对路径只应存在于本机配置，不得提交。V3 会拒绝 `..`、盘符前缀和任何越出基础目录的结果；未配置基础目录时会明确报错，不会猜测路径。

## 6. MinerU 全文

按 MinerU 官方说明安装并认证 `mineru-open-api`。不要把 token 写进 Vault、聊天或 Git。

```powershell
obsidian-vault-mcp mineru parse ABCD1234 --vault-path "$env:OBSIDIAN_VAULT_PATH" --dry-run
obsidian-vault-mcp mineru parse ABCD1234 --vault-path "$env:OBSIDIAN_VAULT_PATH"
```

V3 的规范产物：

```text
Literature/attachment/MinerU/ABCD1234.md
Literature/attachment/MinerU/image/ABCD1234/ABCD1234-fig01.png
Literature/attachment/MinerU/image/ABCD1234/ABCD1234-fig02.jpg
```

Markdown 使用相对链接：

```markdown
![](image/ABCD1234/ABCD1234-fig01.png)
```

解析先进入隐藏 staging。Markdown 选择、图片重命名与链接校验全部成功后才提交正式文件；单篇失败不会发布半成品。批量解析：

```powershell
obsidian-vault-mcp mineru parse-batch ABCD1234 EFGH5678 --vault-path "$env:OBSIDIAN_VAULT_PATH" --dry-run
```

## 7. 五类 Analysis

| 类型 | 适用场景 | 典型 Skill |
|---|---|---|
| `full_read` | 单篇完整精读 | `full-read` |
| `literature_review` | 多篇综述或比较 | `literature-review`、`compare-papers` |
| `passage_qa` | 可定位到段落的问答 | `passage-qa` |
| `figure_qa` | 图、表、Scheme、方程解读 | `figure-qa` |
| `concept` | 跨文献概念学习 | `concept-learning` |

`paper-qa` 负责默认只回答、不强制落盘的单篇问答。五类 Analysis 共用：

- 状态：`draft`、`ready`、`reviewed`、`needs_update`、`archived`。
- Profile：`general`、`medicine`、`chemistry`、`materials`、`catalysis`、`physics`、`mathematics`。
- 稳定 `analysisId`、来源 key、source fingerprint 与受管理正文区块。
- 来源变化时显示 `needs_update`，不会静默覆盖既有分析。

读取单篇与跨篇检索：

```powershell
obsidian-vault-mcp call literature_paper_read --json '{"zotero_key":"ABCD1234","mode":"overview","vault_path":"<VAULT_PATH>"}'
obsidian-vault-mcp call literature_retrieve --json '{"query":"催化活性位点","intent":"compare","depth":"evidence","vault_path":"<VAULT_PATH>"}'
```

检索响应可以报告本次请求是否覆盖查询变体，但不写 Coverage 文件或 state。写 Analysis 时先让 Agent 调用 `literature_analysis_get` 去重，再以 `dry_run: true` 调用 `literature_analysis_write`，审查完整预览后才提交。

## 8. 唯一 Analysis.base

重建：

```powershell
obsidian-vault-mcp call literature_rebuild_analysis_base --json '{"vault_path":"<VAULT_PATH>","dry_run":true}'
obsidian-vault-mcp call literature_rebuild_analysis_base --json '{"vault_path":"<VAULT_PATH>","dry_run":false}'
```

`Literature/Analysis/Analysis.base` 递归读取五类 Analysis，共 9 个视图：

1. Dashboard
2. Full Reads
3. Reviews
4. Passage Q&A
5. Figure Q&A
6. Concepts
7. Needs Attention
8. By Discipline
9. Recently Updated

不会生成 `Literature/Analysis/index.md`，也没有 Topic/Theory 或模板目录。

## 9. MCP Registry 与手工接入

MCP Registry 的正式名称：

```text
io.github.luffysolution-svg/obsidian-vault-mcp
```

Registry 客户端按名称安装即可。手工配置可使用 uvx：

```json
{
  "mcpServers": {
    "obsidian-vault-mcp": {
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

也可用已安装的命令，把 `command` 改为 `obsidian-vault-mcp`，`args` 改为 `["serve","--transport","stdio"]`。

## 10. Codex、Claude、OpenCode、Pi、Hermes、WorkBuddy

统一安装入口：

```powershell
obsidian-vault-mcp agent install <client> --dry-run
obsidian-vault-mcp agent install <client>
```

`<client>` 可选 `codex`、`claude`、`opencode`、`pi`、`hermes`、`workbuddy`。

| 客户端 | 安装内容 |
|---|---|
| Codex | 原生 marketplace 插件、MCP 与 7 Skills |
| Claude Code | 原生 marketplace 插件、MCP 与 7 Skills |
| OpenCode | 项目本地 MCP 配置与 7 Skills |
| Pi | 调用统一 JSON CLI 的薄 TypeScript Extension |
| Hermes | MCP 配置；当前不自动安装 Skills |
| WorkBuddy | MCP 配置；当前不自动安装 Skills |

Codex/Claude 插件 selector 为 `obsidian-literature@obsidian-vault-mcp`。安装器检查现有 marketplace/插件，避免绑定到错误来源；新增步骤失败时清理本次状态。配置型客户端会先备份并合并现有文件，再验证格式和 MCP handshake。

`opencode`、`pi`、`hermes`、`workbuddy` 的目标是项目本地目录；请从目标项目运行，或加 `--project-dir <PROJECT_DIR>`。2.x 升级到 3.0.0 时，先按原安装方式精确升级 Python 包，再刷新客户端的插件缓存：

```powershell
uv tool install --force "zotero-obsidian-mcp==3.0.0"
pipx install --force "zotero-obsidian-mcp==3.0.0"
codex plugin add obsidian-literature@obsidian-vault-mcp --json
claude plugin marketplace update obsidian-vault-mcp
claude plugin update obsidian-literature@obsidian-vault-mcp --scope user
```

Codex 的 `plugin add` 会原子替换旧版本；Claude 更新后需要重启。GitHub Release 的 `obsidian-vault-mcp-3.0.0-plugins.zip` 可作离线 marketplace；先核对 `SHA256SUMS`，解压后执行：

```powershell
codex plugin marketplace add "<EXTRACTED_DIR>" --json
codex plugin add obsidian-literature@obsidian-vault-mcp --json

claude plugin marketplace add "<EXTRACTED_DIR>" --scope user
claude plugin install obsidian-literature@obsidian-vault-mcp --scope user
```

已有同名 marketplace 时按上面的升级流程处理，不要改绑到另一路径。

### 10.1 更新与卸载

卸载 Codex/Claude 时先移除插件；只有确认没有其他插件依赖该 marketplace 后，才移除 marketplace：

```powershell
codex plugin remove obsidian-literature@obsidian-vault-mcp --json
codex plugin marketplace remove obsidian-vault-mcp --json

claude plugin uninstall obsidian-literature@obsidian-vault-mcp --scope user
claude plugin marketplace remove obsidian-vault-mcp --scope user
```

OpenCode、Pi、Hermes、WorkBuddy 没有统一的原生卸载协议，请严格执行安装器返回 JSON 中的 `uninstall_instructions`，只删除该次安装所管理的配置或 Skill/Extension。最后按原安装方式卸载 Python 包：

```powershell
uv tool uninstall zotero-obsidian-mcp
pipx uninstall zotero-obsidian-mcp
python -m pip uninstall zotero-obsidian-mcp
```

卸载客户端插件、marketplace 或 Python 包不会删除 Vault 中的文献笔记、PDF、MinerU、Wiki、Analysis、事务清单或备份；这些研究数据只能由用户另行明确处理。

## 11. 恰好七个 Skills

插件只分发以下目录：

```text
paper-qa
full-read
passage-qa
figure-qa
compare-papers
literature-review
concept-learning
```

每个 Skill 的 `SKILL.md` 是入口，`references/` 保存输出与学科规则。升级只替换受管理区块并保留用户扩展；旧的已管理 Skills 会安全移除，未受管理的用户文件不会被删除。

## 12. 完整 31 工具

V2 稳定工具（26）：

| 分组 | 工具 |
|---|---|
| 系统/配置 | `literature_doctor`, `literature_config_get`, `literature_config_validate`, `literature_config_initialize` |
| Zotero | `zotero_ping`, `zotero_search_items`, `zotero_list_collections`, `zotero_get_item`, `zotero_get_children`, `zotero_get_bibtex` |
| 导入/同步 | `literature_import_item`, `literature_import_collection`, `literature_sync_item`, `literature_sync_collection` |
| MinerU | `literature_parse_mineru`, `literature_parse_mineru_batch`, `literature_remove_mineru_output` |
| 文献导航/验证 | `literature_rebuild_index`, `literature_rebuild_base`, `literature_verify` |
| Wiki | `literature_wiki_context`, `literature_wiki_write`, `literature_wiki_list` |
| 迁移/事务 | `literature_migrate_v1_to_v2`, `literature_preview_transaction`, `literature_rollback_transaction` |

V3 Analysis 工具（5）：

```text
literature_paper_read
literature_retrieve
literature_analysis_get
literature_analysis_write
literature_rebuild_analysis_base
```

V2→V3 Analysis 迁移是 CLI-only，不增加第 32 个 MCP 工具。

## 13. 迁移与回滚

先关闭可能写 Vault 的应用。迁移默认 dry-run：

```powershell
obsidian-vault-mcp migrate mineru-images-v2-to-v3 --vault-path "$env:OBSIDIAN_VAULT_PATH"
obsidian-vault-mcp migrate analysis-v2-to-v3 --vault-path "$env:OBSIDIAN_VAULT_PATH"
```

MinerU 图片迁移报告包含 `copiedImages`、`movedImages`、
`preservedLegacyImages`、`rewrittenMarkdown`、`missingReferencedImages` 与
`reparseZoteroKeys`。默认安全模式复制到每篇目录并重写 Markdown，但保留旧平铺
图片作为兼容别名，避免未协调写入者在提交瞬间新增旧路径引用而产生断链。

Analysis 迁移需检查 `migratedAnalyses`、`skippedAnalyses`、
`manualReviewRequired`、待处理 Topic/Theory 和计划删除的旧 Analysis index。
确认后：

```powershell
obsidian-vault-mcp migrate mineru-images-v2-to-v3 --vault-path "$env:OBSIDIAN_VAULT_PATH" --apply
obsidian-vault-mcp migrate analysis-v2-to-v3 --vault-path "$env:OBSIDIAN_VAULT_PATH" --apply
obsidian-vault-mcp preview <transaction-id> --vault-path "$env:OBSIDIAN_VAULT_PATH"
obsidian-vault-mcp rollback <transaction-id> --vault-path "$env:OBSIDIAN_VAULT_PATH" --dry-run
obsidian-vault-mcp rollback <transaction-id> --vault-path "$env:OBSIDIAN_VAULT_PATH"
```

如需删除旧平铺图片，必须先停止 Obsidian、同步程序、索引器和其他所有 Vault
写入者，再运行：

```powershell
obsidian-vault-mcp migrate mineru-images-v2-to-v3 --vault-path "$env:OBSIDIAN_VAULT_PATH" --apply --cleanup-legacy --confirm-vault-offline
```

图片复制、Markdown 链接重写和旧图片清理位于同一事务；其他笔记仍引用旧路径时，
对应论文不会执行破坏性清理。

回滚前也应 dry-run。迁移只自动处理可证明安全的内容；不能确定类型或目标的文件保留原位并要求人工复核。

## 14. 真实 Vault 端到端验收

自动化测试不能直接写用户 Vault。生产发布前采用两阶段验收：

### 阶段 A：真实 Vault 只读

1. 关闭 Obsidian 与 Zotero，记录 Vault 关键目录的文件清单、大小、时间与 SHA-256。
2. 只运行 `config validate`、`doctor`、`literature_verify`、`literature_paper_read`、`literature_retrieve` 和读取型 Analysis 查询。
3. 再次计算清单与哈希，确认零变化。

### 阶段 B：隔离副本写测

1. 复制真实 Vault 到全新 RC 目录；排除活动锁、staging、历史 backup 与残留临时目录。
2. 在副本依次验证 config、导入/同步、MinerU、五类 Analysis、九视图 Base、迁移、transaction preview 和 rollback。
3. 测试重复执行，确认稳定身份、幂等与无重复产物。
4. 运行 `literature_verify`，确保没有破损链接、越界路径或旧结构化状态。
5. 再次确认原 Vault 哈希完全不变，才允许发布。

### 隐私与维护清单

- MinerU 可能把选中的 PDF 发往外部服务；先确认文档授权、保密要求与组织政策。
- token 只放在受保护的环境变量或工具自己的凭据存储中，不写入项目、Vault、命令历史或聊天。
- `OBSIDIAN_VAULT_PATH`、`linkedAttachmentBaseDir` 等机器绝对路径不得提交到 Git。
- 每次写操作先 preview，提交后保存 `transactionId`；迁移和回滚只在隔离副本验证。
- 保持独立的 Vault 备份；事务备份不是完整备份策略的替代品。
- 本地集成优先使用 stdio。任何网络传输都必须置于可信认证与访问控制边界之后。

## 15. 常见问题

| 现象 | 处理 |
|---|---|
| `doctor` 成功但 Zotero 调用失败 | 启动 Zotero，启用本地 API，检查单独的 `zotero` 状态 |
| 元数据成功但 PDF 未复制 | `storage:` 路径检查 `ZOTERO_STORAGE_DIR`；`attachments:` 路径设置 `zotero.linkedAttachmentBaseDir` 或 `ZOTERO_LINKED_ATTACHMENT_BASE_DIR` |
| 链接附件提示越出基础目录 | 确认 Zotero 与本项目配置使用同一基础目录；附件路径必须位于该目录内，不能包含 `..` 或盘符前缀 |
| MinerU 命令存在但解析失败 | 命令可用不代表 token/网络可用；在隔离副本做一次真实 parse |
| 图片链接冲突 | 升级至 3.0.0；V3 使用 `image/{key}/{key}-figNN.ext` |
| Analysis 显示 `needs_update` | 来源 fingerprint 已变化；重新核查后显式更新 |
| Analysis Base 缺失 | 调用 `literature_rebuild_analysis_base`，不要创建 Analysis index |
| 客户端看不到 31 工具 | 检查实际包版本与启动命令，重启客户端并重新 handshake |
| 迁移结果不确定 | 不要 `--apply`；先处理 `manualReviewRequired` 或只在隔离副本尝试 |

实现、测试矩阵与发布门禁见[开发文档](../DEVELOPMENT.md)。
