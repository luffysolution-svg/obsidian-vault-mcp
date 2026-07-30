---
layout: default
title: Development and contribution
lang: en
---
# Development and contribution

GitHub Pages uses legacy Pages builds from `main/docs`; there is no separate Pages Actions workflow. A commit to `main` builds this Jekyll site. Do not maintain a second documentation artifact.

```bash
uv sync --locked --all-extras
uv run python -m ruff check .
uv run python -m pytest
uv run python scripts/verify_release.py
bundle exec jekyll build --source docs
```

Read root `DEVELOPMENT.en.md` and `AGENTS.md` before contributing. The public tool table is generated from the registry and tests guard links, images, counts, and removed-feature wording.
