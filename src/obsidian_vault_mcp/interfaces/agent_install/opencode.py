"""OpenCode project MCP and Agent Skill installer."""

from __future__ import annotations

import os
from pathlib import Path

from .common import Handshake, InstallResult, Which, detect_client, install_configuration, project_config_path

CLIENT = "opencode"
EXECUTABLE = "opencode"
CONFIG_RELATIVE_PATH = Path("opencode.json")
SKILL_RELATIVE_PATH = Path(".opencode") / "skills"


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
    project_root = project_config_path(project_dir, ".")
    target = Path(config_path).expanduser().resolve() if config_path is not None else project_root / CONFIG_RELATIVE_PATH
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
        uninstall_instructions=(
            f'Remove "mcp.obsidian-literature" from {target}; remove the seven managed Skill folders and manifest from '
            f"{project_root / SKILL_RELATIVE_PATH}."
        ),
        dry_run=dry_run,
        which=which,
        handshake=handshake,
        project_root=project_root,
        skill_directory=project_root / SKILL_RELATIVE_PATH,
    )


install_opencode = install
