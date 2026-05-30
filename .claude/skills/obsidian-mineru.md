---
name: obsidian-mineru
description: "Parse PDFs with MinerU — direct extraction, batch folders, Zotero PDF text extraction. MinerU 直接解析 PDF、批量处理或 Zotero PDF 文本提取时使用。"
---

- **Pipeline** (recommended): use `obsidian_pipeline_parse_with_mineru` for Zotero-attached PDFs; pass `write_ai_summary=true` only when requested.
- **Direct**: `Bash` → `mineru-open-api --files "path.pdf" --output-dir "out/" --method auto`
- **Batch**: PowerShell loop over `*.pdf` → run `mineru-open-api` for each.
- **Text only**: `Bash` → `python -c "import pypdf; r=pypdf.PdfReader('f.pdf'); print('\n'.join(p.extract_text() for p in r.pages))"`
- After extraction: use `obsidian_pipeline_rename_mineru_images` (MCP) to rename images to semantic slugs.
- **Figure analysis**: read `attachments/mineru/<key>/images-index.md` → identify figure by slug/caption → `obsidian_search` with slug filename to locate surrounding text in `paper.md` → answer from caption + context (never decode image bytes).
- **Evals**: parse+summary must preserve user sections; figure rename edits machine assets; figure Q&A answers from extracted captions/context only.
