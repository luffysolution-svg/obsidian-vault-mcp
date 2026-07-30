---
layout: default
title: Agent client installation
lang: en
---
# Agent client installation

The installer supports Codex, Claude Code, OpenCode, Pi, Hermes, and WorkBuddy:

```bash
obsidian-vault-mcp agent install <client> --dry-run
obsidian-vault-mcp agent install <client>
```

| Client | Installed content |
|---|---|
| Codex | Native marketplace plugin, MCP, and 7 Skills |
| Claude Code | Native marketplace plugin, MCP, and 7 Skills |
| OpenCode | Project-local MCP and 7 Skills |
| Pi | TypeScript Extension over the shared JSON CLI |
| Hermes | MCP configuration (does not auto-install Skills) |
| WorkBuddy | MCP configuration (does not auto-install Skills) |

## Codex plugin

Install the Python package first and ensure `codex` is on `PATH`. These commands register the packaged `obsidian-vault-mcp` marketplace, then install the native `obsidian-literature@obsidian-vault-mcp` plugin, its MCP server, and all seven Skills:

```bash
obsidian-vault-mcp agent install codex --dry-run
obsidian-vault-mcp agent install codex
codex plugin marketplace list --json
codex plugin list --json
```

After upgrading the Python package, run `codex plugin add obsidian-literature@obsidian-vault-mcp --json`. To uninstall, run `codex plugin remove obsidian-literature@obsidian-vault-mcp --json`; if the marketplace is no longer needed, then run `codex plugin marketplace remove obsidian-vault-mcp --json`.

## Claude Code plugin

Install the Python package first and ensure `claude` is on `PATH`. The installer registers the same marketplace at user scope and installs the native plugin, MCP server, and all seven Skills:

```bash
obsidian-vault-mcp agent install claude --dry-run
obsidian-vault-mcp agent install claude
claude plugin marketplace list --json
claude plugin list --json
```

After upgrading the Python package:

```bash
claude plugin marketplace update obsidian-vault-mcp
claude plugin update obsidian-literature@obsidian-vault-mcp --scope user
```

Restart Claude Code afterwards. To uninstall, run `claude plugin uninstall obsidian-literature@obsidian-vault-mcp --scope user`; if the marketplace is no longer needed, then run `claude plugin marketplace remove obsidian-vault-mcp --scope user`.

Codex and Claude use `obsidian-literature@obsidian-vault-mcp`. OpenCode, Pi, Hermes, and WorkBuddy target the current project or `--project-dir`. Configuration installers back up, merge, validate, and handshake-test; a failure rolls back the state created by that attempt. If a same-named marketplace points to a different installation path, confirm that you intend to switch versions and follow the error's removal instructions; the installer never removes an existing marketplace automatically.
