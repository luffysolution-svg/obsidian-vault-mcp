---
name: obsidian-cli
description: "Use the Obsidian desktop app and CLI wrappers safely from this plugin. Use when Codex needs app-backed operations such as opening notes, reading through the Obsidian app, listing backlinks, querying Bases, reading or writing properties, listing tasks, taking Obsidian screenshots, reloading an Obsidian plugin, or moving and renaming notes with link-aware behavior. 当用户提到 Obsidian CLI、backlinks、属性读取、Base 查询、任务列表、截图、插件重载或带链接更新的重命名时使用。"
---

# Obsidian CLI

Use this skill for app-backed behavior that should go through the local Obsidian desktop CLI rather than direct file mutation.
处理需要走 Obsidian 桌面端 CLI 的操作时优先使用。

## Preconditions

- Prefer this skill only when Obsidian Desktop is installed and running.
- Remember that CLI wrapper `vault` arguments are Obsidian vault names, not filesystem paths.
- Use direct vault tools instead when the work is only plain file reading or writing.

## Prefer Structured Wrappers

- Use `obsidian_cli_read` and `obsidian_cli_open` for note access.
- Use `obsidian_cli_backlinks` for backlinks.
- Use `obsidian_cli_base_query` for Base queries.
- Use `obsidian_cli_properties`, `obsidian_cli_property_read`, `obsidian_cli_property_set`, and `obsidian_cli_property_remove` for property work.
- Use `obsidian_cli_tasks` for task listings.
- Use `obsidian_cli_screenshot` for app-backed screenshots.
- Use `obsidian_cli_plugin_reload` for plugin reloads.
- Use `obsidian_cli_move_or_rename` for moves and renames that should respect Obsidian link-update behavior.

## Fallback

- Use generic `obsidian_cli` only when no structured wrapper exists for the requested command.
- Pass focused arguments and keep timeouts tight unless the request clearly needs a slower command.

## Safety

- Keep `dry_run=true` for move or rename operations until the destination is confirmed.
- Prefer wrappers over raw CLI strings because they normalize output and reduce argument mistakes.
