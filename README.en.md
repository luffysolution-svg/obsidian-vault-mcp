# Obsidian Vault

Local MCP plugin for Codex, Claude Code, and OpenCode — maintain Obsidian vaults as persistent linked wikis.

[中文 README](./README.md) | [中文文档站](./docs/index.md)

## Quick Start

For a detailed setup guide, see [Technical Guide](./docs/TECHNICAL_GUIDE.md).

From the plugin directory:

```bash
python -m pip install -r requirements.txt
python scripts/obsidian_vault_mcp.py --doctor --doctor-format text --vault /path/to/your-vault
```

Register this folder as a local Codex plugin, or add the MCP server to Claude
Code or OpenCode, then restart or reload your MCP client. Keep personal vault paths, Zotero storage paths, API tokens, and private
note contents in local configuration only; do not commit them to the repository.

It provides:

- MCP tools for vault file listing, search, reading, writing, note creation, and YAML property updates.
- Dry-run diff previews for write operations before changing vault files.
- Batch edit transactions with multi-file preview, apply, vault-local backups, and rollback.
- Wikilink helpers for adding related links and building backlink-aware graph data with aliases, tags, ambiguous links, and unresolved links. Graph scanning is body-only — wikilinks inside YAML frontmatter values are not counted as edges.
- Frontmatter citation fields (`related`, `cites`, `references`, `entities`, `concepts`, `sources`) are extracted as typed edges distinct from body wikilinks, enabling richer literature citation graphs.
- Graph results are mtime-cached per vault/folder; repeated calls return the cached result until a file changes, significantly improving performance on large literature vaults.
- Vault lint checks for orphan notes, dead ends, missing wiki helper files, duplicate keys, and frontmatter consistency.
- Schema and format validation for Markdown frontmatter, Canvas JSON, and Base YAML files.
- Graph improvement suggestions for unresolved links, reciprocal links (capped via `max_reciprocal` to avoid noise), possible duplicate pages (word-boundary-aware, so "My Note" and "MyNote" are not false positives), Markdown links, and attachment embeds.
- Karpathy-style wiki workflow tools for refreshing `index.md`, appending `log.md`, and ingesting source notes into linked source/entity/concept pages.
- Literature and extraction ingestion from BibTeX/reference metadata, existing MinerU Markdown output, optional MinerU CLI extraction, and PDF attachments.
- Direct Zotero Desktop local API integration for collection listing, search, item metadata, child notes, annotations, PDF attachments, PDF text extraction, and one-step item ingestion.
- Zotero round-trip metadata with `zotero://` select/PDF links, duplicate detection by Zotero key, DOI, citekey, or title, and configurable PDF attachment naming.
- Collection names resolved to human-readable labels at import time (`collections` stores names like `苯乙烯优化`, not raw keys like `HXSD675W`); type-specific fields omitted from frontmatter when empty.
- Optional user template discovery from Obsidian Templates, Templater, or plugin config when creating notes.
- Vault-local defaults for output folders, index/log paths, template folders, and Zotero attachment naming.
- A `--doctor` check for vault resolution, templates, dependencies, and optional integrations.
- JSON Canvas creation for visual maps, including automatic graph-to-canvas layout from vault wikilinks with grid, radial, grouped, and layered layouts; layered layout supports a custom `layer_order_json` parameter.
- Obsidian Bases creation for table/card/list views, including built-in Base templates for literature, project tasks, equipment, utilities, economics, and sources.
- Dataview note templates for the same literature, project task, equipment, utilities, economics, and sources workflows.
- A safe wrapper around the local `obsidian` CLI plus structured helpers for read/open, backlinks, Base queries, properties, tasks, screenshots, plugin reloads, and move/rename dry-runs.
- A workflow skill (`skills/obsidian-vault/SKILL.md`) that composes this plugin with `obsidian-markdown`, `json-canvas`, and `obsidian-bases`. After `pip install` the skill file is located inside the Python package at `<site-packages>/obsidian_vault_mcp/skills/obsidian-vault/SKILL.md`; after a source clone it is at `skills/obsidian-vault/SKILL.md` in the repository root.

## Demo Assets

Screenshots are not included in this release. Sanitized demo images may be added in a future release.

## Design References

This plugin intentionally borrows ideas from two references:

- [Kepano's Obsidian Skills](https://github.com/kepano/obsidian-skills): the domain is split into Obsidian Markdown, JSON Canvas, Bases, CLI, and extraction-oriented workflows. This plugin follows that modular approach, then bundles the common local vault operations behind MCP tools.
- [Karpathy's LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f): the vault is treated as a persistent, compounding wiki maintained by an LLM. The plugin supports that pattern with hub notes, wikilinks, graph checks, index/log-friendly workflows, Canvas maps, and Bases views.

See [References and Attribution](./docs/REFERENCES.md) for the fuller rationale.

## Configure

Set `OBSIDIAN_VAULT_PATH` in local MCP configuration, or pass `vault_path` to
each tool call. The checked-in `.mcp.json` defaults to `auto`, which asks the
local Obsidian CLI for the currently active vault path and falls back to the
process working directory if the CLI is unavailable.

```json
{
  "OBSIDIAN_VAULT_PATH": "auto",
  "OBSIDIAN_CLI_COMMAND": "obsidian"
}
```

The CLI wrapper expects Obsidian 1.12.7 or newer and the `obsidian` command on PATH.

Direct Zotero tools expect Zotero Desktop's local API at `http://127.0.0.1:23119/api`. Override it with `ZOTERO_LOCAL_API` if needed.

MinerU support is optional. Existing MinerU Markdown can be ingested without
installing MinerU. To parse documents directly, install `mineru-open-api` and
use the `obsidian_mineru_*` tools. `flash-extract` works without a token for
small/simple documents; precision `extract` may require a MinerU token or a
local MinerU CLI auth configuration. This plugin does not install MinerU CLI,
MinerU MCP, Zotero Desktop, or Obsidian CLI automatically.

Recommended three-step workflow when the document belongs to a Zotero item:

1. `obsidian_ingest_zotero_item` → imports the item into `literature/` with full YAML, notes, and annotations.
2. `obsidian_mineru_extract_and_ingest` with `zotero_key=<key>` → parses the PDF into a MinerU source note and appends `mineru_markdown: [[...]]` to the literature note YAML.
3. The literature note body and all other YAML fields are left unchanged; only the clickable MinerU link is added.

MinerU extraction calls several MinerU/OpenXLab endpoints. If you use a VPN,
proxy, or fake-IP DNS mode, make sure these domains are reachable and preferably
routed directly:

- `mineru.net`
- `mineru.oss-cn-shanghai.aliyuncs.com`
- `cdn-mineru.openxlab.org.cn`
- `*.openxlab.org.cn`

A common failure mode is that the parse task and OSS upload succeed, but
downloading `full.md` from `cdn-mineru.openxlab.org.cn` fails with TLS/EOF
errors. In that case, check proxy/DNS rules before debugging this plugin.

By default, paths must resolve to a folder containing `.obsidian`. Set `OBSIDIAN_ALLOW_NON_VAULT=true` only when intentionally using a plain Markdown folder.

## Vault Defaults

You can keep reusable defaults in `.obsidian-vault-mcp.json` at the vault root,
or in `.obsidian/obsidian-vault-mcp.json`. Tool arguments still win when they
are explicitly set away from their built-in defaults.

```json
{
  "literatureFolder": "01-literature",
  "mineruSourceFolder": "02-sources/mineru",
  "pdfSourceFolder": "02-sources/pdf",
  "entitiesFolder": "entities",
  "conceptsFolder": "concepts",
  "zoteroAttachmentsFolder": "assets/zotero",
  "zoteroAttachmentNameStrategy": "zotero_key",
  "indexPath": "index.md",
  "logPath": "log.md",
  "templateFolder": "Templates",
  "defaultTemplate": "Literature"
}
```

Zotero attachment naming strategies are `original`, `zotero_key`, `citekey`,
`title_year`, and `parent_key`.

## User Templates

`obsidian_list_user_templates` discovers Markdown templates from:

- the Obsidian Templates core plugin config at `.obsidian/templates.json`;
- the Templater plugin config at `.obsidian/plugins/templater-obsidian/data.json`;
- the optional `templateFolder` and `defaultTemplate` plugin defaults above.

`obsidian_create_note` can apply a template with `template_path`,
`template_name`, `use_template=true`, or a configured `defaultTemplate`. It
performs safe text replacement for variables such as `{{title}}`, `{{body}}`,
`{{date}}`, `{{time}}`, and frontmatter property names. It does not execute
Templater JavaScript.

## Doctor Check

Run a local readiness check without starting the MCP server:

```bash
python scripts/obsidian_vault_mcp.py --doctor --doctor-format text --vault /path/to/your-vault
```

Optional integrations such as Zotero Desktop, Obsidian CLI, MinerU, and PDF text
extraction are reported as checks; they do not need to be available for the core
vault tools to work. Omit `--doctor-format text` when you want JSON output for
automation or bug reports.

## Batch Edit Plans

Batch edit tools accept either a JSON array or an object with an `operations`
array. Each operation may use `op`, `operation`, or `type` for the action name.
Supported actions are `write`, `update_properties`, `append`, `replace`, and
`delete`.

```json
{
  "operations": [
    {
      "operation": "update_properties",
      "path": "Projects/Alpha.md",
      "properties": { "status": "draft" }
    },
    {
      "operation": "append",
      "path": "Projects/Alpha.md",
      "content": "\n\nReviewed by Codex."
    }
  ]
}
```

Run `obsidian_preview_edit_plan` first, then `obsidian_apply_edit_plan`. Applied
plans create vault-local backups under `.obsidian-vault-backups/` so
`obsidian_rollback_edit_plan` can restore the previous state.

## Install Dependencies

The MCP server is Python-based:

```bash
python -m pip install -r requirements.txt
```

For editable development installs, use the package metadata in
`pyproject.toml`:

```bash
python -m pip install -e ".[dev]"
obsidian-vault-mcp --doctor --doctor-format text --vault /path/to/your-vault
```

After opening Obsidian and Zotero Desktop, run the local smoke checks:

```bash
python scripts/smoke_integrations.py --vault /path/to/your-vault
```

The smoke script is intentionally read-only except for dry-run write previews.
It checks vault resolution, dry-run note creation, Zotero local API access, and
the Obsidian CLI.

`PyYAML` is used for full YAML compatibility. `pypdf` is used for Zotero PDF text extraction; the code can fall back to `PyPDF2` when it is already installed, but packaged installs should include `pypdf`.

See [Technical Guide](./docs/TECHNICAL_GUIDE.md) for local plugin setup, or the full installation and configuration walkthrough.

## Code Architecture

The checked-in MCP entrypoint remains `scripts/obsidian_vault_mcp.py` so
existing `.mcp.json` installs keep working. That file is intentionally thin:
it adds the `scripts/` directory to `sys.path`, imports the package, and runs
the server.

The implementation lives in `scripts/obsidian_vault_mcp/`:

- `common.py`: shared imports, constants, and MCP tool registration metadata.
- `helpers.py`: vault-safe paths, frontmatter/YAML handling, graph helpers,
  Canvas/Base/schema utilities, edit-plan support, Zotero/MinerU helpers, and
  other non-tool implementation details.
- `tools.py`: public MCP tool functions and CLI wrappers.
- `server.py`: FastMCP server construction and tool registration.
- `__init__.py`: package exports for tests and direct imports.

This keeps the published command stable while avoiding a single multi-thousand
line server script as the project grows.

### Optional External Tools

- **Zotero Desktop** ([Download](https://www.zotero.org/download/), current version 9.x): required only for direct Zotero library search/import.
- **Obsidian CLI**: built into Obsidian 1.12.7+, enable at Settings → General → Enable Obsidian CLI; required only for app-backed read/open/backlinks/Base/property/task/screenshot operations.
- **MinerU** ([GitHub](https://github.com/opendatalab/MinerU)): required only for `obsidian_mineru_extract` and `obsidian_mineru_extract_and_ingest`. Install with `pip install -U "mineru[full]"`. Existing MinerU Markdown can be ingested without installing MinerU.
- **MinerU MCP**: optional companion server. Codex can use MinerU MCP to parse a document, then use this plugin to ingest the generated Markdown. This plugin does not call MinerU MCP internally.

### Zotero Plugin Dependencies

> All plugins below support Zotero 8 / 9. Download the `.xpi` file from the Releases page and install via Zotero → Tools → Add-ons → Install Add-on From File.

| Plugin | Purpose | Required? | Install |
|--------|---------|-----------|---------|
| **Better BibTeX for Zotero** | Generates stable `citekey` values (e.g. `chenLowvalence2024`) used for note naming, duplicate detection, and the `citekey` PDF attachment naming strategy | Strongly recommended; falls back to Zotero key if absent | [GitHub Releases](https://github.com/retorquere/zotero-better-bibtex/releases) |
| **Ethereal Style (ZoteroStyle)** | Assigns custom names to annotation colors (e.g. 背景/实验/结果/方法); those names appear in Obsidian callout labels after import | Optional; falls back to English color names (yellow/red/green…) | [GitHub Releases](https://github.com/MuiseDestiny/zotero-style/releases) |
| **Zotero PDF Translate** | Auto-translates PDF annotation text; the translation is written to `annotationComment` and imported into the **Note:** field in Obsidian | Optional; recommended if you need bilingual annotations | [GitHub Releases](https://github.com/windingwind/zotero-pdf-translate/releases) |

Zotero Desktop's local HTTP service on port `23119` is built-in and requires no extra plugins.

### Recommended Obsidian Plugins

The following Obsidian community plugins work well alongside this MCP plugin. Install them from Obsidian Settings → Community Plugins:

| Plugin | Purpose | GitHub |
|--------|---------|--------|
| **Dataview** | Query vault frontmatter properties; this plugin can generate Dataview query notes | [GitHub](https://github.com/blacksmithgu/obsidian-dataview) |
| **Templater** | Advanced template engine; this plugin discovers and applies Templater templates | [GitHub](https://github.com/SilentVoid13/Templater) |
| **Zotero Integration** | Import literature notes directly from Zotero inside Obsidian (complementary to this plugin, can be used in parallel) | [GitHub](https://github.com/mgmeyers/obsidian-zotero-integration) |

For structured Obsidian CLI wrappers, the optional `vault` argument is the
Obsidian vault name known to the app, not a filesystem path. If omitted, the CLI
uses the active Obsidian vault. Direct file tools such as `obsidian_read_file`
and `obsidian_create_note` still accept `vault_path` filesystem paths.

Quick MinerU connectivity checks on Windows:

```powershell
mineru-open-api version
curl.exe -I https://mineru.net
curl.exe -I https://cdn-mineru.openxlab.org.cn
Resolve-DnsName cdn-mineru.openxlab.org.cn
```

If `cdn-mineru.openxlab.org.cn` resolves to a fake-IP range such as
`198.18.x.x`, configure your proxy/VPN DNS rules so MinerU/OpenXLab domains use
a working route.

## AI-Assisted Setup

Paste this prompt into any AI coding assistant (Codex, Claude Code, OpenCode,
etc.) to have it install and configure the plugin automatically:

```text
Install and configure the open-source Obsidian Vault MCP plugin from
https://github.com/luffysolution-svg/obsidian-vault-mcp.

Please:
1. Clone the repository to a suitable local plugins folder.
2. Install its Python dependencies with `python -m pip install -e .`.
3. Register it as a local MCP server. Use the method that matches the AI client
   you are running in:
   - Codex: register using the checked-in `.mcp.json` as a local Codex plugin.
   - Claude Code: run `claude mcp add obsidian-vault obsidian-vault-mcp`, or add
     the server block from `.mcp.json` to `~/.claude/settings.json`.
   - OpenCode: copy `.opencode.json` from the repository root to the project
     directory, or merge its `mcp` block into `~/.opencode.json`.
   - Trae: add the server block from `.mcp.json` to `.trae/mcp.json` in the
     project root, or paste it in Trae's MCP settings UI.
   - CodeBuddy: the checked-in `.mcp.json` is picked up automatically from the
     project root; or paste the server block in CodeBuddy's MCP settings UI.
   - Kimi Code: run `kimi mcp add --transport stdio obsidian-vault obsidian-vault-mcp`
     and set env `OBSIDIAN_VAULT_PATH=auto`, or edit `~/.kimi/mcp.json` directly.
   - Other MCP clients: register a stdio server with command
     `obsidian-vault-mcp` and env `OBSIDIAN_VAULT_PATH=auto`.
4. Use `OBSIDIAN_VAULT_PATH=auto` by default. If auto-detection fails, ask me
   for my local Obsidian vault path and configure it only in my local
   MCP/plugin settings.
5. Do not modify or publish my Obsidian vault contents.
6. Verify the server can start, then run `python -m unittest discover -s tests`.
7. Tell me how to restart/reload the AI client so the new MCP tools become
   available.

Optional: if I want Zotero features, remind me to open Zotero Desktop so its
local API at `http://127.0.0.1:23119/api` is reachable. For best results,
also install Better BibTeX for Zotero (https://retorque.re/zotero-better-bibtex/)
to enable stable citekeys. If I use Ethereal Style (ZoteroStyle) to assign
custom color labels to annotations, those labels will be picked up automatically.

Optional: if I want MinerU document parsing, check whether `mineru-open-api`
is installed. If it is not installed, tell me how to install it. Do not store
or commit MinerU tokens in the repository. Use `flash-extract` when I do not
have a token, and use precision `extract` only when I have configured MinerU
authentication locally.
```

## Deploy With Claude Code

Install the package, then add the MCP server with the Claude Code CLI:

```bash
python -m pip install -e .
claude mcp add obsidian-vault obsidian-vault-mcp
```

Or add it manually to your Claude Code settings (`~/.claude/settings.json`):

```json
{
  "mcpServers": {
    "obsidian-vault": {
      "type": "stdio",
      "command": "obsidian-vault-mcp",
      "env": {
        "OBSIDIAN_VAULT_PATH": "auto",
        "OBSIDIAN_CLI_COMMAND": "obsidian"
      }
    }
  }
}
```

The root-level `plugin.json` declares this plugin for Claude Code's plugin system.

## Deploy With OpenCode

Install the package, then copy `.opencode.json` from the repository root to
your project directory, or merge the `mcp` block into your global
`~/.opencode.json`:

```json
{
  "mcp": {
    "obsidian-vault": {
      "type": "local",
      "command": ["obsidian-vault-mcp"],
      "environment": {
        "OBSIDIAN_VAULT_PATH": "auto",
        "OBSIDIAN_CLI_COMMAND": "obsidian"
      }
    }
  }
}
```

## Public Release Safety

This repository is intended to be reusable by other users. The checked-in
configuration is portable by default:

- `.mcp.json` uses the installed `obsidian-vault-mcp` entry point instead of
  an absolute script path. Users install the package with `pip install -e .`
  once; all three clients then share the same command.
- `OBSIDIAN_VAULT_PATH` defaults to `auto`; users can set their own local vault
  path without committing it.
- Zotero integration points at the user's own local Zotero Desktop API.
- File tools reject non-vault folders unless `OBSIDIAN_ALLOW_NON_VAULT=true` is
  explicitly set by the user.
- Unit tests create temporary vaults and do not write to a real vault.

## Portability Notes

- The plugin does not hard-code a vault path. `auto` follows the vault currently active in the local Obsidian CLI.
- All file operations are constrained to the resolved vault root.
- Existing files are not overwritten unless the tool call passes `overwrite=true`.
- Write tools support `dry_run=true` to return a unified diff without modifying files.
- Wiki workflow tools keep generated sections inside marker comments so hand-written note content can stay outside the managed block.
- Obsidian CLI features require Obsidian Desktop to be running. Direct file tools still work when the CLI is unavailable if `OBSIDIAN_VAULT_PATH` is set.
- `.mcp.json` uses the installed `obsidian-vault-mcp` entry point. Install the
  package with `pip install -e .` before starting any MCP client.

## Contributing and Publishing

See [Deployment Guide](./docs/DEPLOYMENT.md) for the full release checklist and GitHub publishing flow.

## Useful Prompts

- "Show me the structure of this Obsidian vault."
- "Create a linked wiki note with YAML properties."
- "Add wikilinks between these notes and report orphans."
- "Preview the changes before updating these vault notes."
- "Preview and apply a batch edit plan, then rollback if needed."
- "Lint this vault and show unresolved links, dead ends, and missing index/log files."
- "Validate frontmatter, Canvas, and Base schemas across this vault."
- "Preview schema default fixes for notes that are missing frontmatter."
- "Suggest graph improvements for unresolved and weakly linked pages."
- "Refresh the wiki index and append a log entry."
- "Ingest this source into linked source, entity, and concept notes."
- "Ingest this BibTeX entry or MinerU extraction into the literature wiki."
- "Check whether MinerU CLI is available for this vault."
- "Use MinerU flash-extract on this PDF and ingest the result into Obsidian."
- "Search Zotero and ingest this Zotero item into Obsidian."
- "Create a source note for this PDF attachment."
- "Create an equipment or economics Base template for this project."
- "Create a Dataview equipment table note."
- "Create a Canvas map of this topic cluster."
- "Generate a Canvas knowledge map from this vault's wikilinks."
- "Create a Base view for all project notes."
- "Use the Obsidian CLI to read backlinks or query a Base."

## References

- Kepano's Obsidian skills split the domain into Markdown, Bases, Canvas, CLI, and extraction skills: https://github.com/kepano/obsidian-skills
- Karpathy's LLM Wiki pattern frames Obsidian as an IDE for a persistent, LLM-maintained wiki: https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f
- Obsidian CLI documentation: https://help.obsidian.md/cli
- Codex Skills documentation: https://developers.openai.com/codex/skills
- Codex Plugins documentation: https://developers.openai.com/codex/plugins
- OpenCode MCP documentation: https://docs.opencode.ai/docs/mcp-servers
- OpenCode configuration reference: https://opencode-ai-opencode.mintlify.app/core-concepts/configuration
- Zotero local connector server documentation: https://www.zotero.org/support/dev/client_coding/connector_http_server
- Zotero Web API v3 basics: https://www.zotero.org/support/dev/web_api/v3/basics
- MinerU Open API CLI documentation: https://pkg.go.dev/github.com/opendatalab/MinerU-Ecosystem/cli
