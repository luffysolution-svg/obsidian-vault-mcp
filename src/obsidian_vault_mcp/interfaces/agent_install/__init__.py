"""One-click installers for supported Agent clients."""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from . import claude, codex, hermes, opencode, pi, workbuddy
from .common import (
    AgentInstallError,
    ClientNotFoundError,
    ConfigurationValidationError,
    HandshakeContext,
    HandshakeError,
    InstallResult,
    MarketplaceConflictError,
    PluginInstallResult,
    SkillInstallResult,
)

SUPPORTED_CLIENTS = ("codex", "claude", "opencode", "pi", "hermes", "workbuddy")
AgentInstallResult = InstallResult | PluginInstallResult
INSTALLERS: dict[str, Callable[..., AgentInstallResult]] = {
    "codex": codex.install,
    "claude": claude.install,
    "opencode": opencode.install,
    "pi": pi.install,
    "hermes": hermes.install,
    "workbuddy": workbuddy.install,
}


def get_installer(client: str) -> Callable[..., AgentInstallResult]:
    """Return the normalized client installer."""

    normalized = client.strip().lower()
    try:
        return INSTALLERS[normalized]
    except KeyError as exc:
        supported = ", ".join(SUPPORTED_CLIENTS)
        raise ValueError(f"Unsupported Agent client {client!r}; choose one of: {supported}") from exc


def install_agent(
    client: str,
    project_dir: str | os.PathLike[str] | None = None,
    **kwargs: Any,
) -> AgentInstallResult:
    """Install one supported Agent adapter with its native client lifecycle."""

    return get_installer(client)(project_dir, **kwargs)


install = install_agent

__all__ = [
    "AgentInstallResult",
    "AgentInstallError",
    "ClientNotFoundError",
    "ConfigurationValidationError",
    "HandshakeContext",
    "HandshakeError",
    "INSTALLERS",
    "InstallResult",
    "MarketplaceConflictError",
    "PluginInstallResult",
    "SkillInstallResult",
    "SUPPORTED_CLIENTS",
    "get_installer",
    "install",
    "install_agent",
]
