from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from obsidian_vault_mcp.application.evidence_service import EvidenceService
from obsidian_vault_mcp.application.paper_read_service import PaperReadService
from obsidian_vault_mcp.config.defaults import default_config
from obsidian_vault_mcp.domain.errors import PathValidationError
from obsidian_vault_mcp.domain.evidence import (
    EvidenceChunk,
    evidence_block_id_counts,
    materialize_evidence_block_ids,
    parse_evidence_markdown,
)
from obsidian_vault_mcp.domain.frontmatter import compose_frontmatter

KEY = "ABCD1234"
SOURCE_PATH = f"Literature/attachment/MinerU/{KEY}.md"
REFERENCED_IMAGE = b"image"
CANDIDATE_IMAGE = b"candidate"
REFERENCED_SHA = hashlib.sha256(REFERENCED_IMAGE).hexdigest()
CANDIDATE_SHA = hashlib.sha256(CANDIDATE_IMAGE).hexdigest()
REFERENCED_ASSET_ID = f"IMG-{KEY}-{REFERENCED_SHA[:12]}"
CANDIDATE_ASSET_ID = f"IMG-{KEY}-{CANDIDATE_SHA[:12]}"


class EvidenceDomainTests(unittest.TestCase):
    def test_long_text_uses_configured_bounded_overlapping_chunks(self) -> None:
        text = " ".join(f"token-{index}" for index in range(180))
        result = parse_evidence_markdown(
            f"# Results\n\n{text}\n",
            zotero_key=KEY,
            source_path=f"Literature/attachment/MinerU/{KEY}.md",
            max_chunk_chars=300,
            overlap_chars=40,
            block_id_prefix="source",
        )

        paragraphs = [chunk for chunk in result.chunks if chunk.content_type == "paragraph"]
        self.assertGreater(len(paragraphs), 1)
        self.assertTrue(all(len(chunk.text) <= 300 for chunk in paragraphs))
        self.assertTrue(all(chunk.block_id.startswith("source-") for chunk in paragraphs))
        self.assertIn("evidence-block-split", {warning["code"] for warning in result.warnings})

    def test_materializes_physical_block_ids_idempotently_for_every_chunk(self) -> None:
        text = " ".join(f"token-{index}" for index in range(180))
        markdown = compose_frontmatter(
            {"title": "Paper", "zoteroKey": KEY},
            (
                "# Results\n\n"
                f"{text}\n\n"
                "- first\n- second\n\n"
                "| Catalyst | Rate |\n|---|---:|\n| CdS | 12 |\n\n"
                "Existing source. ^source-existing\n"
            ),
        )

        materialized, warnings = materialize_evidence_block_ids(
            markdown,
            zotero_key=KEY,
            source_path=SOURCE_PATH,
            block_id_prefix="source",
        )
        repeated, repeated_warnings = materialize_evidence_block_ids(
            materialized,
            zotero_key=KEY,
            source_path=SOURCE_PATH,
            block_id_prefix="source",
        )
        parsed = parse_evidence_markdown(
            materialized,
            zotero_key=KEY,
            source_path=SOURCE_PATH,
            block_id_prefix="source",
            max_chunk_chars=300,
            overlap_chars=40,
        )
        counts = evidence_block_id_counts(materialized)

        self.assertEqual(materialized, repeated)
        self.assertEqual(warnings, ())
        self.assertEqual(repeated_warnings, ())
        self.assertTrue(all(counts.get(chunk.block_id) == 1 for chunk in parsed.chunks))
        paragraphs = [chunk for chunk in parsed.chunks if chunk.content_type == "paragraph" and "token-" in chunk.text]
        self.assertGreater(len(paragraphs), 1)
        self.assertEqual(len({chunk.block_id for chunk in paragraphs}), 1)
        self.assertEqual(len({chunk.evidence_id for chunk in paragraphs}), len(paragraphs))

    def test_parses_structured_blocks_stable_ids_and_duplicate_block_ids(self) -> None:
        markdown = compose_frontmatter(
            {"title": "Paper", "zoteroKey": KEY, "sourcePdf": f"../{KEY}.pdf"},
            (
                "# Results\n\n"
                "## 光催化性能\n\n"
                "Stable paragraph. ^stable-block\n\n"
                "Another paragraph. ^stable-block\n\n"
                "- first item\n"
                "- second item\n\n"
                "| Catalyst | Rate |\n"
                "|---|---:|\n"
                "| CdS | 12 |\n\n"
                "Figure 1. Hydrogen evolution.\n\n"
                "$$\nE = mc^2\n$$\n\n"
                "## References\n\n"
                "Smith et al. 2024.\n"
            ),
        )

        first = parse_evidence_markdown(markdown, zotero_key=KEY, source_path=SOURCE_PATH)
        second = parse_evidence_markdown(markdown, zotero_key=KEY, source_path=SOURCE_PATH)

        self.assertEqual([chunk.as_dict() for chunk in first.chunks], [chunk.as_dict() for chunk in second.chunks])
        self.assertEqual(
            {chunk.content_type for chunk in first.chunks},
            {"heading", "paragraph", "list", "table", "caption", "equation", "reference"},
        )
        chinese = next(chunk for chunk in first.chunks if chunk.text == "光催化性能")
        self.assertEqual(chinese.section_path, ("Results", "光催化性能"))
        stable = next(chunk for chunk in first.chunks if chunk.text == "Stable paragraph.")
        duplicate = next(chunk for chunk in first.chunks if chunk.text == "Another paragraph.")
        self.assertEqual(stable.block_id, "stable-block")
        self.assertTrue(duplicate.block_id.startswith("ev-"))
        self.assertEqual([warning["code"] for warning in first.warnings], ["duplicate-block-id"])
        self.assertTrue(all(chunk.page is None for chunk in first.chunks))
        self.assertEqual(len({chunk.evidence_id for chunk in first.chunks}), len(first.chunks))
        self.assertIn("- second item", next(chunk.text for chunk in first.chunks if chunk.content_type == "list"))

    def test_content_hash_changes_but_existing_block_identity_remains_stable(self) -> None:
        before = parse_evidence_markdown(
            "# Results\n\nActivity was 12. ^result-one\n",
            zotero_key=KEY,
            source_path=SOURCE_PATH,
        ).chunks[-1]
        after = parse_evidence_markdown(
            "# Results\n\nActivity was 15. ^result-one\n",
            zotero_key=KEY,
            source_path=SOURCE_PATH,
        ).chunks[-1]

        self.assertEqual(before.evidence_id, after.evidence_id)
        self.assertEqual(before.source_fingerprint, after.source_fingerprint)
        self.assertNotEqual(before.content_hash, after.content_hash)

    def test_caption_links_to_manifest_asset_without_guessing_page(self) -> None:
        asset_id = f"IMG-{KEY}-a31f82"
        manifest = {
            "assets": [
                {
                    "assetId": asset_id,
                    "normalizedPath": f"Literature/attachment/MinerU/image/{KEY}-fig01.png",
                    "references": [{"syntax": "markdown", "alt": "Figure 2. Activity"}],
                }
            ]
        }
        result = parse_evidence_markdown(
            f"# Results\n\n![Figure 2. Activity](image/{KEY}-fig01.png)\n",
            zotero_key=KEY,
            source_path=SOURCE_PATH,
            asset_manifest=manifest,
        )
        caption = next(chunk for chunk in result.chunks if chunk.content_type == "caption")

        self.assertEqual(caption.text, "Figure 2. Activity")
        self.assertEqual(caption.related_asset_ids, (asset_id,))
        self.assertIsNone(caption.page)
        self.assertEqual(EvidenceChunk.from_dict(caption.as_dict()), caption)

    def test_rejects_unsafe_source_path(self) -> None:
        with self.assertRaises(PathValidationError):
            parse_evidence_markdown("Text", zotero_key=KEY, source_path=r"C:\Vault\paper.md")


class EvidenceServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.vault = Path(self.temporary.name)
        self.config = default_config()
        _write_paper(self.vault)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_rebuild_load_noop_dry_run_and_rollback(self) -> None:
        service = EvidenceService(self.vault, self.config)
        first = service.rebuild(KEY, transaction_id="evidence-first", generated_at="2026-07-29T00:00:00Z")
        state_path = self.vault / ".obsidian-vault-mcp" / "state" / "evidence" / f"{KEY}.json"
        first_text = state_path.read_text(encoding="utf-8")
        loaded = service.load(KEY)

        self.assertEqual(first["status"], "committed")
        self.assertFalse(loaded["stale"])
        self.assertGreater(len(loaded["chunks"]), 5)
        self.assertEqual(loaded["generatedAt"], "2026-07-29T00:00:00Z")
        source_path = self.vault / Path(SOURCE_PATH)
        block_counts = evidence_block_id_counts(source_path.read_text(encoding="utf-8"))
        self.assertTrue(all(block_counts.get(chunk["blockId"]) == 1 for chunk in loaded["chunks"]))
        manifest_path = self.vault / ".obsidian-vault-mcp" / "cache" / "mineru-assets" / KEY / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["sourceMarkdownSha256"], hashlib.sha256(source_path.read_bytes()).hexdigest())

        noop = service.rebuild(KEY, transaction_id="evidence-noop", generated_at="2030-01-01T00:00:00Z")
        self.assertEqual(noop["status"], "noop")
        self.assertEqual(state_path.read_text(encoding="utf-8"), first_text)

        source = source_path
        source.write_text(source.read_text(encoding="utf-8").replace("析氢速率 is 12", "析氢速率 is 15"), encoding="utf-8")
        preview = service.rebuild(KEY, dry_run=True, transaction_id="evidence-preview", generated_at="2026-07-30T00:00:00Z")
        self.assertEqual(preview["status"], "dry-run")
        self.assertEqual(state_path.read_text(encoding="utf-8"), first_text)

        changed = service.rebuild(KEY, transaction_id="evidence-change", generated_at="2026-07-30T00:00:00Z")
        self.assertEqual(changed["status"], "committed")
        self.assertNotEqual(state_path.read_text(encoding="utf-8"), first_text)
        rolled_back = service.rollback("evidence-change")
        self.assertEqual(rolled_back["status"], "rolled-back")
        self.assertEqual(state_path.read_text(encoding="utf-8"), first_text)
        self.assertTrue(service.load(KEY)["stale"])


class PaperReadServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.vault = Path(self.temporary.name)
        self.config = default_config()
        _write_paper(self.vault)
        self.service = PaperReadService(self.vault, self.config)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_overview_is_section_aware_and_never_claims_full_coverage(self) -> None:
        result = self.service.read(KEY, mode="overview", max_chars=2_000)

        self.assertTrue(result["ok"])
        self.assertFalse(result["coverage"]["complete"])
        self.assertEqual(result["coverage"]["status"], "overview")
        self.assertIn("introduction", result["overview"])
        self.assertIn("methods", result["overview"])
        self.assertIn("results", result["overview"])
        self.assertIn("conclusion", result["overview"])
        self.assertNotIn("section:introduction", result["missing"])
        self.assertTrue(all(passage["page"] is None for passage in result["passages"]))

    def test_targeted_uses_variants_only_for_recall_and_honors_top_k(self) -> None:
        result = self.service.read(
            KEY,
            mode="targeted",
            query="quantum efficiency",
            query_variants=["析氢速率"],
            top_k=1,
            max_chars=1_000,
        )

        self.assertEqual(len(result["passages"]), 1)
        self.assertIn("析氢速率", result["passages"][0]["text"])
        self.assertNotIn("quantum efficiency", result["passages"][0]["text"].casefold())
        self.assertGreater(result["passages"][0]["score"], 0)
        self.assertEqual(result["queryVariantsUsedForRecall"], ["析氢速率"])

        empty = self.service.read(KEY, mode="targeted", query="", query_variants=["析氢速率"])
        self.assertEqual(empty["passages"], [])
        self.assertIn("empty-query", {warning["code"] for warning in empty["warnings"]})

    def test_sections_reports_unmatched_and_excludes_unrelated_sections(self) -> None:
        result = self.service.read(KEY, mode="sections", sections=["Methods", "不存在"], max_chars=1_000)

        self.assertEqual(result["unmatchedSections"], ["不存在"])
        self.assertTrue(result["passages"])
        self.assertTrue(all("Methods" in passage["sectionPath"] for passage in result["passages"]))
        self.assertNotIn("Conclusion text", " ".join(passage["text"] for passage in result["passages"]))

    def test_full_explicitly_reports_partial_when_budget_truncates(self) -> None:
        result = self.service.read(KEY, mode="full", max_chars=40)

        self.assertEqual(result["coverage"]["status"], "partial")
        self.assertFalse(result["coverage"]["complete"])
        self.assertTrue(result["coverage"]["truncated"])
        self.assertLessEqual(result["budget"]["usedChars"], 40)
        self.assertTrue(result["coverage"]["unreadSections"])

    def test_figures_distinguishes_assets_prefers_table_text_and_never_claims_visual_verification(self) -> None:
        result = self.service.read(KEY, mode="figures", include_images=True, max_chars=2_000)
        by_id = {figure["assetId"]: figure for figure in result["figures"]}
        referenced = by_id[REFERENCED_ASSET_ID]
        candidate = by_id[CANDIDATE_ASSET_ID]

        self.assertEqual(referenced["status"], "referenced")
        self.assertEqual(referenced["visualStatus"], "referenced")
        self.assertEqual(referenced["figureLabel"], "Figure 3")
        self.assertIsNotNone(referenced["captionEvidenceId"])
        self.assertIsNone(referenced["page"])
        self.assertEqual(candidate["status"], "unlinked_candidate")
        self.assertEqual(candidate["visualStatus"], "mineru_candidate")
        self.assertIsNone(candidate["figureLabel"])
        self.assertFalse(result["binaryImagesEmbedded"])
        self.assertTrue(result["tables"])
        self.assertIn("| Catalyst | Rate |", result["tables"][0]["text"])
        self.assertNotIn("visual_verified", {figure["visualStatus"] for figure in result["figures"]})

    def test_optional_coverage_recording_supports_dry_run_and_commit(self) -> None:
        ledger = self.vault / ".obsidian-vault-mcp" / "state" / "coverage" / f"{KEY}.json"
        preview = self.service.read(
            KEY,
            mode="targeted",
            query="析氢速率",
            record_coverage=True,
            coverage_dry_run=True,
            coverage_transaction_id="paper-coverage-preview",
        )
        self.assertEqual(preview["coverageLedger"]["status"], "dry-run")
        self.assertFalse(ledger.exists())

        committed = self.service.read(
            KEY,
            mode="targeted",
            query="析氢速率",
            record_coverage=True,
            coverage_transaction_id="paper-coverage-write",
        )
        self.assertEqual(committed["coverageLedger"]["status"], "committed")
        self.assertTrue(ledger.is_file())

    def test_missing_mineru_and_metadata_fallback_are_structured_not_invented(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            vault = Path(directory)
            note = vault / "Literature" / f"{KEY}.md"
            note.parent.mkdir(parents=True)
            note.write_text(compose_frontmatter({"title": "Metadata Only", "zoteroKey": KEY}, "# Metadata Only\n"), encoding="utf-8")

            result = PaperReadService(vault, self.config).read(KEY, mode="full", max_chars=100)

        self.assertEqual(result["metadata"]["title"], "Metadata Only")
        self.assertEqual(result["coverage"]["status"], "unreadable")
        self.assertEqual(result["passages"], [])
        self.assertIn("mineru", result["missing"])
        self.assertIn("pdf", result["missing"])
        self.assertIn("abstract", result["missing"])


def _write_paper(vault: Path) -> None:
    main_note = vault / "Literature" / f"{KEY}.md"
    source = vault / Path(SOURCE_PATH)
    pdf = vault / "Literature" / "attachment" / f"{KEY}.pdf"
    state = vault / ".obsidian-vault-mcp" / "state" / "items" / f"{KEY}.json"
    manifest = vault / ".obsidian-vault-mcp" / "cache" / "mineru-assets" / KEY / "manifest.json"
    image = vault / "Literature" / "attachment" / "MinerU" / "image" / f"{KEY}-fig01.png"
    candidate = manifest.parent / "assets" / f"{CANDIDATE_ASSET_ID}.png"
    for path in (main_note, source, pdf, state, manifest, image, candidate):
        path.parent.mkdir(parents=True, exist_ok=True)
    pdf.write_bytes(b"PDF")
    image.write_bytes(REFERENCED_IMAGE)
    candidate.write_bytes(CANDIDATE_IMAGE)
    main_note.write_text(
        compose_frontmatter(
            {
                "title": "Photocatalytic Hydrogen Evolution",
                "itemType": "journalArticle",
                "year": 2025,
                "journal": "Catalysis Letters",
                "tags": ["photocatalysis"],
                "abstract": "An abstract supplied by Zotero.",
                "zoteroKey": KEY,
                "attachmentPdfLink": f"[[Literature/attachment/{KEY}.pdf]]",
                "attachmentMinerULink": f"[[Literature/attachment/MinerU/{KEY}]]",
            },
            "# Photocatalytic Hydrogen Evolution\n\n## Reading Notes\n",
        ),
        encoding="utf-8",
    )
    source.write_text(
        compose_frontmatter(
            {"title": "Photocatalytic Hydrogen Evolution", "zoteroKey": KEY, "sourcePdf": f"../{KEY}.pdf"},
            (
                "# Photocatalytic Hydrogen Evolution\n\n"
                "## Introduction\n\n"
                "The introduction describes photocatalysis.\n\n"
                "## Methods\n\n"
                "Catalysts were prepared hydrothermally.\n\n"
                "## Results and Discussion\n\n"
                "The 析氢速率 is 12 under visible light. ^result-rate\n\n"
                "| Catalyst | Rate |\n"
                "|---|---:|\n"
                "| CdS | 12 |\n\n"
                f"![Figure 3. Activity under visible light](image/{KEY}-fig01.png)\n\n"
                "## Conclusion\n\n"
                "Conclusion text reports improved activity.\n"
            ),
        ),
        encoding="utf-8",
    )
    state.write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "zoteroKey": KEY,
                "notePath": f"Literature/{KEY}.md",
                "pdfPath": f"Literature/attachment/{KEY}.pdf",
                "mineruPath": SOURCE_PATH,
                "status": "ready",
                "errors": [],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    manifest.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "zoteroKey": KEY,
                "sourceMarkdown": SOURCE_PATH,
                "sourceMarkdownSha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "generatedAt": "2026-07-29T00:00:00Z",
                "assets": [
                    {
                        "assetId": REFERENCED_ASSET_ID,
                        "zoteroKey": KEY,
                        "sourceRelativePath": "images/figure.png",
                        "status": "referenced",
                        "extension": "png",
                        "sourceRelativePaths": ["images/figure.png"],
                        "sizeBytes": len(REFERENCED_IMAGE),
                        "sha256": REFERENCED_SHA,
                        "normalizedPath": f"Literature/attachment/MinerU/image/{KEY}-fig01.png",
                        "cachePath": None,
                        "references": [
                            {
                                "syntax": "markdown",
                                "alt": "Figure 3. Activity under visible light",
                                "sourceOffset": 100,
                                "sourceRelativePath": "images/figure.png",
                            }
                        ],
                        "captionEvidenceId": None,
                        "contextEvidenceIds": [],
                        "figureLabel": None,
                        "page": None,
                        "visualStatus": "referenced",
                        "pdfCropPath": None,
                    },
                    {
                        "assetId": CANDIDATE_ASSET_ID,
                        "zoteroKey": KEY,
                        "sourceRelativePath": "images/crop.png",
                        "status": "unlinked_candidate",
                        "extension": "png",
                        "sourceRelativePaths": ["images/crop.png"],
                        "sizeBytes": len(CANDIDATE_IMAGE),
                        "sha256": CANDIDATE_SHA,
                        "normalizedPath": None,
                        "cachePath": f".obsidian-vault-mcp/cache/mineru-assets/{KEY}/assets/{CANDIDATE_ASSET_ID}.png",
                        "references": [],
                        "captionEvidenceId": None,
                        "contextEvidenceIds": [],
                        "figureLabel": None,
                        "page": None,
                        "visualStatus": "mineru_candidate",
                        "pdfCropPath": None,
                    },
                ],
                "counts": {"total": 2, "referenced": 1, "unlinkedCandidates": 1, "invalid": 0},
                "warnings": [],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    unittest.main()
