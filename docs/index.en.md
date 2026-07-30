# Obsidian Vault MCP 3.0.0 Installation Guide

[中文](./index.md) · [Project home](../README.en.md) · [Development](../DEVELOPMENT.en.md) · [Changelog](../CHANGELOG.md)

This guide covers the production installation, Zotero, MinerU, Obsidian, Analysis, Skills, Agent plugins, and release validation.

## 1. Requirements

| Component | Requirement | Purpose |
|---|---|---|
| Python | 3.10–3.13 | CLI and MCP server |
| Obsidian | Target Vault opened at least once | Creates `.obsidian/` and displays Markdown/Base |
| Zotero Desktop | Running with local API enabled | Items, attachments, notes, annotations, BibTeX |
| MinerU Open API CLI | Optional | PDF full text, figures, and equations |
| AI client | Optional | Codex, Claude Code, OpenCode, Pi, Hermes, WorkBuddy |

Prefer local stdio. MinerU may upload PDFs; confirm authorization and policy before use.

## 2. Install

### uv

```bash
uv tool install "zotero-obsidian-mcp==3.0.0"
obsidian-vault-mcp --help
```

One-shot execution:

```bash
uvx --from "zotero-obsidian-mcp==3.0.0" obsidian-vault-mcp --help
```

### pipx / pip

```bash
pipx install "zotero-obsidian-mcp==3.0.0"
# or
python -m pip install "zotero-obsidian-mcp==3.0.0"
```

### Source installation from the tag

```bash
git clone https://github.com/luffysolution-svg/obsidian-vault-mcp.git
cd obsidian-vault-mcp
git checkout v3.0.0
uv sync --locked --all-extras
uv run obsidian-vault-mcp --help
```

Verify:

```bash
python -c "from importlib.metadata import version; print(version('zotero-obsidian-mcp'))"
obsidian-vault-mcp call literature_version --json '{}'
```

The version must be `3.0.0`, with 31 tools and 7 Skills.

## 3. Initialize a Vault

The target directory must contain `.obsidian/`.

```bash
export OBSIDIAN_VAULT_PATH="<VAULT_PATH>"
obsidian-vault-mcp config init --vault-path "$OBSIDIAN_VAULT_PATH" --dry-run
obsidian-vault-mcp config init --vault-path "$OBSIDIAN_VAULT_PATH"
obsidian-vault-mcp config validate --vault-path "$OBSIDIAN_VAULT_PATH"
obsidian-vault-mcp doctor --vault-path "$OBSIDIAN_VAULT_PATH"
```

Windows PowerShell uses `$env:OBSIDIAN_VAULT_PATH = "<VAULT_PATH>"`.

## 4. Zotero

1. Start Zotero Desktop.
2. Enable its local HTTP API.
3. Test the connection and search parent items:

```bash
obsidian-vault-mcp call zotero_ping --json '{}'
obsidian-vault-mcp call zotero_search_items --json '{"query":"photocatalysis"}'
```

Do not use a PDF child attachment key as the literature identity.

Linked attachments:

```json
{
  "zotero": {
    "linkedAttachmentBaseDir": "<ZOTERO_LINKED_ATTACHMENT_BASE_DIR>"
  }
}
```

The `ZOTERO_LINKED_ATTACHMENT_BASE_DIR` environment variable is also supported. Paths outside the configured base are rejected.

## 5. Import and synchronize

```bash
obsidian-vault-mcp import item ABCD1234 --dry-run
obsidian-vault-mcp import item ABCD1234

obsidian-vault-mcp import collection COLLECTION_KEY --dry-run
obsidian-vault-mcp import collection COLLECTION_KEY

obsidian-vault-mcp sync item ABCD1234 --dry-run
obsidian-vault-mcp sync item ABCD1234
```

Output:

```text
Literature/ABCD1234.md
Literature/attachment/ABCD1234.pdf
Literature/index.md
Literature/Literature.base
```

The `zoteroKey` remains stable when metadata changes.

## 6. MinerU

Install and authenticate `mineru-open-api` according to MinerU documentation. Never store its token in chat, the Vault, or Git.

```bash
obsidian-vault-mcp mineru parse ABCD1234 --dry-run
obsidian-vault-mcp mineru parse ABCD1234
obsidian-vault-mcp mineru parse-batch ABCD1234 EFGH5678 --dry-run
obsidian-vault-mcp mineru parse-batch ABCD1234 EFGH5678
```

Canonical output:

```text
Literature/attachment/MinerU/ABCD1234.md
Literature/attachment/MinerU/image/ABCD1234/ABCD1234-fig01.png
```

Markdown uses relative links. Parsing is staged and committed only after validation.

## 7. Analysis and Skills

| Analysis | Purpose | Skill |
|---|---|---|
| `full_read` | complete single-paper reading | `full-read` |
| `literature_review` | multi-paper synthesis or comparison | `literature-review`, `compare-papers` |
| `passage_qa` | passage, method, value, or claim lookup | `passage-qa` |
| `figure_qa` | figure, table, scheme, or equation interpretation | `figure-qa` |
| `concept` | cross-paper concept learning | `concept-learning` |

`paper-qa` provides fast non-persistent Q&A by default. Profiles: `general`, `medicine`, `chemistry`, `materials`, `catalysis`, `physics`, and `mathematics`.

```bash
obsidian-vault-mcp call literature_paper_read --json '{"zotero_key":"ABCD1234","mode":"overview"}'
obsidian-vault-mcp call literature_retrieve --json '{"query":"active sites","intent":"compare","depth":"evidence"}'
```

Persistent workflows should use `literature_analysis_get` for duplicate detection and preview `literature_analysis_write` before committing.

```bash
obsidian-vault-mcp call literature_rebuild_analysis_base --json '{"dry_run":true}'
obsidian-vault-mcp call literature_rebuild_analysis_base --json '{"dry_run":false}'
```

`Analysis.base` contains nine views: Dashboard, Full Reads, Reviews, Passage Q&A, Figure Q&A, Concepts, Needs Attention, By Discipline, and Recently Updated.

## 8. MCP Registry

```text
io.github.luffysolution-svg/obsidian-vault-mcp
```

`uvx` stdio configuration:

```json
{
  "mcpServers": {
    "obsidian-literature": {
      "command": "uvx",
      "args": [
        "--from",
        "zotero-obsidian-mcp==3.0.0",
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

## 9. Agent integrations

```bash
obsidian-vault-mcp agent install <client> --dry-run
obsidian-vault-mcp agent install <client>
```

Valid clients: `codex`, `claude`, `opencode`, `pi`, `hermes`, and `workbuddy`.

| Client | Installed result |
|---|---|
| Codex | native marketplace plugin, MCP, 7 Skills |
| Claude Code | native marketplace plugin, MCP, 7 Skills |
| OpenCode | project-local MCP, 7 Skills |
| Pi | TypeScript extension |
| Hermes | MCP configuration |
| WorkBuddy | MCP configuration |

Offline Codex/Claude bundle: `obsidian-vault-mcp-3.0.0-plugins.zip`.

## 10. 31 MCP tools

| Group | Count | Capability |
|---|---:|---|
| Version, system, and configuration | 5 | version, doctor, read, validate, initialize |
| Zotero | 6 | ping, search, collections, item, children, BibTeX |
| Import and sync | 4 | item and collection import/sync |
| MinerU | 3 | single, batch, remove derived output |
| Navigation and validation | 3 | Index, Base, Verify |
| Analysis | 5 | read, retrieve, query, write, Base |
| Wiki | 3 | context, write, list |
| Transactions | 2 | preview, rollback |

## 11. Screenshots

<img src="assets/screenshots/v2/vault-structure.png" alt="Vault literature structure" width="320">

<img src="assets/screenshots/v2/literature-index.png" alt="Literature Index" width="760">

<img src="assets/screenshots/v2/wiki-synthesis.png" alt="Traceable Wiki synthesis" width="780">

## 12. Validation and troubleshooting

```bash
obsidian-vault-mcp call literature_version --json '{}'
obsidian-vault-mcp doctor
obsidian-vault-mcp verify
obsidian-vault-mcp index rebuild --dry-run
obsidian-vault-mcp base rebuild --dry-run
```

| Symptom | Check |
|---|---|
| Zotero call fails | Zotero running and local API enabled |
| PDF not copied | Zotero storage or linked-attachment base directory |
| MinerU fails | CLI, authentication, network, PDF authorization |
| Analysis is `needs_update` | source fingerprint changed; review again |
| Client shows no tools | package version, PATH, environment, and client restart |

## 13. Release acceptance

- Package, runtime, Registry, plugin, and Pi versions are `3.0.0`.
- Tag `v3.0.0` points to the release commit on `main`.
- Wheel, sdist, plugin ZIP, and `SHA256SUMS` pass validation.
- Python tests, Ruff, Pi type checking, wheel smoke, 31-tool check, 7-Skill check, and MCP handshake pass.
- PyPI, MCP Registry, and GitHub Release versions and artifacts match.

## 14. Safety

- Preview every write and retain transaction IDs.
- Preview rollbacks before applying them.
- Run automated write tests only on isolated Vault copies.
- Keep an independent Vault backup.
- Do not expose unauthenticated SSE or HTTP transports.
