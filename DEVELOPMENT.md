# Obsidian Vault MCP V2 开发者文档

[English developer guide](./DEVELOPMENT.en.md) · [用户说明](./README.md) · [完整教程](./docs/index.md)

本文档是 V2 的开发、测试和发布入口，合并原技术、部署、隐私与参考资料。实现遵循项目的 V2 重构规格；仓库内代码与自动测试是最终可执行契约。

## 1. 项目标识与发布线

| 层 | 标识 |
|---|---|
| GitHub | `luffysolution-svg/obsidian-vault-mcp` |
| Python distribution | `zotero-obsidian-mcp` |
| Python package | `obsidian_vault_mcp` |
| Console entry point | `obsidian-vault-mcp` |
| MCP server | `obsidian-literature` |
| 插件 marketplace | `obsidian-vault-mcp` |
| Codex/Claude plugin | `obsidian-literature` |
| Pi package | `obsidian-vault-mcp-pi-extension` |

V2.0.0 是破坏性重构：删除 V1 Skills 镜像、旧脚本入口、分裂配置和标题身份，改为 `src/` 包、单一配置、最初 26 个 MCP 工具、统一 JSON CLI、事务和多客户端薄适配。V2.1.0 在不改名或删除旧工具的前提下新增 7 个结构化精读工具，公开工具面为 33 个。

## 2. 核心不变量

1. 一个 Zotero 父条目只对应一份主 Markdown 笔记。
2. `zoteroKey` 是唯一永久主键；标题、作者、年份和 citekey 都不是身份。
3. 用户可见路径全部是 Vault 相对 POSIX 路径，不含 Zotero 源绝对路径。
4. 主笔记是稳定资产；MinerU Markdown/图片是可重建派生资产。
5. 只更新带 `ovm:*` 标记的托管正文区块，保留其他用户正文和未知 Frontmatter 字段。
6. 正式文件通过 staging、备份、原子替换和事务提交；同一条目与全局索引有锁。
7. 业务逻辑只在 application/domain/adapters 实现；CLI、MCP 和 Pi 只负责适配。
8. Vault 只读取根目录的一份 `.obsidian-vault-mcp.json`。

## 3. 系统边界与数据流

```text
MCP Tools ─┐
           ├─ Interfaces ─> Application Services ─> Domain / Config
JSON CLI ──┘                                  │
                                             ├─ Zotero HTTP adapter
Pi Extension ─> JSON CLI                     ├─ MinerU subprocess adapter
                                             ├─ Vault filesystem/transaction
                                             └─ Obsidian renderers
```

Application 当前直接组合具体 adapters，属于清晰分层但不是严格依赖反转的 ports-and-adapters 实现。MCP Tool 不直接处理 HTTP、YAML、文件复制或 subprocess。

主流程：

```text
Zotero local API
  ├─ metadata / tags / notes / annotations / BibTeX
  └─ PDF attachment
          ↓ ImportService / SyncService
main note + PDF + state + index + base
          ↓ MinerUService
staging → normalize → transaction → MinerU Markdown/images
          ↓ WikiService
source context → Agent-authored content → validated Wiki page
```

## 4. 源码布局

```text
src/obsidian_vault_mcp/
├─ domain/                 # identity、portable paths、frontmatter、models、errors
├─ application/            # import/sync/mineru/index/base/wiki/migration/transaction/verify
├─ adapters/
│  ├─ zotero/              # local API、pagination、BibTeX
│  ├─ mineru/              # CLI subprocess 与输出规范化
│  ├─ vault/               # filesystem、atomic writer、locks
│  └─ obsidian/            # note、index、base renderers
├─ interfaces/
│  ├─ mcp/                 # FastMCP server 与 33 tools
│  ├─ cli/                 # argparse + 单 JSON 输出
│  └─ agent_install/       # Codex/Claude 原生插件入口 + 四种项目适配器 + Pi resource
├─ resources/
│  └─ agent_marketplace/   # 双 marketplace/manifest、共享 MCP 与 9 Skills 的唯一规范源
└─ config/                 # defaults、loader、strict validation

adapters/pi/               # 可独立分发/开发的 Pi Extension
tests/unit/                # 领域、adapter、service 与 renderer
tests/contract/            # 工具面、客户端配置、握手/回滚、Pi bridge
tests/repository/          # 目录、依赖、CI、release hygiene
scripts/verify_release.py  # 版本、仓库和 Python/plugin 产物验证
scripts/build_release.py   # 跨平台、可复现的双客户端 plugin marketplace zip
scripts/build_release.ps1  # PowerShell 兼容 wrapper
```

## 5. 稳定数据契约

### 5.1 身份与路径

Zotero key 接受 ASCII 字母、数字、`_`、`-`，最长 64 字符。默认资产：

| 资产 | 路径 |
|---|---|
| 主笔记 | `Literature/{zoteroKey}.md` |
| PDF | `Literature/attachment/{zoteroKey}.pdf` |
| MinerU Markdown | `Literature/attachment/MinerU/{zoteroKey}.md` |
| MinerU 图片 | `Literature/attachment/MinerU/image/{zoteroKey}-figNN.ext` |
| 条目 state | `.obsidian-vault-mcp/state/items/{zoteroKey}.json` |
| Index | `Literature/index.md` |
| Base | `Literature/Literature.base` |
| Wiki | `Literature/Wiki/{topic}.md` |

路径层拒绝绝对路径、盘符、UNC、`..`、Windows 保留名、控制字符和非法结尾，并在解析后证明目标仍位于 Vault 根目录内。自定义主资产命名 pattern 必须保留完整 `{zoteroKey}`；图片还必须保留 `{index}` 与 `{ext}`。

### 5.2 主笔记 Frontmatter

托管字段顺序固定：

```text
title
itemType
year
journal
tags
doi
url
abstract
zoteroKey
zoteroPdfLink
attachmentPdfLink
attachmentMinerULink
```

空字段默认省略。未知字段在托管字段之后保留。绝对源路径、哈希、错误和事务状态只写隐藏 state。

### 5.3 正文托管区块

固定区块：`abstract`、`pdf`、`mineru`、`zotero-notes`、`bibtex`。

```html
<!-- ovm:<section>:start -->
generated content
<!-- ovm:<section>:end -->
```

渲染器只替换标记内部。标题 H1 与托管章节可重建；Reading Notes 和其他标记外正文保留。BibTeX adapter 会移除本地 `file`/附件字段，防止源路径进入主笔记。

### 5.4 MinerU 产物

MinerU 输入是 Vault 内 PDF 副本。输出先进入事务 staging；normalizer：

- 选择主 Markdown，移除上游 Frontmatter；
- 验证图片存在且位于 staging 内；
- 拒绝绝对路径、URL、目录穿越和未知图片扩展名；
- 按 Markdown 首次引用顺序生成 `figNN`；
- 根据配置的 Markdown/Image 文件夹计算 POSIX 相对链接；
- 写入 `title`、`zoteroKey` 与相对 `sourcePdf`；
- 全部验证成功后才替换正式文件并清理失效的同条目图片。

`auto` 在检测到环境 token 或 `~/.mineru/config.yaml` token 时使用 `extract`，否则使用 `flash-extract`；`api` 和 `local` 分别映射到这两种命令。Windows 会优先解析 `.exe/.com/.cmd/.bat` shim。

### 5.5 Index、Base 与 Wiki

- Index 只从 Literature 根目录的顶层主笔记读取 record，按近期、年份、期刊、标签生成确定性托管区块。
- Base 仅筛选 `file.folder == literature.root` 的顶层主笔记，生成 11 列、7 个视图；MinerU Markdown 不再造成重复行。
- Wiki context 返回相关主笔记、摘要、Zotero notes、MinerU 摘录、现有 Wiki 与来源链接。
- Wiki write 至少要求一个已存在的 `zoteroKey`，拒绝本机/staging 引用，并自动补充 Sources。
- Agent 负责综合推理；server 不调用固定 LLM。

Index 的 `Broken attachment links` 当前仍是 renderer 占位统计，真正链接问题以 `literature_verify` 为准。

### 5.6 V2.1 图片、证据与精读状态

- 图片 Manifest 位于 `.obsidian-vault-mcp/cache/mineru-assets/{zoteroKey}/manifest.json`。正文明确引用的图片进入正式 `imageFolder`；未引用候选仅进入同目录下的 `assets/` 缓存。`assetId` 由 `zoteroKey` 和内容 SHA-256 确定，不依赖 `figNN` 顺序。
- Evidence state 位于 `.obsidian-vault-mcp/state/evidence/{zoteroKey}.json`，包含稳定 `evidenceId`、章节路径、原文、block link、内容哈希、source fingerprint 和关联 `assetId`；重建时确定性的 `^ev-*` block ID 会与 state/Manifest 同事务物理写入派生 MinerU Markdown，Verify 会检查锚点存在且唯一。页码无法可靠确认时始终为 `null`。
- Analysis 笔记默认位于 `Literature/Analysis/{zoteroKey}.md`，只更新 `ovm:analysis` 与 `ovm:analysis-uncertainties` 区块。待复核 state 位于 `.obsidian-vault-mcp/state/uncertainties/{zoteroKey}.json`，resolve 保留原 claim 和追加式审计历史。
- 新导入的 Zotero child notes 与 annotations 在原 `ovm:zotero-notes` 受管区块内使用内部来源标记，`literature_analysis_context` 可离线分别返回 `zoteroNotes`/`zoteroAnnotations`。旧笔记的合并内容继续作为 `zoteroNotes` 返回，并附兼容 warning。
- Coverage Ledger 位于 `.obsidian-vault-mcp/state/coverage/{zoteroKey}.json`。读取工具默认不写账本，只有 `record_coverage=true` 才走 TransactionService；返回的 `coverageLedger` 带真实或 dry-run `transactionId`。它记录实际读取粒度和覆盖边界，不是论文事实证据；源哈希变化后旧记录标记 stale。
- Analysis index 位于 `Literature/Analysis/index.md`，只能由结构化 Analysis/state 确定性重建。一句话定位明确标记为 `agent_synthesis`。

P0 不包含可靠 PDF 图表裁剪、panel 分割、OCR、多模态视觉解释、embedding 或 reranker。MinerU 图片存在只表示候选资产，不等于视觉结论已验证。

## 6. 配置契约

默认配置和编辑器 JSON Schema 分别位于：

- `src/obsidian_vault_mcp/config/defaults.py`
- `obsidian-vault-mcp.schema.json`

运行时 `validate_config()` 先拒绝未知字段和错误类型，再与默认值深合并，并执行路径、identity、命名和跨字段校验。部分配置可省略，但 `schemaVersion: 2` 必须存在。

### 6.1 当前生效字段

- `literature.root/index/base/wikiFolder`
- `naming.*`
- `attachments.pdfFolder/copyPdf/overwritePolicy`
- `frontmatter.omitEmpty/preserveUnknownFields/fieldOrder`
- `note.omitEmptySections/readingNotesHeading/embedPdf/embedMineruMarkdown`
- `zotero.apiBase/linkedAttachmentBaseDir/syncTags/paginationSize`
- `bibtex.enabled/provider`
- `mineru.mode/markdownFolder/imageFolder/maxConcurrentJobs`
- `mineru.preserveUnlinkedImageCandidates/imageManifestEnabled/candidateCacheFolder`
- `analysis.folder/index/topicFolder/theoryFolder`
- `evidence.enabled/blockIdPrefix/maxChunkChars/overlapChars`
- `index.autoRebuild/recentLimit`
- `base.autoRebuild/name`

### 6.2 固定或尚未接线字段

以下字段仍属于 schema 兼容面，但 V2.0 不应当作可切换功能宣传：

- `identity.strategy` 固定为 `zoteroKey`；`frontmatter.fieldOrder` 必须等于固定顺序。
- `mineru.imageLinkStyle` 只允许 `markdown-relative`。
- `note.preserveUserSections` 未分支，主笔记用户区始终保留。
- `zotero.syncNotes`、`syncAnnotations` 当前始终同步。
- `mineru.enabled` 不阻止显式 parse；`replacePreviousOutput` 当前始终整体替换。
- `index.groupBy` 当前始终渲染 year/journal/tags。
- `safety.*` 当前是固定安全不变量；`retainBackups` 尚未实现自动清理。
- `bibtex.fallback=none` 在 `provider=auto` 时尚未改变内置 fallback 链。

修改这些字段的语义前必须先补行为测试、迁移说明和 schema 版本策略。

## 7. Application service 行为

### Import / Sync

- 统一按父条目 `zoteroKey` 查找身份。
- Zotero 搜索、集合和 children 使用分页迭代；集合导入不会截断在 100 条。
- Import 建立主笔记、PDF、state、Index、Base；Sync 对相同路径做增量事务。
- item state 的 `collectionKeys` 保存已知集合成员关系，供 `literature_retrieve.scope.collection_key` 使用；`mineruAssetRoot` 保存当前条目 Manifest/候选缓存根，使 `candidateCacheFolder` 改动时能在同一事务迁移旧目录。缺少这两个字段的旧 state 保持可读，并在后续导入/同步/解析时增量补齐。
- PDF overwrite policy 影响复制规划，最终 SHA 相同则事务 no-op。
- `rename` 只在目标路径被其他身份占用时提供特殊处理；其他策略拒绝危险覆盖。

### MinerU

- 单篇超时默认 600 秒；batch worker 数受 `maxConcurrentJobs` 限制。
- dry-run 只返回计划路径，不启动 CLI。
- 失败时丢弃 staging，不提交半成品；独立事务只记录 error state。
- Pi bridge 超时为 660 秒，以覆盖单篇 MinerU 上限及收尾。

### Verify

Verify 扫描整个 Vault 中可见的 `.md` 和 `.base`，排除顶层隐藏目录；检查绝对/staging 引用、身份和附件链接。warning 也会使 `ok=false`。它不校验 PDF 哈希或所有 state 语义。

### Migration / Rollback

- V1→V2 默认 dry-run；`--apply` 才正式迁移。
- 迁移按旧 `zoteroKey` 聚合、规划路径/链接/Frontmatter/state/Index/Base。
- Rollback 先比较当前 SHA 与事务 `afterSha256`，防止覆盖事务后的用户编辑。
- 冲突时只有 `overwrite-managed` 会强制恢复；其他 policy 拒绝覆盖。

## 8. CLI 与 33 个 MCP Tools

CLI 成功时向 stdout 输出一个 JSON 值。业务异常输出 `{"ok":false,"error":...}` 并返回退出码 2；Windows legacy code page 无法表示字符时回退到 ASCII escaped JSON。

主要命令：

```bash
obsidian-vault-mcp doctor
obsidian-vault-mcp config get|validate|init
obsidian-vault-mcp import item|collection
obsidian-vault-mcp sync item|collection
obsidian-vault-mcp mineru parse|parse-batch|remove
obsidian-vault-mcp index rebuild
obsidian-vault-mcp base rebuild
obsidian-vault-mcp verify
obsidian-vault-mcp wiki context|write|list
obsidian-vault-mcp migrate v1-to-v2
obsidian-vault-mcp preview <transaction-id>
obsidian-vault-mcp rollback <transaction-id>
obsidian-vault-mcp call <tool> --json '{...}'
obsidian-vault-mcp serve --transport stdio
obsidian-vault-mcp agent install <client>
```

Tool surface：

| 分组 | 工具 |
|---|---|
| 配置诊断（4） | `literature_doctor`, `literature_config_get`, `literature_config_validate`, `literature_config_initialize` |
| Zotero（6） | `zotero_ping`, `zotero_search_items`, `zotero_list_collections`, `zotero_get_item`, `zotero_get_children`, `zotero_get_bibtex` |
| 导入同步（4） | `literature_import_item`, `literature_import_collection`, `literature_sync_item`, `literature_sync_collection` |
| MinerU（3） | `literature_parse_mineru`, `literature_parse_mineru_batch`, `literature_remove_mineru_output` |
| 知识库（3） | `literature_rebuild_index`, `literature_rebuild_base`, `literature_verify` |
| 结构化精读（7） | `literature_paper_read`, `literature_analysis_context`, `literature_analysis_write`, `literature_uncertainty_list`, `literature_uncertainty_resolve`, `literature_rebuild_analysis_index`, `literature_retrieve` |
| Wiki（3） | `literature_wiki_context`, `literature_wiki_write`, `literature_wiki_list` |
| 迁移事务（3） | `literature_migrate_v1_to_v2`, `literature_preview_transaction`, `literature_rollback_transaction` |

写工具通常接受 `vault_path`、`dry_run`、`transaction_id`、`conflict_policy`，但各 service 的冲突语义不同；新增/修改工具时必须同步 CLI、MCP、Pi、contract tests 和文档。

## 9. Agent 适配

`SUPPORTED_CLIENTS`：`codex`、`claude`、`opencode`、`pi`、`hermes`、`workbuddy`。

Codex Desktop/CLI 与 Claude Code 的生产主路径是客户端原生 marketplace plugin。`obsidian-vault-mcp agent install codex|claude` 只是便捷入口：从 wheel 的 `obsidian_vault_mcp.resources.agent_marketplace` 解析稳定绝对目录，调用客户端原生 CLI，并用 marketplace/plugin list 做幂等检测。`project_dir` 仅为统一接口兼容保留，不写项目 `.mcp.json`，也不复制项目 Skills；同名 marketplace 已指向其他目录时必须安全失败。

| 客户端 | 机制 | MCP/Extension 目标 | Skill 目标 |
|---|---|---|---|
| Codex Desktop/CLI | 原生 marketplace plugin | Codex 管理 | plugin 内 9 Skills |
| Claude Code | 原生 marketplace plugin，user scope | Claude 管理 | plugin 内 9 Skills |
| OpenCode | 事务式项目适配器 | `opencode.json` | `.opencode/skills` 的 9 个受管 Skills |
| Hermes | MCP-only profile 适配器 | `$HERMES_HOME/config.yaml`（默认 `~/.hermes/config.yaml`） | 无；返回 warning |
| WorkBuddy | MCP-only 项目适配器；探测 `codebuddy`，回退 `cbc` | `.workbuddy/mcp.json` | 无；返回 warning |
| Pi | 薄 Extension 项目适配器 | `.pi/extensions/obsidian-vault-mcp.ts` | 无；Extension-only |

原生插件命令契约：

```text
codex plugin marketplace add <MARKETPLACE_DIR>
codex plugin add obsidian-literature@obsidian-vault-mcp
claude plugin marketplace add <MARKETPLACE_DIR> --scope user
claude plugin install obsidian-literature@obsidian-vault-mcp --scope user
```

`PluginInstallResult` 必须把 client、executable、marketplace name/path、plugin selector/version、dry-run/changed、preexisting/added/installed 状态、实际或计划命令、handshake 状态和卸载说明完整 JSON 化。Codex/Claude 原生命令完成后会直接执行一次 stdio initialize handshake；它证明打包 runtime 可启动，但 plugin 与 Skill 发现仍需新客户端会话。整个过程不写项目配置，也不通过项目配置握手。Codex 卸载使用 `plugin remove`；Claude 使用 `plugin uninstall --scope user`，移除 marketplace 时也必须带 `--scope user`；marketplace 只在确认无其他依赖后移除。

OpenCode、WorkBuddy 与 Pi 项目适配器，以及写 Hermes profile 配置的适配器，都会执行：检测可执行文件 → 规划 → 备份 → 原子写入 → MCP initialize handshake → 失败回滚；`--dry-run` 零写且不 handshake。OpenCode 还会验证受管 Skill 哈希并把配置/Skills 纳入同一事务边界。Hermes 忽略统一接口的 `project_dir`；显式 `config_path` 覆盖仅供 Python 安装器 API 使用，不是 `agent install` CLI 选项。`workbuddy` 是安装器客户端名称，不是平台 executable。

原生 MCP 配置统一调用：

```text
obsidian-vault-mcp serve --transport stdio
```

Pi Extension 不复制业务逻辑，以 `execFile(shell=false)` 调用 `obsidian-vault-mcp call ... --json ...`。`adapters/pi/index.ts` 与 wheel resource `src/.../pi_extension.ts` 必须字节一致。

9 个 Skill 的唯一规范源是 `src/obsidian_vault_mcp/resources/agent_marketplace/plugins/obsidian-literature/skills/`。Codex/Claude 直接消费 plugin 内 Skills；OpenCode 安装目标包含 `.obsidian-vault-mcp-skills.json`，升级只替换受管区块并保留 `User Customizations`，发现篡改或旧格式时写前拒绝。不得增加客户端镜像或同步脚本。Hermes/WorkBuddy 不猜测 `.hermes/skills` 或 `.workbuddy/skills`。

Codex/Claude plugin 的共享 `.mcp.json` 不写 `OBSIDIAN_VAULT_PATH`，由启动进程继承；OpenCode/Pi 同样继承。Hermes profile 配置与 WorkBuddy 项目模板可用 `auto`，但它只搜索进程 cwd 的父链。普通项目需要本机显式 Vault 路径；不要把该绝对路径提交到仓库。

## 10. 事务、并发与文件安全

一个 transaction operation 记录 action、before/after SHA-256、字节数与文本 diff。提交顺序：

```text
plan → stage → backup old file + manifest → same-directory temp file
→ flush → fsync → os.replace → commit result
```

- 完全相同的结果是 no-op，不创建备份。
- 关键失败会尝试恢复旧文件。
- 条目事务使用 `.obsidian-vault-mcp/locks/<zoteroKey>.lock`。
- Index/Base 分别使用全局锁。
- rollback 依据 manifest 与 SHA 防止覆盖后续编辑。
- 事务 preview/diff 可能包含隐藏 state 的源 PDF 绝对路径；它不是可公开日志。

## 11. 本地开发与测试

```bash
python -m pip install -e ".[dev]"
python -m ruff check src tests scripts
python -m pytest tests/unit tests/contract tests/repository
python scripts/verify_release.py
```

Pi（Node 20+；CI 使用 Node 22）：

```bash
cd adapters/pi
npm install --no-audit --no-fund
npm run check
```

测试层次：

- `unit`：identity/path/frontmatter、事务、Zotero 分页、BibTeX、MinerU、renderers、services、migration。
- `contract`：33 工具、原生 plugin 命令、客户端配置合并、备份/握手恢复、Pi bridge。
- `repository`：`src/` layout、删除 V1 路径、依赖边界、CI 和 release bundle。

自动测试不得连接真实 Zotero/MinerU，也不得写用户 Vault。5 篇真实文献是手工端到端验收，不替代 fixtures 和回归测试。

## 12. 构建与发行验证

先确保 `dist/` 没有旧产物，再从同一 checkout 构建 Python 产物和跨客户端 plugin marketplace：

```bash
python -m build --wheel --sdist --outdir dist
python scripts/build_release.py --version 2.1.0 --output-dir dist
python scripts/verify_release.py --artifacts-dir dist --require-sdist --smoke-wheel --bundle-dir dist
```

`scripts/build_release.py` 是 Windows、macOS、Linux 共用的规范入口；`./scripts/build_release.ps1 -Version 2.1.0 -OutputDir dist` 只是 PowerShell 兼容 wrapper。两者必须生成相同的确定性 ZIP。

Release workflow 在 Linux 上生成并验证校验和；本地使用 Git Bash、WSL 或 macOS/Linux 时可执行：

```bash
cd dist
sha256sum -- *.whl *.tar.gz *.zip > SHA256SUMS
cd ..
python scripts/verify_release.py --checksums-dir dist
```

产物：

```text
dist/zotero_obsidian_mcp-2.1.0-py3-none-any.whl
dist/zotero_obsidian_mcp-2.1.0.tar.gz
dist/obsidian-vault-mcp-2.1.0-plugins.zip
dist/SHA256SUMS
```

plugin ZIP 根目录就是 `<MARKETPLACE_DIR>`，没有额外 `obsidian-literature/` 包裹层。精确 allowlist 为 15 个文件：

```text
.agents/plugins/marketplace.json
.claude-plugin/marketplace.json
plugins/obsidian-literature/.codex-plugin/plugin.json
plugins/obsidian-literature/.claude-plugin/plugin.json
plugins/obsidian-literature/.mcp.json
plugins/obsidian-literature/assets/icon.svg
plugins/obsidian-literature/skills/analyze-figures/SKILL.md
plugins/obsidian-literature/skills/compare-papers/SKILL.md
plugins/obsidian-literature/skills/evidence-based-qa/SKILL.md
plugins/obsidian-literature/skills/literature-review/SKILL.md
plugins/obsidian-literature/skills/structured-paper-note/SKILL.md
plugins/obsidian-literature/skills/theory-note-synthesis/SKILL.md
plugins/obsidian-literature/skills/topic-note-synthesis/SKILL.md
plugins/obsidian-literature/skills/uncertainty-audit/SKILL.md
plugins/obsidian-literature/skills/verify-paper-claims/SKILL.md
```

这等于两份 marketplace manifest、两份 client plugin manifest、一份共享兼容 `.mcp.json`、一个 Codex App 图标和 9 个 Skills。ZIP 不包含 Python runtime、`__init__.py`、源码、文档、凭据、Vault 数据或缓存。Wheel/sdist 必须包含相同 canonical marketplace resource、V2 CLI 与 Pi installer resource，不得包含旧 `agent_skills` 镜像或 V1 Skills。

交付前除仓库验证器外，还要验证 plugin 目录本身；路径使用占位符，禁止把个人 Codex Home 写进文档或脚本：

```bash
python "<PLUGIN_CREATOR_DIR>/scripts/validate_plugin.py" "src/obsidian_vault_mcp/resources/agent_marketplace/plugins/obsidian-literature"
claude plugin validate --strict "src/obsidian_vault_mcp/resources/agent_marketplace/plugins/obsidian-literature"
```

生产本机验收必须从 `dist` 产物开始，而不是从 editable checkout 启动：用 `pipx install "<WHEEL_PATH>"` 或 `uv tool install "<WHEEL_PATH>"`，解压 plugin ZIP，把解压根目录交给 Codex/Claude 原生命令，启动新会话后核对 33 Tools、9 Skills，并重跑真实 Zotero→MinerU→Obsidian 的单篇、批量、图片与 Skill→MCP 流程。共享 bundle 的原生安装协议已用 Codex CLI 0.145 和 Claude Code 2.1.217 做过隔离探针；每个候选产物仍必须重复完整验收。

只有在用户明确授权远程发布、发布提交通过 CI 并进入 `main` 后，才创建 tag、让验证器核对 tag 与当前提交并推送。准备生产候选或运行以下命令不代表 tag、GitHub Release 或 PyPI 版本已经存在：

```bash
git switch main
git pull --ff-only
git tag -a v2.1.0 -m "Obsidian Vault MCP V2.1.0"
python scripts/verify_release.py --tag v2.1.0
git push origin v2.1.0
```

验证器检查 tag commit、Python package、两份 marketplace、两份 plugin manifest、共享 MCP、9 Skills、Pi package、源码版本与 adapter 配置的一致性。Release tag 必须使用 `vMAJOR.MINOR.PATCH`。

`.github/workflows/ci.yml` 在 Windows/Linux/macOS × Python 3.10–3.13 上测试，并单独 type-check Pi。`.github/workflows/release.yml` 应 checkout 对应 tag、重跑验证、构建 wheel/sdist/双客户端 plugin ZIP、生成校验和并上传经过授权的 GitHub Release；PyPI 发布只能使用同一批已验证 Python 产物。

发布账号必须把 PyPI token 存在 GitHub Secret 或安全的本机凭据中，绝不能写入 workflow、`.pypirc` 示例、文档或提交历史。长期建议迁移到 PyPI Trusted Publishing/OIDC。

## 13. 安全与隐私边界

### Vault 与 Agent

- 用户可见 Vault 文件不含本机绝对路径；隐藏 state 可以包含源附件路径和哈希。
- `doctor` 返回绝对 `vaultPath`；事务 diff 可能返回隐藏 state；Wiki context 返回本地文献摘录。
- 因此只能保证“绝对路径不进入用户可见文档”，不能声称 Agent host 看不到本机路径或正文。

### Zotero

- 默认通过 `127.0.0.1:23119` 读取本地 API，不需要云端 key。
- `ZOTERO_LOCAL_API` 可覆盖到其他地址，使用者应自行审查信任边界。
- `storage:` 附件从 Zotero storage 解析；`attachments:` 链接附件相对于 `zotero.linkedAttachmentBaseDir` 或 `ZOTERO_LINKED_ATTACHMENT_BASE_DIR` 解析。解析后必须仍位于该基础目录内，拒绝 `..`、盘符和越界路径。

### MinerU

- 精准 API 可能上传 PDF；使用前检查版权、保密和组织政策。
- 优先使用 `mineru-open-api auth` 的本地 token 文件，避免显式 `--token`。
- adapter 对记录到结果的命令参数做 token 脱敏，但外部 CLI 的异常输出仍应按敏感信息处理。

### MCP transport

- 本地 `stdio` 是默认和推荐方式。
- SSE/streamable HTTP 没有项目级鉴权、TLS 或部署加固，不应直接暴露公网。

### 仓库

- `.obsidian-vault-mcp.json`、`.obsidian-vault-mcp/`、`node_modules/`、构建目录和环境文件必须被忽略。
- 只发布用户明确授权并完成敏感信息审查的演示截图。
- 错误报告需删除用户名、绝对路径、token 和私人文献内容。

## 14. 已知限制

- 部分 schema 字段在 2.0 中保持固定行为，见[配置契约](#6-配置契约)。
- 备份保留数量尚未自动执行，需用户按组织策略维护隐藏 backups。
- `doctor.ok` 不汇总外部集成状态。
- `verify` 的 warning 也会令结果失败，且扫描范围是整个 Vault。
- Index 的 broken-link 数字当前不是 Verify 的实时聚合。
- Wiki context 返回有界摘录；全文级综合需要 Agent 另行读取本地文件。
- Wiki `preserve-user` 只保留未知 Frontmatter；提交的 Wiki body 会替换旧 body。
- stdio 之外的 transports 仅提供协议能力，不代表生产部署安全。

## 15. 上游与规范参考

- [Model Context Protocol specification](https://modelcontextprotocol.io/specification/)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [Python packaging specifications](https://packaging.python.org/)
- [Obsidian Bases](https://obsidian.md/help/bases)
- [Obsidian Properties](https://obsidian.md/help/properties)
- [Zotero Web API v3 / Local API](https://www.zotero.org/support/dev/web_api/v3/basics#local_api)
- [Better BibTeX](https://retorque.re/zotero-better-bibtex/)
- [MinerU](https://github.com/opendatalab/MinerU) 与 [MinerU Ecosystem](https://github.com/opendatalab/MinerU-Ecosystem)
- [Pi Extension documentation](https://github.com/badlogic/pi-mono/blob/main/packages/coding-agent/docs/extensions.md)
- [GitHub Actions](https://docs.github.com/actions) 与 [GitHub Releases](https://docs.github.com/repositories/releasing-projects-on-github)
- [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/)

修改公开契约时，应同时更新中英文三类文档、相关 tests 和 release verifier，避免用户说明与可执行行为再次分叉。
