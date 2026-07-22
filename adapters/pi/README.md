# Pi extension

This package exposes the Obsidian Vault MCP V2 tool surface to Pi. It contains no vault, Zotero, or MinerU business logic: every registered tool calls the installed JSON CLI in this form:

```text
obsidian-vault-mcp call <tool-name> --json <arguments>
```

## Install

Install the Python package first so `obsidian-vault-mcp` is on `PATH`, then install this directory as a Pi package:

```bash
python -m pip install "zotero-obsidian-mcp==2.0.0"
pi install ./adapters/pi
```

For a checkout under development, run it directly:

```bash
pi -e ./adapters/pi/index.ts
```

The extension executes the CLI without a shell, stops calls after 660 seconds, limits captured output to 1 MiB, and reports non-JSON or structured CLI failures as Pi tool errors. Configure the vault and integration credentials through the same environment variables used by the CLI, such as `OBSIDIAN_VAULT_PATH`; prefer `mineru-open-api auth` over putting a MinerU token in project configuration.

See the [user guide](../../README.en.md), [complete tutorial](../../docs/index.en.md), and [developer guide](../../DEVELOPMENT.en.md) for the V2 data and safety contracts.
