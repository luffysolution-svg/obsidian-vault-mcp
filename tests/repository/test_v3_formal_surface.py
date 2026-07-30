from __future__ import annotations

import json
from pathlib import Path

from obsidian_vault_mcp.config import CONFIG_SCHEMA, default_config
from obsidian_vault_mcp.interfaces.mcp.tools import TOOL_BY_NAME

ROOT = Path(__file__).resolve().parents[2]


def test_migration_implementations_are_absent_from_the_formal_release() -> None:
    removed_paths = (
        "src/obsidian_vault_mcp/application/migration_service.py",
        "src/obsidian_vault_mcp/application/analysis_migration_service.py",
        "src/obsidian_vault_mcp/application/mineru_image_migration_service.py",
        "tests/unit/test_migration_service.py",
        "tests/unit/test_analysis_migration_v3.py",
        "tests/unit/test_mineru_image_migration_v3.py",
    )

    for relative_path in removed_paths:
        assert not (ROOT / relative_path).exists(), relative_path


def test_public_configuration_contains_no_migration_only_setting() -> None:
    defaults = default_config()
    published = json.loads((ROOT / "obsidian-vault-mcp.schema.json").read_text(encoding="utf-8"))

    assert "defaultDryRunForMigration" not in defaults["safety"]
    assert "defaultDryRunForMigration" not in CONFIG_SCHEMA["properties"]["safety"]["properties"]
    assert "defaultDryRunForMigration" not in published["properties"]["safety"]["properties"]
    assert published == CONFIG_SCHEMA


def test_public_tool_surface_has_no_migration_entry() -> None:
    assert len(TOOL_BY_NAME) == 31
    assert "literature_version" in TOOL_BY_NAME
    assert not any("migrat" in name.casefold() for name in TOOL_BY_NAME)


def test_current_product_docs_do_not_present_legacy_install_or_migration_paths() -> None:
    current_docs = (
        "README.md",
        "README.en.md",
        "docs/index.md",
        "docs/index.en.md",
        "DEVELOPMENT.md",
        "DEVELOPMENT.en.md",
        "AGENTS.md",
        "CLAUDE.md",
    )
    forbidden = (
        "defaultDryRunForMigration",
        "migrate-v1-to-v2",
        "mineru migrate-images",
        "analysis migrate",
    )

    for relative_path in current_docs:
        text = (ROOT / relative_path).read_text(encoding="utf-8")
        for term in forbidden:
            assert term not in text, f"{term!r} remains in {relative_path}"
