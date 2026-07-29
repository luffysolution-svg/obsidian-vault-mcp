from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from obsidian_vault_mcp.adapters.mineru.normalizer import (
    MinerUNormalizationError,
    normalize_mineru_output,
    relative_source_pdf,
)


def _create_directory_link(link: Path, target: Path) -> None:
    if os.name == "nt":
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            raise unittest.SkipTest(f"could not create a Windows junction: {result.stderr or result.stdout}")
        return
    link.symlink_to(target, target_is_directory=True)


def _remove_directory_link(link: Path) -> None:
    if os.name == "nt":
        os.rmdir(link)
    else:
        link.unlink(missing_ok=True)


class MinerUNormalizerTests(unittest.TestCase):
    def test_staging_root_cannot_be_a_symbolic_link_or_junction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            outside = base / "outside"
            outside.mkdir()
            (outside / "paper.md").write_text("# Outside\n\nSecret text.\n", encoding="utf-8")
            staging = base / "staging-link"
            _create_directory_link(staging, outside)
            try:
                with self.assertRaisesRegex(MinerUNormalizationError, "symbolic link or reparse point"):
                    normalize_mineru_output(
                        staging,
                        zotero_key="ABCD1234",
                        title="x",
                        source_pdf_path="../ABCD1234.pdf",
                    )
            finally:
                _remove_directory_link(staging)

    def test_images_follow_first_appearance_and_paths_are_relative(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "raw" / "images").mkdir(parents=True)
            (root / "raw" / "images" / "z.jpg").write_bytes(b"z")
            (root / "raw" / "images" / "a.png").write_bytes(b"a")
            (root / "raw" / "paper.md").write_text(
                "---\nsource: C:/secret/paper.pdf\n---\n\n# Raw\n\n"
                "![first](images/z.jpg)\n\n![second](images/a.png)\n\n![again](images/z.jpg)\n",
                encoding="utf-8",
            )
            result = normalize_mineru_output(
                root,
                zotero_key="ABCD1234",
                title="Normalized title",
                source_pdf_path="../ABCD1234.pdf",
            )
            self.assertEqual([image.filename for image in result.images], ["ABCD1234-fig01.jpg", "ABCD1234-fig02.png"])
            self.assertEqual(result.images[0].content, b"z")
            self.assertEqual(result.markdown.count("image/ABCD1234-fig01.jpg"), 2)
            self.assertNotIn("C:/secret", result.markdown)
            self.assertIn("sourcePdf: ../ABCD1234.pdf", result.markdown)

    def test_traversal_image_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "paper.md").write_text("![bad](../outside.png)\n", encoding="utf-8")
            with self.assertRaises(MinerUNormalizationError):
                normalize_mineru_output(root, zotero_key="ABCD1234", title="x", source_pdf_path="../ABCD1234.pdf")

    def test_scans_referenced_and_unlinked_assets_with_stable_content_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            images = root / "raw" / "images"
            images.mkdir(parents=True)
            (images / "chart(1).png").write_bytes(b"chart")
            (images / "图 表.svg").write_bytes(b"<svg />")
            (images / "candidate.webp").write_bytes(b"candidate")
            (root / "raw" / "paper.md").write_text(
                "# Raw\n\n![nested](images/chart(1).png)\n\n"
                "![[images/图 表.svg]]\n\n![again](images/chart(1).png)\n",
                encoding="utf-8",
            )

            kwargs = {
                "zotero_key": "ABCD1234",
                "title": "Normalized",
                "source_pdf_path": "../ABCD1234.pdf",
                "output_markdown_path": "Literature/attachment/MinerU/ABCD1234.md",
                "normalized_image_folder": "Literature/attachment/MinerU/image",
                "candidate_cache_folder": ".obsidian-vault-mcp/cache/mineru-assets/ABCD1234/assets",
            }
            first = normalize_mineru_output(root, **kwargs)
            second = normalize_mineru_output(root, **kwargs)

            self.assertEqual(len(first.images), 2)
            self.assertEqual(len(first.candidate_images), 1)
            self.assertIn("image/ABCD1234-fig01.png", first.markdown)
            self.assertIn("image/ABCD1234-fig02.svg", first.markdown)
            assets = first.manifest.as_dict()["assets"]
            self.assertEqual([asset["status"] for asset in assets], ["referenced", "referenced", "unlinked_candidate"])
            self.assertEqual(first.manifest.as_dict(), second.manifest.as_dict())
            self.assertEqual(assets[0]["sha256"], hashlib.sha256(b"chart").hexdigest())
            self.assertEqual(assets[0]["assetId"], f"IMG-ABCD1234-{hashlib.sha256(b'chart').hexdigest()[:12]}")
            self.assertEqual(len(assets[0]["references"]), 2)
            self.assertTrue(assets[2]["cachePath"].endswith(f"{assets[2]['assetId']}.webp"))

    def test_same_content_at_different_paths_is_deduplicated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a").mkdir()
            (root / "b").mkdir()
            (root / "a" / "same.png").write_bytes(b"same")
            (root / "b" / "same.png").write_bytes(b"same")
            (root / "paper.md").write_text(
                "![a](a/same.png)\n![b](b/same.png)\n",
                encoding="utf-8",
            )

            result = normalize_mineru_output(
                root,
                zotero_key="ABCD1234",
                title="x",
                source_pdf_path="../ABCD1234.pdf",
            )

            self.assertEqual(len(result.images), 1)
            self.assertEqual(result.markdown.count("image/ABCD1234-fig01.png"), 2)
            asset = result.manifest.as_dict()["assets"][0]
            self.assertEqual(asset["sourceRelativePaths"], ["a/same.png", "b/same.png"])

    def test_reference_style_is_supported_and_html_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "images").mkdir()
            (root / "images" / "a.png").write_bytes(b"a")
            (root / "images" / "html.png").write_bytes(b"html")
            (root / "paper.md").write_text(
                "![figure][fig1]\n\n[fig1]: images/a.png\n\n<img src=\"images/html.png\">\n",
                encoding="utf-8",
            )

            result = normalize_mineru_output(
                root,
                zotero_key="ABCD1234",
                title="x",
                source_pdf_path="../ABCD1234.pdf",
            )

            self.assertIn("![figure](image/ABCD1234-fig01.png)", result.markdown)
            self.assertEqual(result.manifest.counts["referenced"], 1)
            self.assertEqual(result.manifest.counts["unlinkedCandidates"], 1)
            self.assertEqual([warning["code"] for warning in result.manifest.warnings], ["unsupported-image-syntax"])

    def test_unsafe_missing_and_unsupported_references_are_rejected(self) -> None:
        cases = (
            "![bad](/tmp/a.png)",
            "![bad](C:/secret/a.png)",
            "![bad](file:///tmp/a.png)",
            "![bad](https://example.test/a.png)",
            "![bad](missing.png)",
            "![bad](data.txt)",
        )
        for markdown in cases:
            with self.subTest(markdown=markdown), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "data.txt").write_text("not an image", encoding="utf-8")
                (root / "paper.md").write_text(markdown, encoding="utf-8")
                with self.assertRaises(MinerUNormalizationError):
                    normalize_mineru_output(
                        root,
                        zotero_key="ABCD1234",
                        title="x",
                        source_pdf_path="../ABCD1234.pdf",
                    )

    def test_empty_supported_candidate_is_invalid_and_no_image_output_is_supported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "images").mkdir()
            (root / "images" / "empty.bmp").write_bytes(b"")
            (root / "paper.md").write_text("# Paper\n\nNo linked images.\n", encoding="utf-8")

            result = normalize_mineru_output(
                root,
                zotero_key="ABCD1234",
                title="x",
                source_pdf_path="../ABCD1234.pdf",
            )

            self.assertEqual(result.images, ())
            self.assertEqual(result.candidate_images, ())
            self.assertEqual(result.manifest.counts, {"total": 1, "referenced": 0, "unlinkedCandidates": 0, "invalid": 1})
            self.assertEqual(result.manifest.warnings[0]["code"], "invalid-unlinked-image")

    def test_relative_pdf_path_is_portable(self) -> None:
        self.assertEqual(
            relative_source_pdf(
                "Literature/attachment/MinerU/ABCD1234.md",
                "Literature/attachment/ABCD1234.pdf",
            ),
            "../ABCD1234.pdf",
        )


if __name__ == "__main__":
    unittest.main()
