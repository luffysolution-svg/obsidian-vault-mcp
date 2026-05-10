# References and Attribution

This plugin is an original local Codex plugin for Obsidian vault operations, but its design is explicitly influenced by two public references.

## Kepano Obsidian Skills

Reference: https://github.com/kepano/obsidian-skills

Borrowed idea:

- Treat Obsidian work as several small, composable skills rather than one oversized instruction file.
- Keep Markdown, wikilinks, JSON Canvas, Bases, and Obsidian CLI behavior as separate conceptual surfaces.
- Prefer native Obsidian formats so generated files remain useful without a custom runtime.

How this plugin adapts it:

- The bundled `obsidian-vault` skill coordinates local vault operations.
- The MCP server provides practical tools for listing, reading, writing, frontmatter updates, wikilink creation, graph generation, Canvas creation, Base creation, and CLI calls.
- Existing `obsidian-markdown`, `json-canvas`, and `obsidian-bases` skills remain the format authorities for generated content.
- MinerU can be used as an optional external parser; this plugin either ingests
  existing MinerU Markdown or calls the local `mineru-open-api` CLI when users
  choose the optional extraction tools.

## Karpathy LLM Wiki

Reference: https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f

Borrowed idea:

- Use Obsidian as an IDE for a persistent, compounding knowledge base.
- Let the LLM maintain cross-references, topic pages, source summaries, index pages, logs, and graph health.
- File useful answers back into the wiki instead of leaving them only in chat history.

How this plugin adapts it:

- Notes can be generated with stable YAML properties and wikilinks.
- Graph data can be built from the vault to find backlinks, dead ends, orphan pages, unresolved links, and tags.
- Canvas files can visualize topic clusters.
- Bases files can turn frontmatter and file metadata into filterable tables and cards.

## Operational Documentation

The setup and integration docs also rely on the following primary references:

- Obsidian CLI: https://help.obsidian.md/cli
- Codex Skills: https://developers.openai.com/codex/skills
- Codex Plugins: https://developers.openai.com/codex/plugins
- Codex plugin authoring: https://developers.openai.com/codex/plugins/build
- Zotero connector HTTP server: https://www.zotero.org/support/dev/client_coding/connector_http_server
- Zotero Web API v3 basics: https://www.zotero.org/support/dev/web_api/v3/basics
- MinerU Open API CLI: https://pkg.go.dev/github.com/opendatalab/MinerU-Ecosystem/cli
- MinerU Ecosystem: https://github.com/opendatalab/MinerU-Ecosystem

## Demo Screenshots

Screenshots are not included in this release. Sanitized demo images may be added in a future release.
