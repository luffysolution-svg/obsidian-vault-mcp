from __future__ import annotations

import re
from pathlib import Path

from scripts import build_release, verify_release

ROOT = Path(__file__).resolve().parents[2]


def test_v2_package_metadata_uses_src_layout_and_bounded_dependencies() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert re.search(r'(?m)^version = "2\.\d+\.\d+"$', pyproject)
    assert 'package-dir = { "" = "src" }' in pyproject
    assert 'where = ["src"]' in pyproject
    assert 'obsidian-vault-mcp = "obsidian_vault_mcp.interfaces.cli.main:main"' in pyproject

    dependency_blocks = re.findall(r"(?ms)^(?:requires|dependencies|dev)\s*=\s*\[(.*?)\]", pyproject)
    requirements = re.findall(r'"([^"]+)"', "\n".join(dependency_blocks))
    assert requirements
    for requirement in requirements:
        assert re.search(r">=?", requirement), requirement
        assert re.search(r"<=?", requirement), requirement


def test_removed_skill_and_legacy_packaging_paths_are_absent() -> None:
    removed_paths = (
        ".agents",
        ".codex-plugin",
        ".claude-plugin",
        ".mcp.json",
        ".claude/skills",
        "skills",
        "src/obsidian_vault_mcp/resources/agent_skills",
        "scripts/obsidian_vault_mcp/skills",
        "scripts/check_skills_sync.py",
        "scripts/obsidian_vault_mcp.py",
        "scripts/smoke_integrations.py",
        "tests/test_obsidian_vault_mcp.py",
        "docs/superpowers",
        "requirements.txt",
    )
    assert not [relative_path for relative_path in removed_paths if verify_release.legacy_release_path_has_files(relative_path)]


def test_interface_layers_do_not_reimplement_adapter_work() -> None:
    tools = (ROOT / "src/obsidian_vault_mcp/interfaces/mcp/tools/__init__.py").read_text(encoding="utf-8")
    cli = (ROOT / "src/obsidian_vault_mcp/interfaces/cli/main.py").read_text(encoding="utf-8")

    for source in (tools, cli):
        assert "adapters." not in source
        assert "subprocess" not in source
        assert "globals().update" not in source


def test_release_bundle_has_a_cross_platform_deterministic_15_file_allowlist() -> None:
    builder = (ROOT / "scripts" / "build_release.py").read_text(encoding="utf-8")

    assert build_release.BUNDLE_FILES == verify_release.BUNDLE_FILES
    assert len(verify_release.BUNDLE_FILES) == 15
    assert verify_release.BUNDLE_FILES[:2] == (
        ".agents/plugins/marketplace.json",
        ".claude-plugin/marketplace.json",
    )
    assert f"plugins/{verify_release.PLUGIN_NAME}/assets/icon.svg" in verify_release.BUNDLE_FILES
    assert sum(relative_path.endswith("/SKILL.md") for relative_path in verify_release.BUNDLE_FILES) == 9
    assert "obsidian-vault-mcp-{version}-plugins.zip" in builder
    assert "ZipInfo" in builder
    assert "ZIP_TIMESTAMP" in builder
    assert "sorted(resources)" in builder
    assert "external_attr" in builder
    assert "os.replace" in builder
    assert "git" not in builder.lower()


def test_ci_matrix_and_release_tag_checkout_cover_v2_requirements() -> None:
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    release = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")

    for operating_system in ("ubuntu-latest", "windows-latest", "macos-latest"):
        assert operating_system in ci
    for python_version in ("3.10", "3.11", "3.12", "3.13"):
        assert f'"{python_version}"' in ci
    assert "--smoke-wheel" in ci
    assert "actions/checkout@v6" in ci and "actions/checkout@v6" in release
    assert "actions/setup-node@v6" in ci and "actions/setup-node@v6" in release
    assert "actions/upload-artifact@v6" in ci
    for workflow in (ci, release):
        assert "npm ci --no-audit --no-fund" in workflow
        assert "npm install --no-audit --no-fund" not in workflow
        assert "python scripts/build_release.py --output-dir dist" in workflow
        assert "Build Codex/Claude plugin marketplace bundle" in workflow
        assert "Verify Codex/Claude plugin marketplace bundle" in workflow
        assert "scripts/build_release.py scripts/verify_release.py" in workflow
        assert "scripts/build_release.ps1" not in workflow

    resolve_position = release.index("Resolve release tag")
    checkout_position = release.index("Check out release tag")
    assert resolve_position < checkout_position
    assert "ref: ${{ steps.tag.outputs.tag }}" in release
    assert "git merge-base --is-ancestor HEAD origin/main" in release
    assert "--require-sdist --smoke-wheel" in release
    assert "pypa/gh-action-pypi-publish@ba38be9e461d3875417946c167d0b5f3d385a247" in release
    assert "secrets.PYPI_API_TOKEN" in release
    assert release.index("Create or update GitHub release assets") < release.index("Publish wheel and source distribution to PyPI")
    assert "dist/SHA256SUMS" in release
    assert "dist/SHA256SUMS" in ci


def test_pi_adapter_has_a_committed_npm_lockfile() -> None:
    package_lock = (ROOT / "adapters" / "pi" / "package-lock.json").read_text(encoding="utf-8")

    assert '"lockfileVersion": 3' in package_lock
    assert '"name": "obsidian-vault-mcp-pi-extension"' in package_lock


def test_wheel_smoke_uses_a_clean_environment_and_checks_dependencies() -> None:
    verifier = (ROOT / "scripts" / "verify_release.py").read_text(encoding="utf-8")

    assert "system_site_packages=True" not in verifier
    assert '"--no-deps"' not in verifier
    assert '"--ignore-installed"' not in verifier
    assert '[str(python), "-m", "pip", "check"]' in verifier
    assert 'environment["OBSIDIAN_VAULT_PATH"] = str(temporary_path)' in verifier
