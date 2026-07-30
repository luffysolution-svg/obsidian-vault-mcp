# Repository Agent Instructions

## Production contract

This repository implements a local Zotero → MinerU → Obsidian literature workflow. Preserve these invariants:

- A Zotero parent item is permanently identified by `zoteroKey`.
- One parent item maps to one main note, normally `Literature/{zoteroKey}.md`.
- Vault-visible paths are relative, portable, and use `/` separators.
- MinerU output uses `Literature/attachment/MinerU/{zoteroKey}.md` and `image/{zoteroKey}/{zoteroKey}-figNN.ext`.
- Analysis supports only `full_read`, `literature_review`, `passage_qa`, `figure_qa`, and `concept`.
- `Literature/Analysis/Analysis.base` is the only Analysis database.
- The public MCP surface contains exactly 31 tools, including the read-only `literature_version` contract tool.
- The plugin distributes exactly 7 Skills: `paper-qa`, `full-read`, `passage-qa`, `figure-qa`, `compare-papers`, `literature-review`, and `concept-learning`.
- Read operations must not perform hidden writes.
- Writes must support dry-run, path checks, locks, backups, transactions, atomic replacement, and rollback where applicable.
- Never hard-code machine-local paths, Vault data, tokens, or credentials.
- Keep package, runtime, Registry, plugin, Pi, Tag, GitHub Release, and PyPI versions synchronized.

## Required checks

```bash
uv sync --locked --all-extras
uv run python -m ruff check .
uv run python -m pytest
uv run python scripts/verify_release.py

cd adapters/pi
npm ci --no-audit --no-fund
npm run check
```

Use temporary or isolated Vaults for automated write tests. Do not modify a user's active Vault during testing.
