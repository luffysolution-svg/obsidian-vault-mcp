# Pi extension

This package exposes the fixed 33-tool Obsidian Vault MCP V2.1 surface to Pi. It is Extension-only and does not install the nine Codex/Claude/OpenCode Skills. It contains no vault, Zotero, or MinerU business logic: every registered tool calls the installed JSON CLI in this form:

```text
obsidian-vault-mcp call <tool-name> --json <arguments>
```

## Install

Install the Python package persistently first so the Pi process can resolve `obsidian-vault-mcp` on `PATH`. Use the package selector after 2.1.0 is published, or replace it with `"<WHEEL_PATH>"` for local production acceptance:

```bash
pipx install "zotero-obsidian-mcp==2.1.0"
# or: uv tool install "zotero-obsidian-mcp==2.1.0"
```

The release package carries the same thin Extension as a wheel resource. Preview and install it into the target Pi project:

```bash
obsidian-vault-mcp agent install pi --project-dir "<PROJECT_DIR>" --dry-run
obsidian-vault-mcp agent install pi --project-dir "<PROJECT_DIR>"
```

Restart Pi after changing `PATH` or installing the Extension. For a source checkout under development, install or run this directory directly:

```bash
pi install ./adapters/pi
pi -e ./adapters/pi/index.ts
```

The extension executes the CLI without a shell, stops calls after 660 seconds, limits captured output to 1 MiB, and reports non-JSON or structured CLI failures as Pi tool errors. Configure the vault and integration credentials through the same environment variables used by the CLI, such as `OBSIDIAN_VAULT_PATH`; prefer `mineru-open-api auth` over putting a MinerU token in project configuration.

See the [user guide](../../README.en.md), [complete tutorial](../../docs/index.en.md), and [developer guide](../../DEVELOPMENT.en.md) for the V2 data and safety contracts.
