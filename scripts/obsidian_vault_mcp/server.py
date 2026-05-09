from mcp.server.fastmcp import FastMCP

from .common import REGISTERED_TOOLS
from . import tools as tools  # noqa: F401 - importing registers tool functions


def create_server() -> FastMCP:
    server = FastMCP("obsidian-vault")
    for func in REGISTERED_TOOLS:
        server.tool()(func)
    return server


mcp = create_server()


def main() -> None:
    mcp.run()
