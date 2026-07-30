# Repository Agent Instructions

## V3 repository contract

This repository implements a local Zotero → MinerU → Obsidian literature pipeline. Keep every change consistent with these invariants:

- A Zotero parent item is identified permanently by `zoteroKey`.
- One parent item maps to one main note, normally `Literature/{zoteroKey}.md`.
- User-visible files contain vault-relative paths with `/` separators. Source machine paths may appear only in hidden state.
- Managed frontmatter is deterministic, omits empty values, and preserves unknown user fields.
- User-authored Markdown outside managed markers is never overwritten.
- Every write supports preview, locking, staging, backup, atomic replacement, and rollback.
- The vault has one configuration file: `.obsidian-vault-mcp.json` with `schemaVersion: 2`.
- The supported MCP surface contains the 26 stable V2 tools plus the five V3 Analysis tools: `paper_read`, `retrieve`, `analysis_get`, `analysis_write`, and `rebuild_analysis_base`.
- Codex and Claude use the native marketplace plugin; OpenCode receives project-local MCP plus seven managed Skills; Pi uses the thin TypeScript Extension; Hermes and WorkBuddy receive MCP configuration only.
- `src/obsidian_vault_mcp/resources/agent_marketplace/` is the single canonical marketplace and Skill source. Do not add mirrored agent-instruction directories or synchronization scripts.
- Keep `AGENTS.md` and `CLAUDE.md` byte-identical.

## Analysis contract

- The five Analysis types are `full_read`, `literature_review`, `passage_qa`, `figure_qa`, and `concept`.
- Status is one of `draft`, `ready`, `reviewed`, `needs_update`, or `archived`.
- Profile is one of `general`, `medicine`, `chemistry`, `materials`, `catalysis`, `physics`, or `mathematics`.
- Analysis IDs and filenames are stable. Managed metadata and body blocks may be refreshed; user-authored text outside managed markers is preserved.
- `Literature/Analysis/Analysis.base` is the only generated Analysis catalog and contains the nine canonical views.
- MinerU Markdown remains `Literature/attachment/MinerU/{zoteroKey}.md`. Its images are stored below `Literature/attachment/MinerU/image/{zoteroKey}/` and linked as `image/{zoteroKey}/{zoteroKey}-figNN.ext`.
- Do not restore Evidence, Coverage, Uncertainty, Analysis index, Topic/Theory synthesis, analysis templates, `^ev-*` anchors, `[[evidence:*]]`, or `[[asset:*]]`.
- The packaged agent marketplace contains exactly seven skills: `paper-qa`, `full-read`, `passage-qa`, `figure-qa`, `compare-papers`, `literature-review`, and `concept-learning`.

## Architecture boundaries

Production Python code lives under `src/obsidian_vault_mcp/`:

- `domain/`: identities, models, path rules, frontmatter, and domain errors.
- `application/`: import, sync, MinerU, Analysis, index/base, wiki, migration, and transaction orchestration.
- `adapters/`: Zotero, MinerU, vault filesystem, and Obsidian rendering.
- `interfaces/`: CLI, MCP, and agent configuration installers.
- `config/`: defaults, schema validation, and loading.

Business behavior belongs in the domain or application layer. CLI and MCP code only parse input, invoke an application service, and serialize output. Avoid wildcard imports, dynamic namespace injection, and duplicate business implementations.

## Change discipline

- Make the smallest change that satisfies the requested behavior.
- Do not reformat or refactor unrelated files.
- Preserve existing user changes in a dirty worktree.
- Add a failing regression test before fixing a bug when practical.
- Use vault-relative fixtures, including paths with spaces and non-ASCII characters.
- Tests that write files must use disposable vaults and must not contact a real Zotero library or MinerU service.
- Production-vault acceptance is read-only. Hash protected inputs before and after; run migration and rollback tests only on an isolated copy.

## Pi Extension synchronization

`adapters/pi/index.ts` is the distributable Pi package source. The wheel carries the same installer resource at:

```text
src/obsidian_vault_mcp/interfaces/agent_install/pi_extension.ts
```

These two files must remain byte-identical. The Extension must call:

```text
obsidian-vault-mcp call <tool> --json <json>
```

Use `execFile` or `spawn` without a shell and retain cancellation, timeout, output-size, and JSON-error handling.

## Verification

Run the complete repository checks:

```bash
python -m ruff check src tests scripts
python -m pytest
python scripts/verify_release.py
npm --prefix adapters/pi ci --no-audit --no-fund
npm --prefix adapters/pi run check
```

For a release candidate, also build and test the actual artifacts:

```bash
python -m build --wheel --sdist --outdir dist
python scripts/verify_release.py --artifacts-dir dist --require-sdist --smoke-wheel
python scripts/build_release.py --output-dir dist
python scripts/verify_release.py --bundle-dir dist
```

## Version and release rules

The version must agree in Python metadata, package `__version__`, both native plugin manifests, marketplace metadata, and the Pi package/lockfile. Release tags use `vMAJOR.MINOR.PATCH` and must point to a tested commit on `main`.

Never overwrite an existing tag or release asset. Build wheel and sdist from the tag, install the wheel in a clean environment, publish to PyPI, verify installation through both `pip` and `uv`, publish MCP Registry metadata, and verify the downloadable plugin bundle before calling a release complete.

Preparing or verifying a release candidate does not by itself authorize tag creation, pushing, package publication, Registry publication, or any other external mutation. Perform those actions only when the user explicitly requests production release.

Never commit vault contents, credentials, tokens, machine-specific paths, generated backups, staging data, virtual environments, caches, or build artifacts.
