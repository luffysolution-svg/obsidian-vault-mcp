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

Local stdio is recommended. MinerU may upload PDFs; confirm authorization and policy before use.

## 2. Install the Python package

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

### Source installation from the release tag

```bash
git clone https://github.com/luffysolution-svg/obsidian-vault-mcp.git
cd obsidian-vault-mcp
git checkout v3.0.0
uv sync --locked --all-extras
uv run obsidian-vault-mcp --help
```

Verify the installed version:

```bash
python -c "from importlib.metadata import version; print(version('zotero-obsidian-mcp'))"
```

The output must be `3.0.0`.

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

The configuration file is `<Vault>/.obsidian-vault-mcp.json`. Do not commit machine-local paths or credentials.

## 4. Configure Zotero

1. Start Zotero Desktop.
2. Enable its local HTTP API.
3. Test the connection:

```bash
obsidian-vault-mcp call zotero_ping --json '{}'
obsidian-vault-mcp call zotero_search_items --json '{"query":"photocatalysis"}'
```

Use the parent-item key returned by Zotero, not a PDF child attachment key.

### Linked attachments

For Zotero “Link to File” attachments, configure the same linked-attachment base directory:

```json
{
  "zotero": {
    "linkedAttachmentBaseDir": "<ZOTERO_LINKED_ATTACHMENT_BASE_DIR>"
  }
}
```

Or set `ZOTERO_LINKED_ATTACHMENT_BASE_DIR`. Directory traversal, drive injection, and paths outside the configured base are rejected.

## 5. Import and synchronize

```bash
obsidian-vault-mcp import item ABCD1234 --dry-run
obsidian-vault-mcp import item ABCD1234

obsidian-vault-mcp import collection COLLECTION_KEY --dry-run
obsidian-vault-mcp import collection COLLECTION_KEY

obsidian-vault-mcp sync item ABCD1234 --dry-run
obsidian-vault-mcp sync item ABCD1234
```

Default output:

```text
Literature/ABCD1234.md
Literature/attachment/ABCD1234.pdf
Literature/index.md
Literature/Literature.base
```

The `zoteroKey` remains stable when titles, authors, years, or citation keys change.

## 6. Parse full text with MinerU

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

Markdown uses portable relative links. Parsing is staged and committed only after Markdown, figures, and links pass validation.

## 7. Analysis and Skills

| Analysis type | Use case | Skill |
|---|---|---|
| `full_read` | complete single-paper reading | `full-read` |
| `literature_review` | multi-paper synthesis or comparison | `literature-review`, `compare-papers` |
| `passage_qa` | passage, method, value, or claim lookup | `passage-qa` |
| `figure_qa` | figure, table, scheme, or equation interpretation | `figure-qa` |
| `concept` | cross-paper concept learning | `concept-learning` |

`paper-qa` provides fast single-paper Q&A without persistent output by default.

Discipline profiles are `general`, `medicine`, `chemistry`, `materials`, `catalysis`, `physics`, and `mathematics`.

```bash
obsidian-vault-mcp call literature_paper_read --json '{"zotero_key":"ABCD1234","mode":"overview"}'
obsidian-vault-mcp call literature_retrieve --json '{"query":"active sites","intent":"compare","depth":"evidence"}'
```

A persistent workflow should call `literature_analysis_get` for duplicate detection, preview `literature_analysis_write` with `dry_run: true`, and commit only after reviewing the complete output.

Rebuild the nine-view Analysis database:

```bash
obsidian-vault-mcp call literature_rebuild_analysis_base --json '{"dry_run":true}'
obsidian-vault-mcp call literature_rebuild_analysis_base --json '{"dry_run":false}'
```

## 8. MCP Registry and manual configuration

Registry name:

```text
io.github.luffysolution-svg/obsidian-vault-mcp
```

Equivalent `uvx` stdio configuration:

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

## 9. Install Agent integrations

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

The GitHub Release includes `obsidian-vault-mcp-3.0.0-plugins.zip` for offline Codex and Claude installation.

## 10. Production MCP surface

| Group | Tools |
|---|---:|
| System and configuration | 4 |
| Zotero | 6 |
| Import and sync | 4 |
| MinerU | 3 |
| Navigation and validation | 3 |
| Analysis | 5 |
| Wiki | 3 |
| Transactions | 2 |

Total: 30 tools.

## 11. Screenshots

### Vault literature structure

<img src="assets/screenshots/v2/vault-structure.png" alt="Vault literature structure" width="320">

### Literature Index

<img src="assets/screenshots/v2/literature-index.png" alt="Literature Index" width="760">

### Traceable Wiki synthesis

<img src="assets/screenshots/v2/wiki-synthesis.png" alt="Traceable Wiki synthesis" width="780">

## 12. Validation and troubleshooting

```bash
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
| Base missing | call the corresponding rebuild tool |
| Client shows no tools | package version, PATH, environment, and client restart |

## 13. Release acceptance

A production release requires all package, runtime, Registry, plugin, Pi, tag, GitHub Release, and PyPI versions to equal `3.0.0`; tests, Ruff, Pi checks, wheel smoke, MCP handshake, reproducible artifacts, and SHA-256 checks must pass.

## 14. Safety rules

- Preview every write with dry-run.
- Retain transaction IDs and preview rollbacks before applying them.
- Run automated write tests only on isolated Vault copies.
- Keep an independent Vault backup.
- Do not expose unauthenticated SSE or HTTP transports.
