from __future__ import annotations

import json
from pathlib import Path

from obsidian_vault_mcp.config import CONFIG_SCHEMA, default_config, validate_config
from obsidian_vault_mcp.config.defaults import SCHEMA_URL

ROOT = Path(__file__).resolve().parents[2]


def test_published_schema_matches_runtime_configuration_surface() -> None:
    published = json.loads((ROOT / "obsidian-vault-mcp.schema.json").read_text(encoding="utf-8"))
    defaults = default_config()

    assert published == CONFIG_SCHEMA
    assert published["$id"] == defaults["$schema"] == SCHEMA_URL
    assert "example.invalid" not in json.dumps(published)
    assert published["additionalProperties"] is False
    assert set(published["properties"]) == set(defaults)

    for section, values in defaults.items():
        if not isinstance(values, dict):
            continue
        section_schema = published["properties"][section]
        assert section_schema["type"] == "object"
        assert section_schema["additionalProperties"] is False
        assert section_schema["default"] == values
        assert set(section_schema["properties"]) == set(values)

    assert validate_config(defaults) == defaults


def test_published_schema_exposes_runtime_enums_and_numeric_bounds() -> None:
    properties = CONFIG_SCHEMA["properties"]

    assert properties["schemaVersion"]["const"] == 2
    assert properties["identity"]["properties"]["strategy"]["const"] == "zoteroKey"
    assert properties["attachments"]["properties"]["overwritePolicy"]["enum"] == [
        "always",
        "never",
        "if-source-changed",
    ]
    assert properties["bibtex"]["properties"]["provider"]["enum"] == [
        "auto",
        "better-bibtex",
        "zotero",
        "builtin",
    ]
    assert properties["mineru"]["properties"]["mode"]["enum"] == ["auto", "local", "api"]
    assert properties["zotero"]["properties"]["paginationSize"] == {
        "type": "integer",
        "minimum": 1,
        "maximum": 1000,
        "default": 100,
    }
    assert properties["mineru"]["properties"]["maxConcurrentJobs"] == {
        "type": "integer",
        "minimum": 1,
        "maximum": 64,
        "default": 2,
    }
    assert set(properties["analysis"]["properties"]) == {
        "folder",
        "base",
        "fullReadsFolder",
        "reviewsFolder",
        "passageQaFolder",
        "figureQaFolder",
        "conceptsFolder",
    }
    assert properties["zotero"]["properties"]["linkedAttachmentBaseDir"]["default"] == ""


def test_configuration_does_not_expose_removed_v21_state_or_template_fields() -> None:
    serialized = json.dumps(CONFIG_SCHEMA, ensure_ascii=False)

    for removed in (
        '"evidence"',
        '"coverage"',
        '"uncertainty"',
        '"topicFolder"',
        '"theoryFolder"',
        '"templateFolder"',
        '"customTemplate"',
        '"dimensions"',
        '"analysis.index"',
    ):
        assert removed not in serialized
