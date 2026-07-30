<!-- mcp-name: io.github.luffysolution-svg/obsidian-vault-mcp -->

# Obsidian Vault MCP

A local-first, transactional, rollback-capable pipeline connecting Zotero papers, PDFs, MinerU full text, and Obsidian Analysis.

[中文](https://github.com/luffysolution-svg/obsidian-vault-mcp/blob/main/README.md) · [Full tutorial](https://github.com/luffysolution-svg/obsidian-vault-mcp/blob/main/docs/index.en.md) · [Developer guide](https://github.com/luffysolution-svg/obsidian-vault-mcp/blob/main/DEVELOPMENT.en.md)

## V3.0.0

V3 retains the proven V2 core and reduces the structured research layer to one Analysis model:

- The Zotero parent item's `zoteroKey` remains the stable identity for its main note, PDF, and MinerU output.
- MCP exposes exactly 31 tools: the 26 stable V2 tools plus 5 Analysis tools.
- Analysis has five types only: `full_read`, `literature_review`, `passage_qa`, `figure_qa`, and `concept`.
- Status is one of `draft`, `ready`, `reviewed`, `needs_update`, or `archived`.
- The seven profiles are `general`, `medicine`, `chemistry`, `materials`, `catalysis`, `physics`, and `mathematics`.
- `Literature/Analysis/Analysis.base` is the only Analysis navigator and contains nine views.
- Agent behavior is provided by exactly seven Skills: `paper-qa`, `full-read`, `passage-qa`, `figure-qa`, `compare-papers`, `literature-review`, and `concept-learning`.

V3 no longer creates or maintains Evidence, Coverage, Uncertainty, an Analysis index, Topic, Theory, or Analysis templates. The retained `Literature/index.md` and `Literature/Literature.base` are V2 literature assets, not the removed Analysis index.

## Quick install

Python 3.10+ is required. Zotero imports need a running Zotero Desktop instance with its local API enabled. MinerU is optional until full-text parsing is needed.

Choose one installation method:

```powershell
# pip
python -m pip install "zotero-obsidian-mcp==3.0.0"

# pipx
pipx install "zotero-obsidian-mcp==3.0.0"

# uv tool
uv tool install "zotero-obsidian-mcp==3.0.0"
```

Run without a persistent install through uvx:

```powershell
uvx --from "zotero-obsidian-mcp==3.0.0" obsidian-vault-mcp doctor --vault-path "<VAULT_PATH>"
```

In the MCP Registry, search for:

```text
io.github.luffysolution-svg/obsidian-vault-mcp
```

The equivalent stdio configuration is:

```json
{
  "command": "uvx",
  "args": [
    "--from",
    "zotero-obsidian-mcp==3.0.0",
    "obsidian-vault-mcp",
    "serve",
    "--transport",
    "stdio"
  ],
  "env": {
    "OBSIDIAN_VAULT_PATH": "<VAULT_PATH>"
  }
}
```

Never commit machine-specific vault paths, Zotero data, or MinerU tokens.

## Initialize and import

```powershell
obsidian-vault-mcp config init --vault-path "<VAULT_PATH>" --dry-run
obsidian-vault-mcp config init --vault-path "<VAULT_PATH>"
obsidian-vault-mcp doctor --vault-path "<VAULT_PATH>"
obsidian-vault-mcp import item ABCD1234 --vault-path "<VAULT_PATH>" --dry-run
obsidian-vault-mcp import item ABCD1234 --vault-path "<VAULT_PATH>"
```

Preview every write first. A successful configuration result from `doctor` does not replace its separate Zotero and MinerU readiness checks.

If Zotero PDFs use **Link to File**, configure Zotero with a fixed Linked Attachment Base Directory and put the same path in the vault's `.obsidian-vault-mcp.json`:

```json
{
  "zotero": {
    "linkedAttachmentBaseDir": "<ZOTERO_LINKED_ATTACHMENT_BASE_DIR>"
  }
}
```

You may instead set `ZOTERO_LINKED_ATTACHMENT_BASE_DIR` before starting the CLI/MCP server; a non-empty config value takes precedence. `ZOTERO_STORAGE_DIR` is only for Zotero-managed `storage:` attachments, while the linked-attachment setting is only for `attachments:` paths. Never commit this machine-local absolute path. Traversal, drive-prefixed relative values, and any path outside the configured base are rejected.

Parse with MinerU:

```powershell
obsidian-vault-mcp mineru parse ABCD1234 --vault-path "<VAULT_PATH>" --dry-run
obsidian-vault-mcp mineru parse ABCD1234 --vault-path "<VAULT_PATH>"
```

Each paper has an isolated image directory:

```text
Literature/attachment/MinerU/ABCD1234.md
Literature/attachment/MinerU/image/ABCD1234/ABCD1234-fig01.png
```

The Markdown link is `image/ABCD1234/ABCD1234-fig01.png`, so it remains portable with the vault.

## Analysis

The five added MCP tools are:

| Tool | Purpose |
|---|---|
| `literature_paper_read` | Read one paper in overview, targeted, or figures mode without persistent derived state. |
| `literature_retrieve` | Retrieve source-located passages across papers; coverage data exists only in the response. |
| `literature_analysis_get` | Read existing Analysis records by ID, type, or source. |
| `literature_analysis_write` | Validate and transactionally preview or write an Analysis record. |
| `literature_rebuild_analysis_base` | Rebuild the single `Analysis.base`. |

The nine `Analysis.base` views are Dashboard, Full Reads, Reviews, Passage Q&A, Figure Q&A, Concepts, Needs Attention, By Discipline, and Recently Updated.

Prefer using the matching Skill through a connected Agent. Direct tool calls use the shared JSON CLI:

```powershell
obsidian-vault-mcp call literature_paper_read --json '{"zotero_key":"ABCD1234","mode":"overview","vault_path":"<VAULT_PATH>"}'
obsidian-vault-mcp call literature_rebuild_analysis_base --json '{"vault_path":"<VAULT_PATH>","dry_run":true}'
```

## Agents, Skills, and plugins

Install the Python package first, then run a client installer:

```powershell
obsidian-vault-mcp agent install codex --dry-run
obsidian-vault-mcp agent install codex
```

Replace `codex` with `claude`, `opencode`, `pi`, `hermes`, or `workbuddy`. Codex and Claude use native plugin marketplaces containing the MCP server and seven Skills. OpenCode receives project-local MCP/Skills. Pi receives a thin TypeScript Extension. Hermes and WorkBuddy receive MCP configuration, but currently have no verified native Skill installation contract.

Installers merge rather than overwrite where possible, back up before writing, and perform an MCP handshake. Newly added state is rolled back if installation fails.

`opencode`, `pi`, `hermes`, and `workbuddy` write project-local configuration. Run the command in the target project or pass `--project-dir <PROJECT_DIR>`. When upgrading from 2.x, first upgrade the Python package exactly with the installer you originally used, then refresh the native plugin cache and rerun the installer for its handshake:

```powershell
# uv tool users
uv tool install --force "zotero-obsidian-mcp==3.0.0"

# pipx users
pipx install --force "zotero-obsidian-mcp==3.0.0"

# Codex plugin add atomically replaces an installed older version
codex plugin add obsidian-literature@obsidian-vault-mcp --json

# Claude Code: refresh the marketplace, update the plugin, then restart Claude Code
claude plugin marketplace update obsidian-vault-mcp
claude plugin update obsidian-literature@obsidian-vault-mcp --scope user
```

The GitHub Release asset `obsidian-vault-mcp-3.0.0-plugins.zip` is the same offline marketplace. Verify `SHA256SUMS`, extract it, and use the complete clean-install sequence for the target client:

```powershell
codex plugin marketplace add "<EXTRACTED_DIR>" --json
codex plugin add obsidian-literature@obsidian-vault-mcp --json

claude plugin marketplace add "<EXTRACTED_DIR>" --scope user
claude plugin install obsidian-literature@obsidian-vault-mcp --scope user
```

Do not rebind an existing marketplace name to a different path; use the upgrade flow above.

## Migrate older data

Preview the legacy flat MinerU image migration first:

```powershell
obsidian-vault-mcp migrate mineru-images-v2-to-v3 --vault-path "<VAULT_PATH>"
```

Inspect `copiedImages`, `preservedLegacyImages`, `rewrittenMarkdown`,
`missingReferencedImages`, and `reparseZoteroKeys`. Commit only when the report
is acceptable:

```powershell
obsidian-vault-mcp migrate mineru-images-v2-to-v3 --vault-path "<VAULT_PATH>" --apply
```

Safe mode copies each paper's images into `image/{zoteroKey}/` and rewrites its
Markdown in one transaction while preserving the flat images as compatibility
aliases. This prevents an uncoordinated editor from creating a broken old-path
reference at the final instant before commit. Uncertain, missing, or unsafe
entries remain in place and are reported rather than guessed.

To remove the flat images, first stop Obsidian, sync clients, indexers, and every
other Vault writer, then explicitly confirm that offline state:

```powershell
obsidian-vault-mcp migrate mineru-images-v2-to-v3 --vault-path "<VAULT_PATH>" --apply --cleanup-legacy --confirm-vault-offline
```

That mode copies images, rewrites Markdown links, and cleans up old images in the
same transaction. A reference from another Vault note blocks cleanup for that
paper.

Older Analysis migration also produces a plan by default:

```powershell
obsidian-vault-mcp migrate analysis-v2-to-v3 --vault-path "<VAULT_PATH>"
```

Review migrated, skipped, and manual-review items before committing:

```powershell
obsidian-vault-mcp migrate analysis-v2-to-v3 --vault-path "<VAULT_PATH>" --apply
obsidian-vault-mcp preview <transaction-id> --vault-path "<VAULT_PATH>"
obsidian-vault-mcp rollback <transaction-id> --vault-path "<VAULT_PATH>" --dry-run
obsidian-vault-mcp rollback <transaction-id> --vault-path "<VAULT_PATH>"
```

Migration normalizes recognizable older Analysis files, removes obsolete anchors, and creates `Analysis.base`. Topic/Theory files that cannot be mapped safely remain in place and are reported for manual handling.

## Safety boundary

- Preview first, commit second, and retain the returned `transactionId`.
- Never run automated write tests against a user's real vault. Use the real vault for read-only checks and an isolated copy for writes, migration, and rollback.
- Hash or inventory the real vault before and after isolation, excluding locks, staging, and old backups from the test copy.
- MinerU sends selected PDFs to an external service. Confirm document rights and organizational policy first.
- Put any non-stdio MCP transport behind a trusted authentication boundary.

## Contributors

Thanks to [方珸 / Lym Fang (@LimFang)](https://github.com/LimFang) for identifying the Zotero linked-attachment compatibility need and proposing the original implementation in [PR #6](https://github.com/luffysolution-svg/obsidian-vault-mcp/pull/6). The design was ported to the V2 architecture in [PR #8](https://github.com/luffysolution-svg/obsidian-vault-mcp/pull/8) and remains supported in V3. See [CONTRIBUTORS.md](https://github.com/luffysolution-svg/obsidian-vault-mcp/blob/main/CONTRIBUTORS.md) for the complete record.

See the [full tutorial](https://github.com/luffysolution-svg/obsidian-vault-mcp/blob/main/docs/index.en.md) for every installation path, the complete 31-tool table, migration, and end-to-end acceptance. See the [developer guide](https://github.com/luffysolution-svg/obsidian-vault-mcp/blob/main/DEVELOPMENT.en.md) for architecture, contracts, tests, and release procedure.
