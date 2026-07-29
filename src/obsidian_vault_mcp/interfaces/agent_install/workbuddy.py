"""WorkBuddy project MCP installer."""

from __future__ import annotations

import os
from pathlib import Path

from .common import (
    ClientNotFoundError,
    Handshake,
    InstallResult,
    Which,
    detect_client,
    install_configuration,
    project_config_path,
)

CLIENT = "workbuddy"
EXECUTABLES = ("codebuddy", "cbc")
CONFIG_RELATIVE_PATH = Path(".workbuddy") / "mcp.json"
SKILL_NOTICE = "Agent Skills are packaged but were not installed because WorkBuddy has no verified native project-local Skill directory contract."


def detect(*, which: Which | None = None) -> bool:
    return any(detect_client(executable, which=which) is not None for executable in EXECUTABLES)


def _select_executable(*, which: Which | None = None) -> str:
    for executable in EXECUTABLES:
        if detect_client(executable, which=which) is not None:
            return executable
    raise ClientNotFoundError("WorkBuddy/CodeBuddy client executable not found: expected codebuddy or cbc")


def install(
    project_dir: str | os.PathLike[str] | None = None,
    *,
    config_path: str | os.PathLike[str] | None = None,
    dry_run: bool = False,
    which: Which | None = None,
    handshake: Handshake | None = None,
) -> InstallResult:
    executable = _select_executable(which=which)
    target = Path(config_path).expanduser().resolve() if config_path is not None else project_config_path(project_dir, CONFIG_RELATIVE_PATH)
    update = {
        "mcpServers": {
            "obsidian-literature": {
                "command": "obsidian-vault-mcp",
                "args": ["serve", "--transport", "stdio"],
                "env": {"OBSIDIAN_VAULT_PATH": "auto"},
            }
        }
    }
    return install_configuration(
        client=CLIENT,
        executable=executable,
        config_path=target,
        update=update,
        config_format="json",
        uninstall_instructions=f'Remove "mcpServers.obsidian-literature" from {target} and keep all other MCP servers.',
        dry_run=dry_run,
        which=which,
        handshake=handshake,
        warnings=(SKILL_NOTICE,),
    )


install_workbuddy = install
