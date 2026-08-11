<!-- mcp-name: io.github.luffysolution-svg/obsidian-vault-mcp -->

# Obsidian Vault MCP

A local research workflow MCP server that uses Zotero as the source library, MinerU for full-text extraction, and Obsidian for durable literature notes, Wikis, and structured Analysis. Research Skills orchestrate the tools so AI agents work with traceable sources and controlled writes.

[中文](https://github.com/luffysolution-svg/obsidian-vault-mcp/blob/main/README.md) · [Installation guide](https://github.com/luffysolution-svg/obsidian-vault-mcp/blob/main/docs/index.en.md) · [Development](https://github.com/luffysolution-svg/obsidian-vault-mcp/blob/main/DEVELOPMENT.en.md) · [Changelog](https://github.com/luffysolution-svg/obsidian-vault-mcp/blob/main/CHANGELOG.md) · [Contributors](https://github.com/luffysolution-svg/obsidian-vault-mcp/blob/main/CONTRIBUTORS.md)

## Architecture

```text
Natural-language research task
        ↓
7 research Skills: intent routing, workflow planning, evidence and output rules
        ↓
31 MCP tools: version contract, query, import, parse, retrieve, validate, and write
        ↓
Zotero Desktop ── PDF ── MinerU ── Obsidian Vault
                                      ├─ literature notes
                                      ├─ PDFs and full-text Markdown
                                      ├─ Index / Literature.base
                                      ├─ Wiki
                                      └─ five Analysis types / Analysis.base
```

The project is model-provider independent. MCP tools implement deterministic local operations; Skills define reusable research procedures.

## Features

- Stable Zotero parent-item identity based on `zoteroKey`.
- Item and collection import/sync, notes, annotations, BibTeX, stored PDFs, and linked attachments.
- Staged MinerU parsing with one portable image directory per paper.
- Automatic `Literature/index.md`, `Literature/Literature.base`, source-linked Wiki pages, and validation.
- Five Analysis types: `full_read`, `literature_review`, `passage_qa`, `figure_qa`, and `concept`.
- One nine-view `Literature/Analysis/Analysis.base` database.
- Seven Skills: `paper-qa`, `full-read`, `passage-qa`, `figure-qa`, `compare-papers`, `literature-review`, and `concept-learning`.
- Dry-run, staging, locks, backups, atomic replacement, transaction preview, and rollback.
- A read-only `literature_version` tool exposing the version and public capability counts.
- Codex, Claude Code, OpenCode, Pi, Hermes, and WorkBuddy integrations.

## Screenshots

### Literature folder

<img src="https://raw.githubusercontent.com/luffysolution-svg/obsidian-vault-mcp/main/docs/assets/screenshots/v2/vault-structure.png" alt="Obsidian literature folder" width="320">

### Literature Index

<img src="https://raw.githubusercontent.com/luffysolution-svg/obsidian-vault-mcp/main/docs/assets/screenshots/v2/literature-index.png" alt="Literature Index" width="760">

### Traceable multi-paper Wiki

<img src="https://raw.githubusercontent.com/luffysolution-svg/obsidian-vault-mcp/main/docs/assets/screenshots/v2/wiki-synthesis.png" alt="Traceable Wiki synthesis" width="780">

## Install

Version `3.0.2` is published. Python 3.10+ is required. The public installation commands below are available now.

### uv

```bash
uv tool install "zotero-obsidian-mcp==3.0.2"
obsidian-vault-mcp --help
```

One-shot execution:

```bash
uvx --from "zotero-obsidian-mcp==3.0.2" obsidian-vault-mcp doctor --vault-path "<VAULT_PATH>"
```

### pipx / pip

```bash
pipx install "zotero-obsidian-mcp==3.0.2"
# or
python -m pip install "zotero-obsidian-mcp==3.0.2"
```

### MCP Registry

```text
io.github.luffysolution-svg/obsidian-vault-mcp
```

Equivalent stdio configuration:

```json
{
  "mcpServers": {
    "obsidian-literature": {
      "command": "uvx",
      "args": [
        "--from",
        "zotero-obsidian-mcp==3.0.2",
        "obsidian-vault-mcp",
        "serve",
        "--transport",
        "stdio"
      ],
      "env": {
        "OBSIDIAN_VAULT_PATH": "<VAULT_PATH>"
      }
    }
  }
}
```

## First setup

```bash
obsidian-vault-mcp config init --vault-path "<VAULT_PATH>" --dry-run
obsidian-vault-mcp config init --vault-path "<VAULT_PATH>"
obsidian-vault-mcp config validate --vault-path "<VAULT_PATH>"
obsidian-vault-mcp doctor --vault-path "<VAULT_PATH>"
obsidian-vault-mcp call literature_version --json '{}'
```

With Zotero Desktop running and its local API enabled:

```bash
obsidian-vault-mcp call zotero_search_items --json '{"query":"photocatalysis"}'
obsidian-vault-mcp import item ABCD1234 --vault-path "<VAULT_PATH>" --dry-run
obsidian-vault-mcp import item ABCD1234 --vault-path "<VAULT_PATH>"
```

For linked attachments:

```json
{
  "zotero": {
    "linkedAttachmentBaseDir": "<ZOTERO_LINKED_ATTACHMENT_BASE_DIR>"
  }
}
```

MinerU parsing:

```bash
obsidian-vault-mcp mineru parse ABCD1234 --vault-path "<VAULT_PATH>" --dry-run
obsidian-vault-mcp mineru parse ABCD1234 --vault-path "<VAULT_PATH>"
```

## Agent and plugin installation

```bash
obsidian-vault-mcp agent install codex --dry-run
obsidian-vault-mcp agent install codex
```

Replace `codex` with `claude`, `opencode`, `pi`, `hermes`, or `workbuddy`.

| Client | Installed capability |
|---|---|
| Codex | Native marketplace plugin, MCP, and 7 Skills |
| Claude Code | Native marketplace plugin, MCP, and 7 Skills |
| OpenCode | Project-local MCP and 7 Skills |
| Pi | Thin TypeScript extension |
| Hermes | MCP configuration |
| WorkBuddy | MCP configuration |

The GitHub Release provides `obsidian-vault-mcp-3.0.2-plugins.zip`.

## Skills

| Skill | Purpose |
|---|---|
| `paper-qa` | Fast single-paper Q&A without persistent output by default |
| `full-read` | Complete paper reading saved as `full_read` |
| `passage-qa` | Locate a specific passage, method, value, or claim |
| `figure-qa` | Interpret figures, tables, schemes, and equations |
| `compare-papers` | Build a comparability matrix for selected papers |
| `literature-review` | Synthesize a defined literature pool by theme |
| `concept-learning` | Build a reusable concept model across papers |

## Production tool surface

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
| **Total** | **31** |

## Release consistency

Version `3.0.2` must match the Python package, runtime `__version__`, MCP Registry metadata, Codex and Claude manifests, Pi package, Git tag `v3.0.2`, GitHub Release, and PyPI. The release workflow verifies version and tag identity, runs tests and handshakes, builds wheel/sdist/plugin ZIP artifacts, and generates `SHA256SUMS`.

## Safety

- Preview every write with dry-run and retain the returned `transactionId`.
- Never commit Vault paths, Zotero data paths, MinerU tokens, or credentials.
- MinerU may send selected PDFs to an external service; confirm authorization first.
- Prefer local stdio. Place network transports behind trusted authentication and access control.
- Transaction backups do not replace an independent Vault backup.

## Contributors

Thanks to [Lym Fang / 方珸 (@LimFang)](https://github.com/LimFang) for proposing Zotero linked-attachment compatibility. See [CONTRIBUTORS.md](https://github.com/luffysolution-svg/obsidian-vault-mcp/blob/main/CONTRIBUTORS.md).
