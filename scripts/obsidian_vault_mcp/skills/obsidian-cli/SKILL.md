---
name: obsidian-cli
description: "Drive the Obsidian desktop app via its CLI. Use when the user needs to open notes, query backlinks, read or set note properties, run Base queries, list tasks, take screenshots, reload plugins, or move/rename files with live wikilink updates inside a running Obsidian instance. 当需要控制 Obsidian 桌面应用、读取/写入属性、查询 Bases、列出任务或在 Obsidian 运行时移动/重命名文件时使用。"
---

# Obsidian CLI

The `obsidian` CLI is available when Obsidian 1.12.7+ is running and the CLI is on PATH. Check availability with `Bash` → `obsidian --version`.

All commands use the pattern: `obsidian <command> [params] [flags]`

## Reading

**Read note content:**
```bash
obsidian read --path "folder/note.md"
```

**Open a note in Obsidian:**
```bash
obsidian open --path "folder/note.md"
```

**Get backlinks (JSON):**
```bash
obsidian backlinks --path "folder/note.md" --format json [--counts]
```

**Get note properties (YAML frontmatter, JSON output):**
```bash
obsidian properties --path "folder/note.md" --format json [--counts]
```

## Properties

**Read a single property:**
```bash
obsidian property:read --name "status" --path "folder/note.md"
```

**Set a property:**
```bash
obsidian property:set --name "status" --value "done" --type "text" --path "folder/note.md"
```

**Remove a property:**
```bash
obsidian property:remove --name "status" --path "folder/note.md"
```

## Bases & Dataview

**Query a Base file:**
```bash
obsidian base:query --path "bases/literature.base" --view "Main" --format json
```

## Tasks

**List tasks in a note:**
```bash
obsidian tasks --path "folder/note.md" --format json [--todo] [--done]
```

## App Control

**Take a screenshot:**
```bash
obsidian screenshot --output "shot.png"
```

**Reload a plugin:**
```bash
obsidian plugin:reload --id "obsidian-git"
```

## Move & Rename (with wikilink updates)

**Move a note:**
```bash
obsidian move --path "old/note.md" --to "new/note.md"
```

**Rename a note:**
```bash
obsidian rename --path "folder/note.md" --name "new-name.md"
```

Use these instead of filesystem `mv`/`rename` when Obsidian is running — they update all internal wikilinks automatically.

## Parsing CLI Output

All `--format json` commands return a JSON array of objects. Parse with Python:
```python
import json, subprocess
result = subprocess.run(["obsidian", "backlinks", "--path", "note.md", "--format", "json"], capture_output=True, text=True)
data = json.loads(result.stdout)
```

## Error Handling

If `stdout` contains `"Vault not found."` or similar error text, treat as failure even if exit code is 0. Check `returnCode != 0` **and** scan stdout for known error patterns.

Do not use `shell=True` on Windows — pass the executable path directly.

## Eval Scenarios

- **Trigger:** "Open this note in Obsidian." Expected: check CLI availability, then run `obsidian open --path ...`. Must not modify files.
- **Trigger:** "Rename a note and keep links working." Expected: use `obsidian rename` or `obsidian move`, then verify the command output. Must not use raw filesystem rename while Obsidian is running.
- **Trigger:** "List unfinished tasks in this note." Expected: use `obsidian tasks --format json --todo` and parse JSON. Must treat error text in stdout as failure even if exit code is zero.

---

## 中文说明

当 Obsidian 桌面运行时，所有文件移动、重命名、属性读写、任务查询等操作优先通过 `obsidian` CLI 完成，以确保内部双链自动更新。使用 Bash 工具执行上述命令，解析 `--format json` 输出。
