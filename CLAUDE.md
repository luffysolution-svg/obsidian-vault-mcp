# CLAUDE.md

## V2 repository contract

This repository implements a local Zotero → MinerU → Obsidian literature pipeline. Keep every change consistent with these invariants:

- A Zotero parent item is identified permanently by `zoteroKey`.
- One parent item maps to one main note, normally `Literature/{zoteroKey}.md`.
- User-visible files contain vault-relative paths with `/` separators. Source machine paths may appear only in hidden state.
- Managed frontmatter is deterministic, omits empty values, and preserves unknown user fields.
- User-authored Markdown outside managed markers is never overwritten.
- Every write supports preview, locking, staging, backup, atomic replacement, and rollback.
- The vault has one configuration file: `.obsidian-vault-mcp.json` with `schemaVersion: 2`.
- The supported MCP surface contains the 26 V2 literature tools. Do not restore removed modes or pre-V2 tool names.
- Native agent clients connect through MCP. Pi uses the thin TypeScript Extension. Do not add mirrored agent-instruction directories or synchronization scripts.

## Architecture boundaries

Production Python code lives under `src/obsidian_vault_mcp/`:

- `domain/`: identities, models, path rules, frontmatter, and domain errors.
- `application/`: import, sync, MinerU, index, base, wiki, migration, and transaction orchestration.
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
- Tests that write files must use temporary vaults and must not contact a real Zotero library or MinerU service.

## Pi Extension synchronization

`adapters/pi/index.ts` is the distributable Pi package source. The wheel also carries an installer resource at:

```text
src/obsidian_vault_mcp/interfaces/agent_install/pi_extension.ts
```

These two files must remain byte-identical. The Extension must call:

```text
obsidian-vault-mcp call <tool> --json <json>
```

Use `execFile` or `spawn` without a shell and retain cancellation, timeout, output-size, and JSON-error handling.

## Verification

Run the checks relevant to the changed surface:

```bash
python -m ruff check src tests scripts/verify_release.py
python -m pytest tests/unit tests/contract tests/repository
python scripts/verify_release.py
```

For a release candidate, also build and test the actual artifacts:

```bash
python -m build --wheel --sdist --outdir dist
python scripts/verify_release.py --artifacts-dir dist --require-sdist --smoke-wheel
```

The release verifier enforces portable client configuration, removed-path hygiene, dependency bounds, version agreement, Pi resource synchronization, and artifact contents.

## Version and release rules

The version must agree in:

- `pyproject.toml`
- `.codex-plugin/plugin.json`
- `adapters/pi/package.json`

Release tags use `vMAJOR.MINOR.PATCH` and must point to the checked-out commit. Releases build wheel and sdist from the tag, install the wheel for smoke testing, and create a Codex bundle containing only the two allowlisted, Git-tracked configuration files.

Never commit vault contents, credentials, tokens, machine-specific paths, generated backups, staging data, virtual environments, caches, or build artifacts.
