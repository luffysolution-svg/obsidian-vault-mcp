from __future__ import annotations

import asyncio

from obsidian_vault_mcp.interfaces.mcp.server import create_server
from obsidian_vault_mcp.interfaces.mcp.tools import TOOL_FUNCTIONS


def test_exact_v2_tool_surface():
    expected = {
        "literature_doctor", "literature_config_get", "literature_config_validate", "literature_config_initialize",
        "zotero_ping", "zotero_search_items", "zotero_list_collections", "zotero_get_item", "zotero_get_children", "zotero_get_bibtex",
        "literature_import_item", "literature_import_collection", "literature_sync_item", "literature_sync_collection",
        "literature_parse_mineru", "literature_parse_mineru_batch", "literature_remove_mineru_output",
        "literature_rebuild_index", "literature_rebuild_base", "literature_verify",
        "literature_paper_read", "literature_analysis_context", "literature_analysis_write",
        "literature_uncertainty_list", "literature_uncertainty_resolve",
        "literature_rebuild_analysis_index", "literature_retrieve",
        "literature_wiki_context", "literature_wiki_write", "literature_wiki_list",
        "literature_migrate_v1_to_v2", "literature_preview_transaction", "literature_rollback_transaction",
    }
    assert {function.__name__ for function in TOOL_FUNCTIONS} == expected
    assert len(TOOL_FUNCTIONS) == 33
    assert all(function.__doc__ for function in TOOL_FUNCTIONS)


def test_all_v2_tools_have_precise_behavior_annotations():
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
        "literature_analysis_context",
        "literature_uncertainty_list",
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

    assert len(annotations) == 33
    assert set(annotations) == {function.__name__ for function in TOOL_FUNCTIONS}
    assert all(annotation is not None for annotation in annotations.values())
    assert {
        name for name, annotation in annotations.items() if annotation and annotation.readOnlyHint
    } == read_only
    assert {
        name for name, annotation in annotations.items() if annotation and annotation.destructiveHint
    } == destructive
    assert {
        name for name, annotation in annotations.items() if annotation and annotation.idempotentHint
    } == read_only
    assert all(
        annotation
        and annotation.readOnlyHint is not None
        and annotation.destructiveHint is not None
        and annotation.idempotentHint is not None
        and annotation.openWorldHint is not None
        for annotation in annotations.values()
    )
    assert all(annotation and annotation.openWorldHint is False for annotation in annotations.values())
