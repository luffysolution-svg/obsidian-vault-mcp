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

## Demo Screenshots

Screenshots are intentionally not bundled until sanitized examples are created.
