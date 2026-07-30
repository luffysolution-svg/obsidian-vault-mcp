# Obsidian Vault MCP 3.0.0 开发文档

[English](./DEVELOPMENT.en.md) · [README](./README.md) · [安装教程](./docs/index.md) · [更新日志](./CHANGELOG.md)

本文定义正式架构、代码边界、测试矩阵和发布流程。Python 包名为 `zotero-obsidian-mcp`，CLI 为 `obsidian-vault-mcp`，MCP Registry 名称为 `io.github.luffysolution-svg/obsidian-vault-mcp`。

## 1. 架构原则

1. Zotero 父条目 `zoteroKey` 是文献稳定身份。
2. 所有 Vault 路径使用相对路径和 `/` 分隔符。
3. 读取工具不得产生隐藏写操作。
4. 写操作必须支持 dry-run、事务、备份、原子替换和冲突策略。
5. MCP Tools 提供确定性能力；Skills 提供研究工作流，不复制业务逻辑。
6. Analysis 只有五种类型和一个 `Analysis.base`。
7. 版本 `3.0.0` 必须在所有发行元数据中一致。

## 2. 目录结构

```text
src/obsidian_vault_mcp/
├─ adapters/                 # Zotero、MinerU、Obsidian、Vault I/O
├─ application/              # 用例与事务编排
├─ config/                   # 默认值、加载器、Schema
├─ domain/                   # 身份、路径、Analysis 与领域模型
├─ interfaces/
│  ├─ cli/                   # CLI
│  ├─ mcp/                   # 30 个 MCP Tools 与 Server
│  └─ agent_install/         # 六类客户端安装器
└─ resources/agent_marketplace/
   └─ plugins/obsidian-literature/
      ├─ .mcp.json
      ├─ .codex-plugin/
      ├─ .claude-plugin/
      └─ skills/             # 7 个 Skills
```

依赖方向：

```text
interfaces → application → domain
      ↓            ↓
adapters ←─────────┘
```

接口层不得直接实现文件系统、HTTP 或解析逻辑。

## 3. 正式数据模型

### 文献资产

```text
Literature/{zoteroKey}.md
Literature/attachment/{zoteroKey}.pdf
Literature/attachment/MinerU/{zoteroKey}.md
Literature/attachment/MinerU/image/{zoteroKey}/{zoteroKey}-figNN.ext
```

### Analysis

类型：

```text
full_read
literature_review
passage_qa
figure_qa
concept
```

状态：

```text
draft
ready
reviewed
needs_update
archived
```

学科 Profile：

```text
general
medicine
chemistry
materials
catalysis
physics
mathematics
```

统一数据库为 `Literature/Analysis/Analysis.base`。

## 4. MCP 工具契约

正式工具面固定为 30 个：

| 分组 | 数量 |
|---|---:|
| 系统与配置 | 4 |
| Zotero | 6 |
| 导入与同步 | 4 |
| MinerU | 3 |
| 文献导航与校验 | 3 |
| Analysis | 5 |
| Wiki | 3 |
| 事务 | 2 |

每个工具必须：

- 显式注册；
- 有非空 docstring；
- 声明 `readOnlyHint`、`destructiveHint`、`idempotentHint` 和 `openWorldHint`；
- 返回 JSON 可序列化结果；
- 不通过名称推断或动态扫描扩展工具面。

## 5. Skills 契约

发行包只包含：

```text
paper-qa
full-read
passage-qa
figure-qa
compare-papers
literature-review
concept-learning
```

每个 Skill：

- 以 `SKILL.md` 为入口；
- 通过 `references/` 定义输出与学科规则；
- 只调用正式 MCP Tools；
- 不持有独立数据库；
- 保留来源定位，区分事实、作者解释与 Agent 推断；
- 写入前先去重并 dry-run。

## 6. 本地开发

```bash
git clone https://github.com/luffysolution-svg/obsidian-vault-mcp.git
cd obsidian-vault-mcp
uv sync --locked --all-extras
uv run obsidian-vault-mcp --help
```

常用检查：

```bash
uv run python -m ruff check .
uv run python -m pytest
uv run python scripts/verify_release.py

cd adapters/pi
npm ci --no-audit --no-fund
npm run check
```

不得在用户真实 Vault 上运行自动写测试。集成写测必须使用临时或隔离 Vault。

## 7. 测试矩阵

| 层级 | 重点 |
|---|---|
| Unit | 身份、路径、解析、Analysis、事务、安装器 |
| Contract | 客户端配置、插件 manifests、MCP 注册、Schema |
| Repository | 发布卫生、版本一致性、可重复构建、敏感信息扫描 |
| Wheel smoke | 独立环境安装、依赖检查、CLI、30 工具、7 Skills、stdio handshake |
| Platform CI | Ubuntu、Windows、macOS；Python 3.10–3.13 |

新增工具、Skill、配置字段或发行资产时，必须同步更新相应契约测试。

## 8. 发行版本一致性

以下位置必须使用同一个版本：

- `pyproject.toml`
- `src/obsidian_vault_mcp/__init__.py`
- `server.json` 及其 PyPI package metadata
- Codex plugin manifest
- Claude plugin manifest 与 marketplace metadata
- `adapters/pi/package.json`
- `adapters/pi/package-lock.json`
- Git Tag `v3.0.0`
- GitHub Release
- PyPI

`server.json` 必须保留 MCP Registry 所有权标记对应的 README 注释。

## 9. 正式发布流程

1. 在 `main` 上完成所有代码、文档和版本更新。
2. 运行全部测试、Ruff、Pi 类型检查和 `scripts/verify_release.py`。
3. 确认工作区无未跟踪或未提交文件。
4. 在发布提交创建 Tag：

```bash
git tag -a v3.0.0 -m "Obsidian Vault MCP 3.0.0"
git push origin v3.0.0
```

5. Tag 触发 `.github/workflows/release.yml`。
6. Workflow 检查 Tag 与 `main` 提交身份，构建 wheel、sdist 和插件 ZIP。
7. Workflow 执行 artifact smoke、MCP handshake、可重复构建和 SHA-256 校验。
8. Workflow 按顺序发布 PyPI、MCP Registry 和 GitHub Release。

正式产物：

```text
zotero_obsidian_mcp-3.0.0-py3-none-any.whl
zotero_obsidian_mcp-3.0.0.tar.gz
obsidian-vault-mcp-3.0.0-plugins.zip
SHA256SUMS
```

已发布的版本和产物不可覆盖；修复必须使用新的语义化版本。

## 10. 发布前清单

- [ ] 30 个 MCP Tools 精确匹配契约。
- [ ] 7 个 Skills 及 references 完整。
- [ ] README、教程、开发文档与 CLI 一致。
- [ ] 效果截图和贡献者记录可访问。
- [ ] 所有安装命令固定到 `3.0.0`。
- [ ] Tag、PyPI、MCP Registry、插件与 Pi 版本一致。
- [ ] wheel、sdist、插件 ZIP 和校验和通过验证。
- [ ] 仓库、发行包和文档中无凭据或本机绝对路径。

## 11. 安全要求

- 默认使用 `stdio`。
- 网络传输必须位于可信认证和访问控制之后。
- 外部解析服务只处理已获授权的 PDF。
- token 只存放在受保护的环境或工具凭据存储中。
- Vault 写入必须经过路径边界检查、锁和事务。
