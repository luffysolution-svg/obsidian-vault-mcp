from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import yaml

from obsidian_vault_mcp import __version__
from obsidian_vault_mcp.application.skill_service import (
    MANAGED_END,
    MANAGED_START,
    SKILL_NAMES,
    SkillResourceService,
    extract_managed_block,
)
from obsidian_vault_mcp.interfaces.agent_install import (
    claude,
    codex,
    hermes,
    install_agent,
    opencode,
    pi,
    skill_distribution,
    workbuddy,
)
from obsidian_vault_mcp.interfaces.agent_install.common import (
    MARKETPLACE_NAME,
    PLUGIN_SELECTOR,
    AgentInstallError,
    ClientNotFoundError,
    ConfigurationValidationError,
    HandshakeContext,
    HandshakeError,
    MarketplaceConflictError,
    deep_merge,
    mcp_stdio_handshake,
    packaged_marketplace_path,
)
from obsidian_vault_mcp.interfaces.agent_install.skill_distribution import (
    SKILL_MANIFEST_NAME,
    SKILL_MANIFEST_SCHEMA_VERSION,
)

ROOT = Path(__file__).resolve().parents[2]


def found(executable: str) -> str:
    return f"/test-bin/{executable}"


def test_stdio_handshake_reports_the_package_version() -> None:
    requests: list[list[dict[str, object]]] = []

    def runner(command: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
        requests.append(
            [
                json.loads(line)
                for line in kwargs["input"].splitlines()
                if line
            ]
        )
        tools = [{"name": f"tool-{index}"} for index in range(31)]
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=(
                '{"jsonrpc":"2.0","id":1,"result":{}}\n'
                + json.dumps({"jsonrpc": "2.0", "id": 2, "result": {"tools": tools}})
                + "\n"
            ),
            stderr="",
        )

    assert mcp_stdio_handshake(runner=runner)
    assert requests[0][0]["params"]["clientInfo"] == {
        "name": "obsidian-vault-mcp-installer",
        "version": __version__,
    }
    assert [message["method"] for message in requests[0]] == [
        "initialize",
        "notifications/initialized",
        "tools/list",
    ]


def test_stdio_handshake_rejects_an_old_tool_surface() -> None:
    calls = 0

    def runner(command: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        tools = [{"name": f"tool-{index}"} for index in range(26)]
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=(
                '{"jsonrpc":"2.0","id":1,"result":{}}\n'
                + json.dumps({"jsonrpc": "2.0", "id": 2, "result": {"tools": tools}})
                + "\n"
            ),
            stderr="",
        )

    assert not mcp_stdio_handshake(runner=runner)
    assert calls == 1


def test_stdio_handshake_retries_one_incomplete_successful_response() -> None:
    calls = 0

    def runner(command: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        tools = [{"name": f"tool-{index}"} for index in range(31)]
        tools_response = (
            json.dumps({"jsonrpc": "2.0", "id": 2, "result": {"tools": tools}})
            + "\n"
            if calls == 2
            else ""
        )
        return subprocess.CompletedProcess(
            command,
            0,
            stdout='{"jsonrpc":"2.0","id":1,"result":{}}\n' + tools_response,
            stderr="",
        )

    assert mcp_stdio_handshake(runner=runner)
    assert calls == 2


@pytest.mark.parametrize(
    ("installer", "marketplaces", "plugins", "add_args", "install_args", "manifest"),
    [
        (
            codex.install,
            {"marketplaces": []},
            {"installed": [], "available": []},
            ("plugin", "marketplace", "add", "{root}", "--json"),
            ("plugin", "add", PLUGIN_SELECTOR, "--json"),
            Path("plugins/obsidian-literature/.codex-plugin/plugin.json"),
        ),
        (
            claude.install,
            [],
            [],
            ("plugin", "marketplace", "add", "{root}", "--scope", "user"),
            ("plugin", "install", PLUGIN_SELECTOR, "--scope", "user"),
            Path("plugins/obsidian-literature/.claude-plugin/plugin.json"),
        ),
    ],
)
def test_codex_and_claude_use_native_plugin_commands_without_project_writes(
    tmp_path: Path,
    installer,
    marketplaces,
    plugins,
    add_args: tuple[str, ...],
    install_args: tuple[str, ...],
    manifest: Path,
) -> None:
    project = tmp_path / "project with spaces"
    project.mkdir()
    target = project / ".mcp.json"
    original = b'{"mcpServers":{"keep":{"command":"keep"}}}\n'
    target.write_bytes(original)
    calls: list[tuple[str, ...]] = []

    def runner(command: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
        calls.append(tuple(command))
        payloads = [marketplaces, plugins]
        stdout = json.dumps(payloads[len(calls) - 1]) if len(calls) <= 2 else "installed\n"
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    handshakes: list[HandshakeContext] = []
    result = installer(project, which=found, runner=runner, handshake=lambda context: handshakes.append(context))
    root = packaged_marketplace_path()
    executable = found(result.client)
    expected_add = tuple(str(root) if value == "{root}" else value for value in add_args)

    assert calls == [
        (executable, "plugin", "marketplace", "list", "--json"),
        (executable, "plugin", "list", "--json"),
        (executable, *expected_add),
        (executable, *install_args),
    ]
    assert result.commands == tuple(calls[2:])
    assert result.marketplace_added and result.plugin_installed and result.changed
    assert result.handshake_performed
    assert handshakes == [HandshakeContext(client=result.client, config_path=(root / manifest).resolve())]
    assert target.read_bytes() == original
    assert not (project / ".agents").exists()
    assert not (project / ".claude").exists()
    assert json.loads(json.dumps(result.as_dict()))["plugin_selector"] == PLUGIN_SELECTOR
    assert "plugin" in result.uninstall_instructions


@pytest.mark.parametrize(
    ("installer", "marketplaces", "plugins"),
    [
        (
            codex.install,
            {"marketplaces": [{"name": MARKETPLACE_NAME, "root": "{root}"}]},
            {"installed": [{"pluginId": PLUGIN_SELECTOR, "version": __version__}], "available": []},
        ),
        (
            claude.install,
            [{"name": MARKETPLACE_NAME, "source": "directory", "path": "{root}"}],
            [{"id": PLUGIN_SELECTOR, "scope": "user", "version": __version__}],
        ),
    ],
)
def test_native_plugin_install_is_idempotent_after_list_detection(installer, marketplaces, plugins) -> None:
    root = packaged_marketplace_path()
    marketplaces = json.loads(json.dumps(marketplaces).replace("{root}", str(root).replace("\\", "\\\\")))
    calls: list[tuple[str, ...]] = []

    def runner(command: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
        calls.append(tuple(command))
        payload = marketplaces if len(calls) == 1 else plugins
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps(payload), stderr="")

    handshakes: list[bool] = []
    result = installer(which=found, runner=runner, handshake=lambda: handshakes.append(True))

    assert [call[1:] for call in calls] == [
        ("plugin", "marketplace", "list", "--json"),
        ("plugin", "list", "--json"),
    ]
    assert result.marketplace_preexisting and result.plugin_preexisting
    assert not result.marketplace_added and not result.plugin_installed
    assert not result.changed
    assert result.commands == ()
    assert result.handshake_performed
    assert handshakes == [True]


@pytest.mark.parametrize(
    ("installer", "marketplaces", "plugins", "upgrade_commands", "forbidden_command"),
    [
        (
            codex.install,
            {"marketplaces": [{"name": MARKETPLACE_NAME, "root": "{root}"}]},
            {"installed": [{"pluginId": PLUGIN_SELECTOR, "version": "2.0.1"}], "available": []},
            (f"codex plugin add {PLUGIN_SELECTOR}",),
            f"codex plugin remove {PLUGIN_SELECTOR}",
        ),
        (
            claude.install,
            [{"name": MARKETPLACE_NAME, "source": "directory", "path": "{root}"}],
            [{"id": PLUGIN_SELECTOR, "scope": "user", "version": "2.0.1"}],
            (
                f"claude plugin marketplace update {MARKETPLACE_NAME}",
                f"claude plugin update {PLUGIN_SELECTOR}",
                "restart Claude Code",
            ),
            "claude plugin uninstall",
        ),
    ],
)
def test_native_plugin_install_refuses_to_silently_keep_an_old_version(
    installer,
    marketplaces,
    plugins,
    upgrade_commands,
    forbidden_command,
) -> None:
    root = packaged_marketplace_path()
    marketplaces = json.loads(json.dumps(marketplaces).replace("{root}", str(root).replace("\\", "\\\\")))
    payloads = iter((marketplaces, plugins))

    def runner(command: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps(next(payloads)), stderr="")

    with pytest.raises(AgentInstallError, match="installed at version 2.0.1") as error:
        installer(which=found, runner=runner, handshake=lambda: pytest.fail("version mismatch handshook"))
    message = str(error.value)
    assert all(command in message for command in upgrade_commands)
    assert forbidden_command not in message


def test_native_plugin_install_refuses_to_downgrade_a_newer_plugin() -> None:
    root = packaged_marketplace_path()
    payloads = iter(
        (
            {"marketplaces": [{"name": MARKETPLACE_NAME, "root": str(root)}]},
            {
                "installed": [
                    {
                        "pluginId": PLUGIN_SELECTOR,
                        "version": "99.0.0",
                    }
                ],
                "available": [],
            },
        )
    )

    def runner(command: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps(next(payloads)), stderr="")

    with pytest.raises(AgentInstallError, match="refusing to downgrade"):
        codex.install(
            which=found,
            runner=runner,
            handshake=lambda: pytest.fail("downgrade handshook"),
        )


@pytest.mark.parametrize(
    ("installer", "marketplaces"),
    [
        (codex.install, {"marketplaces": [{"name": MARKETPLACE_NAME, "root": "{other}"}]}),
        (claude.install, [{"name": MARKETPLACE_NAME, "source": "directory", "path": "{other}"}]),
    ],
)
def test_native_plugin_install_rejects_same_marketplace_name_from_another_path(
    tmp_path: Path,
    installer,
    marketplaces,
) -> None:
    other = (tmp_path / "different marketplace").resolve()
    marketplaces = json.loads(json.dumps(marketplaces).replace("{other}", str(other).replace("\\", "\\\\")))
    calls: list[tuple[str, ...]] = []

    def runner(command: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
        calls.append(tuple(command))
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps(marketplaces), stderr="")

    with pytest.raises(MarketplaceConflictError, match="already configured"):
        installer(which=found, runner=runner, handshake=lambda: pytest.fail("conflict handshook"))

    assert [call[1:] for call in calls] == [("plugin", "marketplace", "list", "--json")]


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


def test_hermes_deep_merges_and_validates_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / ".hermes" / "config.yaml"
    target.parent.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(target.parent))
    target.write_text(
        "theme: dark\nmcp_servers:\n  keep:\n    command: keep-server\n    env:\n      KEEP: yes\n",
        encoding="utf-8",
    )

    result = hermes.install(tmp_path / "ignored-project", which=found, handshake=lambda: None)

    assert result.config_path == target.resolve()
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

    assert result.executable == found("codebuddy")
    assert result.config_path == (tmp_path / ".workbuddy" / "mcp.json").resolve()
    config = json.loads(result.config_path.read_text(encoding="utf-8"))
    server = config["mcpServers"]["obsidian-literature"]
    assert server["command"] == "obsidian-vault-mcp"
    assert server["args"] == ["serve", "--transport", "stdio"]


def test_workbuddy_falls_back_to_cbc_executable(tmp_path: Path) -> None:
    result = workbuddy.install(
        tmp_path,
        dry_run=True,
        which=lambda executable: found(executable) if executable == "cbc" else None,
        handshake=lambda: pytest.fail("dry-run handshook"),
    )

    assert result.executable == found("cbc")
    assert not result.config_path.exists()


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
    assert result.skill_directory is None
    assert result.skills == ()
    assert not (tmp_path / ".pi" / "skills").exists()


def test_opencode_distributes_all_canonical_project_skills(tmp_path: Path) -> None:
    result = opencode.install(tmp_path, which=found, handshake=lambda: True)
    expected_directory = (tmp_path / ".opencode" / "skills").resolve()
    canonical = SkillResourceService()

    assert result.skill_directory == expected_directory
    assert result.config_changed is True
    assert [skill.name for skill in result.skills] == list(SKILL_NAMES)
    assert all(skill.action == "install" and skill.changed for skill in result.skills)
    for name in SKILL_NAMES:
        for relative_path, content in canonical.files(name).items():
            assert (expected_directory / name / relative_path).read_text(encoding="utf-8") == content

    manifest = json.loads((expected_directory / SKILL_MANIFEST_NAME).read_text(encoding="utf-8"))
    assert manifest["schemaVersion"] == SKILL_MANIFEST_SCHEMA_VERSION
    assert manifest["client"] == result.client
    assert set(manifest["skills"]) == set(SKILL_NAMES)
    assert all("files" in entry for entry in manifest["skills"].values())
    assert json.loads(json.dumps(result.as_dict()))["skills"][0]["path"].endswith("SKILL.md")
    assert "seven managed Skill folders" in result.uninstall_instructions


@pytest.mark.parametrize(
    ("installer", "unsupported_directory"),
    [
        (hermes.install, Path(".hermes/skills")),
        (workbuddy.install, Path(".workbuddy/skills")),
    ],
)
def test_clients_without_verified_project_skill_contracts_do_not_guess_a_directory(
    tmp_path: Path,
    installer,
    unsupported_directory: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / ".hermes"))
    result = installer(tmp_path, which=found, handshake=lambda: True)

    assert result.skill_directory is None
    assert result.skills == ()
    assert result.warnings and "were not installed" in result.warnings[0]
    assert not (tmp_path / unsupported_directory).exists()
    assert result.as_dict()["warnings"] == list(result.warnings)


def test_tracked_skill_upgrade_preserves_user_text_and_reports_backups(tmp_path: Path) -> None:
    first = opencode.install(tmp_path, which=found, handshake=lambda: True)
    skill_path = first.skill_directory / "compare-papers" / "SKILL.md"
    manifest_path = first.skill_manifest_path
    current = extract_managed_block(skill_path.read_text(encoding="utf-8"))
    old_text = (
        f"{current.before}{MANAGED_START}\nold tracked official block\n{MANAGED_END}{current.after.rstrip()}\n\n"
        "Local customization that must survive.\n"
    )
    skill_path.write_text(old_text, encoding="utf-8")
    old_hash = extract_managed_block(old_text).sha256
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["skills"]["compare-papers"] = {"version": "0.9.0", "managedHash": old_hash}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    upgraded = opencode.install(tmp_path, which=found, handshake=lambda: True)
    installed = skill_path.read_text(encoding="utf-8")
    result = next(skill for skill in upgraded.skills if skill.name == "compare-papers")

    assert "old tracked official block" not in installed
    assert "Local customization that must survive." in installed
    assert extract_managed_block(installed).sha256 == extract_managed_block(SkillResourceService().read("compare-papers")).sha256
    assert result.action == "upgrade"
    assert result.backup_path is not None
    assert result.backup_path.read_text(encoding="utf-8") == old_text
    assert upgraded.skill_manifest_backup_path is not None


def test_modified_managed_skill_block_aborts_before_any_write(tmp_path: Path) -> None:
    first = opencode.install(tmp_path, which=found, handshake=lambda: True)
    skill_path = first.skill_directory / "full-read" / "SKILL.md"
    current = extract_managed_block(skill_path.read_text(encoding="utf-8"))
    tampered = f"{current.before}{MANAGED_START}\nuser changed managed content\n{MANAGED_END}{current.after}"
    skill_path.write_text(tampered, encoding="utf-8")
    before_config = first.config_path.read_bytes()
    before_manifest = first.skill_manifest_path.read_bytes()

    with pytest.raises(ConfigurationValidationError, match="managed-block-modified"):
        opencode.install(tmp_path, which=found, handshake=lambda: pytest.fail("validation failure handshook"))

    assert first.config_path.read_bytes() == before_config
    assert first.skill_manifest_path.read_bytes() == before_manifest
    assert skill_path.read_text(encoding="utf-8") == tampered


def test_modified_tracked_reference_aborts_before_any_write(tmp_path: Path) -> None:
    first = opencode.install(tmp_path, which=found, handshake=lambda: True)
    reference = first.skill_directory / "full-read" / "references" / "output-contract.md"
    before_config = first.config_path.read_bytes()
    before_manifest = first.skill_manifest_path.read_bytes()
    reference.write_text("user replacement\n", encoding="utf-8")

    with pytest.raises(ConfigurationValidationError, match="tracked reference"):
        opencode.install(tmp_path, which=found, handshake=lambda: pytest.fail("validation failure handshook"))

    assert first.config_path.read_bytes() == before_config
    assert first.skill_manifest_path.read_bytes() == before_manifest
    assert reference.read_text(encoding="utf-8") == "user replacement\n"


def test_upgrade_removes_only_manifest_tracked_legacy_skill_files(tmp_path: Path) -> None:
    skill_directory = tmp_path / ".opencode" / "skills"
    legacy = skill_directory / "structured-paper-note" / "SKILL.md"
    legacy.parent.mkdir(parents=True)
    legacy_text = (
        "---\nname: structured-paper-note\ndescription: old\n---\n\n"
        f"{MANAGED_START}\nold managed body\n{MANAGED_END}\n\n"
        "## User Customizations\n\nPreserve this in the backup.\n"
    )
    legacy.write_text(legacy_text, encoding="utf-8")
    private = skill_directory / "my-private-skill" / "SKILL.md"
    private.parent.mkdir(parents=True)
    private.write_text("private\n", encoding="utf-8")
    manifest_path = skill_directory / SKILL_MANIFEST_NAME
    manifest_path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "client": "opencode",
                "skills": {
                    "structured-paper-note": {
                        "version": "1.0.0",
                        "managedHash": extract_managed_block(legacy_text).sha256,
                    }
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = opencode.install(tmp_path, which=found, handshake=lambda: True)

    assert not legacy.exists()
    backups = list(legacy.parent.glob("SKILL.md.bak.*"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == legacy_text
    assert private.read_text(encoding="utf-8") == "private\n"
    updated_manifest = json.loads(result.skill_manifest_path.read_text(encoding="utf-8"))
    assert set(updated_manifest["skills"]) == set(SKILL_NAMES)
    removal = next(skill for skill in result.skills if skill.name == "structured-paper-note")
    assert removal.action == "remove"
    assert removal.backup_path == backups[0]


def test_upgrade_never_removes_unknown_manifest_tracked_skill(tmp_path: Path) -> None:
    skill_directory = tmp_path / ".opencode" / "skills"
    custom = skill_directory / "team-private-skill" / "SKILL.md"
    custom.parent.mkdir(parents=True)
    custom_text = (
        "---\nname: team-private-skill\ndescription: private\n---\n\n"
        f"{MANAGED_START}\nprivate managed body\n{MANAGED_END}\n"
    )
    custom.write_text(custom_text, encoding="utf-8")
    manifest_path = skill_directory / SKILL_MANIFEST_NAME
    manifest_path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "client": "opencode",
                "skills": {
                    "team-private-skill": {
                        "version": "1.0.0",
                        "managedHash": extract_managed_block(custom_text).sha256,
                    }
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = opencode.install(tmp_path, which=found, handshake=lambda: True)

    assert custom.read_text(encoding="utf-8") == custom_text
    assert not list(custom.parent.glob("SKILL.md.bak.*"))
    assert "team-private-skill" not in {skill.name for skill in result.skills}


def test_failed_handshake_rolls_back_new_config_and_all_skills(tmp_path: Path) -> None:
    with pytest.raises(HandshakeError, match="configuration and Skills were restored"):
        opencode.install(tmp_path, which=found, handshake=lambda: False)

    assert not (tmp_path / "opencode.json").exists()
    assert not list(tmp_path.glob(".opencode/skills/*/SKILL.md"))
    assert not list(tmp_path.glob(".opencode/skills/*/references/**/*.md"))
    assert not (tmp_path / ".opencode" / "skills" / SKILL_MANIFEST_NAME).exists()


def test_skill_write_failure_rolls_back_config_and_every_partial_skill(tmp_path: Path, monkeypatch) -> None:
    original_write = skill_distribution.atomic_write_text
    skill_writes = 0

    def fail_second_skill(path: Path, text: str) -> Path:
        nonlocal skill_writes
        if path.name == "SKILL.md":
            skill_writes += 1
            if skill_writes == 2:
                raise OSError("simulated Skill write failure")
        return original_write(path, text)

    monkeypatch.setattr(skill_distribution, "atomic_write_text", fail_second_skill)
    with pytest.raises(AgentInstallError, match="configuration was restored"):
        opencode.install(tmp_path, which=found, handshake=lambda: pytest.fail("failed Skill write handshook"))

    assert not (tmp_path / "opencode.json").exists()
    assert not list(tmp_path.glob(".opencode/skills/*/SKILL.md"))
    assert not list(tmp_path.glob(".opencode/skills/*/references/**/*.md"))
    assert not (tmp_path / ".opencode" / "skills" / SKILL_MANIFEST_NAME).exists()


def test_dry_run_detects_and_previews_without_writes_backup_or_handshake(tmp_path: Path) -> None:
    calls: list[tuple[str, ...]] = []

    def runner(command: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
        calls.append(tuple(command))
        return subprocess.CompletedProcess(command, 0, stdout="[]", stderr="")

    result = claude.install(
        tmp_path,
        dry_run=True,
        which=found,
        runner=runner,
        handshake=lambda: pytest.fail("dry-run handshook"),
    )

    assert result.dry_run
    assert result.changed
    assert not result.handshake_performed
    assert result.marketplace_added and result.plugin_installed
    assert not result.marketplace_preexisting and not result.plugin_preexisting
    assert not (tmp_path / ".mcp.json").exists()
    assert not (tmp_path / ".claude").exists()
    assert len(result.commands) == 2
    assert [call[1:] for call in calls] == [
        ("plugin", "marketplace", "list", "--json"),
        ("plugin", "list", "--json"),
    ]


def test_missing_client_is_reported_before_any_write(tmp_path: Path) -> None:
    with pytest.raises(ClientNotFoundError, match="opencode"):
        opencode.install(tmp_path, which=lambda _name: None, handshake=lambda: True)

    assert not (tmp_path / "opencode.json").exists()

    with pytest.raises(ClientNotFoundError, match="codebuddy or cbc"):
        workbuddy.install(tmp_path, which=lambda _name: None, handshake=lambda: True)

    assert not (tmp_path / ".workbuddy" / "mcp.json").exists()


@pytest.mark.parametrize(
    ("installer", "relative_path", "malformed"),
    [
        (opencode.install, Path("opencode.json"), "{not json"),
        (hermes.install, Path(".hermes/config.yaml"), "mcp_servers: [unterminated"),
    ],
)
def test_malformed_existing_config_is_never_overwritten(
    tmp_path: Path,
    installer,
    relative_path: Path,
    malformed: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / ".hermes"))
    target.write_text(malformed, encoding="utf-8")

    with pytest.raises(ConfigurationValidationError):
        installer(tmp_path, which=found, handshake=lambda: True)

    assert target.read_text(encoding="utf-8") == malformed
    assert not list(target.parent.glob(f"{target.name}.bak.*"))


def test_failed_handshake_restores_existing_config_from_backup(tmp_path: Path) -> None:
    target = tmp_path / "opencode.json"
    original = b'{"mcp":{"keep":{"command":["keep"]}}}\n'
    target.write_bytes(original)

    def fail(context: HandshakeContext) -> bool:
        assert context.client == "opencode"
        assert context.config_path == target.resolve()
        return False

    with pytest.raises(HandshakeError, match="restored"):
        opencode.install(tmp_path, which=found, handshake=fail)

    assert target.read_bytes() == original
    backups = list(tmp_path.glob("opencode.json.bak.*"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == original


def test_failed_handshake_removes_a_new_config(tmp_path: Path) -> None:
    with pytest.raises(HandshakeError):
        workbuddy.install(tmp_path, which=found, handshake=lambda: False)

    assert not (tmp_path / ".workbuddy" / "mcp.json").exists()


def test_native_plugin_handshake_failure_rolls_back_only_new_state() -> None:
    calls: list[tuple[str, ...]] = []

    def runner(command: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
        calls.append(tuple(command))
        if len(calls) == 1:
            stdout = '{"marketplaces": []}'
        elif len(calls) == 2:
            stdout = '{"installed": [], "available": []}'
        else:
            stdout = "{}"
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    with pytest.raises(HandshakeError, match="newly installed native plugin state was removed"):
        codex.install(which=found, runner=runner, handshake=lambda: False)

    assert [call[1:] for call in calls[-2:]] == [
        ("plugin", "remove", PLUGIN_SELECTOR, "--json"),
        ("plugin", "marketplace", "remove", MARKETPLACE_NAME, "--json"),
    ]


def test_claude_handshake_failure_rolls_back_only_user_scope() -> None:
    calls: list[tuple[str, ...]] = []

    def runner(command: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
        calls.append(tuple(command))
        stdout = "[]" if len(calls) <= 2 else "{}"
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    with pytest.raises(HandshakeError, match="newly installed native plugin state was removed"):
        claude.install(which=found, runner=runner, handshake=lambda: False)

    assert [call[1:] for call in calls[-2:]] == [
        ("plugin", "uninstall", PLUGIN_SELECTOR, "--scope", "user"),
        ("plugin", "marketplace", "remove", MARKETPLACE_NAME, "--scope", "user"),
    ]


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
