from mcp.server.fastmcp import FastMCP

from . import tools as tools  # noqa: F401 - importing registers tool functions
from .common import get_registered_tools


def create_server() -> FastMCP:
    server = FastMCP("obsidian-vault")
    for func in get_registered_tools():
        server.tool()(func)
    return server


mcp = create_server()


def main() -> None:
    mcp.run()
