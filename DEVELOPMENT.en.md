# Obsidian Vault MCP V2 Developer Guide

[中文开发者文档](./DEVELOPMENT.md) · [English user guide](./README.en.md) · [English tutorial](./docs/index.en.md)

This document is the implementation and release contract for V2. The package is a local Zotero → MinerU → Obsidian pipeline with two thin interfaces—the CLI and MCP—over one application layer.

## Supported baseline

- Release: `2.0.1`
- Python: 3.10–3.13
- Runtime dependencies: `mcp>=1.10,<2`, `PyYAML>=6.0,<7`
- Package/distribution: `zotero-obsidian-mcp`
- Import package: `obsidian_vault_mcp`
- Console entry point: `obsidian-vault-mcp`
- MCP server name: `obsidian-literature`
- License: MIT

The version must agree in `pyproject.toml`, `src/obsidian_vault_mcp/__init__.py`, `.codex-plugin/plugin.json`, and `adapters/pi/package.json`. Release tags use `vMAJOR.MINOR.PATCH`; the current tag is `v2.0.1`.

## Non-negotiable V2 contracts

1. A Zotero parent item's permanent identity is its `zoteroKey`.
2. One parent item maps to one main note, normally `Literature/{zoteroKey}.md`.
3. User-visible files contain vault-relative paths with `/` separators. Machine paths may appear only in hidden state.
4. Managed frontmatter is deterministic, omits empty values, and preserves unknown user fields.
5. User Markdown outside managed markers is never replaced by synchronization.
6. Every formal write can be previewed and goes through locking, staging, backup, atomic replacement, and rollback.
7. A vault has one configuration file: `.obsidian-vault-mcp.json` with `schemaVersion: 2`.
8. The public MCP surface is exactly the 26 tools listed below. Do not restore V1 names or removed modes.
9. Native Agent clients connect through MCP. Pi uses a thin TypeScript Extension that calls the JSON CLI; V2 ships no mirrored Skills.

The fixed managed frontmatter order is:

```text
title
itemType
year
journal
tags
doi
url
abstract
zoteroKey
zoteroPdfLink
attachmentPdfLink
attachmentMinerULink
```

`frontmatter.fieldOrder` is present in the config so the effective contract is inspectable, but runtime validation requires this exact order.

## Architecture

Production code lives under `src/obsidian_vault_mcp/`:

```text
domain/
  identity.py       zoteroKey validation and filename rendering
  models.py         normalized item/state models
  paths.py          vault-relative path rules
  frontmatter.py    strict parse/merge/ordering
  errors.py         structured domain failures
application/
  import_service.py     parent-item and collection import
  sync_service.py       incremental refresh of existing items
  mineru_service.py     staged extraction and normalization
  index_service.py      deterministic dashboard
  base_service.py       native Obsidian Base
  wiki_service.py       context, source validation, safe writeback
  migration_service.py  V1 discovery, planning, and migration
  transaction_service.py preview, commit, manifest, and rollback
  config_service.py / doctor_service.py / verify_service.py
adapters/
  zotero/           local HTTP API, pagination, attachments, BibTeX
  mineru/            mineru-open-api subprocess and output normalizer
  vault/             filesystem, locks, atomic writes
  obsidian/          Markdown, Index, and Base renderers
interfaces/
  cli/               argument parsing and one-JSON-value output
  mcp/               MCP server registration and tool functions
  agent_install/     merge-safe installers for six Agent clients
config/
  defaults.py        canonical effective config
  schema.py          strict validation and normalization
  loader.py          the single vault config loader
```

Dependencies point inward: interfaces parse/serialize, adapters perform I/O, application services orchestrate use cases, and domain/config code holds invariants. Business behavior does not belong in CLI or MCP wrappers.

### End-to-end write path

```text
CLI or MCP tool
    → resolve vault
    → load and strictly validate config
    → application service
    → Zotero/MinerU adapter reads
    → deterministic render/normalize
    → transaction preview
    → item/global lock
    → stage → back up → atomic replace
    → committed manifest + hidden item state
```

Import and sync are idempotent around `zoteroKey`. They search the direct children of the configured literature root for an existing main note with that key. More than one matching main note is an identity conflict, not a cue to guess.

### User content ownership

Generated note sections use `<!-- ovm:*:start -->` / `<!-- ovm:*:end -->` markers. Application services replace only the matching managed region. The configured Reading Notes heading and all unmarked user sections remain user-owned. Unknown frontmatter values are preserved after the fixed managed keys.

### Hidden state and transactions

Hidden state under `.obsidian-vault-mcp/` records the source PDF path and hashes, canonical note/PDF/MinerU paths, Zotero version, timestamps, status, errors, and last transaction ID. That directory also owns staging, backups, locks, and transaction manifests.

A transaction plans create/replace/delete/copy operations with vault-relative destinations. Commit previews while holding the relevant lock, stages only changed files, backs up existing destinations, writes a prepared manifest, atomically replaces targets, marks the manifest committed, and removes owned staging. Rollback compares current hashes with the recorded post-commit hashes and refuses to overwrite later user changes unless `overwrite-managed` is explicitly selected.

Supported conflict policies are `preserve-user`, `overwrite-managed`, `fail`, and `rename`. Their effect is use-case-specific: for example, `rename` can resolve an occupied main-note or Wiki destination, while MinerU normalization uses stable paths and has no equivalent user-file collision to rename.

## The 26 MCP tools

The canonical order is `TOOL_FUNCTIONS` in `interfaces/mcp/tools/__init__.py`.

| Group | Tool | Purpose |
|---|---|---|
| System | `literature_doctor` | Report vault/config status and separate Zotero/MinerU readiness. |
| System | `literature_config_get` | Return the normalized effective V2 config. |
| System | `literature_config_validate` | Validate supplied JSON or the vault config. |
| System | `literature_config_initialize` | Create the one config through the transaction engine. |
| Zotero | `zotero_ping` | Probe the Zotero Desktop local API. |
| Zotero | `zotero_search_items` | Search all matching items with complete pagination. |
| Zotero | `zotero_list_collections` | List all collections with complete pagination. |
| Zotero | `zotero_get_item` | Return one normalized Zotero item. |
| Zotero | `zotero_get_children` | Return notes, annotations, attachments, and other children. |
| Zotero | `zotero_get_bibtex` | Try Better BibTeX, Zotero export, then configured fallback. |
| Import/sync | `literature_import_item` | Import or idempotently refresh one parent item. |
| Import/sync | `literature_import_collection` | Import every parent item in a collection. |
| Import/sync | `literature_sync_item` | Refresh an item that must already exist. |
| Import/sync | `literature_sync_collection` | Refresh imported items from a collection. |
| MinerU | `literature_parse_mineru` | Parse and normalize one imported PDF. |
| MinerU | `literature_parse_mineru_batch` | Parse a deduplicated key batch with bounded concurrency. |
| MinerU | `literature_remove_mineru_output` | Transactionally remove derived Markdown/images and links. |
| Knowledge | `literature_rebuild_index` | Deterministically rebuild `Literature/index.md`. |
| Knowledge | `literature_rebuild_base` | Deterministically rebuild `Literature/Literature.base`. |
| Knowledge | `literature_verify` | Audit identities, links, paths, state, and generated assets. |
| Wiki | `literature_wiki_context` | Rank source-linked local context for an Agent-authored topic. |
| Wiki | `literature_wiki_write` | Validate source keys and safely write Agent-supplied Wiki prose. |
| Wiki | `literature_wiki_list` | List direct Wiki topic pages deterministically. |
| Migration | `literature_migrate_v1_to_v2` | Preview or apply the V1 → V2 migration. |
| Migration | `literature_preview_transaction` | Return the safe manifest of a committed transaction. |
| Migration | `literature_rollback_transaction` | Preview or restore the files backed up by a transaction. |

The generic bridge is deliberately small:

```bash
obsidian-vault-mcp call literature_import_item \
  --json '{"zotero_key":"ABCD1234","vault_path":"/vault","dry_run":true}'
```

The CLI emits exactly one JSON value for each non-server invocation. On a legacy Windows console, it falls back to ASCII-escaped JSON rather than corrupting Unicode.

## Interfaces and client installers

The recommended server transport is local `stdio`:

```bash
obsidian-vault-mcp serve --transport stdio
```

SSE and streamable HTTP are available for controlled integration testing, but the server does not add authentication or TLS. Do not expose either directly to an untrusted network.

The one-click client installer first detects the client executable, parses and validates the destination config, makes a timestamped backup when needed, merges only the `obsidian-literature` entry, writes atomically, and performs an MCP initialization handshake. A failed handshake restores the previous file.

| Client | Executable probed | Project-local destination | Vault environment in generated entry |
|---|---|---|---|
| Codex | `codex` | `.mcp.json` | `OBSIDIAN_VAULT_PATH=auto` |
| Claude Code | `claude` | `.mcp.json` | `OBSIDIAN_VAULT_PATH=auto` |
| OpenCode | `opencode` | `opencode.json` | Inherits launcher environment |
| Hermes | `hermes` | `.hermes/config.yaml` | `OBSIDIAN_VAULT_PATH=auto` |
| WorkBuddy | `workbuddy` | `.workbuddy/mcp.json` | `OBSIDIAN_VAULT_PATH=auto` |
| Pi | `pi` | `.pi/extensions/obsidian-vault-mcp.ts` | Extension inherits launcher environment |

Pi is the only non-native-MCP adapter. `adapters/pi/index.ts` is the distributable source, and `src/obsidian_vault_mcp/interfaces/agent_install/pi_extension.ts` is the wheel resource. The two files must remain byte-identical. The Extension invokes:

```text
obsidian-vault-mcp call <tool> --json <object>
```

It uses process spawning without a shell, forwards cancellation, enforces a 660-second timeout and 1 MiB output cap, and converts non-JSON or structured CLI failures into tool errors.

## Zotero adapter contract

V2 talks to the Zotero Desktop local API, normally `http://127.0.0.1:23119/api`. It does not use the cloud library API and therefore does not need a Zotero cloud API key.

Collection and search endpoints are exhausted with `start`/`limit` pagination. Offsets advance by the number actually returned, and duplicate identities across pages are treated as an upstream pagination error. Parent imports exclude `attachment`, `note`, and `annotation` items from the collection root and fetch those as children instead.

PDF resolution supports Zotero attachment metadata and an optional `ZOTERO_STORAGE_DIR` override for `storage:` paths. Zotero `attachments:` linked-file paths resolve against the non-empty `zotero.linkedAttachmentBaseDir` config value or the `ZOTERO_LINKED_ATTACHMENT_BASE_DIR` environment fallback. Resolution rejects traversal, drive-prefixed relative values, and any result outside that base directory. Source absolute paths remain hidden. BibTeX provider order in `auto` mode is Better BibTeX, Zotero export, then the built-in deterministic fallback; local `file` fields are removed before content enters a vault note.

## MinerU adapter contract

The adapter executes `mineru-open-api` (or `MINERU_CLI_COMMAND`) into a transaction-owned staging directory. On Windows it resolves the corresponding `.cmd` shim when needed.

Mode mapping is intentionally explicit:

| Config value | CLI operation |
|---|---|
| `auto` + token in `MINERU_TOKEN`, `MINERU_API_TOKEN`, or `~/.mineru/config.yaml` | `extract` (precision) |
| `auto` without a token | `flash-extract` |
| `api` | `extract` |
| `local` | `flash-extract` (compatibility name; not an in-process local model) |

The normalizer selects one Markdown result, renames images deterministically, rewrites image links relative to the configured MinerU Markdown directory, and rejects unsupported or unsafe output. Formal files are committed only after normalization succeeds. Batch concurrency is bounded by `mineru.maxConcurrentJobs`.

## Index, Base, and Wiki

The Index renderer scans canonical top-level main notes, sorts deterministically, and owns marked regions for recent items, year/journal/tag groups, Wiki topics, and maintenance counts.

The Base renderer emits a native `.base` YAML document filtered to the configured literature root and `zoteroKey != null`. It defines a primary table plus By Year, By Journal, By Tag, MinerU Complete, Missing PDF, and Missing DOI views.

Wiki context is deterministic weighted lexical matching over titles, tags, abstracts, Zotero notes, and a bounded MinerU excerpt. It is not an embedding index and does not call a model. The connected Agent authors the synthesis and must pass at least one source `zoteroKey`; writeback verifies that every key resolves to exactly one main note and appends any missing source-note links.

## Configuration development

`config/defaults.py` is the single source for defaults. `config/schema.py` rejects unknown keys, wrong types, unsafe paths, duplicate group names, unsupported enums, unstable filename patterns, and a non-V2 identity strategy. Partial user config is deep-merged over defaults only after validating its shape.

When adding or changing a field:

1. Update defaults and strict validation together.
2. Add focused schema tests, including an invalid case.
3. Thread the value into an application service rather than reading ad hoc JSON in an interface.
4. Update both language tutorials and explicitly label fields that are fixed or compatibility-only.
5. Preserve `schemaVersion: 2` unless the persisted contract truly changes.

## Development setup

```bash
git clone https://github.com/luffysolution-svg/obsidian-vault-mcp.git
cd obsidian-vault-mcp
python -m venv .venv
```

Activate the environment:

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

```bash
# macOS/Linux
source .venv/bin/activate
```

Install in editable mode:

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Tests that write must use temporary vaults, including cases with spaces and non-ASCII path components. Unit and contract tests must not contact a real Zotero library or MinerU service.

## Verification

Run the focused suite while developing, then the full release gates before handoff:

```bash
python -m ruff check src tests scripts/verify_release.py
python -m pytest tests/unit tests/contract tests/repository
python scripts/verify_release.py
```

The 2.0.1 release candidate currently reports 119 passing pytest cases. Treat the observed count as informational; the pass/fail result and release verifier are the contract.

CI runs Python 3.10, 3.11, 3.12, and 3.13 on Ubuntu, Windows, and macOS. It also builds and smoke-installs a wheel. A separate Node 22 job installs the Pi adapter dependencies and runs its TypeScript check.

## Build and release

Build in an empty output directory so the verifier sees exactly one wheel and one source distribution:

```bash
python -m build --wheel --sdist --outdir dist
python scripts/verify_release.py \
  --artifacts-dir dist \
  --require-sdist \
  --smoke-wheel
```

Build and verify the Codex plugin bundle:

```powershell
pwsh ./scripts/build_release.ps1
python scripts/verify_release.py --bundle-dir dist
```

Generate and verify a checksum manifest (the release workflow runs this on Linux):

```bash
cd dist
sha256sum -- *.whl *.tar.gz *.zip > SHA256SUMS
cd ..
python scripts/verify_release.py --checksums-dir dist
```

Expected artifacts for `2.0.1` are:

```text
dist/zotero_obsidian_mcp-2.0.1-py3-none-any.whl
dist/zotero_obsidian_mcp-2.0.1.tar.gz
dist/obsidian-vault-mcp-2.0.1.zip
dist/SHA256SUMS
```

The Codex ZIP is intentionally limited to two tracked files under `obsidian-literature/`: `.codex-plugin/plugin.json` and `.mcp.json`. Do not add source, docs, credentials, or vault data to that bundle.

The artifact verifier checks dependency bounds, version agreement, portable client configs, removed-path hygiene, Pi source/resource identity, wheel/sdist contents, the installed console entry point, config validation, and a 26-tool stdio initialization handshake.

After the release commit has passed CI and reached `main`, create the tag, verify it locally, and only then push it:

```bash
git switch main
git pull --ff-only
git tag -a v2.0.1 -m "Obsidian Vault MCP V2.0.1"
python scripts/verify_release.py --tag v2.0.1
git push origin v2.0.1
```

The release workflow checks out the tag, repeats all gates, builds all three artifacts, and creates or updates the GitHub release. The tag must resolve to the checked-out commit.

PyPI publication must use the already verified wheel and sdist, never a rebuild from another commit. Prefer a PyPI trusted publisher in CI. For a manual upload, keep the API token in `TWINE_PASSWORD` (username `__token__`) or an OS credential store, run `python -m twine check dist/*.whl dist/*.tar.gz`, and never paste the token into a command line, file, log, issue, commit, or release note.

## Security and privacy review

Review these boundaries for every change:

- Vault paths: reject absolute paths, traversal, Windows drive/UNC forms, and internal staging references in user-visible content.
- Credentials: read Zotero/MinerU/client credentials from the environment or their own local stores; never persist them in the vault config or state.
- Subprocesses: invoke MinerU and Pi's CLI bridge without a shell; redact token arguments from recorded commands.
- Network: Zotero defaults to loopback. MinerU is external. Non-stdio MCP transports need an authenticated reverse proxy or other trusted boundary.
- Writes: resolve and validate the exact vault target, stage before replacement, back up replaced files, and retain rollback evidence.
- User ownership: preserve unknown frontmatter and unmarked Markdown; never convert a failed parse into a partial success.
- Release: exclude vaults, tokens, machine paths, virtual environments, caches, test output, staging, backups, and `dist/` from Git.

## Current limitations in 2.0.1

- Zotero integration is local Desktop only; cloud libraries and cloud API keys are outside the V2 surface.
- `OBSIDIAN_VAULT_PATH=auto` searches only the server process's current directory and parents. It does not enumerate Obsidian's registered vaults.
- `literature_doctor.ok` reflects configuration validity. Integration readiness remains in `zotero.ok` and `mineru.available`.
- MinerU integration targets the Open API CLI. The config value `local` is a compatibility mapping to token-free `flash-extract`, not an offline local model backend.
- MinerU parse dry-runs validate the imported item/PDF and report the planned staging/output paths, but do not contact MinerU or predict the extracted file set.
- MinerU batch and collection operations return bounded summaries (20 entries by default); aggregate counts remain authoritative when `truncated` is true.
- `safety.retainBackups` is validated but 2.0.1 does not prune old transaction backups automatically; operators must apply their own retention policy to the hidden backup directory.
- Wiki retrieval is lexical and bounded; semantic ranking and prose generation belong to the connected Agent.
- The server accepts SSE and streamable HTTP but supplies no built-in authentication, authorization, or TLS.
- One process invocation resolves one vault path. Multi-vault orchestration requires separate client entries or explicit per-tool `vault_path` values.
- The WorkBuddy installer currently probes an executable named `workbuddy`; client distributions that expose only another command name cannot use the one-click path without a compatible shim or a future installer update.
- Pi tool calls have a 660-second Extension timeout. Exceptionally long MinerU jobs can still exceed it; use the native MCP/CLI path for those jobs or adjust the adapter in a reviewed change.

## Contribution checklist

- Every changed line traces to the requested behavior.
- New behavior has a focused failing test first when practical.
- No test contacts a private vault, Zotero library, or MinerU service.
- `zoteroKey`, portable paths, user content, and transaction guarantees still hold.
- CLI and MCP remain thin and return structured JSON-safe values.
- The tool count and names remain exactly 26 unless a new versioned contract is approved.
- Pi sources are byte-identical after any Extension change.
- Ruff, pytest, repository verification, artifact verification, and wheel smoke tests pass as appropriate.
- English and Chinese canonical docs agree with the live implementation.
