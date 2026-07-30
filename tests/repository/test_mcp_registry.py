from __future__ import annotations

import json
from pathlib import Path

from obsidian_vault_mcp import __version__

ROOT = Path(__file__).resolve().parents[2]
MCP_NAME = "io.github.luffysolution-svg/obsidian-vault-mcp"


def test_server_json_describes_the_published_pypi_stdio_server() -> None:
    server = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert server["$schema"] == "https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json"
    assert server["name"] == MCP_NAME
    assert server["version"] == __version__
    assert server["repository"] == {
        "url": "https://github.com/luffysolution-svg/obsidian-vault-mcp",
        "source": "github",
    }
    assert server["packages"] == [
        {
            "registryType": "pypi",
            "registryBaseUrl": "https://pypi.org",
            "identifier": "zotero-obsidian-mcp",
            "version": __version__,
            "runtimeHint": "uvx",
            "packageArguments": [
                {"type": "positional", "value": "serve", "isRequired": True},
                {"type": "named", "name": "--transport", "value": "stdio", "isRequired": True},
            ],
            "environmentVariables": [
                {
                    "name": "OBSIDIAN_VAULT_PATH",
                    "description": "Absolute path to the Obsidian vault, or auto when the client project is inside it.",
                    "isRequired": True,
                    "isSecret": False,
                    "format": "filepath",
                }
            ],
            "transport": {"type": "stdio"},
        }
    ]
    assert 'zotero-obsidian-mcp = "obsidian_vault_mcp.interfaces.cli.main:main"' in pyproject


def test_pypi_readme_proves_mcp_registry_package_ownership() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert f"<!-- mcp-name: {MCP_NAME} -->" in readme


def test_release_workflow_uses_oidc_and_a_verified_publisher_binary() -> None:
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")

    assert "id-token: write" in workflow
    assert "mcp-publisher_linux_amd64.tar.gz" in workflow
    assert "v1.8.0" in workflow
    assert "1370446bbe74d562608e8005a6ccce02d146a661fbd78674e11cc70b9618d6cf" in workflow
    assert "./mcp-publisher login github-oidc" in workflow
    assert "./mcp-publisher publish server.json" in workflow
    assert workflow.index("./mcp-publisher login github-oidc") < workflow.index(
        "pypa/gh-action-pypi-publish"
    )
    assert workflow.index("pypa/gh-action-pypi-publish") < workflow.index("./mcp-publisher publish server.json")
