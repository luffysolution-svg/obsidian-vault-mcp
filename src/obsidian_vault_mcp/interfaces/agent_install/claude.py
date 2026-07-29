"""Claude Code native plugin marketplace installer."""

from __future__ import annotations

import os
from pathlib import Path

from .common import (
    MARKETPLACE_NAME,
    PLUGIN_SELECTOR,
    Handshake,
    PluginInstallResult,
    Runner,
    Which,
    detect_client,
    install_native_plugin,
    packaged_marketplace_path,
)

CLIENT = "claude"
EXECUTABLE = "claude"
MARKETPLACE_MANIFEST = Path(".claude-plugin") / "marketplace.json"
PLUGIN_MANIFEST = Path("plugins") / "obsidian-literature" / ".claude-plugin" / "plugin.json"


def detect(*, which: Which | None = None) -> bool:
    return detect_client(EXECUTABLE, which=which) is not None


def install(
    project_dir: str | os.PathLike[str] | None = None,
    *,
    marketplace_path: str | os.PathLike[str] | None = None,
    dry_run: bool = False,
    which: Which | None = None,
    runner: Runner | None = None,
    handshake: Handshake | None = None,
) -> PluginInstallResult:
    """Install the bundled marketplace and plugin with the native Claude CLI."""

    del project_dir  # Kept only for the shared ``agent install`` CLI contract.
    root = packaged_marketplace_path(marketplace_path)
    return install_native_plugin(
        client=CLIENT,
        executable=EXECUTABLE,
        marketplace_path=root,
        marketplace_manifest=MARKETPLACE_MANIFEST,
        plugin_manifest=PLUGIN_MANIFEST,
        marketplace_list_args=("plugin", "marketplace", "list", "--json"),
        plugin_list_args=("plugin", "list", "--json"),
        marketplace_add_args=("plugin", "marketplace", "add", str(root), "--scope", "user"),
        plugin_install_args=("plugin", "install", PLUGIN_SELECTOR, "--scope", "user"),
        plugin_uninstall_args=("plugin", "uninstall", PLUGIN_SELECTOR, "--scope", "user"),
        marketplace_remove_args=("plugin", "marketplace", "remove", MARKETPLACE_NAME, "--scope", "user"),
        marketplace_records_key=None,
        marketplace_path_keys=("path", "installLocation"),
        plugin_records_key=None,
        plugin_id_keys=("id", "pluginId"),
        plugin_required_fields={"scope": "user"},
        uninstall_instructions=(
            f"Run `claude plugin uninstall {PLUGIN_SELECTOR} --scope user`. If this marketplace is no longer needed, "
            f"run `claude plugin marketplace remove {MARKETPLACE_NAME} --scope user`."
        ),
        dry_run=dry_run,
        which=which,
        runner=runner,
        handshake=handshake,
    )


install_claude = install
