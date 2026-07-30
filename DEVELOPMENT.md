# Obsidian Vault MCP 3.0.1 开发文档

[English](./DEVELOPMENT.en.md) · [README](./README.md) · [安装教程](./docs/index.md) · [更新日志](./CHANGELOG.md)

本文定义正式架构、代码边界、测试矩阵和发布流程。Python 包名为 `zotero-obsidian-mcp`，CLI 为 `obsidian-vault-mcp`，MCP Registry 名称为 `io.github.luffysolution-svg/obsidian-vault-mcp`。

## 1. 架构原则

1. Zotero 父条目 `zoteroKey` 是稳定身份。
2. Vault 可见路径必须相对、可移植并使用 `/`。
3. 读取工具不得产生隐藏写操作。
4. 写操作必须支持 dry-run、事务、备份、原子替换和冲突策略。
5. MCP Tools 提供确定性能力；Skills 提供科研工作流。
6. Analysis 只有五种类型和一个 `Analysis.base`。
7. 包、运行时、Registry、插件、Pi、Tag、Release 和 PyPI 版本必须一致。

## 2. 目录结构

```text
src/obsidian_vault_mcp/
├─ adapters/                 # Zotero、MinerU、Obsidian、Vault I/O
├─ application/              # 用例与事务编排
├─ config/                   # 默认值、加载器、Schema
├─ domain/                   # 身份、路径、Analysis 与领域模型
├─ interfaces/
│  ├─ cli/
│  ├─ mcp/                   # 31 个 MCP Tools
│  └─ agent_install/
└─ resources/agent_marketplace/
   └─ plugins/obsidian-literature/
      ├─ .mcp.json
      ├─ .codex-plugin/
      ├─ .claude-plugin/
      └─ skills/             # 7 个 Skills
```

依赖方向：`interfaces → application → domain`，适配器实现外部 I/O。接口层不得复制适配器逻辑。

## 3. 正式数据模型

```text
Literature/{zoteroKey}.md
Literature/attachment/{zoteroKey}.pdf
Literature/attachment/MinerU/{zoteroKey}.md
Literature/attachment/MinerU/image/{zoteroKey}/{zoteroKey}-figNN.ext
```

Analysis 类型：`full_read`、`literature_review`、`passage_qa`、`figure_qa`、`concept`。

状态：`draft`、`ready`、`reviewed`、`needs_update`、`archived`。

学科 Profile：`general`、`medicine`、`chemistry`、`materials`、`catalysis`、`physics`、`mathematics`。

唯一 Analysis 数据库：`Literature/Analysis/Analysis.base`。

## 4. MCP 工具契约

正式工具面固定为 31 个：

| 分组 | 数量 |
|---|---:|
| 版本、系统与配置 | 5 |
| Zotero | 6 |
| 导入与同步 | 4 |
| MinerU | 3 |
| 导航与校验 | 3 |
| Analysis | 5 |
| Wiki | 3 |
| 事务 | 2 |

`literature_version` 是只读契约工具，返回版本、工具数、Skills 数和 Analysis 类型。

每个工具必须显式注册、包含 docstring、声明 MCP 行为注解、返回 JSON 可序列化结果，并通过精确工具面测试。

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

每个 Skill 以 `SKILL.md` 为入口，通过 `references/` 定义输出和学科规则，只调用正式 MCP Tools，不持有独立数据库，写入前必须去重和 dry-run。

## 6. 本地开发

```bash
git clone https://github.com/luffysolution-svg/obsidian-vault-mcp.git
cd obsidian-vault-mcp
uv sync --locked --all-extras
uv run obsidian-vault-mcp --help
```

```bash
uv run python -m ruff check .
uv run python -m pytest
uv run python scripts/verify_release.py

cd adapters/pi
npm ci --no-audit --no-fund
npm run check
```

自动写测试必须使用临时或隔离 Vault。

## 7. 测试矩阵

| 层级 | 重点 |
|---|---|
| Unit | 身份、路径、解析、Analysis、事务、安装器 |
| Contract | 31 工具、7 Skills、客户端配置、插件 manifests、Schema |
| Repository | 发布卫生、版本一致性、可重复构建、敏感信息扫描 |
| Wheel smoke | 独立安装、依赖检查、CLI、31 工具、7 Skills、stdio handshake |
| Platform CI | Ubuntu、Windows、macOS；Python 3.10–3.13 |

## 8. 版本一致性

以下位置必须使用 `3.0.1`：

- `pyproject.toml`
- `src/obsidian_vault_mcp/__init__.py`
- `server.json`
- Codex / Claude plugin manifests 与 marketplace metadata
- `adapters/pi/package.json` 和 `package-lock.json`
- Git Tag `v3.0.1`
- GitHub Release
- PyPI

配置文件中的 `schemaVersion` 是独立的数据格式版本，不与软件版本号绑定。

## 9. 发布流程

1. 在 `main` 完成代码、文档和版本更新。
2. 运行全部测试、Ruff、Pi 检查和 `scripts/verify_release.py`。
3. 确认工作区干净。
4. 创建并推送 Tag：

```bash
git tag -a v3.0.1 -m "Obsidian Vault MCP 3.0.1"
git push origin v3.0.1
```

5. `.github/workflows/release.yml` 验证 Tag 身份及其位于 `main`。
6. 构建并验证 wheel、sdist、插件 ZIP 和 `SHA256SUMS`。
7. 执行 wheel smoke、31 工具检查、7 Skills 检查和 MCP handshake。
8. 依次发布 PyPI、MCP Registry 和 GitHub Release。

正式产物：

```text
zotero_obsidian_mcp-3.0.1-py3-none-any.whl
zotero_obsidian_mcp-3.0.1.tar.gz
obsidian-vault-mcp-3.0.1-plugins.zip
SHA256SUMS
```

已发布版本不可覆盖；修复必须发布新的语义化版本。

## 10. 发布恢复规则

发布工作流使用 workflow marker 记录每个外部发布阶段。重新运行时，只允许恢复同一 Tag 对应的 draft GitHub Release，并在上传前重新核对全部 `SHA256`。

- PyPI 和 MCP Registry 已存在相同版本时，只验证内容与状态，不重复上传。
- GitHub draft 可以继续补齐产物，但必须复用同一 Tag 和同一校验和。
- 已公开或已启用 immutable releases 的版本，禁止删除或覆盖。
- 任何产物、Tag 或校验和不一致都必须中止，并改用新的语义化版本。

## 11. 发布前清单

- [ ] 31 个 MCP Tools 精确匹配契约。
- [ ] 7 个 Skills 和 references 完整。
- [ ] README、教程、开发文档与 CLI 一致。
- [ ] 效果截图和贡献者记录可访问。
- [ ] 安装命令固定到 `3.0.1`。
- [ ] Tag、PyPI、MCP Registry、插件与 Pi 版本一致。
- [ ] wheel、sdist、插件 ZIP 和校验和通过验证。
- [ ] 无凭据或本机绝对路径。

## 12. 安全要求

- 默认使用 `stdio`。
- 网络传输必须位于可信认证和访问控制之后。
- 外部解析服务只处理已获授权的 PDF。
- token 只存放在受保护的环境或凭据存储中。
- Vault 写入必须经过路径检查、锁和事务。
