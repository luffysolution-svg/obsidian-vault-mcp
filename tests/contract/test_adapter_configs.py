from __future__ import annotations

import json
from pathlib import Path

from obsidian_vault_mcp import __version__

ROOT = Path(__file__).resolve().parents[2]
MARKETPLACE_ROOT = ROOT / "src" / "obsidian_vault_mcp" / "resources" / "agent_marketplace"
PLUGIN_ROOT = MARKETPLACE_ROOT / "plugins" / "obsidian-literature"


def test_codex_and_claude_plugin_manifests_share_one_portable_bundle() -> None:
    codex = json.loads((PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    claude = json.loads((PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    mcp = json.loads((PLUGIN_ROOT / ".mcp.json").read_text(encoding="utf-8"))

    assert codex["name"] == claude["name"] == "obsidian-literature"
    assert codex["version"] == claude["version"] == __version__
    assert codex["author"] == claude["author"]
    assert codex["repository"] == claude["repository"]
    assert codex["skills"] == "./skills/"
    assert codex["mcpServers"] == "./.mcp.json"
    assert codex["interface"]["displayName"] == "Obsidian Literature"
    assert mcp == {
        "mcpServers": {
            "obsidian-literature": {
                "command": "obsidian-vault-mcp",
                "args": ["serve", "--transport", "stdio"],
            }
        }
    }
    assert "env" not in mcp["mcpServers"]["obsidian-literature"]


def test_codex_and_claude_marketplaces_point_to_the_same_plugin() -> None:
    codex = json.loads((MARKETPLACE_ROOT / ".agents" / "plugins" / "marketplace.json").read_text(encoding="utf-8"))
    claude = json.loads((MARKETPLACE_ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))

    assert codex["name"] == claude["name"] == "obsidian-vault-mcp"
    assert codex["plugins"][0]["name"] == claude["plugins"][0]["name"] == "obsidian-literature"
    assert codex["plugins"][0]["source"]["path"] == claude["plugins"][0]["source"] == "./plugins/obsidian-literature"
    assert claude["plugins"][0]["version"] == claude["metadata"]["version"] == __version__


def test_opencode_uses_the_same_console_entrypoint() -> None:
    config = json.loads((ROOT / "opencode.json").read_text(encoding="utf-8"))
    server = config["mcp"]["obsidian-literature"]

    assert server == {
        "type": "local",
        "command": ["obsidian-vault-mcp", "serve", "--transport", "stdio"],
        "enabled": True,
    }


def test_pi_extension_is_a_bounded_shell_free_json_cli_adapter() -> None:
    package = json.loads((ROOT / "adapters" / "pi" / "package.json").read_text(encoding="utf-8"))
    source = (ROOT / "adapters" / "pi" / "index.ts").read_text(encoding="utf-8")

    assert package["version"] == __version__
    assert package["pi"]["extensions"] == ["./index.ts"]
    assert "execFile" in source
    assert 'shell: false' in source
    assert '["call", toolName, "--json", jsonArguments]' in source
    assert "timeout: CLI_TIMEOUT_MS" in source
    assert "const CLI_TIMEOUT_MS = 660_000;" in source
    assert "maxBuffer: MAX_OUTPUT_BYTES" in source
    assert "JSON.parse(stdout)" in source
    assert "pi.registerTool" in source
    assert "exec(" not in source


def test_pi_extension_registers_the_complete_v3_tool_surface() -> None:
    source = (ROOT / "adapters" / "pi" / "index.ts").read_text(encoding="utf-8")
    expected_tools = {
        "literature_doctor",
        "literature_config_get",
        "literature_config_validate",
        "literature_config_initialize",
        "zotero_ping",
        "zotero_search_items",
        "zotero_list_collections",
        "zotero_get_item",
        "zotero_get_children",
        "zotero_get_bibtex",
        "literature_import_item",
        "literature_import_collection",
        "literature_sync_item",
        "literature_sync_collection",
        "literature_parse_mineru",
        "literature_parse_mineru_batch",
        "literature_remove_mineru_output",
        "literature_rebuild_index",
        "literature_rebuild_base",
        "literature_verify",
        "literature_paper_read",
        "literature_retrieve",
        "literature_analysis_get",
        "literature_analysis_write",
        "literature_rebuild_analysis_base",
        "literature_wiki_context",
        "literature_wiki_write",
        "literature_wiki_list",
        "literature_migrate_v1_to_v2",
        "literature_preview_transaction",
        "literature_rollback_transaction",
    }
    missing = [tool for tool in expected_tools if f'["{tool}",' not in source]
    assert not missing
