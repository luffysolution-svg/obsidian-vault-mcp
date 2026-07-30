from __future__ import annotations

import asyncio

from obsidian_vault_mcp.interfaces.mcp.server import create_server
from obsidian_vault_mcp.interfaces.mcp.tools import TOOL_FUNCTIONS

PRODUCTION_TOOLS = {
    "literature_version",
    "literature_doctor",
    "literature_config_get",
    "literature_config_validate",
    "literature_config_initialize",
    "zotero_ping",
    "zotero_search_items",
    "zotero_list_collections",
    "zotero_get_item",
    "zotero_get_children",
    "zotero_get_bibtex",
    "literature_import_item",
    "literature_import_collection",
    "literature_sync_item",
    "literature_sync_collection",
    "literature_parse_mineru",
    "literature_parse_mineru_batch",
    "literature_remove_mineru_output",
    "literature_rebuild_index",
    "literature_rebuild_base",
    "literature_verify",
    "literature_wiki_context",
    "literature_wiki_write",
    "literature_wiki_list",
    "literature_preview_transaction",
    "literature_rollback_transaction",
    "literature_paper_read",
    "literature_retrieve",
    "literature_analysis_get",
    "literature_analysis_write",
    "literature_rebuild_analysis_base",
}


def test_exact_production_tool_surface() -> None:
    actual = {function.__name__ for function in TOOL_FUNCTIONS}

    assert actual == PRODUCTION_TOOLS
    assert len(TOOL_FUNCTIONS) == 31
    assert all(function.__doc__ for function in TOOL_FUNCTIONS)
    assert not {name for name in actual if "migrat" in name}


def test_version_tool_reports_public_contract() -> None:
    by_name = {function.__name__: function for function in TOOL_FUNCTIONS}
    payload = by_name["literature_version"]()

    assert payload["version"] == "3.0.1"
    assert payload["mcpToolCount"] == 31
    assert payload["skillCount"] == 7
    assert payload["analysisTypes"] == ["full_read", "literature_review", "passage_qa", "figure_qa", "concept"]


def test_all_production_tools_have_precise_behavior_annotations() -> None:
    read_only = {
        "literature_version",
        "literature_doctor",
        "literature_config_get",
        "literature_config_validate",
        "zotero_ping",
        "zotero_search_items",
        "zotero_list_collections",
        "zotero_get_item",
        "zotero_get_children",
        "zotero_get_bibtex",
        "literature_verify",
        "literature_paper_read",
        "literature_retrieve",
        "literature_analysis_get",
        "literature_wiki_context",
        "literature_wiki_list",
        "literature_preview_transaction",
    }
    destructive = {
        "literature_remove_mineru_output",
        "literature_rollback_transaction",
    }

    tools = asyncio.run(create_server().list_tools())
    annotations = {tool.name: tool.annotations for tool in tools}

    assert len(annotations) == 31
    assert set(annotations) == PRODUCTION_TOOLS
    assert {name for name, value in annotations.items() if value and value.readOnlyHint} == read_only
    assert {name for name, value in annotations.items() if value and value.destructiveHint} == destructive
    assert {name for name, value in annotations.items() if value and value.idempotentHint} == read_only
    assert all(
        value
        and value.readOnlyHint is not None
        and value.destructiveHint is not None
        and value.idempotentHint is not None
        and value.openWorldHint is False
        for value in annotations.values()
    )
