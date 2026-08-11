# Changelog

All notable changes to Obsidian Vault MCP are recorded in this file.

## 3.0.2 — 2026-08-11

### Fixed

- Normalized local HTML `<img>` references emitted inside MinerU table output while continuing to reject malformed, remote, missing, and path-traversing image sources.

### Changed

- Aligned the Python package, runtime, MCP Registry metadata, Agent plugin manifests, Pi extension, release workflow, documentation, and release tests on version `3.0.2`.

## 3.0.1 — 2026-07-30

### Changed

- Aligned the package, runtime, MCP Registry metadata, Agent marketplaces, Pi extension, release workflow, documentation, and release tests on version `3.0.1`.
- Published the rebuilt bilingual GitHub Pages documentation as the formal release documentation source.

## 3.0.0 — 2026-07-30

### Added

- Five structured Analysis types: `full_read`, `literature_review`, `passage_qa`, `figure_qa`, and `concept`.
- A single nine-view `Literature/Analysis/Analysis.base` database.
- Seven research Skills: `paper-qa`, `full-read`, `passage-qa`, `figure-qa`, `compare-papers`, `literature-review`, and `concept-learning`.
- Discipline profiles for general research, medicine, chemistry, materials, catalysis, physics, and mathematics.
- Per-paper MinerU image directories with portable relative links.
- A read-only `literature_version` capability reporting the package version and public contract.
- Version-consistency checks across Python, MCP Registry metadata, Codex/Claude plugins, Pi, Git tags, release artifacts, and PyPI.

### Changed

- Established the V3 data model as the production architecture.
- Standardized the public MCP surface at 31 tools.
- Rewrote user and developer documentation around the current architecture, installation paths, screenshots, Skills, and release process.

### Removed

- Legacy Vault, Analysis, and MinerU image migration commands and services.
- Deprecated structured Evidence, Coverage, Uncertainty, Topic, Theory, and Analysis-index assets.

## 2.1.0

- Added evidence-oriented reading and retrieval capabilities.
- Expanded native plugin and client installation support.

## 2.0.1

- Added secure support for Zotero linked attachments.
- Credited the original compatibility proposal from @LimFang.

## 2.0.0

- Introduced stable Zotero-key identity, transactional Vault writes, Index/Base/Wiki generation, and multi-client installers.

## 1.x

- Initial Zotero, MinerU, and Obsidian integration releases.
