---
name: obsidian-mineru
description: "Extract and ingest document content into an Obsidian vault with MinerU. Use when Codex needs to check MinerU availability, parse a PDF or Office document into Markdown, ingest existing MinerU Markdown, create source notes from vault PDFs, or attach parsed full text back to a Zotero-derived literature note. 当用户提到 MinerU、全文解析、PDF 转 Markdown、文档抽取、全文挂接或 PDF 来源笔记时使用。"
---

# Obsidian MinerU

Use this skill when the request is about full-document parsing and source-note ingestion rather than simple literature metadata import.
处理全文提取、PDF 解析和来源笔记导入时优先使用。

## Choose the Path

- If the request is Zotero-linked literature ingestion, prefer `obsidian_pipeline_ingest_item(parse_with_mineru=true)` or `obsidian_pipeline_parse_with_mineru`.
- If MinerU output already exists under the pipeline layout, use `obsidian_pipeline_rename_mineru_images` to normalize images and regenerate `images-index.md`.
- Use older `obsidian_mineru_*` tools only in the `full` or `legacy` profile for compatibility/debugging.

## Direct Extraction Workflow

1. Check `obsidian_pipeline_doctor` or `obsidian_mineru_status`.
2. Parse copied Zotero PDFs into `attachments/mineru/<zoteroKey>/paper.md`.
3. Rename extracted images to English semantic filenames such as `fig-01-process-flow-diagram.png`.
4. Generate `attachments/mineru/<zoteroKey>/images-index.md`.

## Zotero-Linked Workflow

1. Import the literature note with `obsidian_pipeline_ingest_item`.
2. Pass `parse_with_mineru=true`, or later call `obsidian_pipeline_parse_with_mineru(zotero_key=...)`.
3. Expect the literature note to link to the copied PDF, Zotero PDF URI, MinerU Markdown, and image index while preserving user reading work.

## Output Expectations

- MinerU assets are machine-generated and may be overwritten on re-parse.
- Literature notes are stable user workspaces; preserve custom YAML, `Reading Notes`, and `AI Summary`.
- The plugin does not generate AI summaries, wiki pages, graphs, or reviews from MinerU output.

## Troubleshooting

- If task creation succeeds but Markdown download fails, check network routes for `mineru.net`, `mineru.oss-cn-shanghai.aliyuncs.com`, `cdn-mineru.openxlab.org.cn`, and `*.openxlab.org.cn`.
- Treat this skill as optional integration logic. If MinerU is unavailable, fall back to importing existing Markdown or a vault PDF attachment instead of blocking the whole workflow.
