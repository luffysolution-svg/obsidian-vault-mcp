# Obsidian Vault MCP 3.0.0 Developer Guide

[中文](./DEVELOPMENT.md) · [README](./README.en.md) · [User tutorial](./docs/index.en.md)

This is the V3 implementation, test, and release contract. The distribution is `zotero-obsidian-mcp`, the CLI is `obsidian-vault-mcp`, and the MCP Registry name is `io.github.luffysolution-svg/obsidian-vault-mcp`.

## 1. Invariants

1. `zoteroKey` identifies a paper. Title, authors, year, citekey, and path do not.
2. User text changes only under an explicit conflict policy; the default must not silently overwrite it.
3. Formal writes use locks, staging, backups, manifests, atomic replacement, and rollback-capable transactions.
4. Main notes/PDFs are stable assets. MinerU Markdown and images are rebuildable derived assets.
5. MinerU Markdown is `Literature/attachment/MinerU/{key}.md`.
6. MinerU images are `Literature/attachment/MinerU/image/{key}/{key}-figNN.ext`; links are `image/{key}/{key}-figNN.ext`.
7. Structured research uses five Analysis types, five statuses, seven profiles, and one nine-view `Analysis.base`.
8. Runtime code creates no Evidence, Coverage, Uncertainty, Analysis index, Topic, Theory, or Analysis templates.
9. MCP exposes exactly 31 tools: 26 stable V2 tools plus 5 V3 Analysis tools.
10. Exactly seven Agent Skills are recursively packaged from one canonical marketplace resource tree.
11. CLI, MCP, Pi, and Agent installers adapt interfaces only. Business logic stays in application/domain/adapters.
12. Automated tests never write a user's real vault. Real-vault checks are read-only; write tests use an isolated copy.

The retained `Literature/index.md` and `Literature/Literature.base` are V2 literature navigation assets, not the removed Analysis index.

## 2. Architecture

```text
Codex / Claude / OpenCode / Hermes / WorkBuddy ─┐
                                                ├─ MCP stdio
Pi Extension ── JSON CLI ───────────────────────┤
CLI ────────────────────────────────────────────┘
                         ↓
                    application
       config / import / MinerU / Analysis / transaction
                  ↙            ↓             ↘
             Zotero         domain        Obsidian files
             adapter       contracts       + renderers
```

Dependencies point inward:

```text
interfaces → application → domain
                 ↓
              adapters
```

Domain does not load client configuration, run subprocesses, or depend on MCP. Interfaces do not duplicate business rules.

Key directories:

```text
src/obsidian_vault_mcp/
├─ domain/                 # identity, paths, frontmatter, Analysis contracts
├─ application/            # use cases, transactions, migration, Skills
├─ adapters/
│  ├─ zotero/              # local API and linked attachments
│  └─ obsidian/            # note/Base/MinerU normalization
├─ config/                 # defaults, schema, runtime loading
├─ interfaces/
│  ├─ cli/                 # shared JSON CLI
│  ├─ mcp/                 # fixed 31-tool server
│  └─ agent_install/       # six client installers and Pi resource
└─ resources/
   └─ agent_marketplace/   # Codex/Claude manifests and canonical Skills

adapters/pi/               # independently type-checked thin Extension
tests/                     # unit, integration, contract, release
scripts/                   # deterministic build and release verification
server.json                # MCP Registry 3.0.0 metadata
```

## 3. Literature and MinerU contract

Stable main-note frontmatter contains `zoteroKey`, PDF/MinerU links, and Zotero metadata. User body text and managed blocks remain separate; synchronization updates managed content only.

The MinerU normalizer must:

1. Select one Markdown result inside transaction staging.
2. Deterministically rename images into that key's isolated directory.
3. Rewrite image references to relative Markdown paths.
4. Reject escaping, missing, absolute, duplicate-target, and unsupported output.
5. Commit Markdown, images, the main-note link, and state only after every validation succeeds.

Removal is transactional too. Failure cannot leave formal partial output or links into staging.

## 4. Analysis data model

### 4.1 Enums

```text
types:
  full_read
  literature_review
  passage_qa
  figure_qa
  concept

statuses:
  draft
  ready
  reviewed
  needs_update
  archived

profiles:
  general
  medicine
  chemistry
  materials
  catalysis
  physics
  mathematics
```

Every Analysis shares a schema version, stable `analysisId`, type/profile, source keys, source fingerprint, skill/version, timestamps, summary, and tags. `domain/analysis.py` defines and strictly validates type-specific fields.

The body has one managed block. Upgrades and rewrites retain user text outside it. A changed source fingerprint yields `needs_update` on read and never silently replaces the earlier analysis.

### 4.2 Default paths

| Type | Path |
|---|---|
| `full_read` | `Literature/Analysis/full-reads/` |
| `literature_review` | `Literature/Analysis/reviews/` |
| `passage_qa` | `Literature/Analysis/qa/passages/` |
| `figure_qa` | `Literature/Analysis/qa/figures/` |
| `concept` | `Literature/Analysis/concepts/` |
| Base | `Literature/Analysis/Analysis.base` |

`Analysis.base` recursively filters for `analysisId != null` and renders exactly nine ordered views:

```text
Dashboard
Full Reads
Reviews
Passage Q&A
Figure Q&A
Concepts
Needs Attention
By Discipline
Recently Updated
```

The Base does not embed full bodies or create a parallel Markdown index.

## 5. Five Analysis tools

| Tool | Behavior | Contract |
|---|---|---|
| `literature_paper_read` | Read-only | Single-paper overview/targeted/figures; bounded located text/image information, no persistent derived state |
| `literature_retrieve` | Read-only | Cross-paper candidates and passages; query coverage exists only in the response |
| `literature_analysis_get` | Read-only | Query by ID, type, or source and calculate effective status |
| `literature_analysis_write` | Write | Strict validation, stable identity, dry-run, transaction commit, conflict policy |
| `literature_rebuild_analysis_base` | Write | Deterministically preview or rebuild the one Base |

The names of all 26 stable tools are in the user tutorial. Do not add compatibility aliases. Any change to tool names, parameters, or annotations must update server, CLI, Pi/plugin configuration, contract tests, release verifier, and both language docs.

Read-only tools declare `readOnlyHint`/`idempotentHint`; write tools accurately declare destructive/idempotent behavior. Every tool has `openWorldHint=false`.

## 6. Migration contract

V2 flat MinerU image migration is also CLI-only:

```powershell
obsidian-vault-mcp migrate mineru-images-v2-to-v3 --vault-path <vault>
obsidian-vault-mcp migrate mineru-images-v2-to-v3 --vault-path <vault> --apply
```

The report distinguishes `copiedImages`, `movedImages`,
`preservedLegacyImages`, `rewrittenMarkdown`, `missingReferencedImages`,
`reparseZoteroKeys`, and skipped entries. An image is accepted only when its
filename, Markdown frontmatter, and reference prove ownership together. Safe
mode copies and preserves the old path. Destructive cleanup requires both
`--cleanup-legacy` and `--confirm-vault-offline`; copying, reference rewriting,
and legacy deletion then commit atomically in one global transaction.

V2-to-V3 Analysis migration is CLI-only:

```powershell
obsidian-vault-mcp migrate analysis-v2-to-v3 --vault-path <vault>
obsidian-vault-mcp migrate analysis-v2-to-v3 --vault-path <vault> --apply
```

The default call creates a dry-run manifest only. Only `--apply` may commit a transaction. Results distinguish migrated, skipped, manual-review, obsolete-anchor handling, old Analysis-index handling, Base creation, and Topic/Theory files that cannot be mapped safely.

Use the common transaction entry points after commit:

```powershell
obsidian-vault-mcp preview <transaction-id> --vault-path <vault>
obsidian-vault-mcp rollback <transaction-id> --vault-path <vault> --dry-run
obsidian-vault-mcp rollback <transaction-id> --vault-path <vault>
```

Failure rolls back; uncertain files remain in place. Repeated preview/apply operations must be idempotent.

## 7. Skills and plugins

The one canonical set is:

```text
paper-qa
full-read
passage-qa
figure-qa
compare-papers
literature-review
concept-learning
```

Its source is `src/obsidian_vault_mcp/resources/agent_marketplace/plugins/obsidian-literature/skills/`. Each Skill contains `SKILL.md` and optional recursive `references/**/*.md`. Wheel, sdist, plugin zip, and installed files must be byte-for-byte descendants of that resource tree.

Upgrades replace only managed blocks and retain user additions. An obsolete Skill can be removed only when the manifest proves this project managed it. User-created same-name or extra files are never deleted.

Client matrix:

| Client | MCP | Skills/plugin |
|---|---|---|
| Codex | Plugin `.mcp.json` | Native marketplace and seven Skills |
| Claude Code | Plugin `.mcp.json` | Native marketplace and seven Skills |
| OpenCode | Project configuration | Seven project-local Skills |
| Pi | JSON CLI bridge | Thin TypeScript Extension |
| Hermes | YAML configuration | No verified automated Skill contract |
| WorkBuddy | JSON configuration | No verified automated Skill contract |

Run OpenCode, Pi, Hermes, and WorkBuddy installation in the target project or pass `--project-dir`. When upgrading the Python package from 2.x, uv tool users run `uv tool install --force "zotero-obsidian-mcp==3.0.0"` and pipx users run `pipx install --force "zotero-obsidian-mcp==3.0.0"`. Then refresh Codex's local plugin cache with its atomic `plugin add`; for Claude, run `plugin marketplace update obsidian-vault-mcp`, then `plugin update ... --scope user`, and restart. The release zip is the same marketplace for offline extraction; a clean offline Claude installation uses `plugin marketplace add` followed by `plugin install obsidian-literature@obsidian-vault-mcp --scope user`. An existing marketplace name must never be rebound to another source.

`adapters/pi/index.ts` and the wheel resource `src/obsidian_vault_mcp/interfaces/agent_install/pi_extension.ts` must be byte-identical and LF-normalized.

Design references and license boundary:

- `yilewang/llm-for-zotero` (AGPL-3.0): the review covered
  `src/agent/skills/simple-paper-qa.md`, `compare-papers.md`,
  `literature-review.md`, and `analyze-figures.md`. Only high-level ideas for
  intent routing, targeted reading, thematic synthesis, and missing-image
  fallback informed the design.
- `Yuan1z0825/nature-skills` from the user's Stars (repository license
  Apache-2.0): the review covered `skills/nature-literature-pipeline/SKILL.md`
  and `skills/nature-paper-card/SKILL.md`. Only organizational ideas for
  on-demand references, source boundaries, and discipline adaptation informed
  the design.

This repository's seven Skills, references, server code, and tests were written
independently. No code or Skill text from those repositories is copied into the
MIT distribution.

## 8. Tests

Local gates:

```powershell
python -m ruff check src tests scripts/build_release.py scripts/release_guard.py scripts/verify_release.py
python -m pytest
python scripts/verify_release.py

Push-Location adapters/pi
npm ci --no-audit --no-fund
npm run check
Pop-Location
```

At minimum, tests cover:

- Schema, stable identity, status/profile, and managed blocks for all five Analysis types.
- `paper_read`/`retrieve` bounds, locators, 1-based paragraphs, and absence of persistent derived state.
- Per-key MinerU image directories, relative links, atomic failure, and repeat parsing.
- Nine ordered Base views, filters, grouping/sorting, and idempotency.
- Migration dry-run, apply, rollback, conflict, failure recovery, and repeat execution.
- Exact 31-tool names, annotations, and stdio initialization handshake.
- Exactly seven Skills, recursive references, managed upgrades, and obsolete managed-Skill cleanup.
- Six client/plugin installers, backups, merge, handshake, and rollback.
- Wheel/sdist/plugin zip contents, versions, portable configuration, and absence of obsolete assets.

CI runs Python gates on Ubuntu, Windows, and macOS with Python 3.10–3.13. A separate Node 22 job type-checks Pi; a dependent job builds the release candidate.

## 9. Real-vault end-to-end acceptance

Production checks against a real vault are read-only. Create a SHA-256 inventory first, then run config/doctor/verify, paper read, retrieve, and Analysis get, and finally prove the inventory is unchanged.

Only a fresh release-candidate copy may receive writes. Exclude active locks, staging, old backups, and stale temporary directories. Test import/sync, real MinerU, all five Analysis types, Base, migration, preview, rollback, repetition, and final verification against the copy.

Any failed acceptance gate or real-vault hash change blocks tagging and publication.

## 10. Build and verification

```powershell
python -m build --wheel --sdist --outdir dist
python scripts/verify_release.py --artifacts-dir dist --require-sdist --smoke-wheel
python scripts/build_release.py --version 3.0.0 --output-dir dist
python scripts/verify_release.py --bundle-dir dist
```

3.0.0 artifacts:

```text
zotero_obsidian_mcp-3.0.0-py3-none-any.whl
zotero_obsidian_mcp-3.0.0.tar.gz
obsidian-vault-mcp-3.0.0-plugins.zip
SHA256SUMS
```

The verifier checks the 31-tool stdio handshake, seven Skills and references, Pi source equality, MCP/plugin manifests, version agreement, artifact allowlists, a temporary wheel smoke install, and absence of obsolete structured resources.

## 11. Versioning and release

3.0.0 agrees across:

- `pyproject.toml` and `src/obsidian_vault_mcp/__init__.py`
- `adapters/pi/package.json` and root package-lock records
- Codex/Claude plugin manifests and marketplace metadata
- `server.json`
- tag `v3.0.0`

Before release:

```powershell
python scripts/verify_release.py --tag v3.0.0
git status --short
git tag -a v3.0.0 -m "Obsidian Vault MCP V3.0.0"
git push origin v3.0.0
```

The exact `refs/tags/v3.0.0` ref points to a CI-passing commit on `main`; its local tag object, remote tag object, dereferenced commit, and checked-out HEAD must agree. Tags, GitHub Releases, and PyPI versions are immutable. Before triggering the workflow, enable immutable releases and configure an `IMMUTABLE_RELEASES_TOKEN` secret with repository-scoped `Administration: read` only; normal Release access continues to use the less-privileged `GITHUB_TOKEN`. Final verification rejects a published Release unless the GitHub API reports `immutable: true`. The release workflow:

1. Repeats Python, Pi, 31-tool, and package-content gates in a build job with `contents: read` only.
2. Produces reproducible wheel, sdist, plugin zip, and SHA-256 checksums with pinned build tools and the commit timestamp, then hands them to a separate publish job as a workflow artifact.
3. Grants `contents: write` and `id-token: write` only to the publish job. Before its first external mutation, it completes strict remote-tag, GitHub immutability/Release, PyPI, MCP Registry, and pinned-publisher validation.
4. Preflights exact PyPI filenames and SHA-256 digests. It uploads all files for an absent version or only missing files when the remote set is an exact local subset; extra files and same-name digest conflicts fail, and `skip-existing` remains forbidden.
5. Preflights the exact MCP Registry name/version metadata and checks it again immediately before publishing; it publishes only when absent, using a pinned `mcp-publisher` and GitHub OIDC.
6. Finally creates an empty GitHub Release draft with a fixed workflow marker and uploads only missing assets. An interrupted rerun may resume only that owned marker-matching draft when its assets are an exact subset of the local set; foreign drafts, extra assets, and digest conflicts fail without deletion or overwrite.
7. Downloads and verifies every complete draft asset by SHA-256 before publishing the immutable Release; an already-published Release must pass the same exact check.

uv/uvx has no separate repository publication; it installs from PyPI. After release, use clean environments to verify pip, pipx, `uv tool install`, uvx, MCP Registry, all six client installers, seven Skills, and the 31-tool handshake.

## 12. Security and review checklist

- Never persist Zotero/MinerU/client credentials; redact token arguments in logs.
- Run subprocesses with argument arrays and no shell.
- Resolve every vault path and reject reparse/symlink escapes.
- Put non-stdio MCP transport behind an external authentication boundary.
- Never commit real vaults, attachments, state, backups, test copies, or machine-specific absolute paths.
- Keep changes surgical and traceable. Unrelated refactors, formatting, and old-code cleanup do not belong in the release.

“Build succeeded” is not completion. Source tests, artifact smoke tests, real-vault read-only checks, isolated-copy writes, GitHub/PyPI/Registry publication, and the full installation matrix all need reviewable evidence.
