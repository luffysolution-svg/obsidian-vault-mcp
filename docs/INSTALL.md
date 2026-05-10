# Install

For a detailed setup guide that covers plugin storage, Obsidian CLI, Codex
skills, Zotero, and MinerU, see [Configuration Guide](./CONFIGURATION.md).

## Requirements

- Python 3.10 or newer.
- Obsidian with a local vault.
- Zotero Desktop if you want Zotero integration.
- Obsidian 1.12.7 or newer plus the official `obsidian` CLI if you want
  app-backed CLI features. Enable it in Obsidian under `Settings` -> `General`.
- MinerU CLI (`mineru-open-api`) if you want this plugin to parse documents
  before ingesting them. Existing MinerU Markdown can be ingested without the
  CLI.

## Local Plugin Install

1. Clone or download this repository.
2. Open a terminal in the plugin directory and install the Python dependencies:

```bash
python -m pip install -r requirements.txt
```

For development or command-line use, install the package in editable mode:

```bash
python -m pip install -e ".[dev]"
obsidian-vault-mcp --doctor --doctor-format text --vault "C:/path/to/your-vault"
```

3. Register this folder as a local Codex plugin, or expose it through a local
   Codex plugin marketplace. See [Configuration Guide](./CONFIGURATION.md) for
   repo-scoped and personal marketplace examples.
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

`${CLAUDE_PLUGIN_ROOT}` is a portable plugin-root placeholder used by local
plugin hosts. Do not replace it with a personal absolute path in files that will
be committed. If a host requires a hard-coded script path, put that path only in
the host's local configuration.

The bundled Codex skill lives at `skills/obsidian-vault/SKILL.md`. Codex loads
it through `.codex-plugin/plugin.json`; you do not need to copy it into
`~/.agents/skills` unless you are experimenting with a standalone skill outside
the plugin.

Editable installs also expose the `obsidian-vault-mcp` console command. The
checked-in `.mcp.json` continues to use the compatibility script so local plugin
installs remain portable.

5. If `auto` cannot find your vault, set `OBSIDIAN_VAULT_PATH` locally to your
   vault root, for example `C:/path/to/your-vault`. Do not commit personal vault
   paths, Zotero storage paths, private note names, or API tokens to the
   repository.

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
python scripts/obsidian_vault_mcp.py --doctor --doctor-format text --vault "C:/path/to/your-vault"
```

The default doctor output remains JSON for scripts and automation. Use
`--doctor-format text` when checking the setup manually.

## Obsidian CLI Targeting

Direct file tools use `vault_path` as a filesystem path. The app-backed
Obsidian CLI wrappers use the Obsidian CLI's `vault=<name>` option, where the
value is a vault name known to Obsidian, not a filesystem path. Leave `vault`
empty to target the currently active vault, or pass the name shown by
`obsidian vaults verbose`.

Install or enable the official CLI by updating to the Obsidian 1.12.7+ installer,
opening Obsidian, enabling `Command line interface` in `Settings` -> `General`,
and following the registration prompt. Restart your terminal afterwards.

Useful checks:

```bash
obsidian version
obsidian help
obsidian vault info=path
```

## Batch Edit Plan Format

`obsidian_preview_edit_plan`, `obsidian_apply_edit_plan`, and
`obsidian_rollback_edit_plan` use a simple JSON plan format. A plan can be an
array or an object with an `operations` array. Each operation can name its
action with `op`, `operation`, or `type`.

```json
{
  "operations": [
    {
      "operation": "write",
      "path": "Inbox/New note.md",
      "content": "# New note\n",
      "overwrite": false
    },
    {
      "operation": "replace",
      "path": "Inbox/Existing note.md",
      "old": "draft",
      "new": "reviewed"
    }
  ]
}
```

Supported actions are `write`, `update_properties`, `append`, `replace`, and
`delete`. Preview plans before applying them; applied plans store vault-local
rollback backups under `.obsidian-vault-backups/`.

## Local Smoke Checks

After opening Obsidian and Zotero Desktop, run the optional integration smoke
checks:

```bash
python scripts/smoke_integrations.py --vault "C:/path/to/your-vault"
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

The plugin reads local-library endpoints such as `users/0/items`,
`users/0/items/<itemKey>`, and `users/0/items/<itemKey>/children`. Check Zotero
connectivity with:

```powershell
curl.exe "http://127.0.0.1:23119/connector/ping"
python scripts/obsidian_vault_mcp.py --doctor --doctor-format text --vault "C:/path/to/your-vault"
```

Imported Zotero notes include `zoteroKey`, `zoteroSelect`, `zoteroLinks`, and
PDF attachment links when PDF child items are available. PDF copies default to
`attachments/zotero/{zoteroKey}/{original-file-name}` and can be renamed with
the `original`, `zotero_key`, `citekey`, `title_year`, or `parent_key` strategy.
If Zotero stores attachments outside `~/Zotero/storage`, set
`ZOTERO_STORAGE_DIR` locally.

## MinerU

MinerU integration is optional.

- `obsidian_ingest_mineru_markdown` imports Markdown that MinerU already
  produced.
- `obsidian_mineru_status` checks whether `mineru-open-api` is available.
- `obsidian_mineru_extract` runs `mineru-open-api` and saves Markdown under the
  configured vault.
- `obsidian_mineru_extract_and_ingest` runs MinerU, finds the generated
  Markdown, and imports it as an Obsidian source note.

Install the CLI only if you want direct extraction. Current MinerU Open API CLI
documentation uses the single-binary installer:

```powershell
irm https://cdn-mineru.openxlab.org.cn/open-api-cli/install.ps1 | iex
mineru-open-api version
```

Linux/macOS:

```bash
curl -fsSL https://cdn-mineru.openxlab.org.cn/open-api-cli/install.sh | sh
mineru-open-api version
```

`flash-extract` can parse small/simple documents without a token. Precision
`extract` requires authentication and supports larger/richer jobs. Get a token
from `https://mineru.net/apiManage/token`, then configure it locally with
`mineru-open-api auth` or `MINERU_TOKEN`. Do not commit tokens to this
repository. If you use MinerU MCP as a separate server, let Codex call that MCP
directly and then use this plugin to ingest the generated Markdown.

The CLI token resolution order is `--token`, then `MINERU_TOKEN`, then
`~/.mineru/config.yaml`.

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
