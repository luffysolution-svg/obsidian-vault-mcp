---
name: obsidian-mineru
description: "Extract and ingest document content into an Obsidian vault with MinerU. Use when Codex needs to check MinerU availability, parse a PDF or Office document into Markdown, ingest existing MinerU Markdown, create source notes from vault PDFs, or attach parsed full text back to a Zotero-derived literature note. 当用户提到 MinerU、全文解析、PDF 转 Markdown、文档抽取、全文挂接或 PDF 来源笔记时使用。"
---

# Obsidian MinerU

Use this skill when the request is about full-document parsing and source-note ingestion rather than simple literature metadata import.
处理全文提取、PDF 解析和来源笔记导入时优先使用。

## Choose the Path

- If the user already has MinerU Markdown, use `obsidian_ingest_mineru_markdown`.
- If the PDF is already inside the vault and only needs a source note, use `obsidian_ingest_pdf_attachment`.
- If the user wants this plugin to run MinerU directly, start with `obsidian_mineru_status`.

## Direct Extraction Workflow

1. Check `obsidian_mineru_status`.
2. Prefer `flash-extract` when no token is configured.
3. Use `obsidian_mineru_extract` for extraction only.
4. Use `obsidian_mineru_extract_and_ingest` when the goal is a finished Obsidian source note.

## Zotero-Linked Workflow

1. Import the literature note first with `obsidian_ingest_zotero_item`.
2. Pass `zotero_key` to `obsidian_mineru_extract_and_ingest`.
3. Expect the tool to append `mineru_markdown: [[...]]` to the literature note frontmatter while leaving the rest of the note body unchanged.

## Output Expectations

- MinerU content is ingested as a separate source note, typically under the configured MinerU source folder.
- The extracted note can include the parsed Markdown plus an embedded PDF attachment when provided.
- Existing literature notes are not rewritten except for the optional `mineru_markdown` field update in the Zotero-linked path.

## Troubleshooting

- If task creation succeeds but Markdown download fails, check network routes for `mineru.net`, `mineru.oss-cn-shanghai.aliyuncs.com`, `cdn-mineru.openxlab.org.cn`, and `*.openxlab.org.cn`.
- Treat this skill as optional integration logic. If MinerU is unavailable, fall back to importing existing Markdown or a vault PDF attachment instead of blocking the whole workflow.
