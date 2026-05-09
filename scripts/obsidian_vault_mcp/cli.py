from __future__ import annotations

import argparse
import json

from .server import main as run_server
from .tools import obsidian_doctor


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Obsidian Vault MCP server.")
    parser.add_argument("--doctor", action="store_true", help="Check local readiness without starting the MCP server.")
    parser.add_argument("--vault", default="", help="Vault path to check when using --doctor.")
    args = parser.parse_args()

    if args.doctor:
        print(json.dumps(obsidian_doctor(args.vault), ensure_ascii=False, indent=2))
        return

    run_server()


if __name__ == "__main__":
    main()
