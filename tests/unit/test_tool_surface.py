from __future__ import annotations

from obsidian_vault_mcp.interfaces.mcp.tools import TOOL_FUNCTIONS


def test_exact_v2_tool_surface():
    expected = {
        "literature_doctor", "literature_config_get", "literature_config_validate", "literature_config_initialize",
        "zotero_ping", "zotero_search_items", "zotero_list_collections", "zotero_get_item", "zotero_get_children", "zotero_get_bibtex",
        "literature_import_item", "literature_import_collection", "literature_sync_item", "literature_sync_collection",
        "literature_parse_mineru", "literature_parse_mineru_batch", "literature_remove_mineru_output",
        "literature_rebuild_index", "literature_rebuild_base", "literature_verify",
        "literature_wiki_context", "literature_wiki_write", "literature_wiki_list",
        "literature_migrate_v1_to_v2", "literature_preview_transaction", "literature_rollback_transaction",
    }
    assert {function.__name__ for function in TOOL_FUNCTIONS} == expected
    assert len(TOOL_FUNCTIONS) == 26
    assert all(function.__doc__ for function in TOOL_FUNCTIONS)
