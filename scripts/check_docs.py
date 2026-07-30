"""Check that generated public tool-reference source stays aligned with runtime."""

from __future__ import annotations

import argparse
from pathlib import Path

from obsidian_vault_mcp.interfaces.mcp.tools import TOOL_BY_NAME

ROOT = Path(__file__).resolve().parents[1]
TOOL_PAGES = (ROOT / "docs" / "tools.md", ROOT / "docs" / "en" / "tools.md")


def documented_tools(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    return {name for name in TOOL_BY_NAME if f"`{name}`" in text}


def check_tool_pages() -> list[str]:
    expected = set(TOOL_BY_NAME)
    errors: list[str] = []
    for path in TOOL_PAGES:
        actual = documented_tools(path)
        if actual != expected:
            errors.append(f"{path.relative_to(ROOT)}: missing={sorted(expected - actual)}, extra={sorted(actual - expected)}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.parse_args()
    errors = check_tool_pages()
    if errors:
        raise SystemExit("\n".join(errors))
    print(f"Public tool documentation matches {len(TOOL_BY_NAME)} runtime tools.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
