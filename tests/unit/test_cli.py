from __future__ import annotations

import io
import json
from pathlib import Path

from obsidian_vault_mcp.interfaces.cli import main as package_main
from obsidian_vault_mcp.interfaces.cli.main import main
from obsidian_vault_mcp.interfaces.mcp import tools


def test_call_dispatches_exact_json_arguments(monkeypatch, capsys) -> None:
    received = {}

    def fake_tool(**kwargs):
        received.update(kwargs)
        return {"ok": True, "count": 2}

    monkeypatch.setitem(tools.TOOL_BY_NAME, "literature_doctor", fake_tool)
    monkeypatch.setitem(main.__globals__["TOOL_BY_NAME"], "literature_doctor", fake_tool)

    assert main(["call", "literature_doctor", "--json", '{"vault_path":"资料库","extra":2}']) == 0
    assert json.loads(capsys.readouterr().out) == {"ok": True, "count": 2}
    assert received == {"vault_path": "资料库", "extra": 2}


def test_human_command_maps_write_options(monkeypatch, capsys) -> None:
    received = {}

    def fake_tool(**kwargs):
        received.update(kwargs)
        return {"ok": True}

    monkeypatch.setitem(main.__globals__["TOOL_BY_NAME"], "literature_import_item", fake_tool)
    code = main(
        [
            "import",
            "item",
            "ABCD1234",
            "--vault-path",
            "vault",
            "--dry-run",
            "--transaction-id",
            "tx-1",
            "--conflict-policy",
            "fail",
        ]
    )

    assert code == 0
    assert json.loads(capsys.readouterr().out) == {"ok": True}
    assert received == {
        "zotero_key": "ABCD1234",
        "vault_path": "vault",
        "dry_run": True,
        "transaction_id": "tx-1",
        "conflict_policy": "fail",
    }


def test_agent_install_cli_serializes_native_plugin_result(monkeypatch, capsys, tmp_path: Path) -> None:
    received = {}

    class Result:
        def as_dict(self):
            return {
                "client": "codex",
                "marketplace_path": str(tmp_path / "marketplace"),
                "plugin_selector": "obsidian-literature@obsidian-vault-mcp",
                "commands": [["codex", "plugin", "add", "obsidian-literature@obsidian-vault-mcp"]],
            }

    def fake_install(client, project_dir, *, dry_run):
        received.update(client=client, project_dir=project_dir, dry_run=dry_run)
        return Result()

    monkeypatch.setitem(main.__globals__, "install_agent", fake_install)
    assert main(["agent", "install", "codex", "--project-dir", str(tmp_path), "--dry-run"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["plugin_selector"] == "obsidian-literature@obsidian-vault-mcp"
    assert payload["commands"][0][1:3] == ["plugin", "add"]
    assert received == {"client": "codex", "project_dir": tmp_path, "dry_run": True}


def test_cli_returns_structured_json_error(monkeypatch, capsys) -> None:
    def fail(**_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setitem(main.__globals__["TOOL_BY_NAME"], "literature_doctor", fail)
    assert main(["doctor"]) == 2
    assert json.loads(capsys.readouterr().out) == {
        "ok": False,
        "error": {"type": "RuntimeError", "message": "boom"},
    }


def test_emit_falls_back_to_ascii_json_for_legacy_windows_stream() -> None:
    buffer = io.BytesIO()
    stream = io.TextIOWrapper(buffer, encoding="gbk")

    main.__globals__["_emit"]({"value": "10−2"}, stream=stream)
    stream.flush()

    assert json.loads(buffer.getvalue().decode("ascii")) == {"value": "10−2"}


def test_migration_rejects_conflicting_execution_flags(capsys) -> None:
    assert main(["migrate", "v1-to-v2", "--apply", "--dry-run"]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert "cannot be used together" in payload["error"]["message"]


def test_analysis_v3_migration_defaults_to_preview_and_requires_apply(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    calls: list[dict[str, object]] = []

    class FakeMigration:
        def __init__(self, vault_path):
            self.vault_path = vault_path

        def migrate(self, **kwargs):
            calls.append({"vault_path": self.vault_path, **kwargs})
            return {"ok": True, "status": "dry-run" if kwargs["dry_run"] else "committed"}

    (tmp_path / ".obsidian").mkdir()
    monkeypatch.setitem(main.__globals__, "AnalysisMigrationService", FakeMigration)
    preview = ["migrate", "analysis-v2-to-v3", "--vault-path", str(tmp_path)]
    assert main(preview) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "dry-run"
    assert calls[-1]["dry_run"] is True
    assert calls[-1]["apply"] is False

    applied = [
        "migrate",
        "analysis-v2-to-v3",
        "--vault-path",
        str(tmp_path),
        "--apply",
        "--transaction-id",
        "analysis-v3",
    ]
    assert main(applied) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "committed"
    assert calls[-1]["dry_run"] is False
    assert calls[-1]["apply"] is True
    assert calls[-1]["transaction_id"] == "analysis-v3"


def test_package_exports_main() -> None:
    assert package_main is main
