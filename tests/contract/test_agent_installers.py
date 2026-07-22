from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import yaml

from obsidian_vault_mcp import __version__
from obsidian_vault_mcp.interfaces.agent_install import (
    claude,
    codex,
    hermes,
    install_agent,
    opencode,
    pi,
    workbuddy,
)
from obsidian_vault_mcp.interfaces.agent_install.common import (
    ClientNotFoundError,
    ConfigurationValidationError,
    HandshakeContext,
    HandshakeError,
    deep_merge,
    mcp_stdio_handshake,
)

ROOT = Path(__file__).resolve().parents[2]


def found(executable: str) -> str:
    return f"/test-bin/{executable}"


def test_stdio_handshake_reports_the_package_version() -> None:
    requests: list[dict[str, object]] = []

    def runner(command: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
        requests.append(json.loads(kwargs["input"]))
        return subprocess.CompletedProcess(
            command,
            0,
            stdout='{"jsonrpc":"2.0","id":1,"result":{}}\n',
            stderr="",
        )

    assert mcp_stdio_handshake(runner=runner)
    assert requests[0]["params"]["clientInfo"] == {
        "name": "obsidian-vault-mcp-installer",
        "version": __version__,
    }


@pytest.mark.parametrize("installer", [codex.install, claude.install])
def test_codex_and_claude_install_project_mcp_without_touching_other_servers(tmp_path: Path, installer) -> None:
    project = tmp_path / "project with spaces"
    project.mkdir()
    target = project / ".mcp.json"
    original = {
        "projectSetting": {"keep": True},
        "mcpServers": {"other": {"command": "other-server", "env": {"TOKEN": "keep"}}},
    }
    target.write_text(json.dumps(original), encoding="utf-8")
    handshakes: list[bool] = []

    result = installer(project, which=found, handshake=lambda: handshakes.append(True))

    installed = json.loads(target.read_text(encoding="utf-8"))
    assert installed["projectSetting"] == {"keep": True}
    assert installed["mcpServers"]["other"] == original["mcpServers"]["other"]
    assert installed["mcpServers"]["obsidian-literature"] == {
        "type": "stdio",
        "command": "obsidian-vault-mcp",
        "args": ["serve", "--transport", "stdio"],
        "env": {"OBSIDIAN_VAULT_PATH": "auto"},
    }
    assert result.backup_path is not None
    assert json.loads(result.backup_path.read_text(encoding="utf-8")) == original
    assert result.handshake_performed
    assert handshakes == [True]
    assert "obsidian-literature" in result.uninstall_instructions


def test_opencode_installs_the_portable_console_entrypoint(tmp_path: Path) -> None:
    target = tmp_path / "opencode.json"
    target.write_text(json.dumps({"mcp": {"keep": {"type": "remote", "url": "https://example.test"}}}), encoding="utf-8")

    result = opencode.install(tmp_path, which=found, handshake=lambda: True)

    config = json.loads(target.read_text(encoding="utf-8"))
    assert config["mcp"]["keep"]["url"] == "https://example.test"
    assert config["mcp"]["obsidian-literature"] == {
        "type": "local",
        "command": ["obsidian-vault-mcp", "serve", "--transport", "stdio"],
        "enabled": True,
    }
    assert result.changed


def test_hermes_deep_merges_and_validates_yaml(tmp_path: Path) -> None:
    target = tmp_path / ".hermes" / "config.yaml"
    target.parent.mkdir()
    target.write_text(
        "theme: dark\nmcp_servers:\n  keep:\n    command: keep-server\n    env:\n      KEEP: yes\n",
        encoding="utf-8",
    )

    hermes.install(tmp_path, which=found, handshake=lambda: None)

    config = yaml.safe_load(target.read_text(encoding="utf-8"))
    assert config["theme"] == "dark"
    assert config["mcp_servers"]["keep"]["command"] == "keep-server"
    assert config["mcp_servers"]["obsidian-literature"] == {
        "command": "obsidian-vault-mcp",
        "args": ["serve", "--transport", "stdio"],
        "env": {"OBSIDIAN_VAULT_PATH": "auto"},
        "enabled": True,
    }


def test_workbuddy_uses_its_project_level_config(tmp_path: Path) -> None:
    result = workbuddy.install(tmp_path, which=found, handshake=lambda: True)

    assert result.config_path == (tmp_path / ".workbuddy" / "mcp.json").resolve()
    config = json.loads(result.config_path.read_text(encoding="utf-8"))
    server = config["mcpServers"]["obsidian-literature"]
    assert server["command"] == "obsidian-vault-mcp"
    assert server["args"] == ["serve", "--transport", "stdio"]


def test_pi_installs_only_the_packaged_thin_extension(tmp_path: Path) -> None:
    result = pi.install(tmp_path, which=found, handshake=lambda: True)

    expected = (ROOT / "src" / "obsidian_vault_mcp" / "interfaces" / "agent_install" / "pi_extension.ts").read_bytes()
    canonical = (ROOT / "adapters" / "pi" / "index.ts").read_bytes()
    installed = result.config_path.read_bytes()
    assert result.config_path == (tmp_path / ".pi" / "extensions" / "obsidian-vault-mcp.ts").resolve()
    assert installed == expected == canonical
    assert b"execFile" in installed
    assert b'["call", toolName, "--json", jsonArguments]' in installed
    assert b"pi.registerTool" in installed
    assert not (tmp_path / ".pi" / "settings.json").exists()


def test_dry_run_detects_and_previews_without_writes_backup_or_handshake(tmp_path: Path) -> None:
    calls: list[object] = []

    result = claude.install(tmp_path, dry_run=True, which=lambda name: calls.append(name) or name, handshake=lambda: calls.append("handshake"))

    assert result.dry_run
    assert result.changed
    assert not result.handshake_performed
    assert result.backup_path is None
    assert not (tmp_path / ".mcp.json").exists()
    assert calls == ["claude"]


def test_missing_client_is_reported_before_any_write(tmp_path: Path) -> None:
    with pytest.raises(ClientNotFoundError, match="opencode"):
        opencode.install(tmp_path, which=lambda _name: None, handshake=lambda: True)

    assert not (tmp_path / "opencode.json").exists()


@pytest.mark.parametrize(
    ("installer", "relative_path", "malformed"),
    [
        (claude.install, Path(".mcp.json"), "{not json"),
        (hermes.install, Path(".hermes/config.yaml"), "mcp_servers: [unterminated"),
    ],
)
def test_malformed_existing_config_is_never_overwritten(tmp_path: Path, installer, relative_path: Path, malformed: str) -> None:
    target = tmp_path / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(malformed, encoding="utf-8")

    with pytest.raises(ConfigurationValidationError):
        installer(tmp_path, which=found, handshake=lambda: True)

    assert target.read_text(encoding="utf-8") == malformed
    assert not list(target.parent.glob(f"{target.name}.bak.*"))


def test_failed_handshake_restores_existing_config_from_backup(tmp_path: Path) -> None:
    target = tmp_path / ".mcp.json"
    original = b'{"mcpServers":{"keep":{"command":"keep"}}}\n'
    target.write_bytes(original)

    def fail(context: HandshakeContext) -> bool:
        assert context.client == "claude"
        assert context.config_path == target.resolve()
        return False

    with pytest.raises(HandshakeError, match="restored"):
        claude.install(tmp_path, which=found, handshake=fail)

    assert target.read_bytes() == original
    backups = list(tmp_path.glob(".mcp.json.bak.*"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == original


def test_failed_handshake_removes_a_new_config(tmp_path: Path) -> None:
    with pytest.raises(HandshakeError):
        workbuddy.install(tmp_path, which=found, handshake=lambda: False)

    assert not (tmp_path / ".workbuddy" / "mcp.json").exists()


def test_non_dry_run_handshakes_even_when_config_is_unchanged(tmp_path: Path) -> None:
    first = codex.install(tmp_path, which=found, handshake=lambda: True)
    calls: list[bool] = []

    second = codex.install(tmp_path, which=found, handshake=lambda: calls.append(True))

    assert first.changed
    assert not second.changed
    assert second.backup_path is None
    assert second.handshake_performed
    assert calls == [True]


def test_pi_failed_handshake_restores_previous_extension(tmp_path: Path) -> None:
    target = tmp_path / ".pi" / "extensions" / "obsidian-vault-mcp.ts"
    target.parent.mkdir(parents=True)
    target.write_text("export default 'old';\n", encoding="utf-8")

    with pytest.raises(HandshakeError):
        pi.install(tmp_path, which=found, handshake=lambda: False)

    assert target.read_text(encoding="utf-8") == "export default 'old';\n"


def test_dispatch_and_deep_merge_are_stable_and_non_mutating(tmp_path: Path) -> None:
    existing = {"mcpServers": {"keep": {"env": {"A": "1"}}}}
    update = {"mcpServers": {"added": {"command": "new"}}}
    assert deep_merge(existing, update) == {
        "mcpServers": {
            "keep": {"env": {"A": "1"}},
            "added": {"command": "new"},
        }
    }
    assert existing == {"mcpServers": {"keep": {"env": {"A": "1"}}}}

    result = install_agent("WORKBUDDY", tmp_path, dry_run=True, which=found, handshake=lambda: pytest.fail("dry-run handshook"))
    assert result.client == "workbuddy"
