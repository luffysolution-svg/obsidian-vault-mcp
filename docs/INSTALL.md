# Install

## Requirements

- Python 3.10 or newer.
- Obsidian with a local vault.
- Zotero Desktop if you want Zotero integration.
- Obsidian 1.12.7 or newer plus the `obsidian` CLI if you want app-backed CLI
  features.

## Local Plugin Install

1. Clone or download this repository.
2. Install the Python dependencies:

```bash
python -m pip install -r requirements.txt
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

5. If `auto` cannot find your vault, set `OBSIDIAN_VAULT_PATH` locally to your
   vault root. Do not commit personal vault paths to the repository.

## Zotero

Zotero tools use Zotero Desktop's local API at
`http://127.0.0.1:23119/api`. Open Zotero before using Zotero-backed tools.
Set `ZOTERO_LOCAL_API` only if your local Zotero API is exposed elsewhere.
