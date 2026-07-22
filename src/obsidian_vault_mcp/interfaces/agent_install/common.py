"""Shared, transactional helpers for Agent client installers."""

from __future__ import annotations

import copy
import inspect
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal, Mapping, Sequence

import yaml
from mcp.types import LATEST_PROTOCOL_VERSION

from ... import __version__

SERVER_NAME = "obsidian-literature"
SERVER_COMMAND = "obsidian-vault-mcp"
SERVER_ARGS = ("serve", "--transport", "stdio")

ConfigFormat = Literal["json", "yaml"]
Which = Callable[[str], str | None]
Handshake = Callable[..., bool | None]
Merge = Callable[[Mapping[str, Any], Mapping[str, Any]], dict[str, Any]]


class AgentInstallError(RuntimeError):
    """Base class for expected Agent installer failures."""


class ClientNotFoundError(AgentInstallError):
    """Raised when the requested Agent executable cannot be found."""


class ConfigurationValidationError(AgentInstallError, ValueError):
    """Raised when an existing or generated client configuration is invalid."""


class HandshakeError(AgentInstallError):
    """Raised after a failed MCP handshake and configuration rollback."""


@dataclass(frozen=True)
class HandshakeContext:
    """Information made available to an injected handshake callback."""

    client: str
    config_path: Path
    command: str = SERVER_COMMAND
    args: tuple[str, ...] = SERVER_ARGS


@dataclass(frozen=True)
class InstallResult:
    """Description of a completed installation or a dry-run preview."""

    client: str
    executable: str
    config_path: Path
    backup_path: Path | None
    changed: bool
    dry_run: bool
    handshake_performed: bool
    installed_config: dict[str, Any]
    uninstall_instructions: str

    @property
    def uninstall_command(self) -> str:
        """Compatibility alias for callers that display one uninstall field."""

        return self.uninstall_instructions

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation for the CLI layer."""

        result = asdict(self)
        result["config_path"] = str(self.config_path)
        result["backup_path"] = str(self.backup_path) if self.backup_path else None
        return result


def project_config_path(project_dir: str | os.PathLike[str] | None, relative_path: str | os.PathLike[str]) -> Path:
    """Resolve a project-local config path, defaulting to the current project."""

    root = Path.cwd() if project_dir is None else Path(project_dir)
    return (root / relative_path).expanduser().resolve()


def detect_client(executable: str, *, which: Which | None = None) -> str | None:
    """Return the resolved client executable, using an injectable detector."""

    detector = shutil.which if which is None else which
    detected = detector(executable)
    return os.fspath(detected) if detected else None


def require_client(executable: str, *, which: Which | None = None) -> str:
    """Resolve an Agent executable or raise a focused installation error."""

    detected = detect_client(executable, which=which)
    if detected is None:
        raise ClientNotFoundError(f"Agent client executable not found: {executable}")
    return detected


def deep_merge(existing: Mapping[str, Any], update: Mapping[str, Any]) -> dict[str, Any]:
    """Recursively merge mappings without mutating either input."""

    merged: dict[str, Any] = copy.deepcopy(dict(existing))
    for key, value in update.items():
        current = merged.get(key)
        if isinstance(current, Mapping) and isinstance(value, Mapping):
            merged[key] = deep_merge(current, value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def load_config(path: str | os.PathLike[str], *, config_format: ConfigFormat) -> dict[str, Any]:
    """Load and validate a JSON or YAML mapping; a missing file is empty."""

    target = Path(path)
    if not target.exists():
        return {}
    if not target.is_file():
        raise ConfigurationValidationError(f"Configuration path is not a file: {target}")

    try:
        text = target.read_text(encoding="utf-8")
        if config_format == "json":
            loaded = json.loads(text)
        elif config_format == "yaml":
            loaded = yaml.safe_load(text)
        else:  # pragma: no cover - protected by the public type and checked defensively
            raise ConfigurationValidationError(f"Unsupported configuration format: {config_format}")
    except (OSError, UnicodeError, json.JSONDecodeError, yaml.YAMLError) as exc:
        raise ConfigurationValidationError(f"Invalid {config_format.upper()} configuration at {target}: {exc}") from exc

    if loaded is None and config_format == "yaml":
        return {}
    if not isinstance(loaded, dict):
        raise ConfigurationValidationError(f"Configuration root must be an object at {target}")
    return loaded


def serialize_config(config: Mapping[str, Any], *, config_format: ConfigFormat) -> str:
    """Serialize a configuration and parse it again before it can be written."""

    try:
        if config_format == "json":
            text = json.dumps(config, ensure_ascii=False, indent=2) + "\n"
            validated = json.loads(text)
        elif config_format == "yaml":
            text = yaml.safe_dump(dict(config), allow_unicode=True, sort_keys=False)
            validated = yaml.safe_load(text)
        else:
            raise ConfigurationValidationError(f"Unsupported configuration format: {config_format}")
    except (TypeError, ValueError, json.JSONDecodeError, yaml.YAMLError) as exc:
        raise ConfigurationValidationError(f"Generated {config_format.upper()} configuration is invalid: {exc}") from exc

    if not isinstance(validated, dict):
        raise ConfigurationValidationError("Generated configuration root must be an object")
    return text


def atomic_write_bytes(path: str | os.PathLike[str], data: bytes) -> Path:
    """Atomically replace one local configuration file in the same directory."""

    if not isinstance(data, bytes):
        raise TypeError("atomic_write_bytes data must be bytes")

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor = -1
    temporary: Path | None = None
    try:
        descriptor, raw_temporary = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
        temporary = Path(raw_temporary)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if target.exists():
            os.chmod(temporary, target.stat().st_mode)
        os.replace(temporary, target)
        temporary = None
        _fsync_directory(target.parent)
        return target
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def atomic_write_text(path: str | os.PathLike[str], text: str) -> Path:
    """UTF-8 convenience wrapper around :func:`atomic_write_bytes`."""

    return atomic_write_bytes(path, text.encode("utf-8"))


def backup_config(path: str | os.PathLike[str]) -> Path:
    """Create a durable sibling backup without altering the source file."""

    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup = source.with_name(f"{source.name}.bak.{stamp}")
    atomic_write_bytes(backup, source.read_bytes())
    return backup


def mcp_stdio_handshake(
    *,
    command: str = SERVER_COMMAND,
    args: Sequence[str] = SERVER_ARGS,
    timeout: float = 10.0,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> bool:
    """Start the configured server and perform one bounded MCP initialize request."""

    initialize = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": LATEST_PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "obsidian-vault-mcp-installer", "version": __version__},
        },
    }
    try:
        completed = runner(
            [command, *args],
            input=json.dumps(initialize, separators=(",", ":")) + "\n",
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False

    for line in completed.stdout.splitlines():
        try:
            response = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(response, dict) and response.get("id") == 1:
            return "result" in response and "error" not in response
    return False


def install_configuration(
    *,
    client: str,
    executable: str,
    config_path: str | os.PathLike[str],
    update: Mapping[str, Any],
    config_format: ConfigFormat,
    uninstall_instructions: str,
    dry_run: bool = False,
    which: Which | None = None,
    handshake: Handshake | None = None,
    merge: Merge = deep_merge,
) -> InstallResult:
    """Detect, merge, validate, write, handshake, and roll back one config."""

    detected = require_client(executable, which=which)
    target = Path(config_path).expanduser().resolve()
    existed = target.exists()
    existing = load_config(target, config_format=config_format)
    merged = merge(existing, update)
    serialized = serialize_config(merged, config_format=config_format)
    changed = not existed or merged != existing

    if dry_run:
        return InstallResult(
            client=client,
            executable=detected,
            config_path=target,
            backup_path=None,
            changed=changed,
            dry_run=True,
            handshake_performed=False,
            installed_config=merged,
            uninstall_instructions=uninstall_instructions,
        )

    backup_path: Path | None = None
    if changed:
        if existed:
            backup_path = backup_config(target)
        atomic_write_text(target, serialized)

    context = HandshakeContext(client=client, config_path=target)
    try:
        if not _invoke_handshake(handshake, context):
            raise RuntimeError("MCP server did not complete the initialize handshake")
    except Exception as exc:
        try:
            _rollback_config(target, changed=changed, existed=existed, backup_path=backup_path)
        except Exception as rollback_exc:
            raise HandshakeError(
                f"{client} handshake failed and configuration rollback also failed: {rollback_exc}"
            ) from exc
        raise HandshakeError(f"{client} handshake failed; configuration was restored: {exc}") from exc

    return InstallResult(
        client=client,
        executable=detected,
        config_path=target,
        backup_path=backup_path,
        changed=changed,
        dry_run=False,
        handshake_performed=True,
        installed_config=merged,
        uninstall_instructions=uninstall_instructions,
    )


def install_resource(
    *,
    client: str,
    executable: str,
    destination: str | os.PathLike[str],
    content: bytes,
    uninstall_instructions: str,
    dry_run: bool = False,
    which: Which | None = None,
    handshake: Handshake | None = None,
) -> InstallResult:
    """Transactionally install a packaged adapter such as the thin Pi Extension."""

    detected = require_client(executable, which=which)
    target = Path(destination).expanduser().resolve()
    if not isinstance(content, bytes):
        raise TypeError("install_resource content must be bytes")
    existed = target.exists()
    if existed and not target.is_file():
        raise ConfigurationValidationError(f"Extension destination is not a file: {target}")
    changed = not existed or target.read_bytes() != content

    if dry_run:
        return InstallResult(
            client=client,
            executable=detected,
            config_path=target,
            backup_path=None,
            changed=changed,
            dry_run=True,
            handshake_performed=False,
            installed_config={"extensionPath": str(target)},
            uninstall_instructions=uninstall_instructions,
        )

    backup_path: Path | None = None
    if changed:
        if existed:
            backup_path = backup_config(target)
        atomic_write_bytes(target, content)

    context = HandshakeContext(client=client, config_path=target)
    try:
        if not _invoke_handshake(handshake, context):
            raise RuntimeError("MCP server did not complete the initialize handshake")
    except Exception as exc:
        try:
            _rollback_config(target, changed=changed, existed=existed, backup_path=backup_path)
        except Exception as rollback_exc:
            raise HandshakeError(f"{client} handshake failed and Extension rollback also failed: {rollback_exc}") from exc
        raise HandshakeError(f"{client} handshake failed; Extension was restored: {exc}") from exc

    return InstallResult(
        client=client,
        executable=detected,
        config_path=target,
        backup_path=backup_path,
        changed=changed,
        dry_run=False,
        handshake_performed=True,
        installed_config={"extensionPath": str(target)},
        uninstall_instructions=uninstall_instructions,
    )


def _invoke_handshake(handshake: Handshake | None, context: HandshakeContext) -> bool:
    callback: Handshake = mcp_stdio_handshake if handshake is None else handshake
    try:
        signature = inspect.signature(callback)
    except (TypeError, ValueError):
        result = callback(context)
    else:
        try:
            signature.bind()
        except TypeError:
            try:
                signature.bind(context)
            except TypeError as exc:
                raise TypeError("handshake callback must accept zero arguments or one HandshakeContext") from exc
            result = callback(context)
        else:
            result = callback()
    return result is not False


def _rollback_config(path: Path, *, changed: bool, existed: bool, backup_path: Path | None) -> None:
    if not changed:
        return
    if existed:
        if backup_path is None:
            raise RuntimeError("existing configuration has no backup")
        atomic_write_bytes(path, backup_path.read_bytes())
    else:
        path.unlink(missing_ok=True)


def _fsync_directory(directory: Path) -> None:
    if os.name == "nt":
        return
    descriptor = -1
    try:
        descriptor = os.open(directory, os.O_RDONLY)
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        if descriptor >= 0:
            os.close(descriptor)
