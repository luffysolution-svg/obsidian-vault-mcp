from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from obsidian_vault_mcp.adapters.mineru.normalizer import (
    MinerUNormalizationError,
    normalize_mineru_output,
    relative_source_pdf,
)


class MinerUNormalizerTests(unittest.TestCase):
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
