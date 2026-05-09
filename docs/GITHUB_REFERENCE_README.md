# Obsidian Vault MCP Plugin

Open-source Codex MCP plugin for maintaining local Obsidian vaults as
persistent linked wikis.

## What It Does

`obsidian-vault` helps Codex maintain local Obsidian vaults as persistent linked wikis. It includes:

- Vault file listing, search, read, write, and note creation tools.
- YAML frontmatter/property editing.
- Batch edit transactions with multi-file preview, apply, vault-local backups, and rollback.
- Wiki double-link creation.
- Backlink-aware graph generation with aliases, inline tags, unresolved links, and ambiguous link detection.
- Dry-run diff previews for write operations.
- Vault lint checks for graph health and Karpathy-style `index.md`/`log.md` helpers.
- Schema and format validation for frontmatter, Canvas JSON, and Base YAML.
- Graph improvement suggestions for unresolved links, reciprocal links, duplicate pages, Markdown links, and attachments.
- Karpathy-style wiki workflow tools for source ingestion, generated index refreshes, and chronological log entries.
- Literature and extraction ingestion from BibTeX/reference metadata, MinerU Markdown output, and PDF attachments.
- Optional MinerU CLI extraction followed by Obsidian source-note ingestion.
- Direct Zotero Desktop local API integration for search, metadata, child notes, annotations, PDF attachments, PDF text extraction, and one-step item ingestion.
- Vault-local defaults for output folders, template folders, default templates, and Zotero attachment naming.
- User template discovery from Obsidian Templates, Templater, and plugin defaults when creating notes.
- A `--doctor` readiness check and an optional read-only local smoke-check script.
- JSON Canvas creation, including automatic graph-to-canvas maps from vault wikilinks with grid, radial, grouped, and layered layouts.
- Obsidian Bases creation, including built-in templates for literature, project tasks, equipment, utilities, economics, and sources.
- Dataview note templates for literature, project tasks, equipment, utilities, economics, and sources.
- Local Obsidian CLI integration, including structured wrappers for read/open, backlinks, Base queries, properties, tasks, screenshots, plugin reloads, and move/rename dry-runs.

## Demo Screenshots

No screenshots are bundled in the public package yet. Add only sanitized demo
images that do not reveal private vault contents.

## Design References

This package explicitly borrows from two ideas:

- [Kepano's Obsidian Skills](https://github.com/kepano/obsidian-skills): split Obsidian work into modular Markdown, Canvas, Bases, CLI, and extraction-oriented workflows.
- [Karpathy's LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f): treat Obsidian as a persistent LLM-maintained wiki where knowledge accumulates through source ingestion, cross-links, graph health checks, index/log files, Canvas maps, and reusable views.

## Package Layout

The repository contains:

```text
obsidian-vault-mcp/
  .codex-plugin/plugin.json
  .github/workflows/
  .mcp.json
  .gitignore
  LICENSE
  pyproject.toml
  README.md
  requirements.txt
  docs/
  scripts/build_release.ps1
  scripts/obsidian_vault_mcp.py
  scripts/smoke_integrations.py
  scripts/obsidian_vault_mcp/
    __init__.py
    cli.py
    common.py
    helpers.py
    server.py
    tools.py
  skills/obsidian-vault/SKILL.md
  tests/
```

## Install

1. Clone or download this repository.
2. Install Python dependencies:

```bash
python -m pip install -r requirements.txt
```

For development, release checks, or the console command:

```bash
python -m pip install -e ".[dev]"
obsidian-vault-mcp --doctor --vault "path/to/vault"
```

3. Register this folder as a local Codex plugin or copy it into your host's
   local plugin directory.
4. Open Obsidian 1.12.7 or newer.
5. Confirm the core plugins `bases`, `canvas`, and `properties` are enabled.
6. Leave `.mcp.json` as `OBSIDIAN_VAULT_PATH=auto`, or set an explicit vault
   root in your own local configuration.

## Release Checks

Before tagging or uploading a release:

```bash
python -m ruff check .
python -m unittest discover -s tests
python -m py_compile scripts/obsidian_vault_mcp.py scripts/obsidian_vault_mcp/cli.py scripts/obsidian_vault_mcp/common.py scripts/obsidian_vault_mcp/helpers.py scripts/obsidian_vault_mcp/server.py scripts/obsidian_vault_mcp/tools.py
python scripts/obsidian_vault_mcp.py --doctor --vault "path/to/vault"
python scripts/smoke_integrations.py --vault "path/to/vault"
```

Build the portable plugin archive with:

```powershell
./scripts/build_release.ps1
```

The release zip should include `pyproject.toml`, the compatibility entrypoint,
the modular `scripts/obsidian_vault_mcp/` package, `scripts/smoke_integrations.py`,
docs, tests, and `skills/obsidian-vault/SKILL.md`.

## Portability Notes

- No local absolute vault path is embedded in the package.
- File writes are constrained to the resolved vault root.
- Non-vault folders are rejected by default unless `OBSIDIAN_ALLOW_NON_VAULT=true`.
- Existing files require `overwrite=true` before replacement.
- Zotero access uses the user's own local Zotero Desktop API.
- Obsidian CLI wrapper `vault` arguments use Obsidian vault names, while direct
  file tools use filesystem `vault_path` values.
- The smoke script only performs dry-run vault writes; it should not change a
  user's vault.
- MinerU CLI and MinerU MCP are optional external tools and are not installed
  automatically by this plugin.
