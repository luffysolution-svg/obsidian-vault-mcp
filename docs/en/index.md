---
layout: default
title: A local-first literature research workflow
lang: en
description: A local-first literature research workflow connecting Zotero, MinerU, Obsidian, and AI agents.
---
# Obsidian Vault MCP

<p class="lead">A local-first literature research workflow connecting Zotero, MinerU, Obsidian, and AI agents.</p>

<span class="badge">Version 3.0.0</span>

[Quick start](quickstart/){:.button} [Full installation](installation/){:.button} [GitHub](https://github.com/luffysolution-svg/obsidian-vault-mcp){:.button} [Changelog](changelog/){:.button}

{% include release-notice.html %}

## From papers to a knowledge base

```text
Zotero Desktop → stable zoteroKey → Markdown main note + PDF
→ MinerU full text, images, formulas → 31 MCP Tools → 7 Agent Skills
→ 5 Analysis types → Obsidian Base and knowledge base
```

<div class="grid"><div class="card"><div class="metric">31</div>MCP Tools</div><div class="card"><div class="metric">7</div>Agent Skills</div><div class="card"><div class="metric">5</div>Analysis Types</div><div class="card"><div class="metric">1</div>Analysis Base</div></div>

## What it does

<div class="grid"><div class="card"><h3>Zotero and attachments</h3>Import and synchronize parent items using a stable `zoteroKey`, with PDFs.</div><div class="card"><h3>MinerU</h3>Parse full text, images, and formulas into paper-isolated relative paths.</div><div class="card"><h3>Analysis and Wiki</h3>Five structured analysis types, Literature/Analysis Base, and traceable Wiki.</div><div class="card"><h3>Recoverable writes</h3>dry-run, transactions, backups, conflict protection, atomic replacement, and rollback.</div><div class="card"><h3>Agent workflows</h3>Codex, Claude Code, OpenCode, Pi, Hermes, and WorkBuddy integration.</div></div>

## Quick install (after release)

```bash
uv tool install "zotero-obsidian-mcp==3.0.0"
obsidian-vault-mcp --help
obsidian-vault-mcp call literature_version --json '{}'
```

```bash
uvx --from "zotero-obsidian-mcp==3.0.0" obsidian-vault-mcp --help
```

## Documentation

<div class="grid"><div class="card"><h3><a href="installation/">Full installation</a></h3>Requirements, package managers, Vault, Zotero, MinerU, verification, privacy.</div><div class="card"><h3><a href="configuration/">Configuration</a></h3>The only Vault configuration, Schema, and Skill customizations.</div><div class="card"><h3><a href="zotero/">Zotero import and sync</a></h3>Parent items, attachments, and synchronization.</div><div class="card"><h3><a href="mineru/">MinerU parsing</a></h3>Full text, images, formulas, and transactional output.</div><div class="card"><h3><a href="analysis/">Analysis and Skills</a></h3>Five outputs, Analysis.base, and seven workflows.</div><div class="card"><h3><a href="agents/">Agent clients</a></h3>The clients and installation methods actually supported by installers.</div><div class="card"><h3><a href="tools/">MCP Tools</a></h3>31-tool reference generated from the runtime registry.</div><div class="card"><h3><a href="troubleshooting/">Troubleshooting</a></h3>doctor, verify, paths, and client issues.</div><div class="card"><h3><a href="development/">Development</a></h3>Pages source, testing, and contribution.</div></div>

## Real interface

![Literature Base in Obsidian](../assets/screenshots/v2/literature-base.png)

[中文文档](../)
