# Install

## Requirements

- Python 3.10 or newer.
- Obsidian with a local vault.
- Zotero Desktop if you want Zotero integration.
- Obsidian 1.12.7 or newer plus the `obsidian` CLI if you want app-backed CLI
  features.
- MinerU CLI (`mineru-open-api`) if you want this plugin to parse documents
  before ingesting them. Existing MinerU Markdown can be ingested without the
  CLI.

## Local Plugin Install

1. Clone or download this repository.
2. Install the Python dependencies:

```bash
python -m pip install -r requirements.txt
```

For development or command-line use, install the package in editable mode:

```bash
python -m pip install -e ".[dev]"
obsidian-vault-mcp --doctor --vault "path/to/vault"
```

3. Register this folder as a local Codex plugin, or copy the folder into your
   host application's local plugin directory.
4. Keep `.mcp.json` as-is for portable installs:

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

The configured script path points to `scripts/obsidian_vault_mcp.py`. That
file is a small compatibility entrypoint; the implementation package lives next
to it in `scripts/obsidian_vault_mcp/`, so both the file and directory must be
kept together.

Editable installs also expose the `obsidian-vault-mcp` console command. The
checked-in `.mcp.json` continues to use the compatibility script so local plugin
installs remain portable.

5. If `auto` cannot find your vault, set `OBSIDIAN_VAULT_PATH` locally to your
   vault root. Do not commit personal vault paths to the repository.

## Vault Defaults and Templates

Optional vault-local defaults can be stored in `.obsidian-vault-mcp.json` at the
vault root, or `.obsidian/obsidian-vault-mcp.json`:

```json
{
  "literatureFolder": "01-literature",
  "zoteroAttachmentsFolder": "assets/zotero",
  "zoteroAttachmentNameStrategy": "zotero_key",
  "templateFolder": "Templates",
  "defaultTemplate": "Literature"
}
```

The plugin also discovers user templates from Obsidian Templates and Templater
settings. `obsidian_create_note` can apply a template by path, by name, with
`use_template=true`, or with a configured `defaultTemplate`. Template variables
are replaced as text; Templater JavaScript is not executed.

## Doctor

Check the local setup without starting the MCP server:

```bash
python scripts/obsidian_vault_mcp.py --doctor --vault "path/to/vault"
```

## Local Smoke Checks

After opening Obsidian and Zotero Desktop, run the optional integration smoke
checks:

```bash
python scripts/smoke_integrations.py --vault "path/to/vault"
```

The smoke script does not apply vault edits. It verifies vault status, a
dry-run note creation diff, Zotero local API access, a one-item Zotero search,
and the Obsidian CLI vault command. Zotero and Obsidian CLI failures are
reported as warnings so the core vault checks can still pass on machines where
optional apps are closed.

## Zotero

Zotero tools use Zotero Desktop's local API at
`http://127.0.0.1:23119/api`. Open Zotero before using Zotero-backed tools.
Set `ZOTERO_LOCAL_API` only if your local Zotero API is exposed elsewhere.

Imported Zotero notes include `zoteroKey`, `zoteroSelect`, `zoteroLinks`, and
PDF attachment links when PDF child items are available. PDF copies default to
`attachments/zotero/{zoteroKey}/{original-file-name}` and can be renamed with
the `original`, `zotero_key`, `citekey`, `title_year`, or `parent_key` strategy.

## MinerU

MinerU integration is optional.

- `obsidian_ingest_mineru_markdown` imports Markdown that MinerU already
  produced.
- `obsidian_mineru_status` checks whether `mineru-open-api` is available.
- `obsidian_mineru_extract` runs `mineru-open-api` and saves Markdown under the
  configured vault.
- `obsidian_mineru_extract_and_ingest` runs MinerU, finds the generated
  Markdown, and imports it as an Obsidian source note.

Install the CLI only if you want direct extraction:

```bash
npm install -g mineru-open-api
mineru-open-api version
```

`flash-extract` can parse small/simple documents without a token. Precision
`extract` may require a token from MinerU or a local CLI auth configuration.
Do not commit tokens to this repository. If you use MinerU MCP as a separate
server, let Codex call that MCP directly and then use this plugin to ingest the
generated Markdown.

### MinerU Network Notes

MinerU extraction uses more than one endpoint. Successful task creation does
not guarantee that result download will work. Make sure these domains are
reachable:

- `mineru.net`
- `mineru.oss-cn-shanghai.aliyuncs.com`
- `cdn-mineru.openxlab.org.cn`
- `*.openxlab.org.cn`

On VPN/proxy setups, `cdn-mineru.openxlab.org.cn` may be resolved to fake-IP
ranges such as `198.18.x.x`. That can cause TLS handshake or EOF errors when
MinerU downloads the generated Markdown. Prefer direct routing for
MinerU/OpenXLab domains, or configure your proxy DNS rules so these domains
resolve and connect correctly.

Quick checks on Windows:

```powershell
mineru-open-api version
curl.exe -I https://mineru.net
curl.exe -I https://cdn-mineru.openxlab.org.cn
Resolve-DnsName cdn-mineru.openxlab.org.cn
```
