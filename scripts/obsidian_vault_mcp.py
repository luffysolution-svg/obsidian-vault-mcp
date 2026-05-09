from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = str(Path(__file__).resolve().parent)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from obsidian_vault_mcp import *
from obsidian_vault_mcp import tools as _tools
from obsidian_vault_mcp.common import *
from obsidian_vault_mcp.helpers import *
from obsidian_vault_mcp.server import main, mcp

globals().update({name: value for name, value in vars(_tools).items() if not name.startswith("__")})

if __name__ == "__main__":
    main()
