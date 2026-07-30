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

Codex and Claude use `obsidian-literature@obsidian-vault-mcp`. OpenCode, Pi, Hermes, and WorkBuddy target the current project or `--project-dir`. Configuration installers back up, merge, validate, and handshake-test; a failure rolls back the state created by that attempt. Use the returned paths and uninstall instructions as the source of truth.
