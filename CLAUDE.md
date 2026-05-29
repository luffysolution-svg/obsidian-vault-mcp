# CLAUDE.md

## Skills 目录同步规则

项目中有**三套 skills 目录**，必须保持同步：

| 目录 | 用途 |
|------|------|
| `skills/<skill-name>/SKILL.md` | 权威来源，用于 GitHub Release zip 和本地使用 |
| `scripts/obsidian_vault_mcp/skills/<skill-name>/SKILL.md` | 打进 PyPI wheel 的那份（`package-data`） |
| `.claude/skills/<skill-name>.md` | Claude Code 用的精简摘要版（bullet points） |

**每次修改 `skills/` 下任何 SKILL.md，必须同步另外两处。**

```bash
# 批量同步到 PyPI 包目录（完整内容）
for skill in obsidian-vault obsidian-zotero obsidian-mineru obsidian-views obsidian-cli obsidian-graph; do
  cp skills/$skill/SKILL.md scripts/obsidian_vault_mcp/skills/$skill/SKILL.md
done
```

`.claude/skills/<name>.md` 是精简摘要，需要人工维护（不是机械复制，保持 bullet-point 风格）。

新增 skill 目录时，三处都要创建对应文件。

## 版本号同步规则

发版时以下四个文件的 `version` 字段必须一致：

- `pyproject.toml`
- `.codex-plugin/plugin.json`
- `.claude-plugin/plugin.json`
- `scripts/obsidian_vault_mcp/skills/` 通过 wheel 自动携带，无单独版本字段

## PyPI 发布注意

PyPI 不允许重复上传同一版本。修改了 skills 内容后必须升版本号再发布。
