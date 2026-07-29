# Obsidian Vault MCP V2

[English](https://github.com/luffysolution-svg/obsidian-vault-mcp/blob/main/README.en.md) · [完整使用教程](https://github.com/luffysolution-svg/obsidian-vault-mcp/blob/main/docs/index.md) · [开发者文档](https://github.com/luffysolution-svg/obsidian-vault-mcp/blob/main/DEVELOPMENT.md) · [PyPI](https://pypi.org/project/zotero-obsidian-mcp/)

把 Zotero 文献、PDF、MinerU 全文解析和 Obsidian 知识库连接成一条本地优先、可回滚的文献管道。V2 使用 Zotero 父条目的 `zoteroKey` 作为永久身份：标题、作者、年份或 citekey 改变时，只更新原来的主笔记，不再生成重复文件。

```text
Zotero 元数据与 PDF
        ↓
一份稳定主笔记 + PDF 副本
        ↓
MinerU 全文 Markdown 与图片
        ↓
Index 仪表盘 + Obsidian Base + 可追溯 Wiki
```

## 你会得到什么

- 单篇或整套 Zotero 集合导入，完整处理分页，不静默漏掉第 100 条之后的文献。
- 每个父条目只生成一份 `Literature/{zoteroKey}.md` 主笔记。
- 同步元数据、标签、Zotero 存储附件或链接附件 PDF、notes/annotations 与 BibTeX，同时保留托管区块外的用户正文和未知 Frontmatter 字段。
- 可选调用 MinerU Open API CLI，将 PDF 规范化为可移植的 Markdown 与相对图片链接。
- 自动维护 `Literature/index.md`、`Literature/Literature.base` 和来源可追溯的 Wiki 页面。
- 所有正式写入经过 dry-run、staging、原子替换、备份、锁和事务；支持预览与回滚。
- 同一套业务能力同时提供 CLI 和 33 个 MCP Tools；Codex、Claude Code、OpenCode、Hermes、WorkBuddy 与 Pi 均可接入。
- 为每篇 MinerU 全文建立图片 Manifest、可追溯 EvidenceChunk、读取覆盖账本、结构化 Analysis 笔记和待复核事项。

Wiki 正文由连接的 AI 客户端综合撰写，本项目负责检索本地证据、校验 Zotero keys、补充来源链接并安全写回；项目本身不绑定任何大模型供应商。

## 5 分钟开始

前置条件：Python 3.10+、一个已由 Obsidian 打开过的 Vault，以及正在运行且已启用本地 API 的 Zotero Desktop。MinerU 仅在需要全文解析时安装。

以下示例使用 Windows PowerShell。macOS/Linux、软件官方下载、MinerU 精准模式和各 AI 客户端配置见[完整教程](https://github.com/luffysolution-svg/obsidian-vault-mcp/blob/main/docs/index.md)。

```powershell
# 1. 持久安装 V2，任选一种；以下包选择器在 2.1.0 发布到 PyPI 后使用
pipx install "zotero-obsidian-mcp==2.1.0"
# 或：uv tool install "zotero-obsidian-mcp==2.1.0"
# 本地生产验收可把包选择器替换为 "<WHEEL_PATH>"

# 2. 显式指定 Vault。auto 只会从进程当前目录向父目录查找 .obsidian
$env:OBSIDIAN_VAULT_PATH = "<VAULT_DIR>"

# 3. 先预览，再初始化唯一的 Vault 配置
obsidian-vault-mcp config init --dry-run
obsidian-vault-mcp config init
obsidian-vault-mcp config validate

# 4. 检查配置、Zotero 与 MinerU 子状态
obsidian-vault-mcp doctor

# 5. 搜索 Zotero 并导入父条目
obsidian-vault-mcp call zotero_search_items --json '{"query":"photocatalysis"}'
obsidian-vault-mcp import item ABCD1234 --dry-run
obsidian-vault-mcp import item ABCD1234
```

`doctor` 顶层的 `ok` 只表示配置能够加载；请另外检查结果中的 `zotero.ok` 和 `mineru.available`。首次导入成功后应看到主笔记、PDF、Index 与 Base。完成 MinerU 认证后可继续：

如果 Zotero 附件使用“链接到文件”，请先在配置中设置 `zotero.linkedAttachmentBaseDir`，或设置 `ZOTERO_LINKED_ATTACHMENT_BASE_DIR`；完整示例见[教程](https://github.com/luffysolution-svg/obsidian-vault-mcp/blob/main/docs/index.md#5-%E9%85%8D%E7%BD%AE-zotero-%E6%9C%AC%E5%9C%B0-api)。

```powershell
mineru-open-api auth
obsidian-vault-mcp mineru parse ABCD1234
obsidian-vault-mcp verify
```

## 默认 Vault 结构

```text
<Vault>/
├─ .obsidian/
├─ .obsidian-vault-mcp.json
├─ .obsidian-vault-mcp/
│  ├─ state/items/ABCD1234.json
│  ├─ state/evidence/ABCD1234.json
│  ├─ state/uncertainties/ABCD1234.json
│  ├─ state/coverage/ABCD1234.json
│  ├─ cache/mineru-assets/ABCD1234/manifest.json
│  ├─ staging/
│  ├─ backups/
│  └─ locks/
└─ Literature/
   ├─ index.md
   ├─ Literature.base
   ├─ ABCD1234.md
   ├─ Analysis/ABCD1234.md
   ├─ Analysis/index.md
   ├─ Topic/
   ├─ Theory/
   ├─ Wiki/
   └─ attachment/
      ├─ ABCD1234.pdf
      └─ MinerU/
         ├─ ABCD1234.md
         └─ image/ABCD1234-fig01.png
```

用户可见文件只使用 Vault 相对路径和 `/` 分隔符。Zotero 源 PDF 的绝对路径与哈希只保存在隐藏 state 中，不写进主笔记、Index、Base 或 Wiki。

## 实际效果

以下截图来自 5 篇 Zotero 文献的端到端验收，包含 PDF 导入、MinerU 精准解析、Index、Base 和 Wiki 综合。

### 文献目录

<img src="https://raw.githubusercontent.com/luffysolution-svg/obsidian-vault-mcp/main/docs/assets/screenshots/v2/vault-structure.png" alt="Obsidian Literature 目录，包含 PDF、MinerU、Wiki 和 Base" width="300">

### 自动增长的 Index

<img src="https://raw.githubusercontent.com/luffysolution-svg/obsidian-vault-mcp/main/docs/assets/screenshots/v2/literature-index.png" alt="Literature Index 仪表盘，按年份、期刊和标签组织文献" width="720">

### 五篇文献形成的主题 Wiki

<details>
<summary>展开完整 Wiki 效果图</summary>

<img src="https://raw.githubusercontent.com/luffysolution-svg/obsidian-vault-mcp/main/docs/assets/screenshots/v2/wiki-synthesis.png" alt="基于五篇 Zotero 文献生成的可追溯 Wiki 综合页面" width="760">

</details>

单篇主笔记、全文嵌入和 Base 矩阵的完整截图见[教程中的效果展示](https://github.com/luffysolution-svg/obsidian-vault-mcp/blob/main/docs/index.md#10-效果展示)。

## 接入 AI 客户端

Codex Desktop/CLI 与 Claude Code 使用同一个 `obsidian-literature` 原生插件。插件同时提供 33 个 MCP Tools 和 9 个模型无关 Skills；插件包不包含 Python runtime，因此应先用 `pipx` 或 `uv tool` 持久安装上面的 Python 包，并确认 GUI/CLI 客户端启动时能在 `PATH` 中找到 `obsidian-vault-mcp`。

取得并解压本地构建产物或 Release 附件 `obsidian-vault-mcp-2.1.0-plugins.zip` 后，把 `<MARKETPLACE_DIR>` 指向解压根目录（其中直接包含 `.agents/`、`.claude-plugin/` 和 `plugins/`），再使用客户端原生命令：

```powershell
codex plugin marketplace add "<MARKETPLACE_DIR>"
codex plugin add obsidian-literature@obsidian-vault-mcp

claude plugin marketplace add "<MARKETPLACE_DIR>" --scope user
claude plugin install obsidian-literature@obsidian-vault-mcp --scope user
```

也可以让便捷入口调用同一组原生 CLI 命令；它不会为 Codex/Claude 写项目 `.mcp.json` 或复制项目 Skills：

```powershell
obsidian-vault-mcp agent install codex --dry-run
obsidian-vault-mcp agent install codex
# Claude Code：把 codex 换成 claude
```

安装后请完全退出并重新打开 Codex Desktop/Claude Code，或新建 CLI 会话。OpenCode 继续使用项目 `opencode.json` 与 `.opencode/skills`；Pi 使用薄 TypeScript Extension；Hermes 和 WorkBuddy 只安装 MCP，并明确提示不提供未经验证的项目级 Skills。可用客户端名称仍为 `codex`、`claude`、`opencode`、`pi`、`hermes`、`workbuddy`。

共享插件 `.mcp.json` 不写入 Vault 绝对路径，而是继承客户端进程环境。项目不在 Vault 内时，应在本机安全地设置 `OBSIDIAN_VAULT_PATH=<VAULT_DIR>` 后重启客户端；不要把真实路径提交到仓库。

连接后可以直接告诉 Agent：

```text
在执行写操作前先 dry-run。搜索 Zotero 中与 CdS 光催化制氢有关的文献，
导入我确认的父条目，使用 MinerU 精准解析 PDF，重建 Index 和 Base；
然后基于这些 zoteroKey 获取 Wiki context，生成带主笔记来源链接的主题页，
最后运行 literature_verify 并报告 transactionId。
```

## 结构化精读与证据检索

V2.1 保留原 26 个工具并新增 7 个模型无关工具：`literature_paper_read`、`literature_analysis_context`、`literature_analysis_write`、`literature_uncertainty_list`、`literature_uncertainty_resolve`、`literature_rebuild_analysis_index` 和 `literature_retrieve`。

```powershell
obsidian-vault-mcp call literature_paper_read --json '{"zotero_key":"ABCD1234","mode":"targeted","query":"charge transfer mechanism","record_coverage":true}'
obsidian-vault-mcp call literature_analysis_context --json '{"zotero_key":"ABCD1234","include_figures":true}'
obsidian-vault-mcp call literature_retrieve --json '{"query":"CdS nickel cocatalyst","scope":{"zotero_keys":["ABCD1234"]},"depth":"evidence","record_coverage":true}'
```

Server 只返回原文证据、资产状态、覆盖边界和安全写入能力，不自行生成论文结论。Evidence 重建会把确定性的 `^ev-*` block ID 物理写入派生 MinerU Markdown，因此 `sourceLink` 可由 `literature_verify` 核对真实锚点。`assetId` 只代表图片资产；论文事实仍应引用 `evidenceId`。MinerU 候选图在没有可靠 PDF crop 时不会被标记为视觉验证。

读取工具默认不产生写操作；只有显式传入 `record_coverage=true` 才更新 Coverage Ledger。此时单篇读取返回 `coverageLedger`，跨文献检索为每篇返回对应记录及真实 `transactionId`；配合 `coverage_dry_run=true` 可只预览，并可用 `coverage_transaction_id` 指定可辨识的事务前缀。Coverage 只描述读到了什么，不是论文事实。

## 稳定身份与安全边界

- `zoteroKey` 是 V2 唯一永久主键；自定义文件名仍必须包含 `{zoteroKey}`。
- 插件只重建 `<!-- ovm:*:start/end -->` 之间的托管区块；Reading Notes 与其他用户章节保留。
- MinerU 先写 staging，验证 Markdown 和图片后才整体替换正式产物；失败不会提交半成品。
- 默认 MCP transport 是本地 `stdio`。SSE/HTTP 没有内建认证，不建议直接暴露到网络。
- MinerU 精准模式会把 PDF 发送给 MinerU 服务；没有 token 时 `auto` 使用受限的 `flash-extract`。
- `doctor`、事务预览和 Wiki context 会向当前 Agent 返回必要的本机状态或文献内容；请只连接你信任的 Agent host。
- Token、Vault 绝对路径与私人文献内容不得提交到 Git。

## 迁移与恢复

V1 数据必须先预览，再正式迁移：

```powershell
obsidian-vault-mcp migrate v1-to-v2 --dry-run
obsidian-vault-mcp migrate v1-to-v2 --apply
obsidian-vault-mcp preview <transaction-id>
obsidian-vault-mcp rollback <transaction-id> --dry-run
obsidian-vault-mcp rollback <transaction-id>
```

如果事务之后文件又被用户修改，回滚会拒绝覆盖。只有明确接受覆盖风险时才使用 `--conflict-policy overwrite-managed`。

V2.1 会在旧 item state 上增量补充 `mineruAssetRoot` 和 `collectionKeys`：前者用于在 `candidateCacheFolder` 改动时事务化迁移该条目的 Manifest/候选缓存，后者让 `literature_retrieve.scope.collection_key` 可按已知 Zotero 集合成员过滤。旧 state 无需手工改写；后续导入、同步或 MinerU 解析会按实际信息更新，且可随事务回滚。

## 文档

- [完整使用教程](https://github.com/luffysolution-svg/obsidian-vault-mcp/blob/main/docs/index.md)：软件下载、Zotero/MinerU API、可选插件、安装命令、Agent 接入、自定义配置、首次完整流程、截图与排错。
- [开发者文档](https://github.com/luffysolution-svg/obsidian-vault-mcp/blob/main/DEVELOPMENT.md)：架构、数据契约、33 个工具、测试、构建、发布、安全边界和已知限制。
- [English user guide](https://github.com/luffysolution-svg/obsidian-vault-mcp/blob/main/README.en.md) · [English tutorial](https://github.com/luffysolution-svg/obsidian-vault-mcp/blob/main/docs/index.en.md) · [English developer guide](https://github.com/luffysolution-svg/obsidian-vault-mcp/blob/main/DEVELOPMENT.en.md)

## 贡献者

感谢 [方珸 / Lym Fang (@LimFang)](https://github.com/LimFang) 发现 Zotero 链接附件兼容需求并在 [PR #6](https://github.com/luffysolution-svg/obsidian-vault-mcp/pull/6) 中提出原始实现。完整贡献记录见 [CONTRIBUTORS.md](https://github.com/luffysolution-svg/obsidian-vault-mcp/blob/main/CONTRIBUTORS.md)。

## 项目命名

| 对象 | 名称 |
|---|---|
| GitHub 仓库 | `obsidian-vault-mcp` |
| PyPI distribution | `zotero-obsidian-mcp` |
| Python import | `obsidian_vault_mcp` |
| CLI | `obsidian-vault-mcp` |
| MCP server | `obsidian-literature` |
| 插件 marketplace | `obsidian-vault-mcp` |
| Codex/Claude plugin | `obsidian-literature` |

问题请提交到 [GitHub Issues](https://github.com/luffysolution-svg/obsidian-vault-mcp/issues)。项目采用 [MIT License](https://github.com/luffysolution-svg/obsidian-vault-mcp/blob/main/LICENSE)。
