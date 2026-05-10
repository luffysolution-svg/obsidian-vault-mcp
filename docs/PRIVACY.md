# Privacy

This plugin runs locally through an MCP stdio server. It does not send vault
files, Zotero metadata, PDF text, or Obsidian CLI output to any external
service by itself.

The host application using this MCP server can read the data returned by the
tools. Users should review their host application's privacy policy and avoid
connecting this plugin to hosts they do not trust.

## Local Data Access

The plugin can access:

- Files inside the configured Obsidian vault.
- Zotero Desktop's local API at `http://127.0.0.1:23119/api` when Zotero is
  running and reachable.
- Local PDF files referenced by Zotero attachments.
- Obsidian CLI output when the CLI is installed and called through the plugin.
- MinerU CLI output when `mineru-open-api` is installed and called through the
  optional MinerU tools.

## Configuration

No absolute vault path is embedded in the package. By default,
`OBSIDIAN_VAULT_PATH` is set to `auto`, which asks the local Obsidian CLI for
the active vault. Users can set an explicit vault path in their local
`.mcp.json` or host configuration.

Non-vault folders are rejected by default unless the user explicitly sets
`OBSIDIAN_ALLOW_NON_VAULT=true`.

MinerU tokens are not required for Markdown ingestion or `flash-extract`.
Precision MinerU extraction may use a token from the user's local CLI
configuration, environment, or explicit tool call.
