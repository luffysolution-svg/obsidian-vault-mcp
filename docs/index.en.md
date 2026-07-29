---
title: Obsidian Vault MCP V2 Complete Tutorial
lang: en
---

# Obsidian Vault MCP V2 Complete Tutorial

[中文教程](./index.md) · [English user guide](../README.en.md) · [English developer guide](../DEVELOPMENT.en.md)

This tutorial starts with an empty local setup and ends with imported Zotero papers, copied PDFs, MinerU full text, a generated literature dashboard, a native Obsidian Base, and a source-linked Wiki page.

## 1. Know what runs where

Obsidian Vault MCP is local orchestration software:

```text
Zotero Desktop local API ── metadata, children, PDF location
             │
             ▼
obsidian-vault-mcp ── stable note, transaction, Index, Base, Wiki writeback
             │
             ├── local Obsidian vault
             └── MinerU Open API CLI ── PDF extraction service
```

It does not upload your Zotero library to a replacement cloud library. Zotero reads use the Desktop local API and need no Zotero cloud API key. MinerU is a separate external service: precision and token-free flash extraction both send the selected PDF through the MinerU Open API path.

Wiki prose comes from the AI client you connect. The server supplies traceable local context and safe writeback, but does not call a model by itself.

## 2. Download the required software

Use official sources:

| Software | Required | Official source | Why |
|---|---:|---|---|
| Python 3.10–3.13 | Yes | [python.org/downloads](https://www.python.org/downloads/) | Runs the V2 package and CLI. |
| Obsidian | Yes | [obsidian.md/download](https://obsidian.md/download) | Opens the vault, native Base, notes, PDF, and Wiki. |
| Zotero Desktop | Yes | [zotero.org/download](https://www.zotero.org/download/) | Owns the literature library and local API. |
| Git | Source install only | [git-scm.com/downloads](https://git-scm.com/downloads) | Clones the repository. |
| MinerU Open API CLI | Full text only | [official MinerU Ecosystem repository](https://github.com/opendatalab/MinerU-Ecosystem) | Converts PDF content into Markdown and images. |
| Node.js | Some AI clients only | [nodejs.org/download](https://nodejs.org/en/download) | Installs npm-distributed Agent clients. |

After installing Python, open a new terminal and verify:

```bash
python --version
python -m pip --version
```

If Windows maps `python` to the Microsoft Store instead of your installation, re-run the Python installer with **Add python.exe to PATH**, or use the `py` launcher in place of `python`.

## 3. Create or open an Obsidian vault

1. In Obsidian, choose **Create new vault** or open your existing vault.
2. Confirm that the vault root now contains an `.obsidian` directory.
3. In **Settings → Core plugins**, enable **Bases**. See the official [Obsidian Bases documentation](https://help.obsidian.md/bases).

No Obsidian community plugin is required. V2 generates a native `.base` file and ordinary Markdown.

Remember the vault root itself, not a folder inside it. This guide uses one platform-neutral placeholder:

```text
<VAULT_DIR> # the directory that directly contains .obsidian
```

## 4. Enable and test the Zotero local API

1. Start Zotero Desktop and leave it running while importing or synchronizing.
2. Open Zotero settings and enable the option that allows other applications on this computer to communicate with Zotero.
3. Keep the default local endpoint unless you have deliberately changed it: `http://127.0.0.1:23119/api`.

Zotero documents this as the [Local API](https://www.zotero.org/support/dev/web_api/v3/basics#local_api). Test it before installing anything else:

```powershell
# Windows PowerShell
Invoke-RestMethod "http://127.0.0.1:23119/api/users/0/items?format=json&limit=1"
```

```bash
# macOS/Linux
curl "http://127.0.0.1:23119/api/users/0/items?format=json&limit=1"
```

A response from Zotero is enough; the exact payload can vary by version. A connection refusal usually means Zotero is closed. HTTP 403 usually means local API access is disabled. No Zotero cloud API key belongs in this project.

### Make PDFs available

The pipeline copies a PDF only when the Zotero parent item has a PDF child attachment that resolves to an accessible local file. In Zotero, download any cloud-only attachments first.

For a nonstandard Zotero storage layout, set an override before starting the CLI/server:

```powershell
$env:ZOTERO_STORAGE_DIR = "<ZOTERO_STORAGE_DIR>"
```

```bash
export ZOTERO_STORAGE_DIR="<ZOTERO_STORAGE_DIR>"
```

The source path is stored only in hidden transaction/item state, never in user-visible notes.

For Zotero **Link to File** attachments, the local API returns an `attachments:` relative path. Set Zotero's **Settings → Advanced → Files and Folders → Linked Attachment Base Directory**, then configure this project with the same directory:

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

`ZOTERO_STORAGE_DIR` is only for Zotero-managed `storage:` attachments. `linkedAttachmentBaseDir` and `ZOTERO_LINKED_ATTACHMENT_BASE_DIR` are only for `attachments:` linked files. Version 2.1.0 rejects `..` traversal and drive-prefixed paths that could escape the configured base; if no base is configured, import reports a clear error instead of guessing a machine path.

## 5. Optional Zotero components

### Better BibTeX

[Better BibTeX for Zotero](https://retorque.re/zotero-better-bibtex/) is optional. It can supply richer BibTeX and stable citekeys, but citekeys are not V2 identities.

1. Download the current `.xpi` from [Better BibTeX releases](https://github.com/retorquere/zotero-better-bibtex/releases/latest).
2. In Zotero, open **Tools → Plugins**, choose **Install Add-on From File**, and select the `.xpi`.
3. Restart Zotero if prompted.

With `bibtex.provider` set to `auto`, V2 tries Better BibTeX, Zotero's own export, and then its built-in deterministic renderer. A failure in an earlier provider remains visible in the result even when a fallback succeeds.

### Zotero Connector

The [Zotero Connector](https://www.zotero.org/download/connectors) is useful for saving papers from a browser, but it is not needed for the local pipeline itself.

## 6. Install MinerU for full-text parsing

Skip this section if metadata, PDFs, Index, and Base are enough.

The supported adapter calls the official `mineru-open-api` CLI. Follow the [MinerU Ecosystem CLI documentation](https://github.com/opendatalab/MinerU-Ecosystem/tree/main/cli), or use its official installer.

Windows PowerShell:

```powershell
irm https://cdn-mineru.openxlab.org.cn/open-api-cli/install.ps1 | iex
```

macOS/Linux:

```bash
curl -fsSL https://cdn-mineru.openxlab.org.cn/open-api-cli/install.sh | sh
```

Open a new terminal and verify:

```bash
mineru-open-api --help
```

### Precision extraction

Create a MinerU token through the official [API management page](https://mineru.net/apiManage/token), then let the CLI store it outside the vault:

```bash
mineru-open-api auth
```

V2 detects the CLI's `~/.mineru/config.yaml` token. This is preferred over putting a token in a project file. For an ephemeral process, either supported environment variable also works:

```powershell
$env:MINERU_TOKEN = "your-token"
# or: $env:MINERU_API_TOKEN = "your-token"
```

```bash
export MINERU_TOKEN="your-token"
# or: export MINERU_API_TOKEN="your-token"
```

Never paste a real token into `.obsidian-vault-mcp.json`, an MCP config committed to Git, a shell script, issue, log, or screenshot.

Mode behavior in V2 is exact:

| `mineru.mode` | Behavior |
|---|---|
| `auto` with a stored/environment token | Precision `extract` with Markdown output. |
| `auto` without a token | Token-free `flash-extract`, with stricter service limits. |
| `api` | Force precision `extract`; it needs valid authentication. |
| `local` | Compatibility mapping to `flash-extract`; it is not an offline local-model backend. |

If the executable has a custom name or path, set `MINERU_CLI_COMMAND`. Windows `.cmd` shims are resolved automatically.

## 7. Install Obsidian Vault MCP 2.1.0

### Recommended for Agents: persistent tool environment

Codex Desktop/CLI, Claude Code, and other independently launched MCP clients must resolve `obsidian-vault-mcp` on their own startup `PATH`. Install the package with `pipx` or `uv tool` into a persistent isolated environment. Use this package selector once 2.1.0 is published to PyPI; use the local wheel path in the next block for production acceptance before publication:

```bash
pipx install "zotero-obsidian-mcp==2.1.0"
# or
uv tool install "zotero-obsidian-mcp==2.1.0"
```

For a locally built production wheel, use the artifact path instead of the package selector:

```bash
pipx install "<WHEEL_PATH>"
# or
uv tool install "<WHEEL_PATH>"
```

Run `pipx ensurepath` or `uv tool update-shell` when required, then fully restart terminals and GUI clients. Verify the environment inherited by the client:

```bash
obsidian-vault-mcp --help
pipx list    # when using pipx
uv tool list # when using uv
```

The PyPI distribution is `zotero-obsidian-mcp`; the installed command is `obsidian-vault-mcp`; the plugin marketplace is `obsidian-vault-mcp`; and the Codex/Claude plugin selector starts with `obsidian-literature`.

### Isolated virtual environment

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade "zotero-obsidian-mcp==2.1.0"
```

macOS/Linux:

```bash
source .venv/bin/activate
python -m pip install --upgrade "zotero-obsidian-mcp==2.1.0"
```

An AI client launched outside this activated environment will not see the CLI. For Agent integration, install into a persistent environment whose `Scripts`/`bin` directory is on the Agent's `PATH`, or launch the Agent from the activated environment.

### Install from a source checkout

```bash
git clone https://github.com/luffysolution-svg/obsidian-vault-mcp.git
cd obsidian-vault-mcp
git checkout "<RELEASE_TAG>"
python -m pip install -e ".[dev]"
```

Use editable install only when developing or testing a verified checkout. Ordinary Agent installations should use the pinned published package, once available, or the locally verified production wheel; this guide does not assert that an unreleased tag or artifact has already been published remotely.

## 8. Select the vault explicitly

For interactive CLI work, set the environment variable in the same terminal.

Windows PowerShell:

```powershell
$env:OBSIDIAN_VAULT_PATH = "<VAULT_DIR>"
```

macOS/Linux:

```bash
export OBSIDIAN_VAULT_PATH="<VAULT_DIR>"
```

Or pass `--vault-path` to commands that expose it:

```bash
obsidian-vault-mcp doctor --vault-path "<VAULT_DIR>"
```

`OBSIDIAN_VAULT_PATH=auto` is not a global Obsidian vault lookup. It starts at the server process's current directory and walks upward until it finds `.obsidian`. Use `auto` only when the Agent's project lives inside the vault tree. Otherwise set the explicit local vault path in the client process environment; the native Codex/Claude plugin inherits that environment and does not store a project path.

## 9. Initialize the one vault configuration

Preview first:

```bash
obsidian-vault-mcp config init --dry-run
obsidian-vault-mcp config init
obsidian-vault-mcp config validate
obsidian-vault-mcp config get
```

The primary user-facing result is `<Vault>/.obsidian-vault-mcp.json`; the formal write also records its transaction manifest and backup area under `<Vault>/.obsidian-vault-mcp/`. Unknown keys, duplicate JSON keys, unsafe/absolute vault paths, wrong types, unsupported enums, and unstable filename patterns are rejected.

`config init` refuses to silently overwrite an existing config. Edit the file and run `config validate` instead.

### A safe customization example

The loader accepts partial sections and fills omitted values from V2 defaults, although `config init` writes the complete normalized file. For example:

```json
{
  "schemaVersion": 2,
  "literature": {
    "root": "Research/Literature",
    "index": "Research/Literature/index.md",
    "base": "Research/Literature/Literature.base",
    "wikiFolder": "Research/Literature/Wiki"
  },
  "attachments": {
    "pdfFolder": "Research/Literature/attachment",
    "copyPdf": true,
    "overwritePolicy": "if-source-changed"
  },
  "note": {
    "readingNotesHeading": "My Reading Notes",
    "embedPdf": true,
    "embedMineruMarkdown": false
  },
  "zotero": {
    "linkedAttachmentBaseDir": "<ZOTERO_LINKED_ATTACHMENT_BASE_DIR>"
  },
  "mineru": {
    "mode": "auto",
    "markdownFolder": "Research/Literature/attachment/MinerU",
    "imageFolder": "Research/Literature/attachment/MinerU/image",
    "maxConcurrentJobs": 2
  },
  "index": {
    "autoRebuild": true,
    "recentLimit": 30
  },
  "base": {
    "autoRebuild": true,
    "name": "Research Library"
  }
}
```

Vault content paths above are vault-relative and use `/`, even on Windows. `zotero.linkedAttachmentBaseDir` is the sole exception: it is an absolute, machine-local source directory and should not be committed.

### Live, fixed, and reserved fields

The table below describes what the 2.1.0 implementation actually reads. Do not treat every generated schema field as a runtime toggle.

| Section/field | Status in 2.1.0 | Meaning |
|---|---|---|
| `$schema` | Reserved | Editor hint emitted by the generator; leave it unchanged. |
| `schemaVersion` | Fixed: `2` | Other values are rejected. |
| `literature.root/index/base/wikiFolder` | Live | Vault-relative destinations. Keep Index/Base/Wiki under your intended literature layout. |
| `identity.strategy` | Fixed: `zoteroKey` | The only supported identity. |
| `naming.note/pdf/mineruMarkdown/mineruImage` | Live with constraints | Required placeholders must remain; note/MinerU Markdown must end in `.md`, PDF in `.pdf`, and images retain `{ext}`. |
| `attachments.pdfFolder/copyPdf/overwritePolicy` | Live | `overwritePolicy`: `always`, `never`, or `if-source-changed`. |
| `frontmatter.omitEmpty/preserveUnknownFields` | Live | Control empty managed values and unknown user fields. |
| `frontmatter.fieldOrder` | Fixed | Must equal the V2 managed order; reordering is rejected. |
| `note.omitEmptySections/readingNotesHeading/embedPdf/embedMineruMarkdown` | Live | Control generated note presentation. |
| `note.preserveUserSections` | Reserved compatibility field | V2 always preserves unmarked user sections; this is not a switch to disable that guarantee. |
| `zotero.apiBase/syncTags/paginationSize` | Live | Local endpoint, tag import, and page size (1–1000). |
| `zotero.linkedAttachmentBaseDir` | Live | Absolute base directory for Zotero `attachments:` linked-file paths. A non-empty value overrides `ZOTERO_LINKED_ATTACHMENT_BASE_DIR`. |
| `zotero.syncNotes/syncAnnotations` | Reserved compatibility fields | 2.1.0 renders available Zotero notes and annotations; these booleans are validated but are not independent runtime switches. |
| `bibtex.enabled/provider` | Live | Provider: `auto`, `better-bibtex`, `zotero`, or `builtin`. |
| `bibtex.fallback` | Partially effective | `none` disables builtin fallback for explicit `better-bibtex` or `zotero`, but `provider=auto` still includes the builtin provider in 2.1.0. |
| `mineru.mode/markdownFolder/imageFolder/maxConcurrentJobs` | Live | Extraction route, normalized destinations, and batch concurrency (1–64). |
| `mineru.preserveUnlinkedImageCandidates/imageManifestEnabled/candidateCacheFolder` | Live | Hidden candidate preservation and the per-paper image Manifest/cache path. |
| `analysis.folder/index/topicFolder/theoryFolder` | Live | Vault-relative Analysis and knowledge-synthesis destinations. |
| `evidence.enabled/blockIdPrefix/maxChunkChars/overlapChars` | Live | Evidence indexing, deterministic block prefix, and bounded chunk sizing; overlap must be smaller than the chunk limit. |
| `mineru.enabled` | Informational | Reported by `doctor`; the parse command itself remains callable. |
| `mineru.imageLinkStyle` | Fixed: `markdown-relative` | No other link style is accepted. |
| `mineru.replacePreviousOutput` | Reserved compatibility field | Current normalization replaces the prior derived output transactionally. |
| `index.autoRebuild/recentLimit` | Live | Automatic rebuild and recent-item count. |
| `index.groupBy` | Reserved compatibility field | Validated to year/journal/tags, but 2.1.0 renders all three groups. |
| `base.autoRebuild/name` | Live | Automatic rebuild and primary view name. |
| `safety.*` | Reserved contract declaration | Transaction safety is always enforced in 2.1.0; these validated values are not switches that disable locks, backups, or atomic writes. |

The managed frontmatter order is fixed to `title`, `itemType`, `year`, `journal`, `tags`, `doi`, `url`, `abstract`, `zoteroKey`, `zoteroPdfLink`, `attachmentPdfLink`, and `attachmentMinerULink`.

## 10. Run diagnostics correctly

```bash
obsidian-vault-mcp doctor
```

Read the JSON by subsection:

- top-level `ok`: the vault configuration loaded;
- `config.exists` and `config.schemaVersion`: the vault config state;
- `zotero.ok`: the local API is reachable;
- `mineru.available`: the CLI executable is on `PATH`;
- `mineru.enabled`: the informational config flag;
- `tools`: the exact 33 registered V2.1 tool names.

A top-level `"ok": true` does not mean Zotero or MinerU is ready.

## 11. Import your first Zotero item

Search for a parent item and copy its eight-character Zotero key from the JSON result:

```bash
obsidian-vault-mcp call zotero_search_items \
  --json '{"query":"photocatalysis"}'
```

Inspect an item and its children if needed:

```bash
obsidian-vault-mcp call zotero_get_item --json '{"key":"ABCD1234"}'
obsidian-vault-mcp call zotero_get_children --json '{"parent_key":"ABCD1234"}'
```

Preview, then import:

```bash
obsidian-vault-mcp import item ABCD1234 --dry-run
obsidian-vault-mcp import item ABCD1234
```

The result reports `notePath`, optional `pdfPath`, `bibtexProvider`, any fallback diagnostics, and `transactionId`. The default files are:

```text
Literature/ABCD1234.md
Literature/attachment/ABCD1234.pdf
Literature/index.md
Literature/Literature.base
```

Re-running import is safe and idempotent around the same `zoteroKey`. To refresh only previously imported data, use sync:

```bash
obsidian-vault-mcp sync item ABCD1234 --dry-run
obsidian-vault-mcp sync item ABCD1234
```

### Import a collection

```bash
obsidian-vault-mcp call zotero_list_collections --json '{}'
obsidian-vault-mcp import collection COLLKEY --dry-run
obsidian-vault-mcp import collection COLLKEY
```

Searches, collection lists, and collection items are fully paginated. Collection result details are summarized to 20 entries by default; when `truncated` is true, use the aggregate `total`, `succeeded`, and `failed` counts rather than assuming only the displayed entries ran.

## 12. Parse PDFs with MinerU

An item must already have hidden state, a main note, and a copied vault PDF.

```bash
obsidian-vault-mcp mineru parse ABCD1234 --dry-run
obsidian-vault-mcp mineru parse ABCD1234
```

MinerU dry-run verifies prerequisites and reports planned paths, but intentionally does not contact MinerU or predict the extracted image set.

Parse several imported papers with bounded concurrency:

```bash
obsidian-vault-mcp mineru parse-batch \
  ABCD1234 EFGH5678 IJKL9012 MNOP3456 QRST7890
```

The adapter extracts into hidden staging, locates and normalizes the Markdown, deterministically renames images, rewrites relative links, updates the main note, and commits everything as one safe transaction per paper. A failed extraction records an error state without publishing partial MinerU files.

To remove derived output without deleting the main note or PDF:

```bash
obsidian-vault-mcp mineru remove ABCD1234 --dry-run
obsidian-vault-mcp mineru remove ABCD1234
```

### Structured reading, review, and cross-paper retrieval

A successful MinerU parse maintains an image Manifest and physically writes deterministic `^ev-*` block IDs into derived Markdown. Read bounded EvidenceChunks whose real anchors can be checked by Verify in overview, targeted, sections, full, or figures mode:

```bash
obsidian-vault-mcp call literature_paper_read --json '{"zotero_key":"ABCD1234","mode":"overview","max_chars":12000,"record_coverage":true}'
obsidian-vault-mcp call literature_paper_read --json '{"zotero_key":"ABCD1234","mode":"targeted","query":"charge transfer mechanism","query_variants":["interfacial electron transfer"],"record_coverage":true}'
obsidian-vault-mcp call literature_paper_read --json '{"zotero_key":"ABCD1234","mode":"figures","include_images":true,"record_coverage":true}'
```

The external Agent gets the 13-section packet from `literature_analysis_context`, authors the prose, and previews writeback:

```bash
obsidian-vault-mcp call literature_analysis_context --json '{"zotero_key":"ABCD1234","include_figures":true}'
obsidian-vault-mcp call literature_analysis_write --json '{"zotero_key":"ABCD1234","sections":{"findings":[{"claimType":"source_fact","content":"Example grounded finding","evidenceIds":["ABCD1234-results-..."],"assetIds":[],"verificationStatus":"verified"}]},"dry_run":true}'
```

After an approved write, list or resolve uncertainty items, rebuild the Analysis index, and retrieve across an explicit paper scope:

```bash
obsidian-vault-mcp call literature_uncertainty_list --json '{"zotero_key":"ABCD1234","statuses":["pending"]}'
obsidian-vault-mcp call literature_uncertainty_resolve --json '{"zotero_key":"ABCD1234","uncertainty_id":"U-ABCD1234-...","status":"unresolved","resolution_note":"Original evidence remains insufficient","dry_run":true}'
obsidian-vault-mcp call literature_rebuild_analysis_index --json '{"dry_run":true}'
obsidian-vault-mcp call literature_retrieve --json '{"query":"CdS nickel cocatalyst","scope":{"zotero_keys":["ABCD1234"]},"intent":"summarize","depth":"evidence","record_coverage":true}'
```

Reads do not write Coverage by default. Pass `record_coverage=true` explicitly to update the ledger and receive real `transactionId` values in `coverageLedger`; use `coverage_dry_run=true` for a zero-write preview. Cross-paper retrieval returns one transaction result per paper. Coverage is not paper evidence.

Hidden state lives under `state/evidence/`, `state/uncertainties/`, `state/coverage/`, and `cache/mineru-assets/`. Legacy item state needs no manual migration: later work adds `mineruAssetRoot` (for transactional candidate-cache migration after `candidateCacheFolder` changes) and `collectionKeys` (for collection scope). New imports return Zotero child notes and annotations separately; combined legacy main-note content remains in `zoteroNotes` with a warning. User-visible Analysis notes live under `Literature/Analysis/`. An asset ID never replaces text evidence. A PDF crop only makes external inspection possible; only `visualStatus=visual_verified` can support a visual conclusion.

## 13. Rebuild the Index and Base

Imports rebuild both by default. Run explicit rebuilds after manual maintenance or configuration changes:

```bash
obsidian-vault-mcp index rebuild --dry-run
obsidian-vault-mcp index rebuild
obsidian-vault-mcp base rebuild --dry-run
obsidian-vault-mcp base rebuild
```

The Index scans only canonical top-level literature notes. The Base filters to the configured literature root and notes with `zoteroKey`, which prevents MinerU Markdown from appearing as a second literature row.

## 14. Create a source-linked Wiki page

First retrieve deterministic local evidence:

```bash
obsidian-vault-mcp wiki context "CdS photocatalytic hydrogen production" --limit 20
```

This is weighted lexical matching over title, tags, abstract, Zotero notes, and bounded MinerU excerpts. It does not generate prose. Ask your connected Agent to synthesize the returned evidence, then write it with the exact source keys:

```bash
obsidian-vault-mcp wiki write "CdS photocatalytic hydrogen production" \
  --content "# CdS photocatalytic hydrogen production

Agent-authored synthesis based on the selected local sources." \
  --zotero-key ABCD1234 \
  --zotero-key EFGH5678 \
  --dry-run
```

Repeat without `--dry-run` after reviewing the result. Writeback requires at least one source, verifies that every key maps to exactly one main note, preserves unknown Wiki frontmatter, and appends any missing note links under Sources.

```bash
obsidian-vault-mcp wiki list
obsidian-vault-mcp index rebuild
```

## 15. Verify the finished vault

```bash
obsidian-vault-mcp verify
```

Verification audits duplicate keys/DOIs, missing or misplaced main notes, attachment and MinerU links, unsafe machine paths, state mismatches, stale/missing derived assets, and Wiki source integrity. Treat any reported error as unfinished work.

## 16. Connect an AI Agent

Install only the client you actually use and verify that its executable is on `PATH`:

| Client | Official guide | Executable expected by V2 |
|---|---|---|
| Codex | [Codex CLI](https://developers.openai.com/codex/cli/) | `codex` |
| Claude Code | [Claude Code quickstart](https://code.claude.com/docs/en/quickstart) | `claude` |
| OpenCode | [OpenCode docs](https://opencode.ai/docs/) | `opencode` |
| Pi | [Pi documentation](https://pi.dev/docs/latest) | `pi` |
| Hermes | [Hermes Agent docs](https://hermes-agent.nousresearch.com/docs/) | `hermes` |
| WorkBuddy | [MCP guide](https://www.workbuddy.ai/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/MCP-Guide) / [CLI reference](https://www.workbuddy.ai/docs/cli/reference) | `codebuddy` (fallback: `cbc`) |

### Codex Desktop/CLI and Claude Code: native plugins

This is the production installation path for Codex and Claude Code. First complete the persistent Python installation in section 7 and confirm that the **new terminal or GUI process that launches the client** can resolve `obsidian-vault-mcp`. Obtain and extract `obsidian-vault-mcp-2.1.0-plugins.zip`; `<MARKETPLACE_DIR>` must be the extracted root that directly contains `.agents/`, `.claude-plugin/`, and `plugins/`.

Codex Desktop/CLI:

```bash
codex plugin marketplace add "<MARKETPLACE_DIR>"
codex plugin add obsidian-literature@obsidian-vault-mcp
```

Claude Code:

```bash
claude plugin marketplace add "<MARKETPLACE_DIR>" --scope user
claude plugin install obsidian-literature@obsidian-vault-mcp --scope user
```

The convenience entry point resolves the same marketplace from the installed Python package and invokes those native CLIs. `--project-dir` remains accepted only for the uniform six-client API; Codex/Claude do not write project MCP configuration or copy project Skills:

```bash
obsidian-vault-mcp agent install codex --dry-run
obsidian-vault-mcp agent install codex
obsidian-vault-mcp agent install claude --dry-run
obsidian-vault-mcp agent install claude
```

Repeat runs inspect the client's marketplace/plugin lists for idempotency. If the same marketplace name already points to another directory, installation stops safely instead of silently replacing the source. Fully quit and reopen Codex Desktop/Claude Code or start a new CLI session after installation; existing sessions do not load a newly installed plugin. The Codex IDE extension is not this plugin surface.

The production ZIP has exactly 15 files: two marketplace manifests, separate Codex and Claude plugin manifests, one shared compatible `.mcp.json`, one Codex App icon, and these nine Skills: `analyze-figures`, `compare-papers`, `evidence-based-qa`, `literature-review`, `structured-paper-note`, `theory-note-synthesis`, `topic-note-synthesis`, `uncertainty-audit`, and `verify-paper-claims`. The shared MCP entry exposes the fixed 33-tool surface. The ZIP contains no Python runtime, vault data, credentials, or machine path.

### OpenCode, Pi, Hermes, and WorkBuddy

These four clients keep the integration mechanism that fits their native behavior. Both the selected platform executable and `obsidian-vault-mcp` must be on `PATH`. Preview the relevant installer, then repeat only that command without `--dry-run`. Hermes stores MCP configuration in its profile, so the uniform `--project-dir` argument is accepted but ignored:

```bash
obsidian-vault-mcp agent install opencode --project-dir "<PROJECT_DIR>" --dry-run
obsidian-vault-mcp agent install pi --project-dir "<PROJECT_DIR>" --dry-run
obsidian-vault-mcp agent install hermes --dry-run
obsidian-vault-mcp agent install workbuddy --project-dir "<PROJECT_DIR>" --dry-run
```

| Client | Production mechanism | MCP/Extension destination | Skill destination |
|---|---|---|---|
| Codex Desktop/CLI | Native marketplace plugin | Client-managed | Nine bundled Skills |
| Claude Code | Native marketplace plugin, user scope | Client-managed | Nine bundled Skills |
| OpenCode | Project config installer | `opencode.json` | Nine managed Skills in `.opencode/skills` |
| Pi | Thin TypeScript Extension | `.pi/extensions/obsidian-vault-mcp.ts` | None; Extension-only |
| Hermes | MCP-only profile config | `$HERMES_HOME/config.yaml` (default: `~/.hermes/config.yaml`) | None; warning returned |
| WorkBuddy | MCP-only project config | `.workbuddy/mcp.json` | None; warning returned |

OpenCode configuration and Skills share validation, backup, atomic write, and rollback. Managed upgrades preserve `User Customizations`, and a modified managed block is rejected before writes. Pi installs only the thin Extension that calls the JSON CLI. The Hermes and WorkBuddy adapters remain MCP-only and do not populate any Skill directory. The Hermes profile installer and the three project installers perform one MCP initialization handshake; it proves that the server starts, not that the vault, Zotero, and MinerU are ready.

The Codex/Claude plugin `.mcp.json` does not hard-code `OBSIDIAN_VAULT_PATH`; it inherits the client process environment, as do OpenCode and Pi. If the project is outside the vault tree, set `OBSIDIAN_VAULT_PATH=<VAULT_DIR>` securely on the machine and restart the client. The Hermes profile config and WorkBuddy project template may use `auto`, which searches only the process working directory and parents. Never commit a real absolute path.

`workbuddy` is the convenience-installer client name, not the platform executable. The installer probes the official `codebuddy` command first and falls back to its `cbc` alias. For Hermes, an explicit `config_path` override exists only in the Python installer API; it is not an `agent install` CLI option.

### Manual MCP entry

If a client is not covered by the installer, configure a local stdio server:

```json
{
  "mcpServers": {
    "obsidian-literature": {
      "type": "stdio",
      "command": "obsidian-vault-mcp",
      "args": ["serve", "--transport", "stdio"],
      "env": {
        "OBSIDIAN_VAULT_PATH": "<VAULT_DIR>"
      }
    }
  }
}
```

For Codex/Claude, prefer the native plugin instead of writing project configuration manually. Other uncovered native MCP clients can translate the outer field names according to their own documentation. Local `stdio` is recommended. `serve --transport sse` and `serve --transport streamable-http` do not add authentication or TLS; do not expose them directly to a LAN or the internet.

### AI-assisted installation prompt

Give this prompt to a trusted local coding Agent from the target project:

```text
Persistently install zotero-obsidian-mcp==2.1.0 with pipx or uv tool. Do not
store or print secrets, and verify the Agent startup environment can resolve
obsidian-vault-mcp.
Use my explicit Obsidian vault path only in the local client startup environment
or an uncommitted client configuration.
Run config init with --dry-run first, then initialize and validate the V2 config.
Run doctor and inspect config, zotero.ok, and mineru.available separately.
For Codex/Claude, preview `agent install <client> --dry-run`, then use the native
marketplace plugin without writing project MCP/Skill files. For OpenCode, Pi, or
WorkBuddy, preview the project adapter with --project-dir <PROJECT_DIR>. For
Hermes, preview `agent install hermes --dry-run`; it writes the Hermes profile
config and ignores --project-dir. Apply only after review, start a new client
session, and finally call literature_doctor through MCP. Do not use SSE/HTTP.
```

### End-to-end research prompt

```text
Before each write, dry-run it and report the planned paths. Search my local
Zotero Desktop library for five papers on <topic>; show parent-item titles and
zoteroKeys and wait for my selection. Import only the approved parent items,
run MinerU precision extraction, rebuild the Index and Base, and verify the
vault. Then obtain literature_wiki_context for <topic>, synthesize only from
those sources, write a Wiki page citing every selected zoteroKey, run
literature_verify again, and report all transactionIds and any fallback/error.
```

## 17. Migrate from V1 and recover changes

Back up the vault with your normal backup system before migration. Then preview:

```bash
obsidian-vault-mcp migrate v1-to-v2 --dry-run
```

Apply only after resolving ambiguous identities and path collisions:

```bash
obsidian-vault-mcp migrate v1-to-v2 --apply
```

Inspect a committed transaction:

```bash
obsidian-vault-mcp preview <transaction-id>
```

Preview rollback before restoring:

```bash
obsidian-vault-mcp rollback <transaction-id> --dry-run
obsidian-vault-mcp rollback <transaction-id>
```

If a destination changed after the original commit, rollback reports a conflict and refuses to overwrite it. `--conflict-policy overwrite-managed` deliberately bypasses that hash protection; use it only after separately preserving the newer file.

## 18. Troubleshooting

### `obsidian-vault-mcp` is not recognized

```bash
pipx list
uv tool list
python -m pip show zotero-obsidian-mcp
python -m pip --version
```

Use the list command that matches the original installation; `python -m pip show` applies only to that Python environment. The package may have been installed into a different tool or virtual environment. Ensure its `Scripts`/`bin` directory is on the client startup `PATH`, then restart the AI client.

### The vault cannot be resolved

Set `OBSIDIAN_VAULT_PATH` to the directory that directly contains `.obsidian`, or pass `--vault-path`. Do not expect `auto` to discover unrelated vaults elsewhere on disk.

### `doctor.ok` is true but import fails

Check `zotero.ok` separately. Start Zotero, enable the local API, and verify `http://127.0.0.1:23119/api/`. Use `ZOTERO_LOCAL_API` only if you intentionally use another loopback endpoint.

### An imported note has no PDF

Confirm the PDF is a child of the parent Zotero item and downloaded locally. Inspect `zotero_get_children`. For `storage:` paths, check `ZOTERO_STORAGE_DIR`. For `attachments:` paths, set `zotero.linkedAttachmentBaseDir` or `ZOTERO_LINKED_ATTACHMENT_BASE_DIR` to Zotero's linked attachment base.

### A linked attachment is reported outside its base directory

Make sure Zotero and this project use the same linked attachment base. The attachment path must be relative to that directory and cannot contain `..` traversal or a drive prefix.

### MinerU is unavailable

Run `mineru-open-api --help` in the same environment that starts the MCP server. If only a custom executable works, set `MINERU_CLI_COMMAND`. Restart the Agent after changing `PATH`.

### MinerU uses flash instead of precision

Run `mineru-open-api auth`, then restart the MCP server so it sees the stored token. Alternatively set `MINERU_TOKEN` or `MINERU_API_TOKEN` in the server environment. Keep `mineru.mode` at `auto` or `api`.

### A MinerU parse failed

The main note and prior normalized output remain intact. Read the structured `stage` and `error`, fix authentication/network/PDF issues, and retry. The failure state is retained for verification; partial staging is cleaned.

### The Base does not open

Upgrade Obsidian if necessary and enable the **Bases** core plugin. Rebuild with `obsidian-vault-mcp base rebuild`, then open `Literature/Literature.base` from the vault.

### The Base shows duplicate literature rows

Upgrade to `zotero-obsidian-mcp==2.0.0` and rebuild the Base. Current generation filters to canonical top-level literature notes. The screenshot below intentionally preserves the earlier acceptance-run display from before that filter fix.

### Agent installation says the client is missing

The exact expected executable must be on the installer's `PATH`. Install the client from its official guide, open a new terminal, run its executable once, and retry the dry-run.

### A Codex/Claude plugin is installed but Skills or tools are absent

Run `codex plugin list` or `claude plugin list` to confirm that the plugin is installed. Fully close the old client and start a new session, then verify that the client startup environment can resolve `obsidian-vault-mcp`. The plugin carries manifests and Skills, not the Python runtime.

### A marketplace name already points to another directory

Do not overwrite the source silently. Uninstall `obsidian-literature@obsidian-vault-mcp`, remove the old `obsidian-vault-mcp` marketplace, then add the stable `<MARKETPLACE_DIR>` and reinstall.

### A project installer handshake fails

This handshake applies to the OpenCode, Pi, and WorkBuddy project adapters and the Hermes profile adapter. The installer restores the old configuration or Extension. Check that `obsidian-vault-mcp` is on the Agent process's `PATH`, the vault path resolves, and no stale server process is holding an incompatible environment. Re-run `doctor`, then retry the installer dry-run.

### Windows console output contains escaped Unicode

The CLI intentionally emits valid ASCII-escaped JSON when the active console code page cannot represent a character. JSON consumers decode it losslessly; use a UTF-8 terminal for direct reading.

## 19. Update and uninstall

Update the persistent Python tool environment first, using the command that matches the original installation:

```bash
pipx upgrade zotero-obsidian-mcp
# or
uv tool upgrade zotero-obsidian-mcp
```

For a local wheel candidate, replace the tool environment with `pipx install --force "<WHEEL_PATH>"` or `uv tool install --force "<WHEEL_PATH>"`, then recheck `obsidian-vault-mcp --help`.

Codex currently has no `plugin update` subcommand. After updating the marketplace contents, remove the old plugin and rerun the convenience installer. Claude Code can update its marketplace and plugin directly:

```bash
codex plugin remove obsidian-literature@obsidian-vault-mcp --json
obsidian-vault-mcp agent install codex

claude plugin marketplace update obsidian-vault-mcp
claude plugin update obsidian-literature@obsidian-vault-mcp --scope user
```

Fully restart the GUI client or start a new CLI session after an install or update. If the new bundle was extracted to another directory, remove the old marketplace and add the new `<MARKETPLACE_DIR>` instead of allowing the source to drift.

Uninstall the plugin first. Remove its marketplace only after confirming that no other installed plugin needs it:

```bash
codex plugin remove obsidian-literature@obsidian-vault-mcp --json
codex plugin marketplace remove obsidian-vault-mcp --json

claude plugin uninstall obsidian-literature@obsidian-vault-mcp --scope user
claude plugin marketplace remove obsidian-vault-mcp --scope user
```

For OpenCode, Pi, Hermes, and WorkBuddy, follow the exact `uninstall_instructions` returned by `agent install`; remove only the reported project entry, Extension, or Hermes profile entry. Finally uninstall the Python package with `pipx uninstall zotero-obsidian-mcp`, `uv tool uninstall zotero-obsidian-mcp`, or the command matching the original environment.

Removing a plugin or Python package does not delete literature notes, PDFs, Wiki pages, transactions, or backups in the vault.

## 20. Effect gallery

The five original screenshots from the real five-paper Zotero → MinerU precision → Obsidian acceptance run are preserved below. A sixth, newly captured Base screenshot shows the corrected five-row result.

### Vault structure

<img src="./assets/screenshots/v2/vault-structure.png" alt="Obsidian Literature tree with five PDFs, MinerU output, Wiki notes, Index, and Base" width="300">

### Generated literature Index

<details>
<summary>Open the full Index dashboard</summary>

<img src="./assets/screenshots/v2/literature-index.png" alt="Literature Index with dashboard, recent items, year, journal, tags, Wiki, and maintenance sections" width="760">

</details>

### Native Obsidian Base

<img src="./assets/screenshots/v2/literature-base.png" alt="Obsidian Literature Matrix Base captured during the five-paper acceptance run" width="1100">

The corrected Base contains only top-level canonical literature notes: five papers produce five rows, while MinerU Markdown is excluded.

<details>
<summary>Open the original acceptance screenshot and duplicate-row fix note</summary>

<img src="./assets/screenshots/v2/literature-base-before-fix.png" alt="Original acceptance screenshot before the Base top-level folder filter fix" width="1100">

The original screenshot showed ten rows because five MinerU Markdown files also carried `zoteroKey`. Version 2.0.0 limits the Base to top-level notes; after upgrading, run `obsidian-vault-mcp base rebuild` to regenerate the corrected matrix.

</details>

### Five-paper Wiki synthesis

<details>
<summary>Open the full traceable Wiki page</summary>

<img src="./assets/screenshots/v2/wiki-synthesis.png" alt="Wiki synthesis comparing five papers with source links" width="780">

</details>

### Complete main literature note

<details>
<summary>Open the full note with metadata, abstract, PDF, MinerU, BibTeX, and Reading Notes</summary>

<img src="./assets/screenshots/v2/literature-note.png" alt="Complete Zotero literature note with embedded PDF and normalized MinerU full text" width="780">

</details>

## 21. Privacy and maintenance checklist

- Keep Zotero and the vault local; expose only the content needed to a trusted Agent host.
- Understand that MinerU sends selected PDFs to its service.
- Prefer `mineru-open-api auth` over embedding tokens in project environment files.
- Keep explicit vault paths and credentials out of Git.
- Preview imports, migrations, removals, Wiki writes, and rollbacks.
- Record transaction IDs until a change is accepted.
- Run `literature_verify` after batch work and before backups/releases.
- Back up the vault independently; transaction backups are operational rollback data, not a complete backup policy.
- Use only local `stdio` unless you add and operate a separate authenticated network boundary.

For implementation details, tests, release artifacts, and known 2.1.0 limitations, continue with the [developer guide](../DEVELOPMENT.en.md). Report defects through [GitHub Issues](https://github.com/luffysolution-svg/obsidian-vault-mcp/issues).
