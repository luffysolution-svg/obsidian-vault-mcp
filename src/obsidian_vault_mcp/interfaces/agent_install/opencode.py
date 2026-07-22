"""OpenCode project MCP installer."""

from __future__ import annotations

import os
from pathlib import Path

from .common import Handshake, InstallResult, Which, detect_client, install_configuration, project_config_path

CLIENT = "opencode"
EXECUTABLE = "opencode"
CONFIG_RELATIVE_PATH = Path("opencode.json")


def detect(*, which: Which | None = None) -> bool:
    return detect_client(EXECUTABLE, which=which) is not None


def install(
    project_dir: str | os.PathLike[str] | None = None,
    *,
    config_path: str | os.PathLike[str] | None = None,
    dry_run: bool = False,
    which: Which | None = None,
    handshake: Handshake | None = None,
) -> InstallResult:
    target = Path(config_path).expanduser().resolve() if config_path is not None else project_config_path(project_dir, CONFIG_RELATIVE_PATH)
    update = {
        "$schema": "https://opencode.ai/config.json",
        "mcp": {
            "obsidian-literature": {
                "type": "local",
                "command": ["obsidian-vault-mcp", "serve", "--transport", "stdio"],
                "enabled": True,
            }
        },
    }
    return install_configuration(
        client=CLIENT,
        executable=EXECUTABLE,
        config_path=target,
        update=update,
        config_format="json",
        uninstall_instructions=f'Remove "mcp.obsidian-literature" from {target} and keep all other MCP servers.',
        dry_run=dry_run,
        which=which,
        handshake=handshake,
    )


install_opencode = install
