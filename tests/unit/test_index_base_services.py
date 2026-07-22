from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from obsidian_vault_mcp.application.base_service import BaseService
from obsidian_vault_mcp.application.index_service import IndexService
from obsidian_vault_mcp.config.defaults import default_config
from obsidian_vault_mcp.config.loader import initialize_config


class IndexBaseServiceTests(unittest.TestCase):
    def test_rebuild_is_deterministic_in_unicode_vault(self) -> None:
        with tempfile.TemporaryDirectory(prefix="文献 Vault ") as directory:
            vault = Path(directory)
            (vault / ".obsidian").mkdir()
            initialize_config(vault)
            literature = vault / "Literature"
            literature.mkdir()
            (literature / "BBBB2222.md").write_text(
                "---\ntitle: Beta\nyear: 2023\nzoteroKey: BBBB2222\n---\n\n# Beta\n",
                encoding="utf-8",
            )
            (literature / "AAAA1111.md").write_text(
                "---\ntitle: Alpha\nyear: 2024\ndoi: 10.1/alpha\nzoteroKey: AAAA1111\n---\n\n# Alpha\n",
                encoding="utf-8",
            )
            index = IndexService(vault)
            base = BaseService(vault)
            first_index = index.rebuild()
            first_base = base.rebuild()
            index_bytes = (literature / "index.md").read_bytes()
            base_bytes = (literature / "Literature.base").read_bytes()
            second_index = index.rebuild()
            second_base = base.rebuild()
            self.assertEqual((literature / "index.md").read_bytes(), index_bytes)
            self.assertEqual((literature / "Literature.base").read_bytes(), base_bytes)
            self.assertEqual(first_index["status"], "committed")
            self.assertEqual(first_base["status"], "committed")
            self.assertEqual(second_index["status"], "noop")
            self.assertEqual(second_base["status"], "noop")

    def test_index_service_threads_the_configured_wiki_folder_to_renderer(self) -> None:
        with tempfile.TemporaryDirectory(prefix="自定义 Wiki ") as directory:
            vault = Path(directory)
            (vault / ".obsidian").mkdir()
            config = default_config()
            config["literature"]["wikiFolder"] = "Knowledge/Topics"
            topics = vault / "Knowledge" / "Topics"
            topics.mkdir(parents=True)
            (topics / "Catalysis.md").write_text("# Catalysis\n", encoding="utf-8")

            rendered = IndexService(vault, config).render()

            self.assertIn("[[Knowledge/Topics/Catalysis]]", rendered)


if __name__ == "__main__":
    unittest.main()
