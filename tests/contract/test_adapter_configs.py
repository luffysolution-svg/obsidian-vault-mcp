from __future__ import annotations

import json
from pathlib import Path

from obsidian_vault_mcp import __version__

ROOT = Path(__file__).resolve().parents[2]


def test_codex_manifest_and_mcp_config_are_minimal_and_portable() -> None:
    plugin = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    mcp = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))

    assert plugin == {
        "name": "obsidian-literature",
        "version": __version__,
        "description": "Zotero, MinerU and Obsidian literature pipeline",
        "mcpServers": "./.mcp.json",
    }
    assert mcp == {
        "mcpServers": {
            "obsidian-literature": {
                "type": "stdio",
                "command": "obsidian-vault-mcp",
                "args": ["serve", "--transport", "stdio"],
                "env": {"OBSIDIAN_VAULT_PATH": "auto"},
            }
        }
    }


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


def test_pi_extension_registers_the_complete_v2_tool_surface() -> None:
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
        "literature_wiki_context",
        "literature_wiki_write",
        "literature_wiki_list",
        "literature_migrate_v1_to_v2",
        "literature_preview_transaction",
        "literature_rollback_transaction",
    }
    missing = [tool for tool in expected_tools if f'["{tool}",' not in source]
    assert not missing
