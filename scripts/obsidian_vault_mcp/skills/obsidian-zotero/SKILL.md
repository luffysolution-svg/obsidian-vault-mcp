---
name: obsidian-zotero
description: "Import and synchronize Zotero literature with an Obsidian vault. Use when Codex needs to search the local Zotero library, inspect Zotero items or collections, import Zotero items into Obsidian literature notes, include child notes or annotations, copy or link PDF attachments, extract PDF text, or batch-ingest a Zotero collection. 当用户提到 Zotero 文献库、参考文献导入、批注、附件、PDF、合集批量导入或文献笔记同步时使用。"
---

# Obsidian Zotero

Use the Zotero tools in this plugin when the request starts from the user's local Zotero library and the destination is an Obsidian vault.
处理 Zotero 到 Obsidian 的导入、同步、附件和批注时优先使用。

## Start

1. Call `obsidian_zotero_ping` before direct Zotero work.
2. If the ping fails, ask the user to open Zotero Desktop and enable the local API.
3. Use `obsidian_zotero_search_items`, `obsidian_zotero_list_collections`, `obsidian_zotero_get_item`, and `obsidian_zotero_get_children` to find the correct source record before importing.

## Import Workflow

1. Prefer `obsidian_pipeline_ingest_item` for a single parent item.
2. Prefer `obsidian_pipeline_ingest_collection` for collection batch import; it continues after per-item failures and returns a full report.
3. The pipeline always copies PDFs into the configured vault attachment folder, preserves Zotero source paths, and writes `zotero://select` plus `zotero://open-pdf` links.
4. Use `write_ai_summary=true` only when the user asks for a generated `## AI Summary`; the tool fills empty summaries and leaves non-empty user summaries untouched.

## Imported Note Shape

- Pipeline frontmatter includes Zotero identity fields such as `zoteroKey`, `zoteroVersion`, `zoteroSelect`, `zoteroPdfKeys`, `zoteroPdfLinks`, original attachment paths, copied attachment paths, and Obsidian wikilinks.
- Collection names are stored as human-readable names in `collections`, not raw collection keys.
- The note body can include citation details, embedded attachments, abstract text, child notes, annotations, related-item links, attachment warnings, and optional extracted PDF text.

## Re-ingest Behavior

- Repeated pipeline runs preserve user-owned YAML fields, unknown custom fields, `## Reading Notes`, and `## AI Summary`.
- The plugin does not generate AI summaries. Use the `obsidian-ai-summary` skill to generate or update that section — it can be triggered after import or via `obsidian_pipeline_ingest_item(write_ai_summary=true)`.

## Related Tools

- Use `obsidian_zotero_list_pdf_attachments` to inspect attachment inventory before import.
- For raw PDF text without a full note import, use `obsidian_zotero_list_pdf_attachments` to locate the attachment path, then extract text with a local PDF parser such as `pypdf`.
- Use the `obsidian-mineru` skill when the request is about parsing a Zotero-linked PDF into full Markdown.

## Reading a Single Paper

Use when the user asks a question about a specific literature note or wants a summary, key findings, methods, or evidence from one paper.

1. Read the literature note frontmatter with `obsidian_read_file`.
2. Check `mineruStatus`:
   - If `mineruStatus: parsed` → read `attachments/mineru/<zoteroKey>/paper.md` via `obsidian_read_file`. This is the richest source (full structured text + figure captions).
   - Otherwise → read the literature note body directly.
3. For targeted questions (e.g. "what dataset did they use?"), use `obsidian_search` with a focused keyword **before** reading the full file — this often answers the question in ≤ 2 tool calls.
4. Preserve and surface the user's `## Reading Notes` content as primary evidence when answering.

**Budget:** ≤ 3 tool calls for a typical factual question. Escalate to full-file read only if search is insufficient.

## Comparing Multiple Papers

Use when the user wants a structured comparison across 2–10 literature notes (methods, results, datasets, limitations, etc.).

1. Batch-read each paper's literature note (first ~60 lines) to get frontmatter + abstract via `obsidian_read_file`. This covers most comparisons.
2. Agree on the comparison axis with the user (method / result / dataset / limitation / year).
3. For axes requiring deeper detail, run `obsidian_search` with a targeted keyword. Scope the search by including the paper title or zoteroKey in the query to avoid cross-paper noise.
4. Emit a structured Markdown table:

```markdown
| Paper | Method | Dataset | Key Result | Limitation |
|-------|--------|---------|------------|------------|
| Author YYYY | … | … | … | … |
```

5. Append a 2–3 sentence synthesis paragraph below the table.

## Writing a Literature Review

Use when the user wants to draft or scaffold a review section covering multiple papers on a topic.

### Phase 1 — Collect

1. Run `obsidian_search` with the review topic as query; set `extensions=".md"`.
2. Filter results to notes with `type: literature` in frontmatter.
3. Present the candidate list to the user and confirm scope before proceeding.

### Phase 2 — Deep-read

1. For each selected paper:
   - If `mineruStatus: parsed` → read MinerU Markdown (`attachments/mineru/<zoteroKey>/paper.md`).
   - Otherwise → read the literature note.
2. Extract key claims grouped by review theme (background / methods / results / gaps).
3. Always include the user's existing `## Reading Notes` content — it is primary evidence.

### Phase 3 — Synthesize

1. Draft the review section by section, grouping papers under each theme.
2. Use inline wikilinks `[[Lovelace 2024 - Zotero Article]]` to cite papers.
3. Save the draft with `obsidian_write_file` to a path agreed with the user (e.g. `reviews/Topic Review Draft.md`).
4. Mark the draft with `status: draft` in frontmatter.

## Eval Scenarios

- **Trigger:** "Import Zotero item ITEM1 and write a summary." Expected: call `obsidian_zotero_ping`, then `obsidian_pipeline_ingest_item(write_ai_summary=true)`. Must not overwrite existing `## Reading Notes` or a non-empty `## AI Summary`.
- **Trigger:** "What dataset did this paper use?" Expected: read the literature note, prefer MinerU Markdown when `mineruStatus: parsed`, and answer from local evidence. Must not import, re-ingest, or write files.
- **Trigger:** "Compare these five papers by method and limitation." Expected: read notes first, use targeted `obsidian_search` only for missing details, return a Markdown table plus short synthesis. Must preserve user notes as primary evidence.
