from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

import pytest

from scripts import build_release, verify_release


def _configure_version_checks(monkeypatch: pytest.MonkeyPatch, version: str, package_version: str | None = None) -> None:
    monkeypatch.setattr(verify_release, "project_metadata", lambda: (verify_release.PROJECT_NAME, version))
    monkeypatch.setattr(
        verify_release,
        "python_string_constant",
        lambda _path, _name: version if package_version is None else package_version,
    )
    monkeypatch.setattr(verify_release, "check_installer_version_binding", lambda: None)

    def read_json(relative_path: str) -> dict[str, object]:
        if relative_path == "adapters/pi/package.json":
            return {"version": version}
        if relative_path == "adapters/pi/package-lock.json":
            return {"version": version, "lockfileVersion": 3, "packages": {"": {"version": version}}}
        raise AssertionError(relative_path)

    def read_marketplace_json(relative_path: str) -> dict[str, object]:
        if relative_path == "plugins/obsidian-literature/.codex-plugin/plugin.json":
            return {
                "name": "obsidian-literature",
                "version": version,
                "description": "Precise literature workflows",
                "skills": "./skills/",
                "mcpServers": "./.mcp.json",
            }
        if relative_path == "plugins/obsidian-literature/.claude-plugin/plugin.json":
            return {
                "name": "obsidian-literature",
                "version": version,
                "description": "Precise literature workflows",
            }
        if relative_path == ".agents/plugins/marketplace.json":
            return {
                "name": "obsidian-vault-mcp",
                "plugins": [
                    {
                        "name": "obsidian-literature",
                        "source": {"source": "local", "path": "./plugins/obsidian-literature"},
                        "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
                        "category": "Productivity",
                    }
                ],
            }
        if relative_path == ".claude-plugin/marketplace.json":
            return {
                "name": "obsidian-vault-mcp",
                "metadata": {"version": version},
                "plugins": [
                    {
                        "name": "obsidian-literature",
                        "source": "./plugins/obsidian-literature",
                        "version": version,
                    }
                ],
            }
        raise AssertionError(relative_path)

    monkeypatch.setattr(verify_release, "read_json", read_json)
    monkeypatch.setattr(verify_release, "read_marketplace_json", read_marketplace_json)


@pytest.mark.parametrize("version", ["2.0.0", "3.0.0", "12.17.42"])
def test_version_verifier_accepts_stable_semver_releases(monkeypatch: pytest.MonkeyPatch, version: str) -> None:
    _configure_version_checks(monkeypatch, version)

    assert verify_release.check_versions(None) == version


def test_version_verifier_rejects_non_stable_versions_and_package_mismatches(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_version_checks(monkeypatch, "3.0.0rc1")
    with pytest.raises(verify_release.VerificationError, match="MAJOR.MINOR.PATCH"):
        verify_release.check_versions(None)

    _configure_version_checks(monkeypatch, "3.0.0", package_version="2.0.0")
    with pytest.raises(verify_release.VerificationError, match="package __version__"):
        verify_release.check_versions(None)


def test_dependency_verifier_accepts_exact_or_bounded_requirements(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """
[build-system]
requires = ["setuptools==80.9.0", "wheel==0.45.1"]

[project]
dependencies = ["mcp>=1.10,<2"]

[project.optional-dependencies]
dev = ["pytest>=8,<10"]
""".strip()
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(verify_release, "ROOT", tmp_path)

    verify_release.check_dependency_bounds()


def test_dependency_verifier_rejects_unbounded_and_wildcard_pins(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """
[build-system]
requires = ["setuptools==80.*"]

[project]
dependencies = ["mcp>=1.10"]

[project.optional-dependencies]
dev = ["pytest<10"]
""".strip()
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(verify_release, "ROOT", tmp_path)

    with pytest.raises(verify_release.VerificationError, match="lacks lower and upper bounds"):
        verify_release.check_dependency_bounds()


def test_version_verifier_requires_an_exact_tag_ref_not_a_same_named_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_version_checks(monkeypatch, "3.0.0")

    def git(*arguments: str) -> str:
        if arguments == ("show-ref", "--verify", "refs/tags/v3.0.0"):
            raise verify_release.VerificationError("missing ref")
        raise AssertionError(arguments)

    monkeypatch.setattr(verify_release, "git", git)

    with pytest.raises(verify_release.VerificationError, match="refs/tags/v3.0.0"):
        verify_release.check_versions("v3.0.0")


def test_version_verifier_dereferences_the_exact_tag_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_version_checks(monkeypatch, "3.0.0")
    calls: list[tuple[str, ...]] = []

    def git(*arguments: str) -> str:
        calls.append(arguments)
        if arguments == ("show-ref", "--verify", "refs/tags/v3.0.0"):
            return "tag-object refs/tags/v3.0.0"
        if arguments in {
            ("rev-parse", "refs/tags/v3.0.0^{commit}"),
            ("rev-parse", "HEAD"),
        }:
            return "release-commit"
        raise AssertionError(arguments)

    tracked: list[str] = []
    monkeypatch.setattr(verify_release, "git", git)
    monkeypatch.setattr(verify_release, "check_release_inputs_tracked", tracked.append)

    assert verify_release.check_versions("v3.0.0") == "3.0.0"
    assert calls[:2] == [
        ("show-ref", "--verify", "refs/tags/v3.0.0"),
        ("rev-parse", "refs/tags/v3.0.0^{commit}"),
    ]
    assert tracked == ["refs/tags/v3.0.0"]


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


@pytest.mark.parametrize(
    "text",
    [
        "http://127.0.0.1:23119/api/users/0/items?limit=1",
        "https://example.test/home/alice",
        "https://example.test/root/status",
    ],
)
def test_personal_path_patterns_ignore_url_paths(text: str) -> None:
    assert not any(pattern.search(text) for pattern in verify_release.PERSONAL_PATH_PATTERNS)


@pytest.mark.parametrize(
    "text",
    [
        r"C:\Users\alice\vault",
        "/Users/alice/vault",
        "/home/alice/vault",
        "/root/vault",
    ],
)
def test_personal_path_patterns_reject_machine_local_paths(text: str) -> None:
    assert any(pattern.search(text) for pattern in verify_release.PERSONAL_PATH_PATTERNS)


def test_marketplace_resource_set_contains_seven_skills_and_all_recursive_references() -> None:
    resources = verify_release.marketplace_resources()

    assert tuple(resources) == verify_release.BUNDLE_FILES
    assert len(resources) == 22
    assert "__init__.py" not in resources
    plugin_license = f"plugins/{verify_release.PLUGIN_NAME}/LICENSE"
    assert resources[plugin_license].read_text(encoding="utf-8") == (verify_release.ROOT / "LICENSE").read_text(encoding="utf-8")
    assert sum(relative_path.endswith("/SKILL.md") for relative_path in resources) == 7
    assert sum("/references/" in relative_path for relative_path in resources) == 8
    assert all(path.is_file() for path in resources.values())


def test_python_bundle_builder_is_deterministic_and_verifier_compatible(tmp_path: Path) -> None:
    version = verify_release.project_metadata()[1]

    bundle = build_release.build_bundle(tmp_path, version)
    first_digest = hashlib.sha256(bundle.read_bytes()).hexdigest()
    with zipfile.ZipFile(bundle) as archive:
        assert archive.namelist() == sorted(verify_release.BUNDLE_FILES)
    rebuilt = build_release.build_bundle(tmp_path, version)

    assert rebuilt == bundle
    assert hashlib.sha256(rebuilt.read_bytes()).hexdigest() == first_digest
    verify_release.check_bundle(tmp_path, version)
