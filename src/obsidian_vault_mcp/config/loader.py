"""Load and initialize the single V2 Vault configuration file."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ..adapters.vault.filesystem import VaultFilesystem, VaultPathSafetyError
from ..domain.errors import ConfigurationError
from .defaults import CONFIG_FILENAME, default_config
from .schema import validate_config


def config_path(vault_path: str | os.PathLike[str]) -> Path:
    return Path(vault_path).expanduser().resolve() / CONFIG_FILENAME


def load_config(
    vault_path: str | os.PathLike[str],
    *,
    require_exists: bool = True,
) -> dict[str, Any]:
    """Read, strictly parse, validate, and normalize the one V2 config file."""

    root = Path(vault_path).expanduser().resolve()
    path = root / CONFIG_FILENAME
    filesystem = VaultFilesystem(root)
    try:
        content = filesystem.read_bytes_owned(CONFIG_FILENAME)
    except FileNotFoundError:
        if require_exists:
            raise ConfigurationError(f"configuration file does not exist: {path}")
        return default_config()
    except (OSError, VaultPathSafetyError) as exc:
        raise ConfigurationError(f"could not read {CONFIG_FILENAME}: {exc}") from exc
    try:
        text = content.decode("utf-8-sig")
        raw = json.loads(text, object_pairs_hook=_unique_object)
    except ConfigurationError:
        raise
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ConfigurationError(f"could not read {CONFIG_FILENAME}: {exc}") from exc
    return validate_config(raw)


def save_config(vault_path: str | os.PathLike[str], config: Mapping[str, Any]) -> Path:
    """Validate then atomically save canonical UTF-8 JSON."""

    normalized = validate_config(config)
    root = Path(vault_path).expanduser().resolve()
    filesystem = VaultFilesystem(root)
    payload = (json.dumps(normalized, ensure_ascii=False, indent=2) + "\n").encode(
        "utf-8"
    )
    try:
        return filesystem.atomic_write_bytes_owned(CONFIG_FILENAME, payload)
    except (OSError, VaultPathSafetyError) as exc:
        raise ConfigurationError(f"could not write {CONFIG_FILENAME}: {exc}") from exc


def initialize_config(
    vault_path: str | os.PathLike[str],
    *,
    overwrite: bool = False,
) -> Path:
    """Create the canonical config without overwriting it by default."""

    root = Path(vault_path).expanduser().resolve()
    if not root.is_dir():
        raise ConfigurationError(f"Vault path is not a directory: {root}")
    path = root / CONFIG_FILENAME
    filesystem = VaultFilesystem(root)
    try:
        exists = filesystem.is_file_owned(CONFIG_FILENAME)
    except (OSError, VaultPathSafetyError) as exc:
        raise ConfigurationError(f"unsafe configuration path: {path}") from exc
    if exists and not overwrite:
        raise ConfigurationError(f"configuration file already exists: {path}")
    return save_config(root, default_config())


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ConfigurationError(f"duplicate JSON configuration field: {key}")
        result[key] = value
    return result


class ConfigLoader:
    """Object-oriented facade used by CLI and MCP adapters."""

    def __init__(self, vault_path: str | os.PathLike[str]) -> None:
        self.vault_path = Path(vault_path)

    def load(self, *, require_exists: bool = True) -> dict[str, Any]:
        return load_config(self.vault_path, require_exists=require_exists)

    def initialize(self, *, overwrite: bool = False) -> Path:
        return initialize_config(self.vault_path, overwrite=overwrite)

    def save(self, config: Mapping[str, Any]) -> Path:
        return save_config(self.vault_path, config)
