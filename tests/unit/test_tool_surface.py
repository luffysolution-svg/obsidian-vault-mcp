from __future__ import annotations

import asyncio

from obsidian_vault_mcp.interfaces.mcp.server import create_server
from obsidian_vault_mcp.interfaces.mcp.tools import TOOL_FUNCTIONS

CORE_V2_TOOLS = {
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
    "literature_migrate_v1_to_v2",
    "literature_preview_transaction",
    "literature_rollback_transaction",
}
ANALYSIS_V3_TOOLS = {
    "literature_paper_read",
    "literature_retrieve",
    "literature_analysis_get",
    "literature_analysis_write",
    "literature_rebuild_analysis_base",
}


def test_exact_v3_tool_surface() -> None:
    actual = {function.__name__ for function in TOOL_FUNCTIONS}

    assert actual == CORE_V2_TOOLS | ANALYSIS_V3_TOOLS
    assert len(TOOL_FUNCTIONS) == 31
    assert all(function.__doc__ for function in TOOL_FUNCTIONS)
    assert not {
        "literature_analysis_context",
        "literature_uncertainty_list",
        "literature_uncertainty_resolve",
        "literature_rebuild_analysis_index",
    }.intersection(actual)


def test_all_v3_tools_have_precise_behavior_annotations() -> None:
    read_only = {
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
        "literature_migrate_v1_to_v2",
        "literature_rollback_transaction",
    }

    tools = asyncio.run(create_server().list_tools())
    annotations = {tool.name: tool.annotations for tool in tools}

    assert len(annotations) == 31
    assert set(annotations) == {function.__name__ for function in TOOL_FUNCTIONS}
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
