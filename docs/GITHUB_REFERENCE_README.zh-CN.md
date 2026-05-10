# Obsidian Vault MCP 插件

面向 Codex 的开源 MCP 插件，用于把本地 Obsidian vault 维护成持久双链知识库。

## 它能做什么

`obsidian-vault` 可以帮助 Codex 安全地维护本地 Obsidian vault，包括：

- 列出、搜索、读取、写入 vault 文件。
- 编辑 YAML frontmatter/properties。
- 批量编辑事务：预览、应用、vault 内备份和回滚。
- 创建 wiki 双链。
- 基于 backlinks、aliases、inline tags、unresolved links、ambiguous links 构建图谱。
- 写入前 dry-run diff 预览。
- vault lint：图谱健康、`index.md`/`log.md`、重复 key、frontmatter 一致性。
- 校验 frontmatter、Canvas JSON 和 Base YAML。
- 提出图谱改进建议：未解析链接、反向链接、重复页面、Markdown 链接、附件建模。
- Karpathy 风格 wiki 工作流：source 导入、index 刷新、日志追加。
- 从 BibTeX、参考文献元数据、MinerU Markdown 和 PDF 附件导入文献。
- 可选调用 MinerU CLI 解析文档，再导入 Obsidian。
- 直接访问 Zotero Desktop 本地 API，支持搜索、元数据、子笔记、标注、PDF 附件、PDF 文本和一键导入。
- vault-local defaults：输出目录、模板目录、默认模板、Zotero 附件命名。
- 发现 Obsidian Templates、Templater 和插件默认模板。
- `--doctor` 就绪检查和只读 smoke 检查脚本。
- 创建 JSON Canvas，并从 vault wikilinks 自动生成知识图。
- 创建 Obsidian Bases 和 Dataview 查询笔记。
- 包装本地官方 Obsidian CLI。

## 文档

- 中文首页：`docs/index.md`
- 中文 README：`README.zh-CN.md`
- 安装指南：`docs/INSTALL.zh-CN.md`
- 配置指南：`docs/CONFIGURATION.zh-CN.md`
- 部署指南：`docs/DEPLOYMENT.zh-CN.md`
- 隐私说明：`docs/PRIVACY.zh-CN.md`
- 参考与致谢：`docs/REFERENCES.zh-CN.md`

英文文档也保留在同一目录。

## 包结构

```text
obsidian-vault-mcp/
  .codex-plugin/plugin.json
  .github/workflows/
  .mcp.json
  .gitignore
  LICENSE
  pyproject.toml
  README.md
  README.zh-CN.md
  requirements.txt
  docs/
  scripts/build_release.ps1
  scripts/obsidian_vault_mcp.py
  scripts/smoke_integrations.py
  scripts/obsidian_vault_mcp/
    __init__.py
    cli.py
    common.py
    helpers.py
    server.py
    tools.py
  skills/obsidian-vault/SKILL.md
  tests/
```

## 安装

```bash
python -m pip install -r requirements.txt
```

开发模式：

```bash
python -m pip install -e ".[dev]"
obsidian-vault-mcp --doctor --doctor-format text --vault "path/to/vault"
```

之后将本目录注册为 Codex 本地插件，或通过 Codex 本地 marketplace 暴露。默认保持 `.mcp.json` 的 `OBSIDIAN_VAULT_PATH=auto`。

## 发布检查

```bash
python -m ruff check .
python -m unittest discover -s tests
python -m py_compile scripts/obsidian_vault_mcp.py scripts/obsidian_vault_mcp/cli.py scripts/obsidian_vault_mcp/common.py scripts/obsidian_vault_mcp/helpers.py scripts/obsidian_vault_mcp/server.py scripts/obsidian_vault_mcp/tools.py
python scripts/obsidian_vault_mcp.py --doctor --doctor-format text --vault "path/to/vault"
python scripts/smoke_integrations.py --vault "path/to/vault"
```

构建 release zip：

```powershell
./scripts/build_release.ps1
```

## 可移植性说明

- 包中不内置本地绝对 vault 路径。
- 文件写入被限制在解析后的 vault 根目录内。
- 非 vault 文件夹默认拒绝，除非设置 `OBSIDIAN_ALLOW_NON_VAULT=true`。
- 已有文件需要 `overwrite=true` 才会替换。
- Zotero 访问使用用户自己的本地 Zotero Desktop API。
- Obsidian CLI wrapper 的 `vault` 参数使用 Obsidian vault 名称；直接文件工具使用 `vault_path` 文件系统路径。
- smoke 脚本只做 dry-run 写入，不应修改真实 vault。
- MinerU CLI 和 MinerU MCP 是可选外部工具，本插件不会自动安装。
