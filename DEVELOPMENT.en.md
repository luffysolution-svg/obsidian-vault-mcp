# Obsidian Vault MCP 3.0.0 Developer Guide

[中文](./DEVELOPMENT.md) · [README](./README.en.md) · [Installation guide](./docs/index.en.md) · [Changelog](./CHANGELOG.md)

This document defines the production architecture, code boundaries, test matrix, and release process. The Python distribution is `zotero-obsidian-mcp`, the CLI is `obsidian-vault-mcp`, and the MCP Registry name is `io.github.luffysolution-svg/obsidian-vault-mcp`.

## 1. Architecture principles

1. The Zotero parent-item `zoteroKey` is the stable literature identity.
2. All Vault paths are relative and use `/` separators.
3. Read tools must not perform hidden writes.
4. Writes must support dry-run, transactions, backups, atomic replacement, and conflict policies.
5. MCP tools provide deterministic capabilities; Skills define research workflows without duplicating business logic.
6. Analysis has five types and one `Analysis.base`.
7. Version `3.0.0` must match every release metadata surface.

## 2. Source layout

```text
src/obsidian_vault_mcp/
├─ adapters/                 # Zotero, MinerU, Obsidian, and Vault I/O
├─ application/              # use cases and transaction orchestration
├─ config/                   # defaults, loader, and schema
├─ domain/                   # identity, paths, Analysis, and domain models
├─ interfaces/
│  ├─ cli/                   # CLI
│  ├─ mcp/                   # 30 MCP tools and server
│  └─ agent_install/         # installers for six clients
└─ resources/agent_marketplace/
   └─ plugins/obsidian-literature/
      ├─ .mcp.json
      ├─ .codex-plugin/
      ├─ .claude-plugin/
      └─ skills/             # 7 Skills
```

Dependency direction:

```text
interfaces → application → domain
      ↓            ↓
adapters ←─────────┘
```

The interface layer must not reimplement filesystem, HTTP, or parsing work.

## 3. Production data model

Literature assets:

```text
Literature/{zoteroKey}.md
Literature/attachment/{zoteroKey}.pdf
Literature/attachment/MinerU/{zoteroKey}.md
Literature/attachment/MinerU/image/{zoteroKey}/{zoteroKey}-figNN.ext
```

Analysis types:

```text
full_read
literature_review
passage_qa
figure_qa
concept
```

Statuses:

```text
draft
ready
reviewed
needs_update
archived
```

Discipline profiles:

```text
general
medicine
chemistry
materials
catalysis
physics
mathematics
```

The only Analysis database is `Literature/Analysis/Analysis.base`.

## 4. MCP contract

The production surface is fixed at 30 tools:

| Group | Count |
|---|---:|
| System and configuration | 4 |
| Zotero | 6 |
| Import and sync | 4 |
| MinerU | 3 |
| Navigation and validation | 3 |
| Analysis | 5 |
| Wiki | 3 |
| Transactions | 2 |

Every tool must be explicitly registered, have a non-empty docstring, declare all MCP behavior annotations, return JSON-serializable data, and avoid implicit registration through dynamic scanning.

## 5. Skills contract

The release contains exactly:

```text
paper-qa
full-read
passage-qa
figure-qa
compare-papers
literature-review
concept-learning
```

Each Skill uses `SKILL.md` as its entrypoint, stores output and discipline rules under `references/`, calls only production MCP tools, keeps no independent database, preserves source locations, separates facts from interpretations and inferences, and performs duplicate checks plus dry-run before persistent writes.

## 6. Local development

```bash
git clone https://github.com/luffysolution-svg/obsidian-vault-mcp.git
cd obsidian-vault-mcp
uv sync --locked --all-extras
uv run obsidian-vault-mcp --help
```

Checks:

```bash
uv run python -m ruff check .
uv run python -m pytest
uv run python scripts/verify_release.py

cd adapters/pi
npm ci --no-audit --no-fund
npm run check
```

Automated write tests must use temporary or isolated Vaults, never a user's active Vault.

## 7. Test matrix

| Layer | Coverage |
|---|---|
| Unit | identity, paths, parsing, Analysis, transactions, installers |
| Contract | client configuration, plugin manifests, MCP registration, schema |
| Repository | release hygiene, version consistency, reproducible artifacts, secret scanning |
| Wheel smoke | isolated install, dependency check, CLI, 30 tools, 7 Skills, stdio handshake |
| Platform CI | Ubuntu, Windows, macOS; Python 3.10–3.13 |

Any new tool, Skill, configuration field, or release asset must update the associated contract tests.

## 8. Version consistency

The same version must appear in:

- `pyproject.toml`
- `src/obsidian_vault_mcp/__init__.py`
- `server.json` and its PyPI package metadata
- Codex plugin manifest
- Claude plugin manifest and marketplace metadata
- `adapters/pi/package.json`
- `adapters/pi/package-lock.json`
- Git tag `v3.0.0`
- GitHub Release
- PyPI

`server.json` and the README MCP ownership marker must remain aligned.

## 9. Release procedure

1. Complete all code, documentation, and version changes on `main`.
2. Run all tests, Ruff, Pi type checking, and `scripts/verify_release.py`.
3. Confirm the repository is clean.
4. Create the release tag on the exact release commit:

```bash
git tag -a v3.0.0 -m "Obsidian Vault MCP 3.0.0"
git push origin v3.0.0
```

5. The tag triggers `.github/workflows/release.yml`.
6. The workflow verifies tag identity and ancestry on `main`.
7. It builds and verifies wheel, sdist, and plugin ZIP artifacts, runs smoke tests and MCP handshakes, and generates SHA-256 checksums.
8. It publishes PyPI, MCP Registry metadata, and the GitHub Release in a controlled order.

Artifacts:

```text
zotero_obsidian_mcp-3.0.0-py3-none-any.whl
zotero_obsidian_mcp-3.0.0.tar.gz
obsidian-vault-mcp-3.0.0-plugins.zip
SHA256SUMS
```

Published versions and artifacts are immutable. Any correction requires a new semantic version.

## 10. Release checklist

- [ ] Exactly 30 MCP tools.
- [ ] Exactly 7 Skills with all references.
- [ ] README, installation guide, developer guide, and CLI agree.
- [ ] Screenshots and contributor records are accessible.
- [ ] Every installation command pins `3.0.0`.
- [ ] Tag, PyPI, MCP Registry, plugins, and Pi use the same version.
- [ ] Wheel, sdist, plugin ZIP, and checksum verification pass.
- [ ] No credentials or machine-local absolute paths are present.

## 11. Security requirements

- Prefer local stdio.
- Put network transports behind trusted authentication and access control.
- Send only authorized PDFs to external parsing services.
- Store tokens only in protected environments or credential stores.
- Enforce path boundaries, locks, and transactions for Vault writes.
