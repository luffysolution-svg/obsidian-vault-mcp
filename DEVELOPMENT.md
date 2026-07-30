# Obsidian Vault MCP 3.0.0 开发文档

[English](./DEVELOPMENT.en.md) · [README](./README.md) · [用户教程](./docs/index.md)

本文是 V3 的实现、测试与发布契约。包名为 `zotero-obsidian-mcp`，CLI 为 `obsidian-vault-mcp`，MCP Registry 名称为 `io.github.luffysolution-svg/obsidian-vault-mcp`。

## 1. 不变量

1. `zoteroKey` 是文献身份；标题、作者、年份、citekey 和路径不是身份。
2. 用户文本只能由显式冲突策略处理；默认不得静默覆盖。
3. 正式写入经过 lock、staging、backup、manifest、原子替换与可回滚 transaction。
4. 主笔记/PDF 是稳定资产；MinerU Markdown 与图片是可重建派生资产。
5. MinerU Markdown 固定为 `Literature/attachment/MinerU/{key}.md`。
6. MinerU 图片固定为 `Literature/attachment/MinerU/image/{key}/{key}-figNN.ext`，链接固定为 `image/{key}/{key}-figNN.ext`。
7. 结构化研究只使用五类 Analysis、五种 status、七个 profile 与一个九视图 `Analysis.base`。
8. 不创建 Evidence、Coverage、Uncertainty、Analysis index、Topic、Theory 或 Analysis 模板运行时资产。
9. MCP 工具面恰好是 31：V2 的 26 个稳定工具加 5 个 V3 Analysis 工具。
10. Agent Skills 恰好是 7 个，并从一个 canonical marketplace 资源树递归打包。
11. CLI、MCP、Pi 与 Agent installer 只做接口适配；业务逻辑位于 application/domain/adapters。
12. 自动测试不写用户真实 Vault；真实 Vault 只读，所有写测使用隔离副本。

保留的 `Literature/index.md` 和 `Literature/Literature.base` 是 V2 文献导航，不属于已删除的 Analysis index。

## 2. 架构

```text
Codex / Claude / OpenCode / Hermes / WorkBuddy ─┐
                                                ├─ MCP stdio
Pi Extension ── JSON CLI ───────────────────────┤
CLI ────────────────────────────────────────────┘
                         ↓
                    application
       config / import / MinerU / Analysis / transaction
                  ↙            ↓             ↘
             Zotero         domain        Obsidian files
             adapter       contracts       + renderers
```

依赖方向必须向内：

```text
interfaces → application → domain
                 ↓
              adapters
```

Domain 不读取客户端配置、不运行 subprocess、不依赖 MCP。Interfaces 不复制业务规则。

关键目录：

```text
src/obsidian_vault_mcp/
├─ domain/                 # identity、paths、frontmatter、Analysis 契约
├─ application/            # use cases、transaction、migration、Skills
├─ adapters/
│  ├─ zotero/              # local API 与 linked attachment
│  └─ obsidian/            # note/Base/MinerU normalization
├─ config/                 # defaults、schema、runtime loading
├─ interfaces/
│  ├─ cli/                 # 统一 JSON CLI
│  ├─ mcp/                 # 固定 31 tools
│  └─ agent_install/       # 六客户端 installer 与 Pi resource
└─ resources/
   └─ agent_marketplace/   # Codex/Claude manifests 与 canonical Skills

adapters/pi/               # 可独立 type-check 的薄 Extension
tests/                     # unit、integration、contract、release
scripts/                   # 确定性构建与发布验证
server.json                # MCP Registry 3.0.0 元数据
```

## 3. 文献与 MinerU 契约

主笔记 frontmatter 的稳定来源字段包括 `zoteroKey`、PDF/MinerU 链接与 Zotero 元数据。用户正文与受管理区块必须分离；同步只更新受管理内容。

MinerU normalizer 必须：

1. 在 transaction staging 内选择唯一 Markdown 结果。
2. 把图片确定性重命名到该 key 的独立目录。
3. 将图片引用改写为相对 Markdown 路径。
4. 拒绝越界、缺失、绝对路径、重复目标和不支持格式。
5. 全部校验后一次提交 Markdown、图片、主笔记链接和 state。

删除输出也必须是事务式操作。失败不得留下正式半成品或指向 staging 的链接。

## 4. Analysis 数据模型

### 4.1 枚举

```text
types:
  full_read
  literature_review
  passage_qa
  figure_qa
  concept

statuses:
  draft
  ready
  reviewed
  needs_update
  archived

profiles:
  general
  medicine
  chemistry
  materials
  catalysis
  physics
  mathematics
```

所有 Analysis 共享 schema version、稳定 `analysisId`、类型/profile、来源 key、source fingerprint、skill/version、时间戳、summary 与 tags。类型特定字段在 `domain/analysis.py` 定义并严格验证。

正文只有一个受管理区块。升级或重写必须保留区块外用户文本。来源 fingerprint 变化时读取结果产生 `needs_update`，不得自动替换旧分析。

### 4.2 默认路径

| 类型 | 路径 |
|---|---|
| `full_read` | `Literature/Analysis/full-reads/` |
| `literature_review` | `Literature/Analysis/reviews/` |
| `passage_qa` | `Literature/Analysis/qa/passages/` |
| `figure_qa` | `Literature/Analysis/qa/figures/` |
| `concept` | `Literature/Analysis/concepts/` |
| Base | `Literature/Analysis/Analysis.base` |

`Analysis.base` 必须递归筛选 `analysisId != null`，且恰好渲染以下九个有序视图：

```text
Dashboard
Full Reads
Reviews
Passage Q&A
Figure Q&A
Concepts
Needs Attention
By Discipline
Recently Updated
```

Base 不嵌入完整正文，也不创建并行 Markdown index。

## 5. 五个 Analysis 工具

| 工具 | 读写 | 契约 |
|---|---|---|
| `literature_paper_read` | 只读 | 单篇 overview/targeted/figures；返回有定位的有限文本/图片信息，不持久化派生状态 |
| `literature_retrieve` | 只读 | 跨文献候选与片段；查询覆盖仅在响应内 |
| `literature_analysis_get` | 只读 | 按 ID、类型或来源查询并计算有效 status |
| `literature_analysis_write` | 写 | 严格校验、稳定身份、dry-run、事务提交、冲突策略 |
| `literature_rebuild_analysis_base` | 写 | 确定性预览/重建唯一 Base |

原 26 个稳定工具的名称见用户教程。不得增加 compatibility alias；改变工具名、参数或 annotations 必须同步 server、CLI、Pi/插件配置、contract test、发布 verifier 与中英文文档。

只读工具标注 `readOnlyHint`/`idempotentHint`，写工具准确标注 destructive/idempotent 属性，全部工具 `openWorldHint=false`。

## 6. 迁移契约

V2 平铺 MinerU 图片迁移也是 CLI-only：

```powershell
obsidian-vault-mcp migrate mineru-images-v2-to-v3 --vault-path <vault>
obsidian-vault-mcp migrate mineru-images-v2-to-v3 --vault-path <vault> --apply
```

报告必须区分 `copiedImages`、`movedImages`、`preservedLegacyImages`、
`rewrittenMarkdown`、`missingReferencedImages`、`reparseZoteroKeys` 与跳过项。
迁移仅接受能够由文件名、Markdown frontmatter 和引用共同证明归属的图片。默认
模式复制并保留旧路径；破坏性清理必须同时指定 `--cleanup-legacy` 与
`--confirm-vault-offline`，且复制、引用重写和旧图删除在同一全局事务中原子提交。

V2→V3 Analysis 迁移是 CLI-only：

```powershell
obsidian-vault-mcp migrate analysis-v2-to-v3 --vault-path <vault>
obsidian-vault-mcp migrate analysis-v2-to-v3 --vault-path <vault> --apply
```

默认调用只产生 dry-run manifest。仅 `--apply` 可提交 transaction。响应必须区分 migrated、skipped、manual review、旧锚点处理、旧 Analysis index 处理、Base 生成以及未安全映射的 Topic/Theory 文件。

提交后使用通用事务入口：

```powershell
obsidian-vault-mcp preview <transaction-id> --vault-path <vault>
obsidian-vault-mcp rollback <transaction-id> --vault-path <vault> --dry-run
obsidian-vault-mcp rollback <transaction-id> --vault-path <vault>
```

失败必须回滚；不确定文件保留原位。重复 dry-run/apply 必须幂等。

## 7. Skills 与插件

唯一 canonical 集合：

```text
paper-qa
full-read
passage-qa
figure-qa
compare-papers
literature-review
concept-learning
```

源目录为 `src/obsidian_vault_mcp/resources/agent_marketplace/plugins/obsidian-literature/skills/`。每个 Skill 由 `SKILL.md` 和可递归的 `references/**/*.md` 组成；wheel、sdist、插件 zip 与已安装文件必须逐字节来自该资源树。

升级器只替换 managed block，保留用户前后扩展。只有 manifest 证明由本项目管理的旧 Skill 才能删除；用户自建同名/额外文件不得删除。

客户端矩阵：

| 客户端 | MCP | Skills/插件 |
|---|---|---|
| Codex | 插件 `.mcp.json` | 原生 marketplace + 7 Skills |
| Claude Code | 插件 `.mcp.json` | 原生 marketplace + 7 Skills |
| OpenCode | 项目配置 | 项目本地 7 Skills |
| Pi | JSON CLI bridge | 薄 TypeScript Extension |
| Hermes | YAML 配置 | 无已验证的自动 Skill 契约 |
| WorkBuddy | JSON 配置 | 无已验证的自动 Skill 契约 |

OpenCode、Pi、Hermes 与 WorkBuddy 必须在目标项目目录执行，或显式传 `--project-dir`。Python 包从 2.x 升级时，uv tool 用户执行 `uv tool install --force "zotero-obsidian-mcp==3.0.0"`，pipx 用户执行 `pipx install --force "zotero-obsidian-mcp==3.0.0"`。随后 Codex 用原子 `plugin add` 刷新本地插件缓存；Claude 先 `plugin marketplace update obsidian-vault-mcp`，再执行 `plugin update ... --scope user` 并重启。发布 zip 是可离线解压的同一 marketplace；Claude 全新离线安装使用 `plugin marketplace add` 后接 `plugin install obsidian-literature@obsidian-vault-mcp --scope user`。已有同名 marketplace 时禁止改绑到另一来源。

`adapters/pi/index.ts` 与 wheel resource `src/obsidian_vault_mcp/interfaces/agent_install/pi_extension.ts` 必须字节一致，并固定 LF。

设计参考与许可证边界：

- `yilewang/llm-for-zotero`（AGPL-3.0）：实际审阅
  `src/agent/skills/simple-paper-qa.md`、`compare-papers.md`、
  `literature-review.md` 与 `analyze-figures.md`，只借鉴意图路由、定向阅读、
  主题综合和缺图降级的高层思路。
- 用户 Stars 中的 `Yuan1z0825/nature-skills`（仓库许可证
  Apache-2.0）：实际审阅 `skills/nature-literature-pipeline/SKILL.md` 与
  `skills/nature-paper-card/SKILL.md`，只借鉴按需 references、来源边界和
  学科适配的组织方法。

本仓库的七个 Skills、references、服务端实现与测试均独立编写；未复制上述
仓库的代码或 Skill 文本，因此不把 AGPL/Apache 代码混入 MIT 发布物。

## 8. 测试

本地门禁：

```powershell
python -m ruff check src tests scripts/build_release.py scripts/release_guard.py scripts/verify_release.py
python -m pytest
python scripts/verify_release.py

Push-Location adapters/pi
npm ci --no-audit --no-fund
npm run check
Pop-Location
```

测试至少覆盖：

- 五类 Analysis 的 schema、稳定 identity、status/profile 与 managed block。
- `paper_read`/`retrieve` 的边界、定位、1-based paragraph 与无持久派生 state。
- 每 key MinerU 图片目录、相对链接、失败原子性与重复解析。
- 九视图 Base 的顺序、filter、group/sort 与幂等。
- 迁移 dry-run、apply、rollback、冲突、失败恢复和重复运行。
- 完整 31 工具名称、annotations 与 stdio initialization handshake。
- 恰好七 Skills、递归 references、managed upgrade 和旧 managed Skill 清理。
- 六客户端配置/插件安装、备份、合并、handshake 与 rollback。
- wheel/sdist/plugin zip 内容、版本、portable config 与禁用旧资产。

CI 在 Ubuntu、Windows、macOS × Python 3.10–3.13 上执行 Python 门禁；Node 22 单独 type-check Pi，并在依赖 job 成功后构建发布候选。

## 9. 真实 Vault 端到端

发布前的真实 Vault 只允许只读命令。先对关键目录建立 SHA-256 清单，再执行 config/doctor/verify、paper read、retrieve、Analysis get，最后证明清单不变。

将最新真实 Vault 复制到新的 RC 目录后才允许写测。副本必须排除 active locks、staging、旧 backups 和残留临时目录。写测包括导入/同步、真实 MinerU、五类 Analysis、Base、迁移、preview、rollback、重复运行与最终 verify。

验收失败时不得 tag 或发布。真实 Vault 前后哈希不一致也视为失败。

## 10. 构建与验证

```powershell
python -m build --wheel --sdist --outdir dist
python scripts/verify_release.py --artifacts-dir dist --require-sdist --smoke-wheel
python scripts/build_release.py --version 3.0.0 --output-dir dist
python scripts/verify_release.py --bundle-dir dist
```

3.0.0 产物：

```text
zotero_obsidian_mcp-3.0.0-py3-none-any.whl
zotero_obsidian_mcp-3.0.0.tar.gz
obsidian-vault-mcp-3.0.0-plugins.zip
SHA256SUMS
```

验证器必须检查 31-tool stdio handshake、七 Skills 与 references、Pi 字节一致、MCP/插件 manifest、版本一致、artifact allowlist、临时 wheel smoke install 以及禁止旧结构化资源。

## 11. 版本与发布

3.0.0 必须在以下来源一致：

- `pyproject.toml` 与 `src/obsidian_vault_mcp/__init__.py`
- `adapters/pi/package.json` 与根 package-lock 记录
- Codex/Claude plugin manifest 与 marketplace metadata
- `server.json`
- tag `v3.0.0`

发布前：

```powershell
python scripts/verify_release.py --tag v3.0.0
git status --short
git tag -a v3.0.0 -m "Obsidian Vault MCP V3.0.0"
git push origin v3.0.0
```

Tag 必须是 `refs/tags/v3.0.0`，指向 `main` 已通过 CI 的 commit，且本地 tag object、远端 tag object、tag commit 与 checkout HEAD 必须一致。Tag、GitHub Release 与 PyPI 版本均不可覆盖。触发 workflow 前还必须在仓库 Settings 启用 immutable releases，并配置仅对本仓库具有 `Administration: read` 的 `IMMUTABLE_RELEASES_TOKEN` secret；普通 Release 读写继续使用权限更小的 `GITHUB_TOKEN`。最终验证会拒绝 GitHub API 中 `immutable` 不为 `true` 的正式 Release。Release workflow 会：

1. 在只有 `contents: read` 的 build job 重跑 Python/Pi/31-tool/包内容门禁。
2. 以固定构建工具和 commit 时间戳生成可复现的 wheel、sdist、插件 zip 与 SHA256，并通过 workflow artifact 交给独立 publish job。
3. Publish job 才获得 `contents: write` 与 `id-token: write`；在任何外部写入前，先完成严格远端 tag、GitHub immutability/Release、PyPI、MCP Registry 和固定 publisher 的全部预检。
4. 对 PyPI 的文件名与 SHA256 做精确预检；版本不存在时上传全部文件，远端为本地精确子集时只上传缺失文件，任何额外文件或同名异散列都失败；继续禁止 `skip-existing`。
5. 对 MCP Registry 的 exact name/version 做元数据一致性预检，并在发布前再次检查；仅在不存在时用固定版本的 `mcp-publisher` 和 GitHub OIDC 发布。
6. 最后创建带固定 workflow marker 的空 GitHub Release draft，仅上传缺失资产。中断重跑时，只允许续传 marker 相同且资产为本地精确集合子集的自有 draft；陌生 draft、额外资产或散列冲突均立即失败，禁止删除或覆盖。
7. Draft 的完整资产再次逐个下载并校验 SHA256 后，才转为不可变正式 Release；已发布 Release 也必须通过同一精确校验。

uv/uvx 不存在独立仓库发布；它们从 PyPI 安装。发布后必须从干净环境实际验证 pip、pipx、`uv tool install`、uvx、MCP Registry、六客户端安装器、七 Skills 和 31-tool handshake。

## 12. 安全与评审清单

- 不持久化 Zotero/MinerU/client 凭据；日志对 token 参数脱敏。
- subprocess 使用参数数组且不经过 shell。
- 所有 Vault path 解析后必须仍位于 Vault 内，拒绝 reparse/symlink 越界。
- 非 stdio MCP transport 需要外部认证边界。
- 不提交真实 Vault、附件、state、backup、测试副本或机器绝对路径。
- 变更必须小而可追溯；无关重构、格式化和旧代码清理不进入同一发布。

完成条件不是“构建成功”，而是源码测试、artifact smoke、真实只读、隔离写测、GitHub/PyPI/Registry 发布和全安装矩阵全部有可复核结果。
