# Configuration Guide

This guide explains how to install the Obsidian Vault MCP plugin, where to keep
the plugin files, how Codex discovers the bundled skill and MCP server, and how
to configure optional Obsidian CLI, Zotero, and MinerU integrations.

All paths below are examples. Replace them with paths on your own machine and
keep personal paths, API tokens, Zotero storage paths, and private vault names
out of committed files.

## What You Need

- Python 3.10 or newer.
- Git, or the ability to download this repository as a ZIP archive.
- Obsidian Desktop with at least one local vault.
- Codex or another MCP host that can run stdio MCP servers.
- Zotero Desktop only if you want Zotero library search/import tools.
- Obsidian 1.12.7 or newer only if you want app-backed Obsidian CLI tools.
- MinerU Open API CLI only if you want this plugin to parse PDFs/documents
  directly before ingesting the Markdown output.

Check Python:

```powershell
python --version
python -m pip --version
```

On Windows, install Python from python.org or the Microsoft Store if `python`
is not found, and enable "Add Python to PATH" when using the python.org
installer.

## Repository and Plugin Storage

Keep two locations conceptually separate:

- Source checkout: the folder where you edit this repository, for example
  `F:/chemical-design/plugins/obsidian-vault`.
- Installed Codex plugin copy: the copy Codex loads after installation. Codex
  plugin marketplaces install plugins into a cache under
  `~/.codex/plugins/cache/<marketplace>/<plugin>/<version>/`.

For local development, a repo-scoped marketplace is usually easiest:

```text
your-repo/
  .agents/plugins/marketplace.json
  plugins/obsidian-vault/
    .codex-plugin/plugin.json
    .mcp.json
    README.md
    docs/
    scripts/
    skills/obsidian-vault/SKILL.md
```

For a personal install, keep the plugin under a personal plugin folder such as:

```text
~/.codex/plugins/obsidian-vault/
~/.agents/plugins/marketplace.json
```

Codex reads the marketplace file, installs the plugin into its plugin cache,
and then loads the installed copy. After changing plugin files, update the
plugin directory that the marketplace points to and restart Codex so it picks
up the refreshed copy.

## Clone or Download

Option A: clone with Git:

```powershell
cd C:\path\to\plugins
git clone https://github.com/luffysolution-svg/obsidian-vault-mcp.git obsidian-vault
cd obsidian-vault
```

Option B: download from GitHub:

1. Open `https://github.com/luffysolution-svg/obsidian-vault-mcp`.
2. Select `Code` -> `Download ZIP`.
3. Extract the ZIP to a stable local folder.
4. Open a terminal in the extracted plugin root.

The plugin root is the folder that contains `.codex-plugin/plugin.json`,
`.mcp.json`, `README.md`, `scripts/`, and `skills/`.

## Install Python Dependencies

From the plugin root:

```powershell
python -m pip install -r requirements.txt
```

For development and the `obsidian-vault-mcp` console command:

```powershell
python -m pip install -e ".[dev]"
```

The checked-in MCP entrypoint remains:

```text
scripts/obsidian_vault_mcp.py
```

The implementation package lives beside it:

```text
scripts/obsidian_vault_mcp/
```

Keep both the file and the package directory together.

## Register the Plugin in Codex

This plugin follows the Codex plugin layout:

```text
.codex-plugin/plugin.json
.mcp.json
skills/obsidian-vault/SKILL.md
```

The manifest points Codex at the bundled skill folder and MCP configuration:

```json
{
  "skills": "./skills/",
  "mcpServers": "./.mcp.json"
}
```

The `.mcp.json` file is intentionally portable:

```json
{
  "mcpServers": {
    "obsidian-vault": {
      "type": "stdio",
      "command": "python",
      "args": ["${CLAUDE_PLUGIN_ROOT}/scripts/obsidian_vault_mcp.py"],
      "env": {
        "OBSIDIAN_VAULT_PATH": "auto",
        "OBSIDIAN_CLI_COMMAND": "obsidian"
      }
    }
  }
}
```

Do not replace `${CLAUDE_PLUGIN_ROOT}` with your personal path in committed
files. If a host requires an absolute path, keep that override in the host's
local configuration only.

### Repo-Scoped Local Marketplace

Create or update `$REPO_ROOT/.agents/plugins/marketplace.json`:

```json
{
  "name": "local-repo",
  "interface": {
    "displayName": "Local Repo Plugins"
  },
  "plugins": [
    {
      "name": "obsidian-vault",
      "source": {
        "source": "local",
        "path": "./plugins/obsidian-vault"
      },
      "policy": {
        "installation": "AVAILABLE",
        "authentication": "ON_INSTALL"
      },
      "category": "Productivity"
    }
  ]
}
```

Store the plugin at `$REPO_ROOT/plugins/obsidian-vault`. Restart Codex, open
the plugin directory, choose the local marketplace, and install the plugin.

### Personal Local Marketplace

Create or update `~/.agents/plugins/marketplace.json` and point it at the
personal plugin copy, for example `./.codex/plugins/obsidian-vault` if the
marketplace root is your home directory. The marketplace path must be relative
to the marketplace root and should start with `./`.

## Where the Skill Goes

The bundled skill lives inside the plugin:

```text
skills/obsidian-vault/SKILL.md
```

Codex loads bundled skills after the plugin is installed. You do not need to
copy this skill into `~/.agents/skills` for normal plugin use.

Use direct skill locations only for authoring or one-off local skills:

- Repo skill: `$REPO_ROOT/.agents/skills/<skill-name>/SKILL.md`
- User skill: `~/.agents/skills/<skill-name>/SKILL.md`
- Admin skill: `/etc/codex/skills/<skill-name>/SKILL.md`

For reusable distribution, keep the skill bundled in this plugin.

## Configure the Obsidian Vault

`OBSIDIAN_VAULT_PATH` controls the default vault:

```json
"OBSIDIAN_VAULT_PATH": "auto"
```

`auto` asks the local Obsidian CLI for the active vault path. It also falls
back to the current working directory if that directory contains `.obsidian`.

If `auto` cannot resolve a vault, set a local explicit vault path:

```json
"OBSIDIAN_VAULT_PATH": "C:/path/to/your-vault"
```

An Obsidian vault root is the folder that contains `.obsidian`:

```powershell
Test-Path "C:\path\to\your-vault\.obsidian"
```

The plugin rejects plain Markdown folders by default. Set
`OBSIDIAN_ALLOW_NON_VAULT=true` only when you intentionally want to use a
non-Obsidian folder.

## Vault-Local Defaults

Reusable output defaults belong in the vault, not in the plugin repository.
Create either:

```text
<vault>/.obsidian-vault-mcp.json
<vault>/.obsidian/obsidian-vault-mcp.json
```

Example:

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

Tool arguments still win when explicitly provided.

## Obsidian CLI

Obsidian CLI is optional. Direct vault file tools still work without it when
`OBSIDIAN_VAULT_PATH` is explicit or the current directory is a vault.

Use the CLI for app-backed operations such as:

- reading or opening the active file through Obsidian;
- backlinks, outgoing links, unresolved links, orphans, and dead ends;
- Base queries;
- property reads/writes through Obsidian;
- task lists;
- screenshots and plugin reloads;
- move/rename actions that can follow Obsidian's link-update settings.

Install and enable the official CLI:

1. Install or update Obsidian with the 1.12.7+ installer.
2. Open Obsidian.
3. Go to `Settings` -> `General`.
4. Enable `Command line interface`.
5. Follow Obsidian's prompt to register the `obsidian` command.
6. Restart the terminal.

Check availability:

```powershell
obsidian version
obsidian help
obsidian vault info=path
```

For app-backed CLI wrappers, the optional `vault` parameter is an Obsidian
vault name or ID, not a filesystem path. Direct file tools use `vault_path`
as a filesystem path.

## Zotero Local API

Zotero integration is optional and uses Zotero Desktop's local API:

```text
http://127.0.0.1:23119/api
```

Open Zotero Desktop before using Zotero-backed tools. In Zotero 7+, make sure
local API access is enabled in Zotero's advanced settings if your installation
does not expose the local API by default.

The plugin uses local-library endpoints such as:

```text
GET /api/users/0/items?limit=1&format=json
GET /api/users/0/items/<itemKey>?format=json
GET /api/users/0/items/<itemKey>/children?format=json
```

Override the API base only in local configuration:

```json
"ZOTERO_LOCAL_API": "http://127.0.0.1:23119/api"
```

Useful checks:

```powershell
curl.exe "http://127.0.0.1:23119/connector/ping"
python scripts/obsidian_vault_mcp.py --doctor --doctor-format text --vault "C:/path/to/your-vault"
python scripts/smoke_integrations.py --vault "C:/path/to/your-vault"
```

Imported Zotero notes can include:

- `zoteroKey`;
- `zoteroSelect`;
- `zoteroLinks`;
- PDF item keys and `zotero://open-pdf/...` links;
- copied vault attachments when `copy_pdf_attachments=true`;
- original local PDF paths when attachments are linked instead of copied.

If Zotero stores attachments outside the default `~/Zotero/storage` location,
set `ZOTERO_STORAGE_DIR` in local configuration.

## MinerU API and CLI

MinerU integration is optional.

Use `obsidian_ingest_mineru_markdown` when MinerU already produced Markdown.
Install MinerU Open API CLI only when this plugin should parse documents
directly with `obsidian_mineru_extract` or `obsidian_mineru_extract_and_ingest`.

Install the current MinerU Open API CLI:

```powershell
irm https://cdn-mineru.openxlab.org.cn/open-api-cli/install.ps1 | iex
mineru-open-api version
```

Linux/macOS:

```bash
curl -fsSL https://cdn-mineru.openxlab.org.cn/open-api-cli/install.sh | sh
mineru-open-api version
```

The older npm package may exist in some environments, but the current MinerU
Open API CLI documentation uses the single-binary installer above.

### MinerU Tokens

`flash-extract` does not require a token and is best for small/simple first
runs. `extract` requires authentication and supports richer output and larger
jobs.

Get a MinerU token from:

```text
https://mineru.net/apiManage/token
```

Configure the token locally, never in committed files:

```powershell
mineru-open-api auth
```

or:

```powershell
$env:MINERU_TOKEN = "your-token"
```

Token resolution order for the CLI:

1. `--token`
2. `MINERU_TOKEN`
3. `~/.mineru/config.yaml`

This plugin also reports `MINERU_API_TOKEN` in `obsidian_mineru_status` for
compatibility with older local setups, but the current CLI standard is
`MINERU_TOKEN`.

### MinerU Modes

Use `flash-extract` when:

- you have no token;
- the file is small and simple;
- Markdown-only output is enough;
- you are testing connectivity.

Use `extract` when:

- you need OCR, table/formula recognition, or extra formats;
- the file is larger;
- you have configured a MinerU token.

Examples:

```powershell
mineru-open-api flash-extract report.pdf -o ./out/
mineru-open-api flash-extract report.pdf --language en --pages 1-5 -o ./out/
mineru-open-api auth
mineru-open-api extract report.pdf -f md,docx -o ./results/
```

Plugin tools map to these commands:

- `obsidian_mineru_status`: checks CLI availability and local token env vars.
- `obsidian_mineru_extract`: runs MinerU and saves output under the vault.
- `obsidian_mineru_extract_and_ingest`: runs MinerU, finds Markdown output, and
  imports it into the Obsidian wiki.

### MinerU Network Checks

MinerU uses several endpoints. A parse task can succeed while result download
fails, so check all of these when debugging:

```powershell
curl.exe -I https://mineru.net
curl.exe -I https://cdn-mineru.openxlab.org.cn
Resolve-DnsName cdn-mineru.openxlab.org.cn
```

Make sure these domains are reachable:

- `mineru.net`
- `mineru.oss-cn-shanghai.aliyuncs.com`
- `cdn-mineru.openxlab.org.cn`
- `*.openxlab.org.cn`

VPN, proxy, and fake-IP DNS modes can break result downloads, especially when
`cdn-mineru.openxlab.org.cn` resolves to ranges such as `198.18.x.x`.

## Verify the Setup

Run the doctor check:

```powershell
python scripts/obsidian_vault_mcp.py --doctor --doctor-format text --vault "C:/path/to/your-vault"
```

If installed in editable mode:

```powershell
obsidian-vault-mcp --doctor --doctor-format text --vault "C:/path/to/your-vault"
```

Run unit tests:

```powershell
python -m unittest discover -s tests
```

Run read-only integration smoke checks after opening Obsidian and Zotero:

```powershell
python scripts/smoke_integrations.py --vault "C:/path/to/your-vault"
```

Zotero, Obsidian CLI, MinerU, and PDF extraction are optional checks. A warning
there does not mean the core vault tools are unusable.

## Troubleshooting

| Symptom | Likely Cause | Fix |
| --- | --- | --- |
| `python` is not recognized | Python is missing or not on PATH | Install Python and enable PATH integration |
| `No module named mcp` | Dependencies are not installed | Run `python -m pip install -r requirements.txt` |
| `Could not resolve an Obsidian vault` | `auto` cannot find a vault | Open Obsidian or set `OBSIDIAN_VAULT_PATH` locally |
| `Path does not look like an Obsidian vault root` | The path lacks `.obsidian` | Select the vault root folder |
| `Obsidian CLI command not found` | CLI is not enabled or not on PATH | Enable Obsidian CLI and restart the terminal |
| Zotero API check fails | Zotero is closed or local API is disabled/blocked | Open Zotero and check `127.0.0.1:23119` |
| MinerU check fails | MinerU CLI is not installed | Install `mineru-open-api` only if direct extraction is needed |
| Markdown download from MinerU fails | Proxy/DNS route issue | Check MinerU/OpenXLab domains and fake-IP rules |
| MCP tools do not appear | Codex has not reloaded the plugin | Restart Codex or reload MCP/plugin state |
| Existing file write is rejected | Existing files are protected | Pass `overwrite=true` only after reviewing the target |

## Official References

- Obsidian CLI: https://obsidian.md/help/cli
- Codex Skills: https://developers.openai.com/codex/skills
- Codex Plugins: https://developers.openai.com/codex/plugins
- Codex plugin authoring: https://developers.openai.com/codex/plugins/build
- Zotero connector HTTP server: https://www.zotero.org/support/dev/client_coding/connector_http_server
- Zotero Web API v3 basics: https://www.zotero.org/support/dev/web_api/v3/basics
- MinerU Open API CLI: https://pkg.go.dev/github.com/opendatalab/MinerU-Ecosystem/cli
- MinerU Ecosystem: https://github.com/opendatalab/MinerU-Ecosystem
