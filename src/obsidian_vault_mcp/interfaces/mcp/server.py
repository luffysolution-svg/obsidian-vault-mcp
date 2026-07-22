from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .tools import TOOL_FUNCTIONS


def create_server() -> FastMCP:
    """Create a fresh explicitly registered V2 MCP server."""
    server = FastMCP("obsidian-literature", json_response=True)
    for function in TOOL_FUNCTIONS:
        server.tool()(function)
    return server


def run_server(transport: str = "stdio") -> None:
    if transport not in {"stdio", "sse", "streamable-http"}:
        raise ValueError("transport must be stdio, sse, or streamable-http")
    create_server().run(transport=transport)


def main() -> None:
    run_server("stdio")
