# CLAUDE.md

## Skills 目录同步规则

项目中有**两套 skills 目录**，必须保持同步：

| 目录 | 用途 |
|------|------|
| `skills/<skill-name>/SKILL.md` | 顶层目录，用于 GitHub Release zip 和本地使用 |
| `scripts/obsidian_vault_mcp/skills/<skill-name>/SKILL.md` | 打进 PyPI wheel 的那份（`package-data`） |

**每次修改 `skills/` 下任何 SKILL.md，必须同步到 `scripts/obsidian_vault_mcp/skills/` 对应文件。**

```bash
# 批量同步所有 skill 文件
for skill in obsidian-vault obsidian-zotero obsidian-mineru obsidian-views obsidian-cli obsidian-graph; do
  cp skills/$skill/SKILL.md scripts/obsidian_vault_mcp/skills/$skill/SKILL.md
done
```

新增 skill 目录时，也要在 `scripts/obsidian_vault_mcp/skills/` 下创建对应目录。

## 版本号同步规则

发版时以下四个文件的 `version` 字段必须一致：

- `pyproject.toml`
- `.codex-plugin/plugin.json`
- `.claude-plugin/plugin.json`
- `scripts/obsidian_vault_mcp/skills/` 通过 wheel 自动携带，无单独版本字段

## PyPI 发布注意

PyPI 不允许重复上传同一版本。修改了 skills 内容后必须升版本号再发布。
