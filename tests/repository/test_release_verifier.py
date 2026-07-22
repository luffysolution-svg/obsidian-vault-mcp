from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from scripts import verify_release


def _configure_version_checks(monkeypatch: pytest.MonkeyPatch, version: str, package_version: str | None = None) -> None:
    monkeypatch.setattr(verify_release, "project_metadata", lambda: (verify_release.PROJECT_NAME, version))
    monkeypatch.setattr(
        verify_release,
        "python_string_constant",
        lambda _path, _name: version if package_version is None else package_version,
    )
    monkeypatch.setattr(verify_release, "check_installer_version_binding", lambda: None)

    def read_json(relative_path: str) -> dict[str, str]:
        if relative_path == ".codex-plugin/plugin.json":
            return {
                "name": "obsidian-literature",
                "version": version,
                "description": "Zotero, MinerU and Obsidian literature pipeline",
                "mcpServers": "./.mcp.json",
            }
        if relative_path == "adapters/pi/package.json":
            return {"version": version}
        raise AssertionError(relative_path)

    monkeypatch.setattr(verify_release, "read_json", read_json)


@pytest.mark.parametrize("version", ["2.0.0", "2.17.42"])
def test_version_verifier_accepts_current_and_future_v2_releases(monkeypatch: pytest.MonkeyPatch, version: str) -> None:
    _configure_version_checks(monkeypatch, version)

    assert verify_release.check_versions(None) == version


def test_version_verifier_rejects_other_majors_and_package_mismatches(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_version_checks(monkeypatch, "3.0.0")
    with pytest.raises(verify_release.VerificationError, match="2.MINOR.PATCH"):
        verify_release.check_versions(None)

    _configure_version_checks(monkeypatch, "2.1.0", package_version="2.0.0")
    with pytest.raises(verify_release.VerificationError, match="package __version__"):
        verify_release.check_versions(None)


def test_checksum_verifier_covers_every_release_artifact(tmp_path: Path) -> None:
    artifacts = {
        "package.whl": b"wheel",
        "package.tar.gz": b"sdist",
        "obsidian-vault-mcp.zip": b"bundle",
    }
    lines: list[str] = []
    for name, content in artifacts.items():
        (tmp_path / name).write_bytes(content)
        lines.append(f"{hashlib.sha256(content).hexdigest()}  {name}")
    (tmp_path / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")

    verify_release.check_checksums(tmp_path)

    (tmp_path / "package.whl").write_bytes(b"tampered")
    with pytest.raises(verify_release.VerificationError, match="checksum mismatch"):
        verify_release.check_checksums(tmp_path)


def test_text_resource_comparison_ignores_checkout_line_endings() -> None:
    assert verify_release.text_resource_matches(b"first\r\nsecond\r\n", b"first\nsecond\n")
    assert not verify_release.text_resource_matches(b"first\r\nchanged\r\n", b"first\nsecond\n")
