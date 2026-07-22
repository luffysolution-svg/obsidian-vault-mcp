"""Pi installer for the packaged thin JSON-CLI Extension."""

from __future__ import annotations

import os
from importlib import resources
from pathlib import Path

from .common import Handshake, InstallResult, Which, detect_client, install_resource, project_config_path

CLIENT = "pi"
EXECUTABLE = "pi"
CONFIG_RELATIVE_PATH = Path(".pi") / "extensions" / "obsidian-vault-mcp.ts"
EXTENSION_RESOURCE = "pi_extension.ts"


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
    extension = resources.files(__package__).joinpath(EXTENSION_RESOURCE).read_bytes()
    return install_resource(
        client=CLIENT,
        executable=EXECUTABLE,
        destination=target,
        content=extension,
        uninstall_instructions=f"Remove {target}; Pi auto-discovers project Extensions from .pi/extensions.",
        dry_run=dry_run,
        which=which,
        handshake=handshake,
    )


install_pi = install
