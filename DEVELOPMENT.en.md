# Obsidian Vault MCP V2 Developer Guide

[中文开发者文档](./DEVELOPMENT.md) · [English user guide](./README.en.md) · [English tutorial](./docs/index.en.md)

This document is the implementation and release contract for V2. The package is a local Zotero → MinerU → Obsidian pipeline with two thin interfaces—the CLI and MCP—over one application layer.

## Supported baseline

- Release: `2.1.0`
- Python: 3.10–3.13
- Runtime dependencies: `mcp>=1.10,<2`, `PyYAML>=6.0,<7`
- Package/distribution: `zotero-obsidian-mcp`
- Import package: `obsidian_vault_mcp`
- Console entry point: `obsidian-vault-mcp`
- MCP server name: `obsidian-literature`
- Plugin marketplace: `obsidian-vault-mcp`
- Codex/Claude plugin: `obsidian-literature`
- License: MIT

The version must agree in `pyproject.toml`, `src/obsidian_vault_mcp/__init__.py`, the version-bearing Claude marketplace fields, both packaged client manifests, and `adapters/pi/package.json`. The Codex marketplace manifest has no version field; its identity and local source path are still verified. Release tags use `vMAJOR.MINOR.PATCH`; the current release contract is `v2.1.0`.

## Non-negotiable V2 contracts

1. A Zotero parent item's permanent identity is its `zoteroKey`.
2. One parent item maps to one main note, normally `Literature/{zoteroKey}.md`.
3. User-visible files contain vault-relative paths with `/` separators. Machine paths may appear only in hidden state.
4. Managed frontmatter is deterministic, omits empty values, and preserves unknown user fields.
5. User Markdown outside managed markers is never replaced by synchronization.
6. Every formal write can be previewed and goes through locking, staging, backup, atomic replacement, and rollback.
7. A vault has one configuration file: `.obsidian-vault-mcp.json` with `schemaVersion: 2`.
8. The public MCP surface is exactly the 33 tools listed below: all original 26 V2 tools plus seven V2.1 structured-reading tools. Do not restore V1 names or removed modes.
9. Codex Desktop/CLI and Claude Code use their native marketplace plugin lifecycle. OpenCode uses project MCP plus Skills, Pi uses a thin TypeScript Extension, and Hermes/WorkBuddy remain MCP-only. Nine model-independent Skills live only inside one canonical packaged plugin tree, never client-specific mirrors.

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
  evidence.py       deterministic original-text EvidenceChunks
  image_assets.py   image identity, status, and Manifest models
  analysis.py       analysis claims and uncertainty models
  paths.py          vault-relative path rules
  frontmatter.py    strict parse/merge/ordering
  errors.py         structured domain failures
application/
  import_service.py     parent-item and collection import
  sync_service.py       incremental refresh of existing items
  mineru_service.py     staged extraction and normalization
  evidence_service.py   rebuildable evidence state
  paper_read_service.py bounded single-paper evidence views
  analysis_service.py   structured context and safe Analysis writeback
  uncertainty_service.py audited claim review
  analysis_index_service.py deterministic Analysis index
  retrieval_service.py / coverage_service.py bounded cross-paper retrieval
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
  agent_install/     native Codex/Claude plugin entry points and four project adapters
config/
  defaults.py        canonical effective config
  schema.py          strict validation and normalization
  loader.py          the single vault config loader
resources/
  agent_marketplace/ canonical dual-client marketplace, shared MCP, and nine Skills
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

Item state also carries `collectionKeys`, the known Zotero memberships used by `literature_retrieve.scope.collection_key`, and `mineruAssetRoot`, the current per-item Manifest/candidate-cache root. The latter lets a `candidateCacheFolder` change remove the old root and install the new root in one rollback-capable transaction. Legacy state without either field remains readable and is incrementally populated by later import, sync, or MinerU work.

### User content ownership

Generated note sections use `<!-- ovm:*:start -->` / `<!-- ovm:*:end -->` markers. Application services replace only the matching managed region. The configured Reading Notes heading and all unmarked user sections remain user-owned. Unknown frontmatter values are preserved after the fixed managed keys.

### Hidden state and transactions

Hidden state under `.obsidian-vault-mcp/` records the source PDF path and hashes, canonical note/PDF/MinerU paths, Zotero version, timestamps, status, errors, and last transaction ID. That directory also owns staging, backups, locks, and transaction manifests.

A transaction plans create/replace/delete/copy operations with vault-relative destinations. Commit previews while holding the relevant lock, stages only changed files, backs up existing destinations, writes a prepared manifest, atomically replaces targets, marks the manifest committed, and removes owned staging. Rollback compares current hashes with the recorded post-commit hashes and refuses to overwrite later user changes unless `overwrite-managed` is explicitly selected.

Supported conflict policies are `preserve-user`, `overwrite-managed`, `fail`, and `rename`. Their effect is use-case-specific: for example, `rename` can resolve an occupied main-note or Wiki destination, while MinerU normalization uses stable paths and has no equivalent user-file collision to rename.

## The 33 MCP tools

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
| Structured reading | `literature_paper_read` | Read overview, targeted, section, full, or figure evidence from one paper. |
| Structured reading | `literature_analysis_context` | Organize evidence for the 13-section reading template. |
| Structured reading | `literature_analysis_write` | Validate anchors and transactionally write an Analysis note. |
| Structured reading | `literature_uncertainty_list` | List uncertainty items and audit history. |
| Structured reading | `literature_uncertainty_resolve` | Resolve one uncertainty with validated evidence. |
| Structured reading | `literature_rebuild_analysis_index` | Rebuild the deterministic Analysis index. |
| Structured reading | `literature_retrieve` | Retrieve bounded evidence across an explicit paper scope. |
| Wiki | `literature_wiki_context` | Rank source-linked local context for an Agent-authored topic. |
| Wiki | `literature_wiki_write` | Validate source keys and safely write Agent-supplied Wiki prose. |
| Wiki | `literature_wiki_list` | List direct Wiki topic pages deterministically. |
| Migration | `literature_migrate_v1_to_v2` | Preview or apply the V1 → V2 migration. |
| Migration | `literature_preview_transaction` | Return the safe manifest of a committed transaction. |
| Migration | `literature_rollback_transaction` | Preview or restore the files backed up by a transaction. |

The generic bridge is deliberately small:

```bash
obsidian-vault-mcp call literature_import_item \
  --json '{"zotero_key":"ABCD1234","vault_path":"<VAULT_DIR>","dry_run":true}'
```

The CLI emits exactly one JSON value for each non-server invocation. On a legacy Windows console, it falls back to ASCII-escaped JSON rather than corrupting Unicode.

## Interfaces and client installers

The recommended server transport is local `stdio`:

```bash
obsidian-vault-mcp serve --transport stdio
```

SSE and streamable HTTP are available for controlled integration testing, but the server does not add authentication or TLS. Do not expose either directly to an untrusted network.

The production path for Codex Desktop/CLI and Claude Code is the client-native marketplace plugin lifecycle. `obsidian-vault-mcp agent install codex|claude` is a convenience wrapper: it resolves `obsidian_vault_mcp.resources.agent_marketplace` from the installed wheel, invokes the native CLI, and uses marketplace/plugin lists for idempotency. The uniform `project_dir` argument remains accepted but does not cause a project `.mcp.json` or project Skills write. An existing marketplace name that points elsewhere is a safe failure.

| Client | Executable | Mechanism | MCP/Extension destination | Skill destination | Vault environment |
|---|---|---|---|---|---|
| Codex Desktop/CLI | `codex` | Native marketplace plugin | Codex-managed | Nine bundled Skills | Inherits launcher environment |
| Claude Code | `claude` | Native marketplace plugin, user scope | Claude-managed | Nine bundled Skills | Inherits launcher environment |
| OpenCode | `opencode` | Transactional project adapter | `opencode.json` | `.opencode/skills` | Inherits launcher environment |
| Hermes | `hermes` | MCP-only profile adapter | `$HERMES_HOME/config.yaml` (default: `~/.hermes/config.yaml`) | None; warning | `OBSIDIAN_VAULT_PATH=auto` |
| WorkBuddy | `codebuddy` (fallback: `cbc`) | MCP-only project adapter | `.workbuddy/mcp.json` | None; warning | `OBSIDIAN_VAULT_PATH=auto` |
| Pi | `pi` | Thin Extension project adapter | `.pi/extensions/obsidian-vault-mcp.ts` | None; Extension-only | Inherits launcher environment |

The native command contract is:

```text
codex plugin marketplace add <MARKETPLACE_DIR>
codex plugin add obsidian-literature@obsidian-vault-mcp
claude plugin marketplace add <MARKETPLACE_DIR> --scope user
claude plugin install obsidian-literature@obsidian-vault-mcp --scope user
```

`PluginInstallResult` must serialize the client/executable, marketplace name/path, plugin selector/version, dry-run/changed state, preexisting/added/installed state, planned or executed commands, handshake state, and uninstall instructions. Native Codex/Claude installation performs a direct stdio initialization handshake after the plugin commands; this proves that the packaged runtime starts, while plugin and Skill discovery still requires a new client session. It never writes or handshakes through project configuration. Codex removal uses `plugin remove`; Claude uses `plugin uninstall --scope user`, and its marketplace removal must also use `--scope user`; remove the marketplace only after checking that nothing else depends on it.

OpenCode, WorkBuddy, and Pi retain the project-adapter transaction, while Hermes uses the same transaction against its profile configuration: detect executable, plan, back up, write atomically, perform an MCP initialization handshake, and roll back on failure. Dry-runs do not write or handshake. OpenCode additionally validates managed Skill hashes and keeps config/Skills in one rollback boundary. The shared `project_dir` argument is ignored by Hermes; an explicit `config_path` override is available only through the Python installer API, not the `agent install` CLI.

The sole canonical Skill tree is `src/obsidian_vault_mcp/resources/agent_marketplace/plugins/obsidian-literature/skills/`. Codex/Claude consume it directly inside the plugin. OpenCode installs `.obsidian-vault-mcp-skills.json` with versions and managed-block hashes; upgrades replace only the managed block and preserve `User Customizations`. A modified managed block or legacy untracked format is rejected before writes. Do not add client mirrors or synchronization scripts, and do not guess `.hermes/skills` or `.workbuddy/skills`.

The shared Codex/Claude `.mcp.json` does not set `OBSIDIAN_VAULT_PATH`; it inherits the launching process environment, as do OpenCode and Pi. The Hermes profile configuration and WorkBuddy project template may use `auto`, which searches only the process working directory and parents. Never commit a real machine path.

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

## V2.1 image, evidence, and analysis state

- Each MinerU paper has `.obsidian-vault-mcp/cache/mineru-assets/{zoteroKey}/manifest.json`. Referenced images enter the formal image folder; unlinked candidates stay only in the adjacent hidden `assets/` cache. An `assetId` derives from `zoteroKey` and the content SHA-256, never `figNN` order.
- `.obsidian-vault-mcp/state/evidence/{zoteroKey}.json` stores stable EvidenceChunks with section paths, original text, block links, content hashes, source fingerprints, and related assets. Rebuild physically writes deterministic `^ev-*` block IDs into derived MinerU Markdown in the same transaction as state/Manifest updates, and Verify requires every anchor to exist exactly once. An unverifiable page is always `null`.
- `Literature/Analysis/{zoteroKey}.md` owns only the `ovm:analysis` and `ovm:analysis-uncertainties` blocks. `.obsidian-vault-mcp/state/uncertainties/{zoteroKey}.json` preserves the original claim and append-only resolution history.
- Newly imported Zotero child notes and annotations use source markers inside the existing `ovm:zotero-notes` managed block, so `literature_analysis_context` can return `zoteroNotes` and `zoteroAnnotations` separately while offline. Legacy combined content remains in `zoteroNotes` with a compatibility warning.
- `.obsidian-vault-mcp/state/coverage/{zoteroKey}.json` records what was actually read. Read tools do not write it by default: `record_coverage=true` explicitly routes the update through TransactionService, and the returned `coverageLedger` carries a real or dry-run `transactionId`. It is audit metadata, not paper evidence; a changed source hash makes the old record stale.
- `Literature/Analysis/index.md` is rebuilt deterministically from Analysis notes and state. Its one-line positioning field is explicitly `agent_synthesis`.

P0 does not include reliable PDF figure cropping, panel segmentation, OCR fallback, multimodal interpretation, embeddings, or reranking. The existence of a MinerU image is never visual verification.

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
python -m ruff check src tests scripts
python -m pytest tests/unit tests/contract tests/repository
python scripts/verify_release.py
```

The observed pytest count is informational; the pass/fail result and release verifier are the contract.

CI runs Python 3.10, 3.11, 3.12, and 3.13 on Ubuntu, Windows, and macOS. It also builds and smoke-installs a wheel. A separate Node 22 job installs the Pi adapter dependencies and runs its TypeScript check.

## Build and release

Build in an empty output directory so the verifier sees exactly one wheel, one source distribution, and one dual-client plugin marketplace ZIP from the same checkout:

```bash
python -m build --wheel --sdist --outdir dist
python scripts/build_release.py --version 2.1.0 --output-dir dist
python scripts/verify_release.py --artifacts-dir dist --require-sdist --smoke-wheel --bundle-dir dist
```

`scripts/build_release.py` is the canonical cross-platform entry point for Windows, macOS, and Linux. The PowerShell command below is a compatibility wrapper and must produce the same deterministic ZIP:

```powershell
./scripts/build_release.ps1 -Version 2.1.0 -OutputDir dist
```

Generate and verify a checksum manifest (the release workflow runs this on Linux):

```bash
cd dist
sha256sum -- *.whl *.tar.gz *.zip > SHA256SUMS
cd ..
python scripts/verify_release.py --checksums-dir dist
```

Expected artifacts for `2.1.0` are:

```text
dist/zotero_obsidian_mcp-2.1.0-py3-none-any.whl
dist/zotero_obsidian_mcp-2.1.0.tar.gz
dist/obsidian-vault-mcp-2.1.0-plugins.zip
dist/SHA256SUMS
```

The plugin ZIP root is `<MARKETPLACE_DIR>` itself; there is no extra `obsidian-literature/` wrapper. Its exact 15-file allowlist is:

```text
.agents/plugins/marketplace.json
.claude-plugin/marketplace.json
plugins/obsidian-literature/.codex-plugin/plugin.json
plugins/obsidian-literature/.claude-plugin/plugin.json
plugins/obsidian-literature/.mcp.json
plugins/obsidian-literature/assets/icon.svg
plugins/obsidian-literature/skills/analyze-figures/SKILL.md
plugins/obsidian-literature/skills/compare-papers/SKILL.md
plugins/obsidian-literature/skills/evidence-based-qa/SKILL.md
plugins/obsidian-literature/skills/literature-review/SKILL.md
plugins/obsidian-literature/skills/structured-paper-note/SKILL.md
plugins/obsidian-literature/skills/theory-note-synthesis/SKILL.md
plugins/obsidian-literature/skills/topic-note-synthesis/SKILL.md
plugins/obsidian-literature/skills/uncertainty-audit/SKILL.md
plugins/obsidian-literature/skills/verify-paper-claims/SKILL.md
```

That contract is two marketplace manifests, two client plugin manifests, one shared compatible `.mcp.json`, one Codex App icon, and nine Skills. The ZIP contains no Python runtime, `__init__.py`, source, docs, credentials, vault data, or machine path. Wheel/sdist must contain the same canonical marketplace resource, the V2 CLI, and the Pi installer resource, with no legacy `agent_skills` tree or V1 Skill mirror.

Validate the plugin itself before handoff. Keep the local Plugin Creator location as a placeholder instead of documenting a personal Codex Home path:

```bash
python "<PLUGIN_CREATOR_DIR>/scripts/validate_plugin.py" "src/obsidian_vault_mcp/resources/agent_marketplace/plugins/obsidian-literature"
claude plugin validate --strict "src/obsidian_vault_mcp/resources/agent_marketplace/plugins/obsidian-literature"
```

The artifact verifier checks dependency bounds, both marketplace identities/sources, version agreement across version-bearing manifests, portable MCP config, the exact nine-Skill set, removed-path hygiene, Pi source/resource identity, wheel/sdist/plugin ZIP contents, the installed console entry point, config validation, and a 33-tool stdio initialization handshake.

Production local acceptance starts from `dist`, not an editable checkout: install `"<WHEEL_PATH>"` with `pipx` or `uv tool`, extract the plugin ZIP, give its root to the native Codex/Claude marketplace commands, start new sessions, confirm 33 tools and nine Skills, then repeat real single-paper, batch, image, and Skill→MCP Zotero→MinerU→Obsidian flows. The shared marketplace protocol has passed isolated probes with Codex CLI 0.145 and Claude Code 2.1.217; every release candidate must still repeat full acceptance from its own artifacts.

Only after explicit user authorization for remote publication, and after the release commit has passed CI and reached `main`, create the tag, verify it locally, and then push it. Preparing a production candidate or showing these commands does not assert that a tag, GitHub Release, or PyPI version already exists:

```bash
git switch main
git pull --ff-only
git tag -a v2.1.0 -m "Obsidian Vault MCP V2.1.0"
python scripts/verify_release.py --tag v2.1.0
git push origin v2.1.0
```

The release workflow should check out the tag, repeat all gates, build all three artifacts, and create or update an authorized GitHub release. The tag must resolve to the checked-out commit.

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

## Current limitations in 2.1.0

- Zotero integration is local Desktop only; cloud libraries and cloud API keys are outside the V2 surface.
- `OBSIDIAN_VAULT_PATH=auto` searches only the server process's current directory and parents. It does not enumerate Obsidian's registered vaults.
- `literature_doctor.ok` reflects configuration validity. Integration readiness remains in `zotero.ok` and `mineru.available`.
- MinerU integration targets the Open API CLI. The config value `local` is a compatibility mapping to token-free `flash-extract`, not an offline local model backend.
- MinerU parse dry-runs validate the imported item/PDF and report the planned staging/output paths, but do not contact MinerU or predict the extracted file set.
- MinerU batch and collection operations return bounded summaries (20 entries by default); aggregate counts remain authoritative when `truncated` is true.
- `safety.retainBackups` is validated but 2.1.0 does not prune old transaction backups automatically; operators must apply their own retention policy to the hidden backup directory.
- Precise PDF figure crops, panel segmentation, OCR fallback, multimodal interpretation, embeddings, reranking, citation graphs, and automated figure digitization remain post-P0 work.
- Wiki retrieval is lexical and bounded; semantic ranking and prose generation belong to the connected Agent.
- The server accepts SSE and streamable HTTP but supplies no built-in authentication, authorization, or TLS.
- One process invocation resolves one vault path. Multi-vault orchestration requires separate client entries or explicit per-tool `vault_path` values.
- Pi tool calls have a 660-second Extension timeout. Exceptionally long MinerU jobs can still exceed it; use the native MCP/CLI path for those jobs or adjust the adapter in a reviewed change.

## Contribution checklist

- Every changed line traces to the requested behavior.
- New behavior has a focused failing test first when practical.
- No test contacts a private vault, Zotero library, or MinerU service.
- `zoteroKey`, portable paths, user content, and transaction guarantees still hold.
- CLI and MCP remain thin and return structured JSON-safe values.
- The tool count and names remain exactly 33 unless another versioned contract is approved.
- Pi sources are byte-identical after any Extension change.
- Ruff, pytest, repository verification, artifact verification, and wheel smoke tests pass as appropriate.
- English and Chinese canonical docs agree with the live implementation.
