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
from importlib import resources
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
Runner = Callable[..., subprocess.CompletedProcess[str]]

MARKETPLACE_PACKAGE = "obsidian_vault_mcp.resources.agent_marketplace"
MARKETPLACE_NAME = "obsidian-vault-mcp"
PLUGIN_NAME = "obsidian-literature"
PLUGIN_SELECTOR = f"{PLUGIN_NAME}@{MARKETPLACE_NAME}"


class AgentInstallError(RuntimeError):
    """Base class for expected Agent installer failures."""


class ClientNotFoundError(AgentInstallError):
    """Raised when the requested Agent executable cannot be found."""


class ConfigurationValidationError(AgentInstallError, ValueError):
    """Raised when an existing or generated client configuration is invalid."""


class HandshakeError(AgentInstallError):
    """Raised after a failed MCP handshake and configuration rollback."""


class MarketplaceConflictError(AgentInstallError):
    """Raised when a marketplace name is already bound to another source."""


@dataclass(frozen=True)
class HandshakeContext:
    """Information made available to an injected handshake callback."""

    client: str
    config_path: Path
    command: str = SERVER_COMMAND
    args: tuple[str, ...] = SERVER_ARGS


@dataclass(frozen=True)
class SkillInstallResult:
    """One project-local Agent Skill installation result."""

    name: str
    path: Path
    changed: bool
    action: str
    version: str
    managed_hash: str
    backup_path: Path | None = None

    def as_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["path"] = str(self.path)
        result["backup_path"] = str(self.backup_path) if self.backup_path else None
        return result


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
    config_changed: bool = False
    skill_directory: Path | None = None
    skill_manifest_path: Path | None = None
    skill_manifest_backup_path: Path | None = None
    skills: tuple[SkillInstallResult, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def uninstall_command(self) -> str:
        """Compatibility alias for callers that display one uninstall field."""

        return self.uninstall_instructions

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation for the CLI layer."""

        result = asdict(self)
        result["config_path"] = str(self.config_path)
        result["backup_path"] = str(self.backup_path) if self.backup_path else None
        result["skill_directory"] = str(self.skill_directory) if self.skill_directory else None
        result["skill_manifest_path"] = str(self.skill_manifest_path) if self.skill_manifest_path else None
        result["skill_manifest_backup_path"] = (
            str(self.skill_manifest_backup_path) if self.skill_manifest_backup_path else None
        )
        result["skills"] = [skill.as_dict() for skill in self.skills]
        result["warnings"] = list(self.warnings)
        return result


@dataclass(frozen=True)
class PluginInstallResult:
    """Description of a native Codex or Claude plugin installation."""

    client: str
    executable: str
    marketplace_name: str
    marketplace_path: Path
    plugin_selector: str
    plugin_version: str
    changed: bool
    dry_run: bool
    handshake_performed: bool
    marketplace_added: bool
    plugin_installed: bool
    marketplace_preexisting: bool
    plugin_preexisting: bool
    commands: tuple[tuple[str, ...], ...]
    uninstall_instructions: str

    @property
    def uninstall_command(self) -> str:
        """Compatibility alias for callers that display one uninstall field."""

        return self.uninstall_instructions

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation for the CLI layer."""

        result = asdict(self)
        result["marketplace_path"] = str(self.marketplace_path)
        result["commands"] = [list(command) for command in self.commands]
        return result


def packaged_marketplace_path(
    marketplace_path: str | os.PathLike[str] | None = None,
) -> Path:
    """Resolve the packaged, shared Codex/Claude marketplace directory."""

    if marketplace_path is None:
        traversable = resources.files(MARKETPLACE_PACKAGE)
        try:
            raw_path = os.fspath(traversable)
        except TypeError as exc:
            raise ConfigurationValidationError(
                "The packaged Agent marketplace is not available as a persistent filesystem directory"
            ) from exc
    else:
        raw_path = os.fspath(marketplace_path)

    root = Path(raw_path).expanduser().resolve()
    if not root.is_dir():
        raise ConfigurationValidationError(f"Agent plugin marketplace directory does not exist: {root}")
    return root


def install_native_plugin(
    *,
    client: str,
    executable: str,
    marketplace_path: str | os.PathLike[str],
    marketplace_manifest: str | os.PathLike[str],
    plugin_manifest: str | os.PathLike[str],
    marketplace_list_args: Sequence[str],
    plugin_list_args: Sequence[str],
    marketplace_add_args: Sequence[str],
    plugin_install_args: Sequence[str],
    plugin_uninstall_args: Sequence[str],
    marketplace_remove_args: Sequence[str],
    marketplace_records_key: str | None,
    marketplace_path_keys: Sequence[str],
    plugin_records_key: str | None,
    plugin_id_keys: Sequence[str],
    uninstall_instructions: str,
    plugin_required_fields: Mapping[str, Any] | None = None,
    dry_run: bool = False,
    which: Which | None = None,
    runner: Runner | None = None,
    handshake: Handshake | None = None,
) -> PluginInstallResult:
    """Install a bundled plugin with a client's native marketplace lifecycle."""

    detected = require_client(executable, which=which)
    root = packaged_marketplace_path(marketplace_path)
    version = _validate_native_plugin_bundle(
        root,
        marketplace_manifest=marketplace_manifest,
        plugin_manifest=plugin_manifest,
    )
    command_runner = subprocess.run if runner is None else runner

    marketplace_payload = _run_native_json(
        detected,
        marketplace_list_args,
        client=client,
        runner=command_runner,
    )
    marketplace_entries = _json_records(
        marketplace_payload,
        key=marketplace_records_key,
        description=f"{client} marketplace list",
    )
    named_marketplaces = [entry for entry in marketplace_entries if entry.get("name") == MARKETPLACE_NAME]
    for entry in named_marketplaces:
        configured_path = _first_string(entry, marketplace_path_keys)
        if configured_path is None or not _same_path(configured_path, root):
            source = configured_path or _describe_marketplace_source(entry)
            raise MarketplaceConflictError(
                f"{client} marketplace {MARKETPLACE_NAME!r} is already configured from {source!r}, "
                f"not {str(root)!r}. Remove the existing marketplace explicitly before installing this bundle."
            )
    marketplace_preexisting = bool(named_marketplaces)

    plugin_payload = _run_native_json(
        detected,
        plugin_list_args,
        client=client,
        runner=command_runner,
    )
    plugin_entries = _json_records(
        plugin_payload,
        key=plugin_records_key,
        description=f"{client} plugin list",
    )
    required_fields = {} if plugin_required_fields is None else dict(plugin_required_fields)
    matching_plugins = [
        entry
        for entry in plugin_entries
        if _first_string(entry, plugin_id_keys) == PLUGIN_SELECTOR
        and all(entry.get(key) == value for key, value in required_fields.items())
    ]
    installed_versions = {
        entry["version"]
        for entry in matching_plugins
        if isinstance(entry.get("version"), str) and entry["version"]
    }
    if installed_versions and installed_versions != {version}:
        found = ", ".join(sorted(installed_versions))
        raise AgentInstallError(
            f"{client} plugin {PLUGIN_SELECTOR} is installed at version {found}, but this bundle is {version}. "
            "Use the documented native update or remove-and-reinstall flow before rerunning the installer."
        )
    plugin_preexisting = bool(matching_plugins)

    add_marketplace = not marketplace_preexisting
    install_plugin = not plugin_preexisting
    planned_commands: list[tuple[str, ...]] = []
    if add_marketplace:
        planned_commands.append((detected, *map(str, marketplace_add_args)))
    if install_plugin:
        planned_commands.append((detected, *map(str, plugin_install_args)))

    if dry_run:
        return PluginInstallResult(
            client=client,
            executable=detected,
            marketplace_name=MARKETPLACE_NAME,
            marketplace_path=root,
            plugin_selector=PLUGIN_SELECTOR,
            plugin_version=version,
            changed=bool(planned_commands),
            dry_run=True,
            handshake_performed=False,
            marketplace_added=add_marketplace,
            plugin_installed=install_plugin,
            marketplace_preexisting=marketplace_preexisting,
            plugin_preexisting=plugin_preexisting,
            commands=tuple(planned_commands),
            uninstall_instructions=uninstall_instructions,
        )

    marketplace_added = False
    plugin_installed = False
    try:
        if add_marketplace:
            _run_native_command(
                detected,
                marketplace_add_args,
                client=client,
                runner=command_runner,
            )
            marketplace_added = True
        if install_plugin:
            _run_native_command(
                detected,
                plugin_install_args,
                client=client,
                runner=command_runner,
            )
            plugin_installed = True
    except Exception as exc:
        rollback_errors = _rollback_native_plugin(
            detected=detected,
            client=client,
            runner=command_runner,
            plugin_installed=plugin_installed,
            marketplace_added=marketplace_added,
            plugin_uninstall_args=plugin_uninstall_args,
            marketplace_remove_args=marketplace_remove_args,
        )
        if rollback_errors:
            raise AgentInstallError(
                f"{client} native plugin installation failed and rollback also failed: {'; '.join(rollback_errors)}"
            ) from exc
        raise AgentInstallError(f"{client} native plugin installation failed; newly added state was removed: {exc}") from exc

    context = HandshakeContext(client=client, config_path=(root / plugin_manifest).resolve())
    try:
        if not _invoke_handshake(handshake, context):
            raise RuntimeError("MCP server did not complete the initialize handshake")
    except Exception as exc:
        rollback_errors = _rollback_native_plugin(
            detected=detected,
            client=client,
            runner=command_runner,
            plugin_installed=plugin_installed,
            marketplace_added=marketplace_added,
            plugin_uninstall_args=plugin_uninstall_args,
            marketplace_remove_args=marketplace_remove_args,
        )
        if rollback_errors:
            raise HandshakeError(
                f"{client} plugin handshake failed and native installation rollback also failed: "
                f"{'; '.join(rollback_errors)}"
            ) from exc
        if plugin_installed or marketplace_added:
            raise HandshakeError(f"{client} plugin handshake failed; newly installed native plugin state was removed") from exc
        raise HandshakeError(f"{client} plugin handshake failed; pre-existing native plugin state was left unchanged") from exc

    return PluginInstallResult(
        client=client,
        executable=detected,
        marketplace_name=MARKETPLACE_NAME,
        marketplace_path=root,
        plugin_selector=PLUGIN_SELECTOR,
        plugin_version=version,
        changed=marketplace_added or plugin_installed,
        dry_run=False,
        handshake_performed=True,
        marketplace_added=marketplace_added,
        plugin_installed=plugin_installed,
        marketplace_preexisting=marketplace_preexisting,
        plugin_preexisting=plugin_preexisting,
        commands=tuple(planned_commands),
        uninstall_instructions=uninstall_instructions,
    )


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
    project_root: str | os.PathLike[str] | None = None,
    skill_directory: str | os.PathLike[str] | None = None,
    warnings: Sequence[str] = (),
) -> InstallResult:
    """Install one client config and its optional project-local Skill set."""

    detected = require_client(executable, which=which)
    target = Path(config_path).expanduser().resolve()
    existed = target.exists()
    existing = load_config(target, config_format=config_format)
    merged = merge(existing, update)
    serialized = serialize_config(merged, config_format=config_format)
    config_changed = not existed or merged != existing

    skill_plan = None
    if skill_directory is not None:
        if project_root is None:
            raise ValueError("project_root is required when skill_directory is provided")
        from .skill_distribution import plan_skill_distribution

        skill_plan = plan_skill_distribution(
            client=client,
            project_root=project_root,
            skill_directory=skill_directory,
        )
    skill_preview = skill_plan.results() if skill_plan is not None else ()
    changed = config_changed or bool(skill_plan and skill_plan.changed)

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
            config_changed=config_changed,
            skill_directory=skill_plan.skill_directory if skill_plan is not None else None,
            skill_manifest_path=skill_plan.manifest_path if skill_plan is not None else None,
            skills=skill_preview,
            warnings=tuple(warnings),
        )

    backup_path: Path | None = None
    if config_changed:
        if existed:
            backup_path = backup_config(target)
        atomic_write_text(target, serialized)

    skill_receipt = None
    if skill_plan is not None:
        try:
            from .skill_distribution import apply_skill_distribution

            skill_receipt = apply_skill_distribution(skill_plan)
        except Exception as exc:
            try:
                _rollback_config(target, changed=config_changed, existed=existed, backup_path=backup_path)
            except Exception as rollback_exc:
                raise AgentInstallError(
                    f"{client} Skill installation failed and configuration rollback also failed: {rollback_exc}"
                ) from exc
            raise AgentInstallError(f"{client} Skill installation failed; configuration was restored: {exc}") from exc

    context = HandshakeContext(client=client, config_path=target)
    try:
        if not _invoke_handshake(handshake, context):
            raise RuntimeError("MCP server did not complete the initialize handshake")
    except Exception as exc:
        rollback_errors: list[str] = []
        if skill_receipt is not None:
            try:
                from .skill_distribution import rollback_skill_distribution

                rollback_skill_distribution(skill_receipt)
            except Exception as rollback_exc:
                rollback_errors.append(f"Skills: {rollback_exc}")
        try:
            _rollback_config(target, changed=config_changed, existed=existed, backup_path=backup_path)
        except Exception as rollback_exc:
            rollback_errors.append(f"configuration: {rollback_exc}")
        if rollback_errors:
            raise HandshakeError(
                f"{client} handshake failed and installation rollback also failed: {'; '.join(rollback_errors)}"
            ) from exc
        raise HandshakeError(f"{client} handshake failed; configuration and Skills were restored: {exc}") from exc

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
        config_changed=config_changed,
        skill_directory=skill_plan.skill_directory if skill_plan is not None else None,
        skill_manifest_path=skill_plan.manifest_path if skill_plan is not None else None,
        skill_manifest_backup_path=skill_receipt.manifest_backup_path if skill_receipt is not None else None,
        skills=skill_receipt.results if skill_receipt is not None else (),
        warnings=tuple(warnings),
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


def _validate_native_plugin_bundle(
    root: Path,
    *,
    marketplace_manifest: str | os.PathLike[str],
    plugin_manifest: str | os.PathLike[str],
) -> str:
    marketplace_path = (root / marketplace_manifest).resolve()
    plugin_path = (root / plugin_manifest).resolve()
    if root not in marketplace_path.parents or root not in plugin_path.parents:
        raise ConfigurationValidationError("Agent plugin manifest paths must remain inside the marketplace directory")

    marketplace = load_config(marketplace_path, config_format="json")
    if marketplace.get("name") != MARKETPLACE_NAME:
        raise ConfigurationValidationError(
            f"Marketplace manifest at {marketplace_path} must declare name {MARKETPLACE_NAME!r}"
        )
    plugin = load_config(plugin_path, config_format="json")
    if plugin.get("name") != PLUGIN_NAME:
        raise ConfigurationValidationError(f"Plugin manifest at {plugin_path} must declare name {PLUGIN_NAME!r}")
    version = plugin.get("version")
    if not isinstance(version, str) or not version.strip():
        raise ConfigurationValidationError(f"Plugin manifest at {plugin_path} must declare a non-empty version")
    return version


def _run_native_json(
    executable: str,
    args: Sequence[str],
    *,
    client: str,
    runner: Runner,
) -> Any:
    completed = _run_native_command(executable, args, client=client, runner=runner)
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise AgentInstallError(f"{client} returned invalid JSON for {' '.join(map(str, args))}: {exc}") from exc


def _run_native_command(
    executable: str,
    args: Sequence[str],
    *,
    client: str,
    runner: Runner,
) -> subprocess.CompletedProcess[str]:
    command = [executable, *map(str, args)]
    try:
        completed = runner(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise AgentInstallError(f"Could not run {client} native plugin command: {exc}") from exc
    if completed.returncode != 0:
        stdout = (completed.stdout or "").strip()
        stderr = (completed.stderr or "").strip()
        detail = stderr or stdout or f"exit code {completed.returncode}"
        raise AgentInstallError(f"{client} native plugin command failed ({' '.join(command)}): {detail}")
    return completed


def _json_records(payload: Any, *, key: str | None, description: str) -> list[Mapping[str, Any]]:
    records = payload if key is None else payload.get(key) if isinstance(payload, Mapping) else None
    if not isinstance(records, list) or not all(isinstance(record, Mapping) for record in records):
        raise AgentInstallError(f"{description} returned an unexpected JSON structure")
    return records


def _first_string(record: Mapping[str, Any], keys: Sequence[str]) -> str | None:
    for key in keys:
        value = record.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _describe_marketplace_source(record: Mapping[str, Any]) -> str:
    for key in ("url", "repo", "source", "installLocation"):
        value = record.get(key)
        if isinstance(value, str) and value:
            return value
    return "an unknown source"


def _same_path(left: str | os.PathLike[str], right: str | os.PathLike[str]) -> bool:
    left_path = Path(_strip_extended_windows_prefix(os.fspath(left))).expanduser()
    right_path = Path(_strip_extended_windows_prefix(os.fspath(right))).expanduser()
    try:
        return os.path.samefile(left_path, right_path)
    except (OSError, ValueError):
        left_normalized = os.path.normcase(os.path.abspath(os.path.realpath(left_path)))
        right_normalized = os.path.normcase(os.path.abspath(os.path.realpath(right_path)))
        return left_normalized == right_normalized


def _strip_extended_windows_prefix(path: str) -> str:
    if path.startswith("\\\\?\\UNC\\"):
        return "\\\\" + path[8:]
    if path.startswith("\\\\?\\"):
        return path[4:]
    return path


def _rollback_native_plugin(
    *,
    detected: str,
    client: str,
    runner: Runner,
    plugin_installed: bool,
    marketplace_added: bool,
    plugin_uninstall_args: Sequence[str],
    marketplace_remove_args: Sequence[str],
) -> list[str]:
    errors: list[str] = []
    if plugin_installed:
        try:
            _run_native_command(detected, plugin_uninstall_args, client=client, runner=runner)
        except Exception as exc:
            errors.append(f"plugin removal: {exc}")
    if marketplace_added:
        try:
            _run_native_command(detected, marketplace_remove_args, client=client, runner=runner)
        except Exception as exc:
            errors.append(f"marketplace removal: {exc}")
    return errors


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
