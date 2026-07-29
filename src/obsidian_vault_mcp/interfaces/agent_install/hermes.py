"""Hermes profile-level MCP installer."""

from __future__ import annotations

import os
from pathlib import Path

from .common import Handshake, InstallResult, Which, detect_client, install_configuration

CLIENT = "hermes"
EXECUTABLE = "hermes"
SKILL_NOTICE = "Agent Skills are packaged but were not installed because Hermes has no verified installer-managed Skill contract."


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
    del project_dir  # Hermes reads profile state, not project-local MCP configuration.
    if config_path is not None:
        target = Path(config_path).expanduser().resolve()
    else:
        configured_home = os.environ.get("HERMES_HOME")
        hermes_home = Path(configured_home).expanduser() if configured_home else Path.home() / ".hermes"
        target = (hermes_home / "config.yaml").resolve()
    update = {
        "mcp_servers": {
            "obsidian-literature": {
                "command": "obsidian-vault-mcp",
                "args": ["serve", "--transport", "stdio"],
                "env": {"OBSIDIAN_VAULT_PATH": "auto"},
                "enabled": True,
            }
        }
    }
    return install_configuration(
        client=CLIENT,
        executable=EXECUTABLE,
        config_path=target,
        update=update,
        config_format="yaml",
        uninstall_instructions=f'Remove "mcp_servers.obsidian-literature" from {target} and keep all other MCP servers.',
        dry_run=dry_run,
        which=which,
        handshake=handshake,
        warnings=(SKILL_NOTICE,),
    )


install_hermes = install
