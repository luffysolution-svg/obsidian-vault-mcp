# Obsidian Vault MCP 3.0.2 Developer Guide

[中文](./DEVELOPMENT.md) · [README](./README.en.md) · [Installation guide](./docs/index.en.md) · [Changelog](./CHANGELOG.md)

This document defines the production architecture, code boundaries, test matrix, and release process. The Python distribution is `zotero-obsidian-mcp`, the CLI is `obsidian-vault-mcp`, and the MCP Registry name is `io.github.luffysolution-svg/obsidian-vault-mcp`.

## 1. Architecture principles

1. The Zotero parent-item `zoteroKey` is the stable identity.
2. Vault-visible paths are relative, portable, and use `/`.
3. Read tools must not perform hidden writes.
4. Writes must support dry-run, transactions, backups, atomic replacement, and conflict policies.
5. MCP tools provide deterministic capabilities; Skills define research workflows.
6. Analysis has five types and one `Analysis.base`.
7. Package, runtime, Registry, plugin, Pi, tag, Release, and PyPI versions must match.

## 2. Source layout

```text
src/obsidian_vault_mcp/
├─ adapters/                 # Zotero, MinerU, Obsidian, and Vault I/O
├─ application/              # use cases and transaction orchestration
├─ config/                   # defaults, loader, and schema
├─ domain/                   # identity, paths, Analysis, and models
├─ interfaces/
│  ├─ cli/
│  ├─ mcp/                   # 31 MCP tools
│  └─ agent_install/
└─ resources/agent_marketplace/
   └─ plugins/obsidian-literature/
      ├─ .mcp.json
      ├─ .codex-plugin/
      ├─ .claude-plugin/
      └─ skills/             # 7 Skills
```

Dependency direction is `interfaces → application → domain`; adapters implement external I/O. Interface code must not duplicate adapter logic.

## 3. Production data model

```text
Literature/{zoteroKey}.md
Literature/attachment/{zoteroKey}.pdf
Literature/attachment/MinerU/{zoteroKey}.md
Literature/attachment/MinerU/image/{zoteroKey}/{zoteroKey}-figNN.ext
```

Analysis types: `full_read`, `literature_review`, `passage_qa`, `figure_qa`, `concept`.

Statuses: `draft`, `ready`, `reviewed`, `needs_update`, `archived`.

Profiles: `general`, `medicine`, `chemistry`, `materials`, `catalysis`, `physics`, `mathematics`.

The only Analysis database is `Literature/Analysis/Analysis.base`.

## 4. MCP contract

The production surface is fixed at 31 tools:

| Group | Count |
|---|---:|
| Version, system, and configuration | 5 |
| Zotero | 6 |
| Import and sync | 4 |
| MinerU | 3 |
| Navigation and validation | 3 |
| Analysis | 5 |
| Wiki | 3 |
| Transactions | 2 |

`literature_version` is a read-only contract tool exposing the version, tool count, Skill count, and Analysis types.

Every tool must be explicitly registered, have a docstring, declare MCP behavior annotations, return JSON-serializable data, and pass the exact surface test.

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

Each Skill uses `SKILL.md`, stores output and discipline rules under `references/`, calls only production tools, keeps no independent database, and performs duplicate checks plus dry-run before persistent writes.

## 6. Local development

```bash
git clone https://github.com/luffysolution-svg/obsidian-vault-mcp.git
cd obsidian-vault-mcp
uv sync --locked --all-extras
uv run obsidian-vault-mcp --help
```

```bash
uv run python -m ruff check .
uv run python -m pytest
uv run python scripts/verify_release.py

cd adapters/pi
npm ci --no-audit --no-fund
npm run check
```

Automated write tests must use temporary or isolated Vaults.

## 7. Test matrix

| Layer | Coverage |
|---|---|
| Unit | identity, paths, parsing, Analysis, transactions, installers |
| Contract | 31 tools, 7 Skills, client configuration, plugin manifests, schema |
| Repository | release hygiene, version consistency, reproducible artifacts, secret scanning |
| Wheel smoke | isolated install, dependency check, CLI, 31 tools, 7 Skills, stdio handshake |
| Platform CI | Ubuntu, Windows, macOS; Python 3.10–3.13 |

## 8. Version consistency

The following must use `3.0.2`:

- `pyproject.toml`
- `src/obsidian_vault_mcp/__init__.py`
- `server.json`
- Codex and Claude plugin manifests and marketplace metadata
- `adapters/pi/package.json` and `package-lock.json`
- Git tag `v3.0.2`
- GitHub Release
- PyPI

The configuration `schemaVersion` is an independent data-format version and is not tied to the software version.

## 9. Release procedure

1. Complete code, documentation, and version changes on `main`.
2. Run all tests, Ruff, Pi checks, and `scripts/verify_release.py`.
3. Confirm a clean worktree.
4. Create and push the tag:

```bash
git tag -a v3.0.2 -m "Obsidian Vault MCP 3.0.2"
git push origin v3.0.2
```

5. `.github/workflows/release.yml` verifies the tag and its ancestry on `main`.
6. It builds and verifies wheel, sdist, plugin ZIP, and `SHA256SUMS`.
7. It runs wheel smoke, the 31-tool check, the 7-Skill check, and the MCP handshake.
8. It publishes PyPI, MCP Registry metadata, and the GitHub Release in order.

Artifacts:

```text
zotero_obsidian_mcp-3.0.2-py3-none-any.whl
zotero_obsidian_mcp-3.0.2.tar.gz
obsidian-vault-mcp-3.0.2-plugins.zip
SHA256SUMS
```

Published versions are immutable. Corrections require a new semantic version.

## 10. Release recovery rules

The release workflow stores a workflow marker for each external publish stage. On rerun, it may resume only the draft GitHub Release for the same tag and must revalidate every `SHA256` before upload.

- If the version already exists on PyPI or MCP Registry, verify its content and state instead of uploading again.
- A GitHub draft may be completed only with the same tag and checksums.
- Once public or protected by immutable releases, the release must be resumed without deletion or overwrite.
- Any artifact, tag, or checksum mismatch must stop the workflow and require a new semantic version.

## 11. Release checklist

- [ ] Exactly 31 MCP tools.
- [ ] Exactly 7 Skills with references.
- [ ] README, installation guide, developer guide, and CLI agree.
- [ ] Screenshots and contributor records are accessible.
- [ ] Installation commands pin `3.0.2`.
- [ ] Tag, PyPI, MCP Registry, plugins, and Pi use the same version.
- [ ] Wheel, sdist, plugin ZIP, and checksums pass verification.
- [ ] No credentials or machine-local absolute paths are present.

## 12. Security requirements

- Prefer local stdio.
- Put network transports behind trusted authentication and access control.
- Send only authorized PDFs to external parsing services.
- Store tokens only in protected environments or credential stores.
- Enforce path checks, locks, and transactions for Vault writes.
