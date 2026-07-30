from __future__ import annotations

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
            raise unittest.SkipTest(
                f"could not create a Windows junction: {result.stderr or result.stdout}"
            )
        return
    link.symlink_to(target, target_is_directory=True)


def _remove_directory_link(link: Path) -> None:
    if os.name == "nt":
        os.rmdir(link)
    else:
        link.unlink(missing_ok=True)


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
            self.assertEqual(result.markdown.count("image/ABCD1234/ABCD1234-fig01.jpg"), 2)
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

    def test_rewrites_destinations_without_losing_image_syntax_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "images").mkdir()
            (root / "images" / "raw.png").write_bytes(b"image")
            (root / "paper.md").write_text(
                (
                    "# Raw\n\n"
                    '![inline](images/raw.png "Inline title")\n\n'
                    "![[images/raw.png|300]]\n\n"
                    "![shortcut]\n\n"
                    '[shortcut]: images/raw.png "Definition title"\n'
                ),
                encoding="utf-8",
            )

            result = normalize_mineru_output(
                root,
                zotero_key="ABCD1234",
                title="Normalized title",
                source_pdf_path="../ABCD1234.pdf",
            )

            target = "image/ABCD1234/ABCD1234-fig01.png"
            self.assertEqual(len(result.images), 1)
            self.assertIn(f'![inline]({target} "Inline title")', result.markdown)
            self.assertIn(f"![[{target}|300]]", result.markdown)
            self.assertIn("![shortcut]\n", result.markdown)
            self.assertIn(
                f'[shortcut]: {target} "Definition title"',
                result.markdown,
            )

    def test_missing_unsupported_absolute_and_url_images_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for destination in (
                "images/missing.png",
                "images/payload.exe",
                "C:/secret/image.png",
                "https://example.test/image.png",
                "data:image/png;base64,AAAA",
            ):
                (root / "paper.md").write_text(f"![bad]({destination})\n", encoding="utf-8")
                if destination.endswith("payload.exe"):
                    (root / "images").mkdir(exist_ok=True)
                    (root / "images" / "payload.exe").write_bytes(b"bad")
                with self.assertRaises(MinerUNormalizationError):
                    normalize_mineru_output(
                        root,
                        zotero_key="ABCD1234",
                        title="x",
                        source_pdf_path="../ABCD1234.pdf",
                        image_link_prefix="image/ABCD1234",
                    )

    def test_staging_root_cannot_be_a_symbolic_link_or_junction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            real = base / "real"
            real.mkdir()
            (real / "paper.md").write_text("# Paper\n", encoding="utf-8")
            linked = base / "linked"
            _create_directory_link(linked, real)
            try:
                with self.assertRaises(MinerUNormalizationError):
                    normalize_mineru_output(
                        linked,
                        zotero_key="ABCD1234",
                        title="x",
                        source_pdf_path="../ABCD1234.pdf",
                        image_link_prefix="image/ABCD1234",
                    )
            finally:
                _remove_directory_link(linked)


if __name__ == "__main__":
    unittest.main()
