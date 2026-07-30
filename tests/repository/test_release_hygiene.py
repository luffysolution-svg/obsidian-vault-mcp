from __future__ import annotations

import re
from pathlib import Path

from scripts import build_release, verify_release

ROOT = Path(__file__).resolve().parents[2]


def test_repository_agent_instructions_are_byte_identical() -> None:
    assert (ROOT / "AGENTS.md").read_bytes() == (ROOT / "CLAUDE.md").read_bytes()


def test_v3_package_metadata_uses_src_layout_and_bounded_dependencies() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert re.search(r'(?m)^version = "3\.\d+\.\d+"$', pyproject)
    assert 'package-dir = { "" = "src" }' in pyproject
    assert 'where = ["src"]' in pyproject
    assert 'obsidian-vault-mcp = "obsidian_vault_mcp.interfaces.cli.main:main"' in pyproject

    dependency_blocks = re.findall(r"(?ms)^(?:requires|dependencies|dev)\s*=\s*\[(.*?)\]", pyproject)
    requirements = re.findall(r'"([^"]+)"', "\n".join(dependency_blocks))
    assert requirements
    for requirement in requirements:
        assert "==" in requirement or (
            re.search(r">=", requirement) and re.search(r"<", requirement)
        ), requirement


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
        "src/obsidian_vault_mcp/application/analysis_index_service.py",
        "src/obsidian_vault_mcp/application/coverage_service.py",
        "src/obsidian_vault_mcp/application/evidence_service.py",
        "src/obsidian_vault_mcp/application/uncertainty_service.py",
        "src/obsidian_vault_mcp/domain/coverage.py",
        "src/obsidian_vault_mcp/domain/evidence.py",
        "src/obsidian_vault_mcp/domain/image_assets.py",
        "src/obsidian_vault_mcp/resources/agent_marketplace/plugins/obsidian-literature/skills/analyze-figures",
        "src/obsidian_vault_mcp/resources/agent_marketplace/plugins/obsidian-literature/skills/evidence-based-qa",
        "src/obsidian_vault_mcp/resources/agent_marketplace/plugins/obsidian-literature/skills/structured-paper-note",
        "src/obsidian_vault_mcp/resources/agent_marketplace/plugins/obsidian-literature/skills/theory-note-synthesis",
        "src/obsidian_vault_mcp/resources/agent_marketplace/plugins/obsidian-literature/skills/topic-note-synthesis",
        "src/obsidian_vault_mcp/resources/agent_marketplace/plugins/obsidian-literature/skills/uncertainty-audit",
        "src/obsidian_vault_mcp/resources/agent_marketplace/plugins/obsidian-literature/skills/verify-paper-claims",
        "tests/unit/test_analysis_services.py",
        "tests/unit/test_coverage_service.py",
        "tests/unit/test_evidence_paper_read_services.py",
        "tests/unit/test_retrieval_service.py",
        "tests/unit/test_verify_mineru_assets.py",
    )
    assert removed_paths == verify_release.REMOVED_PATHS
    assert not [relative_path for relative_path in removed_paths if verify_release.legacy_release_path_has_files(relative_path)]


def test_interface_layers_do_not_reimplement_adapter_work() -> None:
    tools = (ROOT / "src/obsidian_vault_mcp/interfaces/mcp/tools/__init__.py").read_text(encoding="utf-8")
    cli = (ROOT / "src/obsidian_vault_mcp/interfaces/cli/main.py").read_text(encoding="utf-8")

    for source in (tools, cli):
        assert "adapters." not in source
        assert "subprocess" not in source
        assert "globals().update" not in source


def test_release_bundle_has_a_cross_platform_deterministic_recursive_allowlist() -> None:
    builder = (ROOT / "scripts" / "build_release.py").read_text(encoding="utf-8")

    assert build_release.BUNDLE_FILES == verify_release.BUNDLE_FILES
    assert len(verify_release.BUNDLE_FILES) == 22
    assert verify_release.BUNDLE_FILES[:2] == (
        ".agents/plugins/marketplace.json",
        ".claude-plugin/marketplace.json",
    )
    assert f"plugins/{verify_release.PLUGIN_NAME}/assets/icon.svg" in verify_release.BUNDLE_FILES
    plugin_license = f"plugins/{verify_release.PLUGIN_NAME}/LICENSE"
    assert plugin_license in verify_release.BUNDLE_FILES
    assert (verify_release.MARKETPLACE_ROOT / plugin_license).read_text(encoding="utf-8") == (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert sum(relative_path.endswith("/SKILL.md") for relative_path in verify_release.BUNDLE_FILES) == 7
    assert sum("/references/" in relative_path for relative_path in verify_release.BUNDLE_FILES) == 8
    assert "obsidian-vault-mcp-{version}-plugins.zip" in builder
    assert "ZipInfo" in builder
    assert "ZIP_TIMESTAMP" in builder
    assert "rglob" in builder
    assert "sorted(resources)" in builder
    assert "external_attr" in builder
    assert "os.replace" in builder
    assert "git" not in builder.lower()


def test_python_package_data_includes_recursive_skill_references() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert '"plugins/obsidian-literature/skills/*/SKILL.md"' in pyproject
    assert '"plugins/obsidian-literature/skills/*/references/**/*.md"' in pyproject
    assert '"plugins/obsidian-literature/LICENSE"' in pyproject


def test_pypi_readmes_use_web_resolvable_document_links() -> None:
    for filename in ("README.md", "README.en.md"):
        readme = (ROOT / filename).read_text(encoding="utf-8")
        assert "](./" not in readme
        assert "https://github.com/luffysolution-svg/obsidian-vault-mcp/blob/main/" in readme


def test_documentation_site_metadata_names_v3() -> None:
    config = (ROOT / "docs/_config.yml").read_text(encoding="utf-8")

    assert "title: Obsidian Vault MCP V3 完整教程" in config


def test_ci_matrix_and_release_tag_checkout_cover_v3_requirements() -> None:
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    release = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")

    for operating_system in ("ubuntu-latest", "windows-latest", "macos-latest"):
        assert operating_system in ci
    for python_version in ("3.10", "3.11", "3.12", "3.13"):
        assert f'"{python_version}"' in ci
    assert "--smoke-wheel" in ci
    assert "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1" in ci
    assert "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1" in release
    assert "actions/setup-node@820762786026740c76f36085b0efc47a31fe5020 # v7.0.0" in ci
    assert "actions/setup-node@820762786026740c76f36085b0efc47a31fe5020 # v7.0.0" in release
    assert "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7.0.1" in ci
    for workflow in (ci, release):
        assert "astral-sh/setup-uv@c771a70e6277c0a99b617c7a806ffedaca235ff9 # v9.0.0" in workflow
        assert 'version: "0.11.30"' in workflow
        assert "uv sync --locked --all-extras" in workflow
        assert "python -m pip install" not in workflow
        assert "npm ci --no-audit --no-fund" in workflow
        assert "npm install --no-audit --no-fund" not in workflow
        assert "python scripts/build_release.py --output-dir dist" in workflow
        assert "Build Codex/Claude plugin marketplace bundle" in workflow
        assert "Verify Codex/Claude plugin marketplace bundle" in workflow
        assert "scripts/build_release.py" in workflow
        assert "scripts/verify_release.py" in workflow
        assert "scripts/build_release.ps1" not in workflow

    resolve_position = release.index("Resolve strict release tag ref")
    checkout_position = release.index("Check out exact release tag ref")
    assert resolve_position < checkout_position
    assert "ref: ${{ steps.tag.outputs.ref }}" in release
    assert "ref: ${{ needs.build.outputs.commit_sha }}" in release
    assert "persist-credentials: false" in release
    assert "refs/tags/$tag" in release
    assert "git merge-base --is-ancestor HEAD origin/main" in release
    assert "--require-sdist --smoke-wheel" in release
    assert "pypa/gh-action-pypi-publish@ba38be9e461d3875417946c167d0b5f3d385a247" in release
    assert "secrets.PYPI_API_TOKEN" in release
    assert release.index("Publish only missing Python artifacts to PyPI") < release.index("Publish metadata to the MCP Registry")
    assert release.index("Publish metadata to the MCP Registry") < release.index("Publish verified GitHub Release draft")
    assert "--clobber" not in release
    assert "SHA256SUMS" in release
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
