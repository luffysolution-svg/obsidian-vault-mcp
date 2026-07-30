---
layout: default
title: 开发与贡献
lang: zh-CN
---
# 开发与贡献

GitHub Pages 使用 legacy Pages 构建，发布来源是 `main/docs`，没有独立 Pages Actions workflow。提交到 `main` 后由 GitHub Pages 构建此 Jekyll 站点；不要维护第二套文档产物。

本地验证：

```bash
uv sync --locked --all-extras
uv run python -m ruff check .
uv run python -m pytest
uv run python scripts/verify_release.py
bundle exec jekyll build --source docs
```

贡献前阅读仓库根目录的 `DEVELOPMENT.md` 与 `AGENTS.md`。公开文档的工具表由注册表生成，并由测试检查链接、图片、计数和已删除功能文案。
