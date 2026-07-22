# Obsidian Vault MCP V2

[中文](./README.md) · [Full tutorial](./docs/index.en.md) · [Developer guide](./DEVELOPMENT.en.md) · [PyPI](https://pypi.org/project/zotero-obsidian-mcp/)

Obsidian Vault MCP is a local-first, rollback-capable Zotero → MinerU → Obsidian literature pipeline. V2 uses the Zotero parent item's `zoteroKey` as its permanent identity: changing a title, author, year, journal, or citekey updates the same main note instead of creating another one.

```text
Zotero metadata and PDF
          ↓
one stable main note + PDF copy
          ↓
MinerU full-text Markdown and images
          ↓
Index dashboard + Obsidian Base + traceable Wiki
```

## What you get

- Import one Zotero parent item or a fully paginated collection.
- Keep exactly one main note at `Literature/{zoteroKey}.md` for each parent item.
- Synchronize metadata, tags, stored or linked Zotero PDFs, notes/annotations, and BibTeX while preserving unknown frontmatter fields and user-authored Markdown.
- Optionally normalize a PDF through the MinerU Open API CLI into portable Markdown and relative image links.
- Rebuild `Literature/index.md`, `Literature/Literature.base`, and source-linked Wiki pages.
- Preview writes, lock per item, stage and back up changes, replace files atomically, and roll back a committed transaction.
- Use the same application behavior through the CLI or the fixed 26-tool MCP surface. Codex, Claude Code, OpenCode, Pi, Hermes, and WorkBuddy installers are included.

Wiki prose is authored by the connected AI client. This project retrieves local evidence, validates the cited Zotero keys, adds source links, and writes the result safely; it does not bundle or require a particular model provider.

## Five-minute start

Prerequisites: Python 3.10+, an Obsidian vault that has been opened at least once, and a running Zotero Desktop instance with its local API enabled. MinerU is optional until you need full-text parsing.

Install the exact V2 release:

```bash
python -m pip install "zotero-obsidian-mcp==2.0.1"
```

Point the process at the actual vault. `auto` searches only the current working directory and its parents for `.obsidian`; it does not scan all vaults on the machine.

Windows PowerShell:

```powershell
$env:OBSIDIAN_VAULT_PATH = "D:\Notes\MyVault"
```

macOS/Linux:

```bash
export OBSIDIAN_VAULT_PATH="/home/me/Notes/MyVault"
```

Initialize and test the pipeline:

```bash
obsidian-vault-mcp config init --dry-run
obsidian-vault-mcp config init
obsidian-vault-mcp config validate
obsidian-vault-mcp doctor

obsidian-vault-mcp call zotero_search_items --json '{"query":"photocatalysis"}'
obsidian-vault-mcp import item ABCD1234 --dry-run
obsidian-vault-mcp import item ABCD1234
obsidian-vault-mcp verify
```

`doctor.ok` means that the vault configuration loaded successfully. Check `zotero.ok` and `mineru.available` separately before relying on those integrations.

If Zotero uses **Link to File** attachments, set `zotero.linkedAttachmentBaseDir` or `ZOTERO_LINKED_ATTACHMENT_BASE_DIR` before importing. See [Make PDFs available](./docs/index.en.md#make-pdfs-available) for examples.

For precision PDF parsing, install and authenticate the MinerU Open API CLI, then run:

```bash
mineru-open-api auth
obsidian-vault-mcp mineru parse ABCD1234
obsidian-vault-mcp verify
```

In MinerU `auto` mode, a stored or environment token selects precision `extract`; otherwise the adapter selects the more limited token-free `flash-extract` path.

## Default vault layout

```text
<Vault>/
├─ .obsidian/
├─ .obsidian-vault-mcp.json
├─ .obsidian-vault-mcp/
│  ├─ state/items/ABCD1234.json
│  ├─ staging/
│  ├─ backups/
│  └─ locks/
└─ Literature/
   ├─ index.md
   ├─ Literature.base
   ├─ ABCD1234.md
   ├─ Wiki/
   └─ attachment/
      ├─ ABCD1234.pdf
      └─ MinerU/
         ├─ ABCD1234.md
         └─ image/ABCD1234-fig01.png
```

User-visible files contain only vault-relative paths with `/` separators. Source PDF paths and hashes remain in hidden state and are not written into main notes, the Index, Base, or Wiki.

## Results from a five-paper acceptance run

These screenshots show an end-to-end run with five Zotero papers, PDF copies, MinerU precision extraction, an Index, an Obsidian Base, and a synthesized Wiki.

### Literature tree

<img src="./docs/assets/screenshots/v2/vault-structure.png" alt="Obsidian Literature tree with PDF, MinerU, Wiki, and Base files" width="300">

### Generated Index

<img src="./docs/assets/screenshots/v2/literature-index.png" alt="Literature Index grouped by year, journal, and tags" width="720">

### Native Obsidian Base

<img src="./docs/assets/screenshots/v2/literature-base.png" alt="Obsidian Literature Matrix Base" width="980">

The corrected V2 Base limits the view to canonical top-level literature notes, so five papers produce five rows.

<details>
<summary>Open the full five-paper Wiki synthesis</summary>

<img src="./docs/assets/screenshots/v2/wiki-synthesis.png" alt="Traceable Wiki synthesis generated from five Zotero papers" width="760">

</details>

The [full tutorial](./docs/index.en.md#19-effect-gallery) includes all five original screenshots, including a complete main note with embedded PDF, MinerU output, and BibTeX.

## Connect an AI client

Make sure the chosen client executable is already on `PATH`. From the project that should receive the MCP configuration, preview and then apply the merge-safe installer:

```bash
obsidian-vault-mcp agent install codex --project-dir "/path/to/project" --dry-run
obsidian-vault-mcp agent install codex --project-dir "/path/to/project"
```

Supported names are `codex`, `claude`, `opencode`, `pi`, `hermes`, and `workbuddy`. The installer backs up and merges existing configuration and then performs an MCP initialization handshake. The Codex, Claude, Hermes, and WorkBuddy templates set `OBSIDIAN_VAULT_PATH=auto`; that value is appropriate only when the client starts inside the vault tree. Otherwise replace it locally with an explicit vault path and do not commit that machine-specific value. OpenCode and Pi inherit the launching process environment.

After connecting, an Agent can receive a request such as:

```text
Before every write, run a dry-run. Search Zotero for papers about CdS
photocatalytic hydrogen production and import the parent items I approve.
Use MinerU precision parsing, rebuild the Index and Base, collect Wiki context
for the selected zoteroKeys, write a source-linked synthesis, run
literature_verify, and report every transactionId.
```

Native MCP clients should use local `stdio`:

```json
{
  "command": "obsidian-vault-mcp",
  "args": ["serve", "--transport", "stdio"],
  "env": {"OBSIDIAN_VAULT_PATH": "D:\\Notes\\MyVault"}
}
```

## Safety boundaries

- `zoteroKey` is the only permanent V2 identity. Custom filename patterns must still include `{zoteroKey}`.
- Managed sections are bounded by `<!-- ovm:*:start/end -->` markers. Reading Notes and other user sections remain outside those markers.
- MinerU writes into staging first and replaces the complete normalized output only after validation; a failed parse does not commit partial output.
- Local `stdio` is the recommended MCP transport. The optional SSE and streamable-HTTP transports do not add authentication and should not be exposed directly to a network.
- MinerU precision mode sends the PDF to the MinerU service. Token-free flash mode is still an external service path and has stricter limits.
- Diagnostics, transaction previews, and Wiki context can return local paths or literature content to the connected Agent host. Connect only clients you trust.
- Never commit API tokens, absolute vault paths, private vault contents, backups, staging output, or generated release artifacts.

## Migration and recovery

Always preview a V1 migration before applying it:

```bash
obsidian-vault-mcp migrate v1-to-v2 --dry-run
obsidian-vault-mcp migrate v1-to-v2 --apply
obsidian-vault-mcp preview <transaction-id>
obsidian-vault-mcp rollback <transaction-id> --dry-run
obsidian-vault-mcp rollback <transaction-id>
```

Rollback refuses to overwrite a file changed after the transaction. Use `--conflict-policy overwrite-managed` only after consciously accepting that overwrite.

## Documentation and names

- [Full English tutorial](./docs/index.en.md): software downloads, local API setup, optional components, source/PyPI installation, all six Agent clients, configuration, end-to-end use, screenshots, migration, and troubleshooting.
- [English developer guide](./DEVELOPMENT.en.md): architecture, contracts, 26 tools, tests, packaging, release procedure, security, and current limitations.
- [中文用户文档](./README.md) · [中文完整教程](./docs/index.md) · [中文开发者文档](./DEVELOPMENT.md)

## Contributors

Thanks to [方珸 / Lym Fang (@LimFang)](https://github.com/LimFang) for identifying the Zotero linked-attachment compatibility need and proposing the original implementation in [PR #6](https://github.com/luffysolution-svg/obsidian-vault-mcp/pull/6). See [CONTRIBUTORS.md](./CONTRIBUTORS.md) for the complete contribution record.

| Surface | Name |
|---|---|
| GitHub repository | `obsidian-vault-mcp` |
| PyPI distribution | `zotero-obsidian-mcp` |
| Python import | `obsidian_vault_mcp` |
| CLI | `obsidian-vault-mcp` |
| MCP server | `obsidian-literature` |

Report problems through [GitHub Issues](https://github.com/luffysolution-svg/obsidian-vault-mcp/issues). Licensed under the [MIT License](./LICENSE).
