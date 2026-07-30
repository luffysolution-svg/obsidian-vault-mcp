from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from obsidian_vault_mcp.config import default_config, validate_config
from obsidian_vault_mcp.domain.errors import ConfigurationError, IdentityError, PathValidationError
from obsidian_vault_mcp.domain.identity import item_id, render_filename, sanitize_filename
from obsidian_vault_mcp.domain.paths import (
    VaultPaths,
    naming_metadata_from_fields,
    normalize_vault_relative,
    resolve_vault_path,
)


class IdentityAndPathTests(unittest.TestCase):
    def test_zotero_key_is_stable_storage_identity(self) -> None:
        self.assertEqual(item_id("ABCD1234"), "ABCD1234")
        first = render_filename(
            "{firstAuthor}-{year}-{shortTitle}-{zoteroKey}.md",
            zotero_key="ABCD1234",
            first_author="Smith",
            year=2024,
            short_title="Original title",
        )
        changed = render_filename(
            "{firstAuthor}-{year}-{shortTitle}-{zoteroKey}.md",
            zotero_key="ABCD1234",
            first_author="Smith",
            year=2024,
            short_title="Changed title",
        )
        self.assertNotEqual(first, changed)
        self.assertIn("ABCD1234", first)
        self.assertIn("ABCD1234", changed)

    def test_custom_pattern_must_include_complete_key(self) -> None:
        with self.assertRaises(IdentityError):
            render_filename("{shortTitle}.md", zotero_key="ABCD1234", short_title="Mutable")

    def test_note_fields_supply_all_configurable_naming_metadata(self) -> None:
        config = default_config()
        config["naming"]["mineruMarkdown"] = (
            "{firstAuthor}-{year}-{shortTitle}-{zoteroKey}.md"
        )
        paths = VaultPaths("C:/Vault", config)

        relative = paths.mineru_markdown(
            "ABCD1234",
            **naming_metadata_from_fields(
                {
                    "authors": [{"lastName": "Smith"}],
                    "year": 2024,
                    "title": "Custom title",
                }
            ),
        )

        self.assertEqual(
            relative,
            "Literature/attachment/MinerU/Smith-2024-Custom title-ABCD1234.md",
        )

    def test_filename_is_portable(self) -> None:
        self.assertEqual(sanitize_filename('A:B?C*D|E<test>".md'), "A-B-C-D-E-test-.md")
        self.assertEqual(sanitize_filename("CON.txt"), "_CON.txt")
        self.assertFalse(sanitize_filename("paper. ").endswith((".", " ")))

    def test_relative_paths_use_posix_and_reject_escape(self) -> None:
        self.assertEqual(normalize_vault_relative(r"Literature\中文 空格\A.md"), "Literature/中文 空格/A.md")
        for unsafe in ("../secret", "Literature/../../secret", "/absolute", r"C:\absolute", r"\\server\share"):
            with self.subTest(unsafe=unsafe), self.assertRaises(PathValidationError):
                normalize_vault_relative(unsafe)

    def test_resolution_remains_inside_vault(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            vault = Path(directory)
            resolved = resolve_vault_path(vault, "Literature/A.md")
            self.assertEqual(resolved, (vault / "Literature" / "A.md").resolve())
            self.assertTrue(resolved.is_relative_to(vault.resolve()))
            paths = VaultPaths(vault)
            self.assertEqual(paths.note("ABCD1234"), "Literature/ABCD1234.md")
            self.assertEqual(
                paths.mineru_image("ABCD1234", 1, "png"),
                "Literature/attachment/MinerU/image/ABCD1234/ABCD1234-fig01.png",
            )
            self.assertEqual(
                paths.mineru_image_folder("ABCD1234"),
                "Literature/attachment/MinerU/image/ABCD1234",
            )
            self.assertEqual(paths.analysis_base, "Literature/Analysis/Analysis.base")
            self.assertEqual(
                paths.analysis_folder("figure_qa"),
                "Literature/Analysis/qa/figures",
            )

    def test_config_is_strict_and_normalized(self) -> None:
        config = default_config()
        config["literature"]["root"] = r"Literature\Papers"
        validated = validate_config(config)
        self.assertEqual(validated["literature"]["root"], "Literature/Papers")
        config["unexpected"] = True
        with self.assertRaises(ConfigurationError):
            validate_config(config)

    def test_removed_v21_analysis_configuration_is_rejected(self) -> None:
        for field in ("index", "topicFolder", "theoryFolder", "templateFolder"):
            with self.subTest(field=field):
                config = default_config()
                config["analysis"][field] = "Literature/obsolete"
                with self.assertRaises(ConfigurationError):
                    validate_config(config)


if __name__ == "__main__":
    unittest.main()
