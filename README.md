<!-- mcp-name: io.github.luffysolution-svg/obsidian-vault-mcp -->

# Obsidian Vault MCP

把 Zotero 文献、PDF、MinerU 全文与 Obsidian Analysis 连接成一条本地优先、事务式、可回滚的研究管道。

[English](https://github.com/luffysolution-svg/obsidian-vault-mcp/blob/main/README.en.md) · [完整教程](https://github.com/luffysolution-svg/obsidian-vault-mcp/blob/main/docs/index.md) · [开发文档](https://github.com/luffysolution-svg/obsidian-vault-mcp/blob/main/DEVELOPMENT.md)

## V3.0.0

V3 保留经过验证的 V2 稳定核心，并把结构化研究层收敛为一个 Analysis 模型：

- Zotero 父条目的 `zoteroKey` 仍是主笔记、PDF 与 MinerU 产物的稳定身份。
- MCP 固定为 31 个工具：V2 的 26 个稳定工具，加 5 个 Analysis 工具。
- Analysis 仅有 `full_read`、`literature_review`、`passage_qa`、`figure_qa`、`concept` 五类。
- 状态仅有 `draft`、`ready`、`reviewed`、`needs_update`、`archived`。
- 学科 profile 仅有 `general`、`medicine`、`chemistry`、`materials`、`catalysis`、`physics`、`mathematics`。
- `Literature/Analysis/Analysis.base` 是唯一 Analysis 导航，内含 9 个视图。
- Agent 能力恰好由 7 个 Skills 提供：`paper-qa`、`full-read`、`passage-qa`、`figure-qa`、`compare-papers`、`literature-review`、`concept-learning`。

V3 不再创建或维护 Evidence、Coverage、Uncertainty、Analysis index、Topic、Theory 或 Analysis 模板。`Literature/index.md` 与 `Literature/Literature.base` 属于保留的 V2 文献资产，不是已删除的 Analysis index。

## 快速安装

要求 Python 3.10+。Zotero 导入需要正在运行且已启用本地 API 的 Zotero Desktop；MinerU 仅在解析全文时需要。

任选一种安装方式：

```powershell
# pip
python -m pip install "zotero-obsidian-mcp==3.0.0"

# pipx
pipx install "zotero-obsidian-mcp==3.0.0"

# uv tool
uv tool install "zotero-obsidian-mcp==3.0.0"
```

无需持久安装也可用 uvx：

```powershell
uvx --from "zotero-obsidian-mcp==3.0.0" obsidian-vault-mcp doctor --vault-path "<VAULT_PATH>"
```

从 MCP Registry 安装时，搜索：

```text
io.github.luffysolution-svg/obsidian-vault-mcp
```

等价的 stdio 启动配置是：

```json
{
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
```

不要把机器绝对路径、Zotero 数据或 MinerU token 提交到仓库。

## 初始化与首次导入

```powershell
obsidian-vault-mcp config init --vault-path "<VAULT_PATH>" --dry-run
obsidian-vault-mcp config init --vault-path "<VAULT_PATH>"
obsidian-vault-mcp doctor --vault-path "<VAULT_PATH>"
obsidian-vault-mcp import item ABCD1234 --vault-path "<VAULT_PATH>" --dry-run
obsidian-vault-mcp import item ABCD1234 --vault-path "<VAULT_PATH>"
```

所有写操作都应先 dry-run。`doctor` 的配置状态不能替代对 Zotero 与 MinerU 子状态的检查。

如果 Zotero PDF 使用“链接到文件”，请把 Zotero 的“链接附件基础目录”配置为固定目录，并在 Vault 的 `.obsidian-vault-mcp.json` 中填写同一路径：

```json
{
  "zotero": {
    "linkedAttachmentBaseDir": "<ZOTERO_LINKED_ATTACHMENT_BASE_DIR>"
  }
}
```

也可在启动 CLI/MCP server 前设置 `ZOTERO_LINKED_ATTACHMENT_BASE_DIR`；非空配置值优先于环境变量。`ZOTERO_STORAGE_DIR` 只处理 Zotero 管理的 `storage:` 附件，前述配置只处理 `attachments:` 链接附件。这个本机绝对路径不得提交到仓库；越出基础目录的 `..`、盘符路径和其他不安全路径会被拒绝。

MinerU 解析：

```powershell
obsidian-vault-mcp mineru parse ABCD1234 --vault-path "<VAULT_PATH>" --dry-run
obsidian-vault-mcp mineru parse ABCD1234 --vault-path "<VAULT_PATH>"
```

每篇文献使用独立图片目录：

```text
Literature/attachment/MinerU/ABCD1234.md
Literature/attachment/MinerU/image/ABCD1234/ABCD1234-fig01.png
```

Markdown 中的链接为 `image/ABCD1234/ABCD1234-fig01.png`，移动 Vault 后仍可用。

## Analysis

五个新增 MCP 工具是：

| 工具 | 用途 |
|---|---|
| `literature_paper_read` | 按 overview、targeted 或 figures 模式读取单篇文献，不写持久状态。 |
| `literature_retrieve` | 跨文献检索有来源定位的片段；覆盖信息仅存在于本次响应。 |
| `literature_analysis_get` | 按 ID、类型或来源读取已有 Analysis。 |
| `literature_analysis_write` | 校验并事务式预览/写入 Analysis。 |
| `literature_rebuild_analysis_base` | 重建唯一的 `Analysis.base`。 |

`Analysis.base` 的 9 个视图是 Dashboard、Full Reads、Reviews、Passage Q&A、Figure Q&A、Concepts、Needs Attention、By Discipline、Recently Updated。

建议让已连接的 Agent 使用对应 Skill 完成检索、阅读、溯源和写入。直接调用工具时可用统一 JSON CLI：

```powershell
obsidian-vault-mcp call literature_paper_read --json '{"zotero_key":"ABCD1234","mode":"overview","vault_path":"<VAULT_PATH>"}'
obsidian-vault-mcp call literature_rebuild_analysis_base --json '{"vault_path":"<VAULT_PATH>","dry_run":true}'
```

## Agent、Skills 与插件

先安装 Python 包，再执行客户端安装器：

```powershell
obsidian-vault-mcp agent install codex --dry-run
obsidian-vault-mcp agent install codex
```

将 `codex` 替换为 `claude`、`opencode`、`pi`、`hermes` 或 `workbuddy` 即可。Codex 与 Claude 使用原生插件 marketplace，包含 MCP server 与 7 个 Skills；OpenCode 安装项目本地 MCP/Skills；Pi 安装薄 TypeScript Extension。Hermes 与 WorkBuddy 安装 MCP 配置，但当前没有已验证的原生 Skill 安装契约。

安装器会尽量合并而非覆盖已有配置，写前备份并执行 MCP handshake；失败时回滚本次新增状态。

`opencode`、`pi`、`hermes`、`workbuddy` 都写入项目本地配置，请在目标项目目录运行，或显式传入 `--project-dir <PROJECT_DIR>`。从 2.x 升级时，先按原安装方式精确升级 Python 包，再刷新原生插件缓存并重新运行安装器完成 handshake：

```powershell
# uv tool 用户
uv tool install --force "zotero-obsidian-mcp==3.0.0"

# pipx 用户
pipx install --force "zotero-obsidian-mcp==3.0.0"

# Codex 的 plugin add 会原子替换已安装的旧版本
codex plugin add obsidian-literature@obsidian-vault-mcp --json

# Claude Code：先刷新 marketplace，再更新插件；完成后重启 Claude Code
claude plugin marketplace update obsidian-vault-mcp
claude plugin update obsidian-literature@obsidian-vault-mcp --scope user
```

GitHub Release 中的 `obsidian-vault-mcp-3.0.0-plugins.zip` 是同一份离线 marketplace。校验 `SHA256SUMS` 后解压；全新安装执行对应的完整命令：

```powershell
codex plugin marketplace add "<EXTRACTED_DIR>" --json
codex plugin add obsidian-literature@obsidian-vault-mcp --json

claude plugin marketplace add "<EXTRACTED_DIR>" --scope user
claude plugin install obsidian-literature@obsidian-vault-mcp --scope user
```

已有同名 marketplace 时不要重新绑定到另一路径，应按升级命令处理。

## 从旧数据迁移

旧版平铺 MinerU 图片先默认预览迁移计划：

```powershell
obsidian-vault-mcp migrate mineru-images-v2-to-v3 --vault-path "<VAULT_PATH>"
```

检查 `copiedImages`、`preservedLegacyImages`、`rewrittenMarkdown`、
`missingReferencedImages` 与 `reparseZoteroKeys`；只有报告可接受时才提交：

```powershell
obsidian-vault-mcp migrate mineru-images-v2-to-v3 --vault-path "<VAULT_PATH>" --apply
```

默认安全模式会把图片复制到 `image/{zoteroKey}/` 并在同一事务中重写对应
Markdown，同时保留旧平铺图片作为兼容别名；这样即使未协调的编辑器在提交瞬间
新增旧路径引用，也不会产生断链。不确定、缺失或不安全的条目保留原位并报告。

只有确实需要清理旧平铺图片时，先停止 Obsidian、同步程序、索引器及其他所有
Vault 写入者，再显式确认离线状态：

```powershell
obsidian-vault-mcp migrate mineru-images-v2-to-v3 --vault-path "<VAULT_PATH>" --apply --cleanup-legacy --confirm-vault-offline
```

此模式把图片复制、Markdown 链接重写和旧图片清理放在同一事务中；发现其他
Vault 笔记仍引用旧路径时会阻止对应论文迁移。

旧 Analysis 迁移同样默认只生成计划：

```powershell
obsidian-vault-mcp migrate analysis-v2-to-v3 --vault-path "<VAULT_PATH>"
```

先检查报告中的迁移、跳过与人工复核项，再提交：

```powershell
obsidian-vault-mcp migrate analysis-v2-to-v3 --vault-path "<VAULT_PATH>" --apply
obsidian-vault-mcp preview <transaction-id> --vault-path "<VAULT_PATH>"
obsidian-vault-mcp rollback <transaction-id> --vault-path "<VAULT_PATH>" --dry-run
obsidian-vault-mcp rollback <transaction-id> --vault-path "<VAULT_PATH>"
```

迁移会规范化可识别的旧 Analysis、移除旧锚点并生成 `Analysis.base`；无法安全映射的 Topic/Theory 文件保留并列入人工处理，不会静默删除。

## 安全边界

- 先 dry-run，再提交；保存返回的 `transactionId`。
- 不在用户真实 Vault 上运行自动写测试。真实 Vault 只做只读校验，写入、迁移和回滚必须在隔离副本中完成。
- 隔离前后对真实 Vault 建立文件清单/哈希，并排除锁、staging 与历史备份。
- MinerU 模式会把选中的 PDF 发往外部服务；使用前确认授权与组织政策。
- 非 stdio MCP 传输必须置于可信认证边界之后。

## 贡献者

感谢 [方珸 / Lym Fang (@LimFang)](https://github.com/LimFang) 发现 Zotero 链接附件兼容需求并在 [PR #6](https://github.com/luffysolution-svg/obsidian-vault-mcp/pull/6) 中提出原始实现；该方案经 V2 架构移植后由 [PR #8](https://github.com/luffysolution-svg/obsidian-vault-mcp/pull/8) 落地，并由 V3 继续保留。完整记录见 [CONTRIBUTORS.md](https://github.com/luffysolution-svg/obsidian-vault-mcp/blob/main/CONTRIBUTORS.md)。

详细安装、完整 31 工具表、迁移与端到端验收见[完整教程](https://github.com/luffysolution-svg/obsidian-vault-mcp/blob/main/docs/index.md)。架构、契约、测试和发布流程见[开发文档](https://github.com/luffysolution-svg/obsidian-vault-mcp/blob/main/DEVELOPMENT.md)。
