from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote

from obsidian_vault_mcp.interfaces.mcp.tools import TOOL_BY_NAME
from scripts.check_docs import check_tool_pages

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
PAGE_NAMES = (
    "index",
    "quickstart",
    "installation",
    "configuration",
    "zotero",
    "mineru",
    "analysis",
    "agents",
    "tools",
    "troubleshooting",
    "development",
    "changelog",
)


def test_bilingual_pages_share_the_formal_3_0_0_information_architecture() -> None:
    for name in PAGE_NAMES:
        chinese = DOCS / f"{name}.md"
        english = DOCS / "en" / f"{name}.md"
        assert chinese.is_file(), chinese
        assert english.is_file(), english
        for page in (chinese, english):
            text = page.read_text(encoding="utf-8")
            assert text.startswith("---\nlayout: default\n"), page


def test_public_tool_references_match_the_runtime_registry() -> None:
    assert len(TOOL_BY_NAME) == 31
    assert check_tool_pages() == []


def test_release_notes_describe_the_production_architecture() -> None:
    release = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "## Obsidian Vault MCP 3.0.0" in release
    assert "31 MCP tools across the production architecture." in release
    assert "V2 surface" not in release
    assert "V2-to-V3 migration" not in release


def test_public_docs_do_not_advertise_removed_migration_commands_or_old_cli_flags() -> None:
    public_docs = "\n".join(path.read_text(encoding="utf-8") for path in DOCS.rglob("*.md"))
    for forbidden in (
        "migrate mineru-images-v2-to-v3",
        "migrate analysis-v2-to-v3",
        "--apply --cleanup-legacy",
        "--doctor",
        "--doctor-format",
    ):
        assert forbidden not in public_docs


def test_markdown_links_and_images_resolve_inside_the_pages_source() -> None:
    pattern = re.compile(r"!?(?:\[[^\]]*\]\(([^)]+)\))")
    liquid_path = re.compile(r"\{\{\s*'(/[^']*)'\s*\|\s*relative_url\s*\}\}")
    for page in DOCS.rglob("*.md"):
        rendered_markdown = re.sub(r"```.*?```|`[^`]*`", "", page.read_text(encoding="utf-8"), flags=re.DOTALL)
        for raw_target in pattern.findall(rendered_markdown):
            match = liquid_path.fullmatch(raw_target)
            if match:
                target = match.group(1).lstrip("/")
                candidate = (DOCS / target).resolve()
            else:
                target = unquote(raw_target.split(maxsplit=1)[0]).split("#", 1)[0].split("?", 1)[0]
                if not target or target.startswith(("http://", "https://", "mailto:", "#", "{{")):
                    continue
                candidate = (page.parent / target).resolve()
            options = (candidate, candidate.with_suffix(".md"), candidate / "index.md")
            assert any(option.is_file() for option in options), f"{page.relative_to(ROOT)} -> {raw_target}"
