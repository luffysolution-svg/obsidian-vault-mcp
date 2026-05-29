# 部署与发布指南

本插件可以作为普通开源仓库发布。仓库根目录就是插件根目录。

## 仓库结构

```text
obsidian-vault-mcp/
  .codex-plugin/plugin.json
  .claude-plugin/plugin.json
  .mcp.json
  opencode.json
  .gitignore
  LICENSE
  pyproject.toml
  README.md
  README.zh-CN.md
  requirements.txt
  docs/
  scripts/obsidian_vault_mcp.py
  scripts/smoke_integrations.py
  scripts/obsidian_vault_mcp/
    __init__.py
    cli.py
    common.py
    helpers.py
    server.py
    tools.py
  skills/
    obsidian-vault/SKILL.md
    obsidian-zotero/SKILL.md
    obsidian-mineru/SKILL.md
    obsidian-views/SKILL.md
    obsidian-cli/SKILL.md
  tests/
```

不要发布本地 vault 文件、生成的备份、虚拟环境、`__pycache__` 或会写入真实 vault 的临时脚本。

`.codex-plugin/plugin.json` 是 Codex 插件清单。`.claude-plugin/plugin.json` 是 Claude Code 插件清单。`opencode.json` 是 OpenCode 的 MCP server 配置。三个文件都应提交，方便各客户端用户直接连接。

`scripts/obsidian_vault_mcp.py` 是保留的兼容入口，与实现包并列存放。`pyproject.toml` 用于 editable install 和 `obsidian-vault-mcp` 控制台命令。`scripts/smoke_integrations.py` 是发布前使用的只读集成检查脚本。

## 本地插件放置

开发时推荐把插件源目录放在：

```text
$REPO_ROOT/plugins/obsidian-vault
```

并通过：

```text
$REPO_ROOT/.agents/plugins/marketplace.json
```

暴露给 Codex。

个人测试可放在：

```text
~/.codex/plugins/obsidian-vault
```

并通过：

```text
~/.agents/plugins/marketplace.json
```

暴露。

Codex 会把 marketplace 插件安装到：

```text
~/.codex/plugins/cache/<marketplace>/<plugin>/<version>/
```

并加载缓存副本。修改插件后，需要更新 marketplace 指向的源目录并重启 Codex。

只有 Codex 清单应放在 `.codex-plugin/` 下。Claude Code 清单位于 `.claude-plugin/`。`skills/`、`.mcp.json`、`opencode.json`、`docs/`、`scripts/` 和 assets 都应位于插件根目录。

## 发布前检查

1. 确认 `.codex-plugin/plugin.json` 中的 `repository`、`homepage`、`websiteURL`、`privacyPolicyURL`、`termsOfServiceURL` 正确。确认 `.claude-plugin/plugin.json` 中的对应字段也保持一致（供 Claude Code 使用）。
2. 保持 `.mcp.json` 可移植：使用 `obsidian-vault-mcp` 入口命令，默认 `OBSIDIAN_VAULT_PATH=auto`。用户需先执行 `pip install -e .` 再连接任何 MCP 客户端。
3. 安装开发依赖并运行检查：

```bash
python -m pip install -e ".[dev]"
python -m ruff check .
python -m unittest discover -s tests
python -m py_compile scripts/obsidian_vault_mcp.py scripts/obsidian_vault_mcp/cli.py scripts/obsidian_vault_mcp/common.py scripts/obsidian_vault_mcp/helpers.py scripts/obsidian_vault_mcp/server.py scripts/obsidian_vault_mcp/tools.py
python scripts/obsidian_vault_mcp.py --doctor --doctor-format text --vault path/to/test-vault
```

4. 使用干净临时 vault 和包含非 ASCII 字符路径的真实 vault 测试。
5. 打开 Obsidian 和 Zotero Desktop 后运行：

```bash
python scripts/smoke_integrations.py --vault path/to/test-vault
```

Zotero 与 Obsidian CLI 失败会作为 warning。建议在这些集成可用的环境中完整执行一次集成检查后再发布。

6. 构建 release zip：

```powershell
./scripts/build_release.ps1
```

## GitHub CLI 发布流程

```powershell
Set-Location "path/to/obsidian-vault-mcp"
git init
git add .
git commit -m "publish obsidian vault mcp plugin"
gh repo create obsidian-vault-mcp --public --source . --remote origin --push
```

如果 GitHub CLI 不可用，先在 GitHub 创建仓库，再运行：

```powershell
Set-Location "path/to/obsidian-vault-mcp"
git init
git add .
git commit -m "publish obsidian vault mcp plugin"
git branch -M main
git remote add origin https://github.com/luffysolution-svg/obsidian-vault-mcp.git
git push -u origin main
```

## GitHub Pages

本仓库使用 `docs/` 作为 GitHub Pages 源目录。中文首页是：

```text
docs/index.md
```

启用 Pages：

```powershell
gh api -X POST repos/luffysolution-svg/obsidian-vault-mcp/pages `
  -f source[branch]=main `
  -f source[path]=/docs
```

如果 Pages 已存在，用：

```powershell
gh api -X PUT repos/luffysolution-svg/obsidian-vault-mcp/pages `
  -f source[branch]=main `
  -f source[path]=/docs
```

发布后访问：

```text
https://luffysolution-svg.github.io/obsidian-vault-mcp/
```

## 发布检查清单

- `python -m ruff check .` 通过。
- `python -m unittest discover -s tests` 通过。
- `python -m py_compile scripts/obsidian_vault_mcp.py scripts/obsidian_vault_mcp/cli.py scripts/obsidian_vault_mcp/common.py scripts/obsidian_vault_mcp/helpers.py scripts/obsidian_vault_mcp/server.py scripts/obsidian_vault_mcp/tools.py` 通过。
- `python scripts/obsidian_vault_mcp.py --doctor --doctor-format text --vault path/to/test-vault` 通过核心检查。
- `python scripts/smoke_integrations.py --vault path/to/test-vault` 没有必需检查失败。
- `./scripts/build_release.ps1` 生成 release zip，并包含 `pyproject.toml`、兼容入口、实现包、smoke 脚本、docs、tests、skills 套件。
- `docs/PRIVACY.zh-CN.md` 与 `docs/PRIVACY.md` 描述一致。
- `docs/TECHNICAL_GUIDE.md` 覆盖 Obsidian CLI、Codex skills/plugin、Claude Code plugin、OpenCode MCP、Zotero、MinerU 配置细节。
- `LICENSE` 存在。
- 没有提交个人 vault 路径、用户名、缓存路径、Zotero 存储路径或 API token。
- 示例截图经过脱敏。
- 从零克隆后可直接执行 `python -m pip install -e ".[dev]"`。
- MinerU 相关测试使用模拟（mock），无需真实的 MinerU API token。
