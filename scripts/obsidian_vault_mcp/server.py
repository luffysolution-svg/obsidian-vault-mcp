import os

from mcp.server.fastmcp import FastMCP

from . import tools as tools  # noqa: F401 - importing registers tool functions
from .common import DEFAULT_TOOL_PROFILE, get_registered_tools


def create_server(profile: str = "") -> FastMCP:
    server = FastMCP("obsidian-vault")
    selected_profile = profile or os.environ.get("OBSIDIAN_VAULT_TOOL_PROFILE", DEFAULT_TOOL_PROFILE)
    for func in get_registered_tools(selected_profile):
        server.tool()(func)
    return server


mcp = create_server()


def main() -> None:
    mcp.run()
