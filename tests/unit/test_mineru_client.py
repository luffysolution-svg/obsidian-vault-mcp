from __future__ import annotations

from obsidian_vault_mcp.adapters.mineru.client import MinerUClient, _has_cli_token, _resolve_command


def test_v2_config_modes_map_to_cli_modes(tmp_path, monkeypatch) -> None:
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"pdf")
    output = tmp_path / "output"
    client = MinerUClient(command="mineru-open-api")
    monkeypatch.delenv("MINERU_TOKEN", raising=False)
    monkeypatch.delenv("MINERU_API_TOKEN", raising=False)

    assert client.build_command(pdf, output, mode="local")[1] == "flash-extract"
    api = client.build_command(pdf, output, mode="api", token="secret")
    assert api[1] == "extract"
    assert "--token" in api


def test_windows_prefers_launchable_command_shim(monkeypatch) -> None:
    def fake_which(command: str) -> str | None:
        return r"C:\node\mineru-open-api.cmd" if command == "mineru-open-api.cmd" else None

    monkeypatch.setattr("obsidian_vault_mcp.adapters.mineru.client.shutil.which", fake_which)

    assert _resolve_command("mineru-open-api", is_windows=True) == r"C:\node\mineru-open-api.cmd"
    assert _resolve_command("custom.exe", is_windows=True) == "custom.exe"
    assert _resolve_command("mineru-open-api", is_windows=False) == "mineru-open-api"


def test_auto_mode_uses_precision_when_cli_auth_has_token(tmp_path, monkeypatch) -> None:
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"pdf")
    output = tmp_path / "output"
    config = tmp_path / "config.yaml"
    config.write_text("token: configured-secret\n", encoding="utf-8")
    monkeypatch.delenv("MINERU_TOKEN", raising=False)
    monkeypatch.delenv("MINERU_API_TOKEN", raising=False)
    monkeypatch.setattr(
        "obsidian_vault_mcp.adapters.mineru.client._has_cli_token",
        lambda: _has_cli_token(config),
    )

    command = MinerUClient(command="mineru-open-api").build_command(pdf, output, mode="auto")

    assert command[1] == "extract"
    assert "--token" not in command
