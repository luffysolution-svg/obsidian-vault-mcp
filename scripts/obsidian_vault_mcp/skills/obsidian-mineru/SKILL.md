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
- Literature notes are stable user workspaces; preserve custom YAML, `Reading Notes`, and `AI Summary`. To generate or update `## AI Summary` after parsing, use the `obsidian-ai-summary` skill. It can also be triggered via `obsidian_pipeline_parse_with_mineru(write_ai_summary=true)`.
- The plugin does not generate AI summaries, wiki pages, graphs, or reviews from MinerU output.

## Troubleshooting

- If task creation succeeds but Markdown download fails, check network routes for `mineru.net`, `mineru.oss-cn-shanghai.aliyuncs.com`, `cdn-mineru.openxlab.org.cn`, and `*.openxlab.org.cn`.
- Treat this skill as optional integration logic. If MinerU is unavailable, fall back to importing existing Markdown or a vault PDF attachment instead of blocking the whole workflow.

## Direct Extraction (without Zotero)

To parse a PDF directly with MinerU without going through the Zotero pipeline:

1. Confirm MinerU is available: `Bash` → `mineru-open-api --version` (or check `MINERU_CLI_COMMAND` env var).
2. Run MinerU on a PDF path:

```bash
mineru-open-api --files "C:\path\to\paper.pdf" --output-dir "C:\vault\mineru-output" --method auto
```

3. The output directory will contain:
   - `paper.md` — extracted Markdown
   - `images/` — extracted figures
4. Use `obsidian_read_file` on the generated `.md` to review.
5. Use `obsidian_write_file` to copy the content into the vault's literature folder.

## Extract and Ingest

To extract a PDF and immediately create a literature note:
1. Run MinerU as above.
2. Read the generated Markdown.
3. Create the literature note with `obsidian_write_file`, including frontmatter and links to extracted images.
4. Use `obsidian_pipeline_rename_mineru_images` (MCP) to rename extracted images to semantic English slugs.

## Batch Folder Extraction

To process all PDFs in a folder:

```powershell
Get-ChildItem "C:\zotero-exports" -Filter "*.pdf" | ForEach-Object {
    $out = "C:\vault\mineru-batch\$($_.BaseName)"
    mineru-open-api --files $_.FullName --output-dir $out --method auto
}
```

Then ingest each output folder individually following the "Extract and Ingest" workflow above.

## Zotero PDF Text Extraction

To extract text from a Zotero-managed PDF without full MinerU parsing:
1. Get the PDF path from `obsidian_zotero_list_pdf_attachments` (MCP).
2. Use Bash + pypdf:

```python
import pypdf, sys
reader = pypdf.PdfReader(sys.argv[1])
text = "\n".join(page.extract_text() or "" for page in reader.pages)
print(text[:5000])
```

Run: `python extract_text.py "C:\Zotero\storage\KEY\paper.pdf"`

## Figure & Table Analysis

Use when the user asks a specific question about a figure, chart, or table in a parsed paper.

1. Read `attachments/mineru/<zoteroKey>/images-index.md` with `obsidian_read_file`.
   The index lists every figure with its semantic slug filename and the original caption context, e.g.:
   ```
   - fig-01-process-flow-diagram.png (was: image-a.png)
     Caption context: "Figure 1 Process flow diagram showing…"
   ```
2. Identify which figure matches the user's question from the slug name and caption.
3. Run `obsidian_search` using the slug filename (e.g. `fig-01-process-flow-diagram`) as query to locate the surrounding paragraph in `paper.md`. The search snippet will include the figure's Markdown image tag and adjacent text.
4. Read that section of `paper.md` with `obsidian_read_file` if the search snippet is insufficient.
5. Answer using the extracted caption and surrounding text only. Do **not** attempt to decode image binary data — the image files are not readable as text.

**Typical budget:** 2–3 tool calls (read index → search → answer, or read index → read section → answer).
