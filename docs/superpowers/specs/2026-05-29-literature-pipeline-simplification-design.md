# Literature Pipeline Simplification Design

Date: 2026-05-29

## Goal

Refocus the plugin from a broad Obsidian knowledge-base toolbox into a focused Zotero-MinerU-Obsidian literature pipeline.

The plugin should reliably move literature material into Obsidian:

- read Zotero metadata, collections, child notes, annotations, and PDF attachments;
- copy PDFs into the vault while preserving Zotero source paths and `zotero://` links;
- optionally parse PDFs with MinerU;
- normalize MinerU Markdown, images, and image indexes as Obsidian assets;
- update stable literature notes without overwriting user-owned reading work;
- leave AI summaries, wiki generation, knowledge graphs, and high-level knowledge organization to skills or separate projects.

## Product Boundary

The plugin is responsible for ingestion, parsing, file organization, and stable metadata links.

The plugin is not responsible for:

- AI summaries;
- wiki page generation;
- knowledge graph analysis;
- graph community detection;
- literature review synthesis;
- concept maps or Canvas views;
- long-term knowledge-base curation beyond the imported literature assets.

Existing graph, wiki, Canvas, Bases, and broad CLI tools can remain available through a `full` or `legacy` profile, but they should not be part of the default tool surface.

## Default Vault Layout

Default layout:

```text
literature/
  Smith 2024 - Efficient Ethanol Alkylation.md

attachments/
  zotero/
    ABCD1234/
      efficient-ethanol-alkylation.pdf

  mineru/
    ABCD1234/
      paper.md
      images-index.md
      images/
        fig-01-process-flow-diagram.png
        fig-02-catalyst-performance-comparison.png
```

The default note filename pattern is:

```text
FirstAuthor Year - Short Title.md
```

MinerU outputs belong under `attachments/mineru` because they are machine-generated assets attached to the literature item, similar to copied Zotero PDFs under `attachments/zotero`.

## Vault-Local Configuration

Folders and naming patterns must be configurable through a vault-local file:

```text
.obsidian-vault-pipeline.json
```

Default config:

```json
{
  "literatureFolder": "literature",
  "zoteroAttachmentsFolder": "attachments/zotero",
  "mineruAttachmentsFolder": "attachments/mineru",
  "noteFilenamePattern": "{firstAuthor} {year} - {shortTitle}",
  "pdfFilenamePattern": "{shortTitle}",
  "mineruMarkdownName": "paper.md",
  "mineruImagesIndexName": "images-index.md"
}
```

Users may change folder names, including non-English folder names. All plugin-managed paths and wikilinks must be derived from this config.

## Core Obsidian Assets

Each Zotero item has one stable literature note.

When MinerU is used, each item also has:

- one MinerU extraction note;
- one MinerU image index note;
- one image folder containing renamed image assets.

The three note assets must link to each other:

```text
literature note
  -> copied PDF
  -> zotero://select
  -> zotero://open-pdf
  -> MinerU Markdown
  -> MinerU image index

MinerU paper.md
  -> parent literature note
  -> copied PDF
  -> Zotero PDF link
  -> image index

images-index.md
  -> parent literature note
  -> MinerU paper.md
  -> renamed image embeds
```

## Literature Note Model

Example YAML:

```yaml
---
type: literature
title: Efficient Ethanol Alkylation
authors:
  - Smith, Jane
year: 2024
doi: 10.xxxx/example
publicationTitle: Journal Name
abstract: Abstract from Zotero.

zoteroKey: ABCD1234
zoteroVersion: 128
zoteroSelect: zotero://select/library/items/ABCD1234
zoteroPdfKeys:
  - PDFKEY01
zoteroPdfLinks:
  - zotero://open-pdf/library/items/PDFKEY01
zoteroAttachmentPaths:
  - C:/Users/example/Zotero/storage/XXXX/paper.pdf

attachments:
  - attachments/zotero/ABCD1234/efficient-ethanol-alkylation.pdf
attachmentLinks:
  - "[[attachments/zotero/ABCD1234/efficient-ethanol-alkylation.pdf]]"

mineruStatus: parsed
mineruExtractedAt: 2026-05-29T16:30:00+08:00
mineruMarkdown: attachments/mineru/ABCD1234/paper.md
mineruMarkdownLink: "[[attachments/mineru/ABCD1234/paper]]"
mineruImagesFolder: attachments/mineru/ABCD1234/images
mineruImagesIndex: attachments/mineru/ABCD1234/images-index.md
mineruImagesIndexLink: "[[attachments/mineru/ABCD1234/images-index]]"

status: unread
rating:
priority:
project:
userTags: []
tags:
  - literature
  - zotero
  - mineru
---
```

Recommended body:

```markdown
# Efficient Ethanol Alkylation

## Abstract

Plugin-managed abstract from Zotero.

## PDF

- Local: ![[attachments/zotero/ABCD1234/efficient-ethanol-alkylation.pdf]]
- Zotero: [Open in Zotero](zotero://open-pdf/library/items/PDFKEY01)

## Zotero Notes & Annotations

Plugin-managed Zotero child notes and annotations.

## MinerU Extraction

- Markdown: [[attachments/mineru/ABCD1234/paper]]
- Images: [[attachments/mineru/ABCD1234/images-index]]

## Reading Notes

User-owned section. The plugin must not overwrite it.

## AI Summary

Skill-owned section. The plugin must not generate or overwrite it.
```

## MinerU Extraction Note Model

Path:

```text
attachments/mineru/<zoteroKey>/paper.md
```

Example YAML:

```yaml
---
type: mineru-extraction
parent: literature/Smith 2024 - Efficient Ethanol Alkylation.md
parentLink: "[[Smith 2024 - Efficient Ethanol Alkylation]]"
zoteroKey: ABCD1234
sourcePdf: attachments/zotero/ABCD1234/efficient-ethanol-alkylation.pdf
sourcePdfLink: "[[attachments/zotero/ABCD1234/efficient-ethanol-alkylation.pdf]]"
zoteroPdfLink: zotero://open-pdf/library/items/PDFKEY01
imagesFolder: attachments/mineru/ABCD1234/images
imagesIndex: attachments/mineru/ABCD1234/images-index.md
imagesIndexLink: "[[attachments/mineru/ABCD1234/images-index]]"
---
```

Recommended body:

```markdown
# Efficient Ethanol Alkylation - MinerU Extraction

## Original PDF

![[attachments/zotero/ABCD1234/efficient-ethanol-alkylation.pdf]]

## Images

[[attachments/mineru/ABCD1234/images-index]]

## Extracted Content

MinerU-generated Markdown content.
```

The MinerU extraction note is a machine-generated asset. It can be overwritten when the PDF is re-parsed.

## MinerU Image Index Model

Path:

```text
attachments/mineru/<zoteroKey>/images-index.md
```

Example YAML:

```yaml
---
type: mineru-image-index
parent: literature/Smith 2024 - Efficient Ethanol Alkylation.md
parentLink: "[[Smith 2024 - Efficient Ethanol Alkylation]]"
zoteroKey: ABCD1234
sourceExtraction: attachments/mineru/ABCD1234/paper.md
sourceExtractionLink: "[[attachments/mineru/ABCD1234/paper]]"
---
```

Recommended body:

```markdown
# Images - Smith 2024

| ID | Image | File | Caption | Used For |
|---|---|---|---|---|
| fig-01 | ![[attachments/mineru/ABCD1234/images/fig-01-process-flow-diagram.png]] | `fig-01-process-flow-diagram.png` | Process flow diagram. | Explains process flow. |
```

The image index is machine-generated and can be overwritten during re-parse or image rename operations.

## MinerU Image Naming

Image filenames must use English slugs for portability across GitHub, URLs, scripts, and sync tools.

Pattern:

```text
<type>-<number>-<english-semantic-slug>.<ext>
```

Examples:

```text
fig-01-process-flow-diagram.png
fig-02-catalyst-performance-comparison.png
table-01-reaction-condition-summary.png
scheme-01-reaction-pathway.png
eq-01-rate-equation.png
img-01-unclassified-figure.png
```

Type prefixes:

```text
fig     ordinary figure
table   table screenshot or table image
scheme  reaction pathway, mechanism, process scheme
eq      equation image
img     fallback when type cannot be inferred
```

The rename process should use caption text first, then nearby Markdown context. It must preserve an original-to-renamed mapping in the image index. If an old image is no longer referenced after regeneration, it should be reported as a cleanup candidate rather than deleted automatically.

## Field Ownership

Plugin-owned fields and sections may be updated:

```text
title
authors
year
doi
publicationTitle
abstract
zoteroKey
zoteroVersion
zoteroSelect
zoteroPdfKeys
zoteroPdfLinks
zoteroAttachmentPaths
attachments
attachmentLinks
mineruStatus
mineruExtractedAt
mineruMarkdown
mineruMarkdownLink
mineruImagesFolder
mineruImagesIndex
mineruImagesIndexLink
Abstract section
PDF section
Zotero Notes & Annotations section
MinerU Extraction section
```

User-owned fields and sections must be preserved:

```text
status
rating
priority
project
userTags
unknown custom YAML fields
Reading Notes section
AI Summary section
```

The plugin must not generate AI summaries. Skills may read the imported notes and write summaries separately.

## Tool Profiles

Add tool profiles:

```text
literature    default profile
full          all current tools
legacy        alias of full or a compatibility profile
```

The default profile should expose only the literature pipeline surface. Existing graph, wiki, Canvas, Bases, and broad CLI wrapper tools should remain available in `full` or `legacy`, but not in the default profile.

## Default Public Tools

Health and config:

```text
obsidian_pipeline_doctor
obsidian_pipeline_config
obsidian_pipeline_migrate_layout
```

Obsidian basic operations:

```text
obsidian_search
obsidian_read_file
obsidian_write_file
obsidian_update_properties
```

Zotero query operations:

```text
obsidian_zotero_ping
obsidian_zotero_search_items
obsidian_zotero_list_collections
obsidian_zotero_get_item
obsidian_zotero_get_children
obsidian_zotero_list_pdf_attachments
```

Pipeline operations:

```text
obsidian_pipeline_ingest_item
obsidian_pipeline_ingest_collection
obsidian_pipeline_parse_with_mineru
obsidian_pipeline_rename_mineru_images
```

High-level `obsidian_pipeline_*` tools are the main product API. Lower-level existing tools should remain callable in full mode for compatibility and debugging.

## Single-Item Workflow

Tool:

```text
obsidian_pipeline_ingest_item(zotero_key, parse_with_mineru=false)
```

Flow:

1. Read Zotero item, children, collections, and PDF attachments.
2. Create or update the literature note.
3. Copy PDF into the configured Zotero attachments folder.
4. Preserve Zotero original file paths and `zotero://` links.
5. Sync Zotero child notes and annotations.
6. If `parse_with_mineru=true`, parse the copied PDF with MinerU.
7. Write MinerU output under the configured MinerU attachments folder.
8. Rename MinerU images with English semantic slugs.
9. Generate or update the image index note.
10. Update the literature note MinerU fields and links.
11. Preserve user-owned fields and sections.
12. Return a structured report.

## Collection Workflow

Tool:

```text
obsidian_pipeline_ingest_collection(collection_key, parse_with_mineru=false)
```

Flow:

1. List all Zotero items in the collection.
2. Call the single-item pipeline for each item.
3. Continue after per-item failures.
4. If `parse_with_mineru=true`, re-parse every item and overwrite machine-generated MinerU assets.
5. Return a batch report.

Batch report should include:

```yaml
ok: true
total: 42
succeeded: 38
failed: 4
created: 10
updated: 28
mineruParsed: 35
mineruFailed: 3
imageRenamed: 34
imageRenameFailed: 1
results:
  - zoteroKey: ABCD1234
    title: Paper A
    literaturePath: literature/Smith 2024 - Paper A.md
    pdfPath: attachments/zotero/ABCD1234/paper-a.pdf
    mineruMarkdown: attachments/mineru/ABCD1234/paper.md
    status: parsed
  - zoteroKey: WXYZ5678
    title: Paper B
    status: failed
    stage: mineru_extract
    error: MinerU CLI failed.
```

## Re-Parse Workflow

Tool:

```text
obsidian_pipeline_parse_with_mineru(zotero_key or literature_path)
```

Flow:

1. Find the literature note.
2. Resolve the copied PDF or Zotero PDF attachment.
3. Run MinerU.
4. Overwrite `attachments/mineru/<zoteroKey>/paper.md`.
5. Regenerate image files and image index.
6. Update literature note MinerU fields.
7. Preserve user-owned literature note fields and sections.

MinerU assets are regenerable. Literature notes are stable user workspaces.

## Image Rename Workflow

Tool:

```text
obsidian_pipeline_rename_mineru_images(zotero_key or mineru_markdown_path)
```

Flow:

1. Read the MinerU Markdown.
2. Detect image references.
3. Extract captions and nearby context.
4. Generate English semantic filenames.
5. Move or rename images.
6. Rewrite Markdown image references.
7. Generate or update `images-index.md`.
8. Report cleanup candidates for obsolete files.

## Error Handling

Single-item behavior:

```text
Zotero unreachable        -> fail the item with a clear error
Item not found            -> fail the item
PDF missing               -> create or update literature note, set pdfStatus: missing
PDF copy failed           -> create or update literature note, record attachmentErrors
MinerU failed             -> keep literature note, set mineruStatus: failed and mineruError
Image rename failed       -> keep MinerU Markdown, set mineruImageRenameStatus: failed
```

Collection behavior:

- do not stop on per-item failure;
- record the failed stage and error;
- return success and failure counts;
- return per-item reports.

## Idempotency

Repeated runs for the same Zotero item must converge on the same paths:

```text
literature/<FirstAuthor Year - Short Title>.md
attachments/zotero/<zoteroKey>/<pdf-slug>.pdf
attachments/mineru/<zoteroKey>/paper.md
attachments/mineru/<zoteroKey>/images-index.md
attachments/mineru/<zoteroKey>/images/
```

Zotero metadata updates may refresh plugin-owned fields. MinerU re-parsing may overwrite machine-generated assets. User-owned fields and sections must survive repeated runs.

## Layout Migration

Tool:

```text
obsidian_pipeline_migrate_layout
```

Default:

```text
dry_run=true
```

The migration plan should include:

```text
plannedMoves
plannedYamlUpdates
plannedMarkdownLinkUpdates
warnings
```

Apply behavior:

1. Move plugin-managed PDFs, MinerU Markdown, images, and image indexes.
2. Update literature note YAML paths and wikilinks.
3. Update MinerU extraction note parent/source links.
4. Update image index parent/source links.
5. Only process files with recognized `type` and `zoteroKey`.
6. Do not move or rewrite unrelated user files.

Recognized types:

```text
literature
mineru-extraction
mineru-image-index
```

## Implementation Phases

Phase 1: Product positioning and tool surface

- add tool profiles;
- set default profile to `literature`;
- hide graph, wiki, Canvas, Bases, and most CLI wrappers from default registration;
- update README, technical guide, plugin manifests, and skill descriptions.

Phase 2: Pipeline data model

- add vault-local pipeline config;
- implement path planning from config;
- adopt `FirstAuthor Year - Short Title.md` literature filenames;
- place MinerU outputs under `attachments/mineru/<zoteroKey>/`;
- add jumpable YAML fields for PDF, Zotero, MinerU Markdown, and image index.

Phase 3: High-level pipeline tools

- implement `obsidian_pipeline_ingest_item`;
- implement `obsidian_pipeline_ingest_collection`;
- implement `obsidian_pipeline_parse_with_mineru`;
- implement `obsidian_pipeline_rename_mineru_images`;
- preserve field ownership and user-owned sections;
- return structured reports.

Phase 4: Migration and cleanup

- implement `obsidian_pipeline_migrate_layout`;
- support dry-run migration plans;
- update plugin-owned paths and wikilinks;
- report cleanup candidates;
- document legacy profile usage.

## Test Plan

Required tests:

- default tool profile exposes only literature pipeline tools;
- full profile exposes existing legacy tools;
- config defaults are applied when no config file exists;
- custom folder config changes planned output paths;
- single Zotero item ingest without MinerU creates or updates a literature note;
- single Zotero item ingest copies PDF while preserving Zotero source path and URI;
- single Zotero item ingest with MinerU creates `paper.md`, `images-index.md`, and renamed images;
- image rename produces English slug filenames and rewrites Markdown references;
- repeated ingest preserves user YAML fields and Reading Notes;
- repeated MinerU parse overwrites machine assets but preserves the literature note user content;
- collection ingest continues after failures and returns a full report;
- migration dry-run reports moves and YAML/link updates without writing;
- migration apply updates plugin-managed paths and links only.

## Success Criteria

The simplification is successful when:

- the default MCP tool surface clearly presents a Zotero-MinerU-Obsidian literature pipeline;
- a user can import a single Zotero item into a stable Obsidian literature note;
- a user can batch import a Zotero collection with per-item reporting;
- copied PDFs, Zotero links, MinerU Markdown, and image indexes are all jumpable from YAML or note body;
- MinerU images are renamed into portable English semantic filenames;
- user-owned reading notes and custom fields survive repeated updates;
- graph, wiki, Canvas, Bases, and broad CLI tools no longer compete for attention in the default profile.
