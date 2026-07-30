# Obsidian Vault MCP 3.0.0 Full Tutorial

[中文](./index.md) · [Project home](../README.en.md) · [Developer guide](../DEVELOPMENT.en.md)

This tutorial covers installation, Zotero import, MinerU parsing, Analysis, Agent plugins, migration, and safe acceptance against a real vault.

## 1. Understand V3 first

```text
Zotero Desktop local API
        ↓
stable zoteroKey → main note + PDF
        ↓
MinerU Markdown + one image directory per paper
        ↓
paper_read / retrieve
        ↓
five Analysis types → one Analysis.base
```

Three boundaries matter:

1. The V2 literature core remains, including `Literature/index.md`, `Literature/Literature.base`, Wiki, transactions, and 26 tools.
2. The structured research layer has only five Analysis types and one `Analysis.base`.
3. Evidence, Coverage, Uncertainty, the Analysis index, Topic, Theory, and Analysis templates have left the runtime model. Migration may recognize old files, but V3 does not maintain them.

## 2. Prepare software

| Software | Requirement | Purpose |
|---|---|---|
| Python | 3.10+ | Package, CLI, and MCP server |
| Obsidian | Has opened the target vault once | Creates `.obsidian` and displays Markdown/Base |
| Zotero Desktop | Running with local API enabled | Parent items, attachments, notes, and BibTeX |
| MinerU Open API CLI | Optional | PDF to Markdown and images |
| AI client | Optional | Codex, Claude Code, OpenCode, Pi, Hermes, WorkBuddy |

Zotero's local API normally stays on the machine. MinerU is external, and even token-free fast extraction may upload a PDF. Confirm rights and policy first.

## 3. Install the Python package

All four methods use the same PyPI release:

```powershell
# Current Python environment
python -m pip install --upgrade "zotero-obsidian-mcp==3.0.0"

# Isolated command
pipx install "zotero-obsidian-mcp==3.0.0"

# Persistent uv tool
uv tool install "zotero-obsidian-mcp==3.0.0"

# Ephemeral uv execution
uvx --from "zotero-obsidian-mcp==3.0.0" obsidian-vault-mcp --help
```

Verify the installed distribution:

```powershell
obsidian-vault-mcp --help
python -c "from importlib.metadata import version; print(version('zotero-obsidian-mcp'))"
```

For a source installation, check out a published tag and use an isolated environment:

```powershell
git clone https://github.com/luffysolution-svg/obsidian-vault-mcp.git
cd obsidian-vault-mcp
git checkout v3.0.0
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
```

## 4. Select and initialize a vault

Replace the example path:

```powershell
$env:OBSIDIAN_VAULT_PATH = "<VAULT_PATH>"
obsidian-vault-mcp config init --vault-path "$env:OBSIDIAN_VAULT_PATH" --dry-run
obsidian-vault-mcp config init --vault-path "$env:OBSIDIAN_VAULT_PATH"
obsidian-vault-mcp config validate --vault-path "$env:OBSIDIAN_VAULT_PATH"
obsidian-vault-mcp doctor --vault-path "$env:OBSIDIAN_VAULT_PATH"
```

`config init` writes `.obsidian-vault-mcp.json`. Inspect the dry-run before the first write. A top-level success from `doctor` only proves that basic configuration can be read; inspect its separate Zotero and MinerU status.

Default Analysis configuration:

```json
{
  "analysis": {
    "folder": "Literature/Analysis",
    "base": "Literature/Analysis/Analysis.base",
    "fullReadsFolder": "Literature/Analysis/full-reads",
    "reviewsFolder": "Literature/Analysis/reviews",
    "passageQaFolder": "Literature/Analysis/qa/passages",
    "figureQaFolder": "Literature/Analysis/qa/figures",
    "conceptsFolder": "Literature/Analysis/concepts"
  }
}
```

Every path must stay inside the vault, the five type directories must be distinct, and the Base path must end in `.base`.

## 5. Configure Zotero and import

Enable Zotero's local HTTP API, then probe and search:

```powershell
obsidian-vault-mcp call zotero_ping --json '{}'
obsidian-vault-mcp call zotero_search_items --json '{"query":"catalysis"}'
```

Use the returned parent-item key, not an attachment key:

```powershell
obsidian-vault-mcp import item ABCD1234 --vault-path "$env:OBSIDIAN_VAULT_PATH" --dry-run
obsidian-vault-mcp import item ABCD1234 --vault-path "$env:OBSIDIAN_VAULT_PATH"
```

Import a Zotero collection:

```powershell
obsidian-vault-mcp import collection COLLECTION_KEY --vault-path "$env:OBSIDIAN_VAULT_PATH" --dry-run
obsidian-vault-mcp import collection COLLECTION_KEY --vault-path "$env:OBSIDIAN_VAULT_PATH"
```

Default assets:

```text
Literature/ABCD1234.md
Literature/attachment/ABCD1234.pdf
```

Changing title, authors, year, or citekey still updates the same note because `zoteroKey` is stable. Use `sync item` or `sync collection`, always previewing before commit.

For Zotero **Link to File** attachments, the local API returns an `attachments:` relative path. Set Zotero's **Settings → Advanced → Files and Folders → Linked Attachment Base Directory**, then put the same directory in the vault's `.obsidian-vault-mcp.json`:

```json
{
  "zotero": {
    "linkedAttachmentBaseDir": "<ZOTERO_LINKED_ATTACHMENT_BASE_DIR>"
  }
}
```

Alternatively, set an environment variable before starting the CLI/MCP server. A non-empty config value takes precedence:

```powershell
$env:ZOTERO_LINKED_ATTACHMENT_BASE_DIR = "<ZOTERO_LINKED_ATTACHMENT_BASE_DIR>"
```

```bash
export ZOTERO_LINKED_ATTACHMENT_BASE_DIR="<ZOTERO_LINKED_ATTACHMENT_BASE_DIR>"
```

`ZOTERO_STORAGE_DIR` resolves only Zotero-managed `storage:` attachments. `linkedAttachmentBaseDir` and `ZOTERO_LINKED_ATTACHMENT_BASE_DIR` resolve only `attachments:` linked files. Keep this absolute path in machine-local configuration and never commit it. V3 rejects traversal, drive-prefixed relative values, and results outside the base; if no base is configured, import reports a clear error instead of guessing.

## 6. MinerU full text

Install and authenticate `mineru-open-api` according to MinerU's official documentation. Never put its token in a vault, chat, or Git.

```powershell
obsidian-vault-mcp mineru parse ABCD1234 --vault-path "$env:OBSIDIAN_VAULT_PATH" --dry-run
obsidian-vault-mcp mineru parse ABCD1234 --vault-path "$env:OBSIDIAN_VAULT_PATH"
```

Canonical V3 output:

```text
Literature/attachment/MinerU/ABCD1234.md
Literature/attachment/MinerU/image/ABCD1234/ABCD1234-fig01.png
Literature/attachment/MinerU/image/ABCD1234/ABCD1234-fig02.jpg
```

Markdown uses a relative link:

```markdown
![](image/ABCD1234/ABCD1234-fig01.png)
```

Extraction first enters hidden staging. Formal files are committed only after Markdown selection, image renaming, and link validation all succeed. One failed paper cannot publish partial output. Batch preview:

```powershell
obsidian-vault-mcp mineru parse-batch ABCD1234 EFGH5678 --vault-path "$env:OBSIDIAN_VAULT_PATH" --dry-run
```

## 7. Five Analysis types

| Type | Use | Typical Skill |
|---|---|---|
| `full_read` | Complete reading of one paper | `full-read` |
| `literature_review` | Multi-paper review or comparison | `literature-review`, `compare-papers` |
| `passage_qa` | Question answered at a located passage | `passage-qa` |
| `figure_qa` | Figure, table, scheme, or equation interpretation | `figure-qa` |
| `concept` | Cross-paper concept learning | `concept-learning` |

`paper-qa` handles answer-first single-paper questions without forcing persistence. All Analysis types share:

- Status: `draft`, `ready`, `reviewed`, `needs_update`, `archived`.
- Profile: `general`, `medicine`, `chemistry`, `materials`, `catalysis`, `physics`, `mathematics`.
- A stable `analysisId`, source keys, source fingerprint, and managed body block.
- A source change produces `needs_update`; it does not silently replace the old analysis.

Read one paper and retrieve across papers:

```powershell
obsidian-vault-mcp call literature_paper_read --json '{"zotero_key":"ABCD1234","mode":"overview","vault_path":"<VAULT_PATH>"}'
obsidian-vault-mcp call literature_retrieve --json '{"query":"catalytic active sites","intent":"compare","depth":"evidence","vault_path":"<VAULT_PATH>"}'
```

A retrieval response may describe request-local query-variant coverage, but it writes no Coverage file or state. Before writing, have the Agent use `literature_analysis_get` to avoid duplicates, call `literature_analysis_write` with `dry_run: true`, inspect the full preview, and only then commit.

## 8. The single Analysis.base

Rebuild it:

```powershell
obsidian-vault-mcp call literature_rebuild_analysis_base --json '{"vault_path":"<VAULT_PATH>","dry_run":true}'
obsidian-vault-mcp call literature_rebuild_analysis_base --json '{"vault_path":"<VAULT_PATH>","dry_run":false}'
```

`Literature/Analysis/Analysis.base` recursively reads all five types and has nine views:

1. Dashboard
2. Full Reads
3. Reviews
4. Passage Q&A
5. Figure Q&A
6. Concepts
7. Needs Attention
8. By Discipline
9. Recently Updated

V3 does not generate `Literature/Analysis/index.md`, Topic/Theory directories, or Analysis template directories.

## 9. MCP Registry and manual setup

The canonical MCP Registry name is:

```text
io.github.luffysolution-svg/obsidian-vault-mcp
```

Registry-aware clients can install by that name. A manual uvx configuration is:

```json
{
  "mcpServers": {
    "obsidian-vault-mcp": {
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
  }
}
```

For a persistent install, set `command` to `obsidian-vault-mcp` and `args` to `["serve","--transport","stdio"]`.

## 10. Codex, Claude, OpenCode, Pi, Hermes, and WorkBuddy

Shared installer:

```powershell
obsidian-vault-mcp agent install <client> --dry-run
obsidian-vault-mcp agent install <client>
```

`<client>` is `codex`, `claude`, `opencode`, `pi`, `hermes`, or `workbuddy`.

| Client | Installed content |
|---|---|
| Codex | Native marketplace plugin, MCP, and seven Skills |
| Claude Code | Native marketplace plugin, MCP, and seven Skills |
| OpenCode | Project-local MCP configuration and seven Skills |
| Pi | Thin TypeScript Extension over the shared JSON CLI |
| Hermes | MCP configuration; Skills are not auto-installed |
| WorkBuddy | MCP configuration; Skills are not auto-installed |

The Codex/Claude plugin selector is `obsidian-literature@obsidian-vault-mcp`. Installers inspect existing marketplace/plugin state to prevent source conflicts. Configuration-based clients are backed up, merged, validated, and handshake-tested. A failure removes state added by that attempt.

`opencode`, `pi`, `hermes`, and `workbuddy` target a project-local directory. Run from that project or add `--project-dir <PROJECT_DIR>`. When upgrading from 2.x to 3.0.0, first upgrade the Python package exactly with the installer you originally used, then refresh the native plugin cache:

```powershell
uv tool install --force "zotero-obsidian-mcp==3.0.0"
pipx install --force "zotero-obsidian-mcp==3.0.0"
codex plugin add obsidian-literature@obsidian-vault-mcp --json
claude plugin marketplace update obsidian-vault-mcp
claude plugin update obsidian-literature@obsidian-vault-mcp --scope user
```

Codex `plugin add` atomically replaces an older version; restart Claude after its update. The GitHub Release asset `obsidian-vault-mcp-3.0.0-plugins.zip` is an offline marketplace. Verify `SHA256SUMS`, extract it, then run:

```powershell
codex plugin marketplace add "<EXTRACTED_DIR>" --json
codex plugin add obsidian-literature@obsidian-vault-mcp --json

claude plugin marketplace add "<EXTRACTED_DIR>" --scope user
claude plugin install obsidian-literature@obsidian-vault-mcp --scope user
```

If the marketplace name already exists, use the upgrade flow above instead of rebinding it to another path.

### 10.1 Update and uninstall

For Codex and Claude, remove the plugin first. Remove the marketplace only after confirming that no other installed plugin depends on it:

```powershell
codex plugin remove obsidian-literature@obsidian-vault-mcp --json
codex plugin marketplace remove obsidian-vault-mcp --json

claude plugin uninstall obsidian-literature@obsidian-vault-mcp --scope user
claude plugin marketplace remove obsidian-vault-mcp --scope user
```

OpenCode, Pi, Hermes, and WorkBuddy do not share a native uninstall protocol. Follow the installer's returned `uninstall_instructions` exactly and remove only the configuration, Skill, or Extension managed by that installation. Then uninstall the Python package with the original package manager:

```powershell
uv tool uninstall zotero-obsidian-mcp
pipx uninstall zotero-obsidian-mcp
python -m pip uninstall zotero-obsidian-mcp
```

Removing the client plugin, marketplace, or Python package does not delete literature notes, PDFs, MinerU output, Wiki pages, Analysis files, transaction manifests, or backups from the vault. Those research assets require a separate, explicit user decision.

## 11. Exactly seven Skills

The plugin distributes only:

```text
paper-qa
full-read
passage-qa
figure-qa
compare-papers
literature-review
concept-learning
```

Each `SKILL.md` is an entry point and `references/` contains output and discipline rules. Upgrades replace only managed blocks and retain user additions. Older managed Skills are removed safely; unmanaged user files are not deleted.

## 12. Complete 31-tool surface

Stable V2 tools (26):

| Group | Tools |
|---|---|
| System/config | `literature_doctor`, `literature_config_get`, `literature_config_validate`, `literature_config_initialize` |
| Zotero | `zotero_ping`, `zotero_search_items`, `zotero_list_collections`, `zotero_get_item`, `zotero_get_children`, `zotero_get_bibtex` |
| Import/sync | `literature_import_item`, `literature_import_collection`, `literature_sync_item`, `literature_sync_collection` |
| MinerU | `literature_parse_mineru`, `literature_parse_mineru_batch`, `literature_remove_mineru_output` |
| Literature navigation/verification | `literature_rebuild_index`, `literature_rebuild_base`, `literature_verify` |
| Wiki | `literature_wiki_context`, `literature_wiki_write`, `literature_wiki_list` |
| Migration/transactions | `literature_migrate_v1_to_v2`, `literature_preview_transaction`, `literature_rollback_transaction` |

V3 Analysis tools (5):

```text
literature_paper_read
literature_retrieve
literature_analysis_get
literature_analysis_write
literature_rebuild_analysis_base
```

V2-to-V3 Analysis migration is CLI-only and does not create a 32nd MCP tool.

## 13. Migration and rollback

Close applications that may write the vault. Migration defaults to dry-run:

```powershell
obsidian-vault-mcp migrate mineru-images-v2-to-v3 --vault-path "$env:OBSIDIAN_VAULT_PATH"
obsidian-vault-mcp migrate analysis-v2-to-v3 --vault-path "$env:OBSIDIAN_VAULT_PATH"
```

The MinerU image report includes `copiedImages`, `movedImages`,
`preservedLegacyImages`, `rewrittenMarkdown`, `missingReferencedImages`, and
`reparseZoteroKeys`. Safe mode copies images into each paper folder and rewrites
Markdown while preserving flat compatibility aliases. That prevents an
uncoordinated writer from creating a broken old-path reference at the final
instant before commit.

For Analysis, inspect `migratedAnalyses`, `skippedAnalyses`,
`manualReviewRequired`, pending Topic/Theory files, and the planned removal of
the old Analysis index. Then commit:

```powershell
obsidian-vault-mcp migrate mineru-images-v2-to-v3 --vault-path "$env:OBSIDIAN_VAULT_PATH" --apply
obsidian-vault-mcp migrate analysis-v2-to-v3 --vault-path "$env:OBSIDIAN_VAULT_PATH" --apply
obsidian-vault-mcp preview <transaction-id> --vault-path "$env:OBSIDIAN_VAULT_PATH"
obsidian-vault-mcp rollback <transaction-id> --vault-path "$env:OBSIDIAN_VAULT_PATH" --dry-run
obsidian-vault-mcp rollback <transaction-id> --vault-path "$env:OBSIDIAN_VAULT_PATH"
```

To delete legacy flat images, first stop Obsidian, sync clients, indexers, and
every other Vault writer, then run:

```powershell
obsidian-vault-mcp migrate mineru-images-v2-to-v3 --vault-path "$env:OBSIDIAN_VAULT_PATH" --apply --cleanup-legacy --confirm-vault-offline
```

Image copies, Markdown rewrites, and old-image cleanup share one transaction. A
reference from another Vault note blocks destructive cleanup for that paper.

Preview rollback as well. Migration changes only content that can be mapped safely. Ambiguous files remain in place and require manual review.

## 14. End-to-end acceptance with a real vault

Automated tests must never write a user's real vault. Production acceptance has two phases.

### Phase A: real vault, read only

1. Close Obsidian and Zotero, then record paths, sizes, timestamps, and SHA-256 values for key vault directories.
2. Run only `config validate`, `doctor`, `literature_verify`, `literature_paper_read`, `literature_retrieve`, and read-only Analysis queries.
3. Recompute the inventory and prove zero changes.

### Phase B: isolated-copy writes

1. Copy the real vault into a new release-candidate directory, excluding active locks, staging, old backups, and stale temporary directories.
2. Against the copy, test config, import/sync, MinerU, all five Analysis types, all nine Base views, migration, transaction preview, and rollback.
3. Repeat operations to prove stable identity, idempotency, and no duplicate output.
4. Run `literature_verify` and confirm there are no broken links, escaping paths, or obsolete structured state.
5. Reconfirm that the original vault hash inventory is unchanged before release.

### Privacy and maintenance checklist

- MinerU may send selected PDFs to an external service. Confirm document rights, confidentiality requirements, and organizational policy first.
- Keep tokens in protected environment variables or the tool's credential store, never in the project, vault, command history, or chat.
- Never commit machine-specific absolute paths such as `OBSIDIAN_VAULT_PATH` or `linkedAttachmentBaseDir`.
- Preview every write and retain its `transactionId`; validate migration and rollback only against an isolated copy.
- Maintain an independent vault backup. Transaction backups are not a replacement for a complete backup strategy.
- Prefer local stdio integration. Put every network transport behind trusted authentication and access control.

## 15. Troubleshooting

| Symptom | Action |
|---|---|
| `doctor` succeeds but Zotero fails | Start Zotero, enable its local API, and inspect the separate `zotero` result |
| Metadata imports but no PDF is copied | For `storage:` paths, check `ZOTERO_STORAGE_DIR`; for `attachments:` paths, set `zotero.linkedAttachmentBaseDir` or `ZOTERO_LINKED_ATTACHMENT_BASE_DIR` |
| A linked attachment is outside its base | Use the same linked attachment base in Zotero and this project; the path must stay inside it and contain no `..` traversal or drive prefix |
| MinerU command exists but parsing fails | Availability is not authentication/network readiness; run one real parse only in the isolated copy |
| Image links collide | Upgrade to 3.0.0; V3 uses `image/{key}/{key}-figNN.ext` |
| Analysis shows `needs_update` | Its source fingerprint changed; review and explicitly update it |
| Analysis Base is missing | Call `literature_rebuild_analysis_base`; do not create an Analysis index |
| Client does not show 31 tools | Verify the actual distribution and launch command, restart the client, and repeat handshake |
| Migration is ambiguous | Do not use `--apply`; resolve `manualReviewRequired` or test only in the isolated copy |

For implementation details, the test matrix, and release gates, continue with the [developer guide](../DEVELOPMENT.en.md).
