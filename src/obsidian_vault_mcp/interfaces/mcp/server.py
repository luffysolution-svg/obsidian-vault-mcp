from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .tools import TOOL_FUNCTIONS

_READ_ONLY_TOOLS = frozenset(
    {
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
)

_MUTATING_TOOLS = frozenset(
    {
        "literature_config_initialize",
        "literature_import_item",
        "literature_import_collection",
        "literature_sync_item",
        "literature_sync_collection",
        "literature_parse_mineru",
        "literature_parse_mineru_batch",
        "literature_remove_mineru_output",
        "literature_rebuild_index",
        "literature_rebuild_base",
        "literature_analysis_write",
        "literature_rebuild_analysis_base",
        "literature_wiki_write",
        "literature_rollback_transaction",
    }
)

_DESTRUCTIVE_TOOLS = frozenset(
    {
        "literature_remove_mineru_output",
        "literature_rollback_transaction",
    }
)


def _tool_annotations(name: str) -> ToolAnnotations:
    if name in _READ_ONLY_TOOLS:
        read_only = True
    elif name in _MUTATING_TOOLS:
        read_only = False
    else:
        raise RuntimeError(f"MCP tool is missing an explicit behavior classification: {name}")
    return ToolAnnotations(
        readOnlyHint=read_only,
        destructiveHint=name in _DESTRUCTIVE_TOOLS,
        idempotentHint=read_only,
        openWorldHint=False,
    )


def create_server() -> FastMCP:
    """Create a fresh explicitly registered production MCP server."""

    server = FastMCP("obsidian-literature", json_response=True)
    for function in TOOL_FUNCTIONS:
        server.tool(annotations=_tool_annotations(function.__name__))(function)
    return server


def run_server(transport: str = "stdio") -> None:
    if transport not in {"stdio", "sse", "streamable-http"}:
        raise ValueError("transport must be stdio, sse, or streamable-http")
    create_server().run(transport=transport)


def main() -> None:
    run_server("stdio")
