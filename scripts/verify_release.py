from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import venv
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PROJECT_NAME = "zotero-obsidian-mcp"
PLUGIN_NAME = "obsidian-literature"
MCP_NAME = "io.github.luffysolution-svg/obsidian-vault-mcp"
MCP_SCHEMA = "https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json"
MARKETPLACE_RELATIVE = Path("src/obsidian_vault_mcp/resources/agent_marketplace")
MARKETPLACE_ROOT = ROOT / MARKETPLACE_RELATIVE
PLUGIN_RELATIVE = Path("plugins") / PLUGIN_NAME
AGENT_SKILL_NAMES = (
    "paper-qa",
    "full-read",
    "passage-qa",
    "figure-qa",
    "compare-papers",
    "literature-review",
    "concept-learning",
)
CORE_BUNDLE_FILES = (
    ".agents/plugins/marketplace.json",
    ".claude-plugin/marketplace.json",
    f"plugins/{PLUGIN_NAME}/.codex-plugin/plugin.json",
    f"plugins/{PLUGIN_NAME}/.claude-plugin/plugin.json",
    f"plugins/{PLUGIN_NAME}/.mcp.json",
    f"plugins/{PLUGIN_NAME}/assets/icon.svg",
    f"plugins/{PLUGIN_NAME}/LICENSE",
)
SKILL_FILES = tuple(f"plugins/{PLUGIN_NAME}/skills/{name}/SKILL.md" for name in AGENT_SKILL_NAMES)
REFERENCE_FILES = tuple(
    sorted(
        path.relative_to(MARKETPLACE_ROOT).as_posix()
        for name in AGENT_SKILL_NAMES
        for path in (MARKETPLACE_ROOT / "plugins" / PLUGIN_NAME / "skills" / name / "references").rglob("*.md")
        if path.is_file()
    )
)
BUNDLE_FILES = (*CORE_BUNDLE_FILES, *SKILL_FILES, *REFERENCE_FILES)
TRACKED_RELEASE_INPUTS = (
    ".github/workflows/release.yml",
    "pyproject.toml",
    "scripts/build_release.py",
    "scripts/release_guard.py",
    "server.json",
    "src/obsidian_vault_mcp/__init__.py",
    "adapters/pi/package.json",
    "adapters/pi/package-lock.json",
    "adapters/pi/index.ts",
    "src/obsidian_vault_mcp/interfaces/agent_install/pi_extension.ts",
    "opencode.json",
    *(f"{MARKETPLACE_RELATIVE.as_posix()}/{relative_path}" for relative_path in BUNDLE_FILES),
)
REMOVED_PATHS = (
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
TEXT_SUFFIXES = {".json", ".md", ".ps1", ".py", ".svg", ".toml", ".ts", ".yaml", ".yml"}
PERSONAL_PATH_PATTERNS = (
    re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]"),
    re.compile(r"(?<![A-Za-z0-9:])/(?:Users|home)/[^/\s\"']+", re.IGNORECASE),
    re.compile(r"(?<![A-Za-z0-9:])/" + r"root(?:/|\b)", re.IGNORECASE),
)
CREDENTIAL_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"(?<![A-Za-z0-9])ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"(?<![A-Za-z0-9])github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"(?<![A-Za-z0-9])AKIA[A-Z0-9]{16}"),
    re.compile(r"(?<![A-Za-z0-9])xox[baprs]-[A-Za-z0-9-]{10,}"),
)
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


class VerificationError(RuntimeError):
    pass


def text_resource_matches(left: bytes, right: bytes) -> bool:
    """Compare UTF-8 text resources without platform checkout line endings."""
    return left.replace(b"\r\n", b"\n") == right.replace(b"\r\n", b"\n")


def read_json(relative_path: str) -> dict[str, Any]:
    path = ROOT / relative_path
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VerificationError(f"Cannot read valid JSON from {relative_path}: {exc}") from exc
    if not isinstance(value, dict):
        raise VerificationError(f"Expected a JSON object in {relative_path}.")
    return value


def read_marketplace_json(relative_path: str) -> dict[str, Any]:
    return read_json((MARKETPLACE_RELATIVE / relative_path).as_posix())


def one_plugin_entry(payload: dict[str, Any], relative_path: str) -> dict[str, Any]:
    plugins = payload.get("plugins")
    if not isinstance(plugins, list) or len(plugins) != 1 or not isinstance(plugins[0], dict):
        raise VerificationError(f"{relative_path} must contain exactly one plugin entry.")
    return plugins[0]


def toml_section(text: str, name: str) -> str:
    match = re.search(rf"(?ms)^\[{re.escape(name)}\]\s*(.*?)(?=^\[|\Z)", text)
    if match is None:
        raise VerificationError(f"pyproject.toml is missing [{name}].")
    return match.group(1)


def toml_string(section: str, key: str) -> str:
    match = re.search(rf'(?m)^{re.escape(key)}\s*=\s*"([^"]+)"\s*$', section)
    if match is None:
        raise VerificationError(f"pyproject.toml is missing string field {key}.")
    return match.group(1)


def toml_string_array(section: str, key: str) -> list[str]:
    match = re.search(rf"(?ms)^{re.escape(key)}\s*=\s*(\[.*?\])\s*$", section)
    if match is None:
        raise VerificationError(f"pyproject.toml is missing array field {key}.")
    try:
        value = ast.literal_eval(match.group(1))
    except (SyntaxError, ValueError) as exc:
        raise VerificationError(f"Cannot parse pyproject.toml array {key}: {exc}") from exc
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise VerificationError(f"pyproject.toml field {key} must be an array of strings.")
    return value


def project_metadata() -> tuple[str, str]:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    project = toml_section(text, "project")
    return toml_string(project, "name"), toml_string(project, "version")


def python_string_constant(relative_path: str, name: str) -> str:
    """Read one module-level string constant without importing the package."""

    try:
        module = ast.parse((ROOT / relative_path).read_text(encoding="utf-8"), filename=relative_path)
    except (OSError, SyntaxError) as exc:
        raise VerificationError(f"Cannot parse {relative_path}: {exc}") from exc

    values: list[str] = []
    for statement in module.body:
        value: ast.expr | None = None
        if isinstance(statement, ast.Assign) and any(isinstance(target, ast.Name) and target.id == name for target in statement.targets):
            value = statement.value
        elif isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name) and statement.target.id == name:
            value = statement.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            values.append(value.value)
    if len(values) != 1:
        raise VerificationError(f"{relative_path} must define exactly one string constant named {name}.")
    return values[0]


def check_installer_version_binding() -> None:
    """Ensure the MCP installer handshake reports the package version."""

    relative_path = "src/obsidian_vault_mcp/interfaces/agent_install/common.py"
    try:
        module = ast.parse((ROOT / relative_path).read_text(encoding="utf-8"), filename=relative_path)
    except (OSError, SyntaxError) as exc:
        raise VerificationError(f"Cannot parse {relative_path}: {exc}") from exc

    imports_package_version = any(
        isinstance(statement, ast.ImportFrom)
        and statement.level == 3
        and any(alias.name == "__version__" for alias in statement.names)
        for statement in module.body
    )
    handshake = next(
        (statement for statement in module.body if isinstance(statement, ast.FunctionDef) and statement.name == "mcp_stdio_handshake"),
        None,
    )
    version_values: list[ast.expr] = []
    if handshake is not None:
        for node in ast.walk(handshake):
            if not isinstance(node, ast.Dict):
                continue
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and key.value == "version":
                    version_values.append(value)
    if (
        not imports_package_version
        or len(version_values) != 1
        or not isinstance(version_values[0], ast.Name)
        or version_values[0].id != "__version__"
    ):
        raise VerificationError("Agent installer handshake must use obsidian_vault_mcp.__version__.")


def check_dependency_bounds() -> None:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    groups = {
        "build-system.requires": toml_string_array(toml_section(text, "build-system"), "requires"),
        "project.dependencies": toml_string_array(toml_section(text, "project"), "dependencies"),
        "project.optional-dependencies.dev": toml_string_array(toml_section(text, "project.optional-dependencies"), "dev"),
    }
    for group_name, requirements in groups.items():
        for requirement in requirements:
            specifier = requirement.split(";", 1)[0]
            has_exact = re.search(
                r"(?<![!<>=~])==\s*[0-9][A-Za-z0-9._+-]*\s*$",
                specifier,
            ) is not None
            has_lower = re.search(r">=?\s*[^,]+", specifier) is not None
            has_upper = re.search(r"<=?\s*[^,]+", specifier) is not None
            if not has_exact and (not has_lower or not has_upper):
                raise VerificationError(f"{group_name} dependency lacks lower and upper bounds: {requirement}")


def git(*arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(ROOT), *arguments],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip()
        raise VerificationError(f"git {' '.join(arguments)} failed: {message}")
    return result.stdout.strip()


def check_release_inputs_tracked(ref: str) -> None:
    """Require production inputs in the release commit without rejecting a dirty local checkout."""

    for relative_path in TRACKED_RELEASE_INPUTS:
        try:
            git("cat-file", "-e", f"{ref}:{relative_path}")
        except VerificationError as exc:
            raise VerificationError(f"Release input is not tracked at {ref}: {relative_path}") from exc


def check_versions(tag: str | None) -> str:
    project_name, version = project_metadata()
    if project_name != PROJECT_NAME:
        raise VerificationError(f"Unexpected Python project name: {project_name}")
    if re.fullmatch(r"\d+\.\d+\.\d+", version) is None:
        raise VerificationError(f"Release version must use MAJOR.MINOR.PATCH, found {version}.")

    package_version = python_string_constant("src/obsidian_vault_mcp/__init__.py", "__version__")
    if package_version != version:
        raise VerificationError(f"Python project version {version} does not match package __version__ {package_version}.")
    check_installer_version_binding()

    codex_plugin_path = f"{PLUGIN_RELATIVE.as_posix()}/.codex-plugin/plugin.json"
    claude_plugin_path = f"{PLUGIN_RELATIVE.as_posix()}/.claude-plugin/plugin.json"
    codex_plugin = read_marketplace_json(codex_plugin_path)
    claude_plugin = read_marketplace_json(claude_plugin_path)
    for label, manifest in (("Codex", codex_plugin), ("Claude", claude_plugin)):
        if manifest.get("name") != PLUGIN_NAME:
            raise VerificationError(f"{label} plugin name must be {PLUGIN_NAME}.")
        if manifest.get("version") != version:
            raise VerificationError(f"Python version {version} does not match {label} plugin version {manifest.get('version')}.")
        if not isinstance(manifest.get("description"), str) or not manifest["description"].strip():
            raise VerificationError(f"{label} plugin manifest must have a non-empty description.")
    if codex_plugin.get("skills") != "./skills/":
        raise VerificationError("Codex plugin manifest must load the canonical ./skills/ directory.")
    if codex_plugin.get("mcpServers") != "./.mcp.json":
        raise VerificationError("Codex plugin manifest must point mcpServers at the shared ./.mcp.json file.")

    codex_marketplace_path = ".agents/plugins/marketplace.json"
    claude_marketplace_path = ".claude-plugin/marketplace.json"
    codex_marketplace = read_marketplace_json(codex_marketplace_path)
    claude_marketplace = read_marketplace_json(claude_marketplace_path)
    if codex_marketplace.get("name") != "obsidian-vault-mcp" or claude_marketplace.get("name") != "obsidian-vault-mcp":
        raise VerificationError("Codex and Claude marketplace names must both be obsidian-vault-mcp.")

    codex_entry = one_plugin_entry(codex_marketplace, codex_marketplace_path)
    claude_entry = one_plugin_entry(claude_marketplace, claude_marketplace_path)
    expected_source = f"./plugins/{PLUGIN_NAME}"
    expected_codex_source = {"source": "local", "path": expected_source}
    if codex_entry.get("name") != PLUGIN_NAME or codex_entry.get("source") != expected_codex_source:
        raise VerificationError("Codex marketplace must point to the canonical local plugin directory.")
    if codex_entry.get("policy") != {"installation": "AVAILABLE", "authentication": "ON_INSTALL"}:
        raise VerificationError("Codex marketplace plugin policy does not match the production defaults.")
    if codex_entry.get("category") != "Productivity":
        raise VerificationError("Codex marketplace plugin category must be Productivity.")

    metadata = claude_marketplace.get("metadata")
    if not isinstance(metadata, dict) or metadata.get("version") != version:
        found = metadata.get("version") if isinstance(metadata, dict) else None
        raise VerificationError(f"Python version {version} does not match Claude marketplace metadata version {found}.")
    if claude_entry.get("name") != PLUGIN_NAME or claude_entry.get("source") != expected_source:
        raise VerificationError("Claude marketplace must point to the canonical local plugin directory.")
    if claude_entry.get("version") != version:
        raise VerificationError(f"Python version {version} does not match Claude marketplace plugin version {claude_entry.get('version')}.")

    pi_package = read_json("adapters/pi/package.json")
    if pi_package.get("version") != version:
        raise VerificationError(f"Python version {version} does not match Pi package version {pi_package.get('version')}.")
    pi_lock = read_json("adapters/pi/package-lock.json")
    lock_root = pi_lock.get("packages", {}).get("") if isinstance(pi_lock.get("packages"), dict) else None
    if (
        pi_lock.get("lockfileVersion") != 3
        or pi_lock.get("version") != version
        or not isinstance(lock_root, dict)
        or lock_root.get("version") != version
    ):
        raise VerificationError("Pi package-lock.json must use lockfileVersion 3 and match the production package version.")

    if tag is not None:
        if not re.fullmatch(r"v\d+\.\d+\.\d+", tag):
            raise VerificationError(f"Release tag must use vMAJOR.MINOR.PATCH: {tag}")
        if tag != f"v{version}":
            raise VerificationError(f"Release tag {tag} does not match package version {version}.")
        tag_ref = f"refs/tags/{tag}"
        try:
            git("show-ref", "--verify", tag_ref)
        except VerificationError as exc:
            raise VerificationError(f"Release tag ref does not exist: {tag_ref}") from exc
        tag_commit = git("rev-parse", f"{tag_ref}^{{commit}}")
        head_commit = git("rev-parse", "HEAD")
        if tag_commit != head_commit:
            raise VerificationError(f"Checked-out commit {head_commit} is not release tag {tag} ({tag_commit}).")
        check_release_inputs_tracked(tag_ref)

    return version


def check_adapter_configs() -> None:
    expected_servers = {
        PLUGIN_NAME: {
            "command": "obsidian-vault-mcp",
            "args": ["serve", "--transport", "stdio"],
        }
    }
    mcp = read_marketplace_json(f"{PLUGIN_RELATIVE.as_posix()}/.mcp.json")
    if mcp != {"mcpServers": expected_servers}:
        raise VerificationError("Shared .mcp.json must use Claude's portable mcpServers wrapper.")

    codex = read_marketplace_json(f"{PLUGIN_RELATIVE.as_posix()}/.codex-plugin/plugin.json")
    declaration = codex.get("mcpServers")
    if isinstance(declaration, str):
        codex_payload = mcp
    elif isinstance(declaration, dict):
        codex_payload = declaration
    else:
        raise VerificationError("Codex mcpServers must be a relative companion path or an MCP server object.")
    codex_servers = codex_payload.get("mcpServers", codex_payload)
    if codex_servers != expected_servers:
        raise VerificationError("Codex cannot resolve the shared Claude-wrapped MCP server configuration.")

    expected_opencode = {
        "$schema": "https://opencode.ai/config.json",
        "mcp": {
            "obsidian-literature": {
                "type": "local",
                "command": ["obsidian-vault-mcp", "serve", "--transport", "stdio"],
                "enabled": True,
            }
        },
    }
    if read_json("opencode.json") != expected_opencode:
        raise VerificationError("opencode.json does not match the portable stdio configuration.")


def check_mcp_registry_metadata(version: str) -> None:
    """Require immutable Registry metadata for the published PyPI stdio server."""

    scripts_section = toml_section(
        (ROOT / "pyproject.toml").read_text(encoding="utf-8"),
        "project.scripts",
    )
    expected_entrypoint = "obsidian_vault_mcp.interfaces.cli.main:main"
    for command in ("obsidian-vault-mcp", PROJECT_NAME):
        if toml_string(scripts_section, command) != expected_entrypoint:
            raise VerificationError(
                f"PyPI must expose {command!r} as the production CLI entrypoint."
            )

    server = read_json("server.json")
    if server.get("$schema") != MCP_SCHEMA:
        raise VerificationError(f"server.json must use the supported MCP Registry schema {MCP_SCHEMA}.")
    if server.get("name") != MCP_NAME or server.get("version") != version:
        raise VerificationError("server.json name/version does not match the production release.")
    if server.get("repository") != {
        "url": "https://github.com/luffysolution-svg/obsidian-vault-mcp",
        "source": "github",
    }:
        raise VerificationError("server.json repository metadata is not canonical.")
    expected_package = {
        "registryType": "pypi",
        "registryBaseUrl": "https://pypi.org",
        "identifier": PROJECT_NAME,
        "version": version,
        "runtimeHint": "uvx",
        "packageArguments": [
            {"type": "positional", "value": "serve", "isRequired": True},
            {"type": "named", "name": "--transport", "value": "stdio", "isRequired": True},
        ],
        "environmentVariables": [
            {
                "name": "OBSIDIAN_VAULT_PATH",
                "description": "Absolute path to the Obsidian vault, or auto when the client project is inside it.",
                "isRequired": True,
                "isSecret": False,
                "format": "filepath",
            }
        ],
        "transport": {"type": "stdio"},
    }
    if server.get("packages") != [expected_package]:
        raise VerificationError("server.json must expose the exact PyPI/uvx stdio installation contract.")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    if f"<!-- mcp-name: {MCP_NAME} -->" not in readme:
        raise VerificationError("README.md is missing the MCP Registry PyPI ownership marker.")


def marketplace_resources() -> dict[str, Path]:
    """Return the exact recursive marketplace payload used by every release artifact."""

    resources = {relative_path: MARKETPLACE_ROOT / relative_path for relative_path in BUNDLE_FILES}
    missing = [relative_path for relative_path, path in resources.items() if not path.is_file()]
    actual = {
        path.relative_to(MARKETPLACE_ROOT).as_posix()
        for path in MARKETPLACE_ROOT.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and path.name != "__init__.py"
    }
    unexpected = sorted(actual - set(BUNDLE_FILES))
    if missing or unexpected:
        raise VerificationError(
            f"Marketplace resource set mismatch; missing={missing}, unexpected={unexpected}."
        )
    plugin_license = resources[f"plugins/{PLUGIN_NAME}/LICENSE"]
    if plugin_license.read_text(encoding="utf-8") != (ROOT / "LICENSE").read_text(encoding="utf-8"):
        raise VerificationError("Bundled plugin LICENSE differs from the repository LICENSE.")
    return {relative_path: resources[relative_path] for relative_path in BUNDLE_FILES}


def check_portability() -> None:
    """Reject machine-local paths and high-confidence credential formats from shipped text."""

    scan_roots = (
        ROOT / "src" / "obsidian_vault_mcp",
        ROOT / "adapters" / "pi",
        ROOT / "scripts",
        ROOT / ".github" / "workflows",
        ROOT / "docs",
    )
    files = {
        path
        for root in scan_roots
        for path in root.rglob("*")
        if path.is_file()
        and path.suffix.lower() in TEXT_SUFFIXES
        and not {"__pycache__", "node_modules"}.intersection(path.parts)
    }
    files.update(
        ROOT / relative_path
        for relative_path in (
            "AGENTS.md",
            "CLAUDE.md",
            "DEVELOPMENT.en.md",
            "DEVELOPMENT.md",
            "README.en.md",
            "README.md",
            "opencode.json",
            "obsidian-vault-mcp.schema.json",
            "pyproject.toml",
            "server.json",
        )
    )
    for path in sorted(files):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise VerificationError(f"Cannot inspect release text {path.relative_to(ROOT)}: {exc}") from exc
        relative_path = path.relative_to(ROOT).as_posix()
        for pattern in PERSONAL_PATH_PATTERNS:
            match = pattern.search(text)
            if match is not None:
                raise VerificationError(f"Machine-local absolute path in release input {relative_path}: {match.group(0)!r}")
        for pattern in CREDENTIAL_PATTERNS:
            if pattern.search(text) is not None:
                raise VerificationError(f"Possible credential embedded in release input: {relative_path}")


def legacy_release_path_has_files(relative_path: str) -> bool:
    path = ROOT / relative_path
    if path.is_file():
        return True
    if not path.is_dir():
        return False
    return any(
        candidate.is_file() and candidate.suffix.lower() not in {".pyc", ".pyo"} and "__pycache__" not in candidate.parts
        for candidate in path.rglob("*")
    )


def check_repository() -> str:
    version = check_versions(None)
    check_dependency_bounds()
    check_adapter_configs()
    check_mcp_registry_metadata(version)
    marketplace_resources()
    check_portability()

    for relative_path in REMOVED_PATHS:
        if legacy_release_path_has_files(relative_path):
            raise VerificationError(f"Removed root manifest/Skill mirror still exists: {relative_path}")

    required_pi_files = ("package.json", "index.ts", "README.md", "tsconfig.json")
    for filename in required_pi_files:
        if not (ROOT / "adapters" / "pi" / filename).is_file():
            raise VerificationError(f"Pi adapter is missing adapters/pi/{filename}.")
    packaged_pi_resource = ROOT / "src" / "obsidian_vault_mcp" / "interfaces" / "agent_install" / "pi_extension.ts"
    if not packaged_pi_resource.is_file():
        raise VerificationError("Pi installer package resource is missing.")
    if packaged_pi_resource.read_bytes() != (ROOT / "adapters" / "pi" / "index.ts").read_bytes():
        raise VerificationError("Pi installer package resource differs from adapters/pi/index.ts.")

    return version


def wheel_metadata_version(archive: zipfile.ZipFile) -> str:
    metadata_files = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
    if len(metadata_files) != 1:
        raise VerificationError("Wheel must contain exactly one .dist-info/METADATA file.")
    metadata = archive.read(metadata_files[0]).decode("utf-8")
    match = re.search(r"(?m)^Version:\s*(\S+)\s*$", metadata)
    if match is None:
        raise VerificationError("Wheel METADATA has no Version field.")
    return match.group(1)


def verify_wheel(wheel: Path, version: str) -> None:
    with zipfile.ZipFile(wheel) as archive:
        names = [name.replace("\\", "/") for name in archive.namelist()]
        if wheel_metadata_version(archive) != version:
            raise VerificationError(f"Wheel metadata version does not match {version}: {wheel.name}")
        if "obsidian_vault_mcp/interfaces/cli/main.py" not in names:
            raise VerificationError("Wheel is missing the CLI entrypoint module.")
        pi_resource = "obsidian_vault_mcp/interfaces/agent_install/pi_extension.ts"
        if pi_resource not in names:
            raise VerificationError("Wheel is missing the Pi installer Extension resource.")
        if not text_resource_matches(
            archive.read(pi_resource),
            (ROOT / "adapters" / "pi" / "index.ts").read_bytes(),
        ):
            raise VerificationError("Wheel Pi Extension resource differs from adapters/pi/index.ts.")
        resource_prefix = "obsidian_vault_mcp/resources/agent_marketplace/"
        expected_resources = {
            f"{resource_prefix}{relative_path}": path
            for relative_path, path in marketplace_resources().items()
        }
        archived_resources = {
            name
            for name in names
            if name.startswith(resource_prefix) and name != f"{resource_prefix}__init__.py"
        }
        if archived_resources != set(expected_resources):
            raise VerificationError("Wheel marketplace resources do not match the canonical recursive source tree.")
        for name, source in expected_resources.items():
            if archive.read(name) != source.read_bytes():
                raise VerificationError(f"Wheel marketplace resource differs from the canonical source tree: {name}")
        forbidden = [
            name
            for name in names
            if "/resources/agent_skills/" in name.lower() or name.startswith(("scripts/", "skills/", ".codex-plugin/", ".claude-plugin/"))
        ]
        if forbidden:
            raise VerificationError(f"Wheel contains a removed root manifest/Skill mirror: {forbidden[0]}")


def verify_sdist(sdist: Path, version: str) -> None:
    with tarfile.open(sdist, "r:gz") as archive:
        names = [member.name.replace("\\", "/") for member in archive.getmembers() if member.isfile()]
        expected_prefix = f"zotero_obsidian_mcp-{version}/"
        metadata_name = f"{expected_prefix}PKG-INFO"
        try:
            metadata_file = archive.extractfile(metadata_name)
        except KeyError as exc:
            raise VerificationError("Source distribution is missing its root PKG-INFO.") from exc
        if metadata_file is None:
            raise VerificationError("Source distribution PKG-INFO is not a regular file.")
        metadata = metadata_file.read().decode("utf-8")
        metadata_version = re.search(r"(?m)^Version:\s*(\S+)\s*$", metadata)
        if metadata_version is None or metadata_version.group(1) != version:
            raise VerificationError(f"Source distribution metadata version does not match {version}: {sdist.name}")
        if not any(name.endswith("/src/obsidian_vault_mcp/interfaces/cli/main.py") for name in names):
            raise VerificationError("Source distribution is missing the CLI entrypoint module.")
        pi_resource = f"{expected_prefix}src/obsidian_vault_mcp/interfaces/agent_install/pi_extension.ts"
        if pi_resource not in names:
            raise VerificationError("Source distribution is missing the Pi installer Extension resource.")
        pi_resource_file = archive.extractfile(pi_resource)
        if pi_resource_file is None or not text_resource_matches(
            pi_resource_file.read(),
            (ROOT / "adapters" / "pi" / "index.ts").read_bytes(),
        ):
            raise VerificationError("Source distribution Pi Extension resource differs from adapters/pi/index.ts.")
        resource_prefix = f"{expected_prefix}src/obsidian_vault_mcp/resources/agent_marketplace/"
        expected_resources = {
            f"{resource_prefix}{relative_path}": path
            for relative_path, path in marketplace_resources().items()
        }
        archived_resources = {
            name
            for name in names
            if name.startswith(resource_prefix) and name != f"{resource_prefix}__init__.py"
        }
        if archived_resources != set(expected_resources):
            raise VerificationError("Source distribution marketplace resources do not match the canonical recursive source tree.")
        for name, source in expected_resources.items():
            resource_file = archive.extractfile(name)
            if resource_file is None or resource_file.read() != source.read_bytes():
                raise VerificationError(f"Source distribution marketplace resource differs from the canonical source tree: {name}")
        forbidden = [
            name
            for name in names
            if "/resources/agent_skills/" in name.lower()
            or name.startswith(
                (
                    f"{expected_prefix}skills/",
                    f"{expected_prefix}.codex-plugin/",
                    f"{expected_prefix}.claude-plugin/",
                )
            )
        ]
        if forbidden:
            raise VerificationError(f"Source distribution contains a removed root manifest/Skill mirror: {forbidden[0]}")
        if not any(name.startswith(expected_prefix) for name in names):
            raise VerificationError(f"Source distribution root/version does not match {version}: {sdist.name}")


def smoke_wheel(wheel: Path, version: str) -> None:
    with tempfile.TemporaryDirectory(prefix="ovm-wheel-smoke-") as temporary_directory:
        temporary_path = Path(temporary_directory)
        environment_path = temporary_path / "venv"
        venv.EnvBuilder(with_pip=True).create(environment_path)
        if os.name == "nt":
            python = environment_path / "Scripts" / "python.exe"
        else:
            python = environment_path / "bin" / "python"

        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        environment.pop("OBSIDIAN_VAULT_PATH", None)
        environment["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
        environment["PIP_NO_INPUT"] = "1"
        (temporary_path / ".obsidian").mkdir()
        environment["OBSIDIAN_VAULT_PATH"] = str(temporary_path)
        subprocess.run(
            [str(python), "-m", "pip", "install", str(wheel.resolve())],
            check=True,
            cwd=temporary_path,
            env=environment,
        )
        subprocess.run([str(python), "-m", "pip", "check"], check=True, cwd=temporary_path, env=environment)
        smoke_code = (
            "from importlib.metadata import distribution; "
            f"d=distribution({PROJECT_NAME!r}); "
            f"assert d.version == {version!r}; "
            "eps={e.name:e for e in d.entry_points if e.group == 'console_scripts'}; "
            "assert {'obsidian-vault-mcp','zotero-obsidian-mcp'} <= set(eps); "
            "assert all(callable(eps[name].load()) for name in ('obsidian-vault-mcp','zotero-obsidian-mcp'))"
        )
        subprocess.run([str(python), "-c", smoke_code], check=True, cwd=temporary_path, env=environment)

        executable = environment_path / ("Scripts/obsidian-vault-mcp.exe" if os.name == "nt" else "bin/obsidian-vault-mcp")
        if not executable.is_file():
            raise VerificationError("Installed wheel did not create the obsidian-vault-mcp console executable.")
        registry_executable = environment_path / (
            "Scripts/zotero-obsidian-mcp.exe" if os.name == "nt" else "bin/zotero-obsidian-mcp"
        )
        if not registry_executable.is_file():
            raise VerificationError("Installed wheel did not create the MCP Registry package-name console executable.")
        cli = subprocess.run(
            [
                str(executable),
                "call",
                "literature_config_validate",
                "--json",
                '{"config_json":"{\\"schemaVersion\\":2}"}',
            ],
            check=False,
            capture_output=True,
            text=True,
            cwd=temporary_path,
            env=environment,
        )
        try:
            cli_payload = json.loads(cli.stdout)
        except json.JSONDecodeError as exc:
            raise VerificationError(f"Installed JSON CLI returned invalid output: {cli.stdout!r}") from exc
        if cli.returncode != 0 or cli_payload.get("ok") is not True:
            raise VerificationError(f"Installed JSON CLI smoke failed: {cli_payload!r} {cli.stderr.strip()}")

        protocol_smoke = (
            "from obsidian_vault_mcp.interfaces.agent_install.common import mcp_stdio_handshake; "
            "from obsidian_vault_mcp.interfaces.mcp.server import create_server; "
            "from obsidian_vault_mcp.application.skill_service import SkillResourceService; "
            "assert len(create_server()._tool_manager.list_tools()) == 31; "
            "skills=SkillResourceService(); "
            "assert len(skills.list()) == 7; "
            "assert sum(len(skills.files(item['name']))-1 for item in skills.list()) == 8; "
            f"assert mcp_stdio_handshake(command={str(executable)!r}, args=('serve','--transport','stdio'), timeout=30)"
        )
        subprocess.run([str(python), "-c", protocol_smoke], check=True, cwd=temporary_path, env=environment)
        registry_protocol_smoke = (
            "from obsidian_vault_mcp.interfaces.agent_install.common import mcp_stdio_handshake; "
            f"assert mcp_stdio_handshake(command={str(registry_executable)!r}, "
            "args=('serve','--transport','stdio'), timeout=30)"
        )
        subprocess.run([str(python), "-c", registry_protocol_smoke], check=True, cwd=temporary_path, env=environment)


def check_artifacts(directory: Path, version: str, require_sdist: bool, run_smoke: bool) -> None:
    wheels = sorted(directory.glob("*.whl"))
    if len(wheels) != 1:
        raise VerificationError(f"Expected exactly one wheel in {directory}, found {len(wheels)}.")
    verify_wheel(wheels[0], version)

    sdists = sorted(directory.glob("*.tar.gz"))
    if require_sdist and len(sdists) != 1:
        raise VerificationError(f"Expected exactly one source distribution in {directory}, found {len(sdists)}.")
    for sdist in sdists:
        verify_sdist(sdist, version)

    if run_smoke:
        smoke_wheel(wheels[0], version)


def check_bundle(directory: Path, version: str) -> None:
    bundle = directory / f"obsidian-vault-mcp-{version}-plugins.zip"
    if not bundle.is_file():
        raise VerificationError(f"Codex/Claude plugin marketplace bundle is missing: {bundle}")

    expected_entries = sorted(BUNDLE_FILES)
    resources = marketplace_resources()
    with zipfile.ZipFile(bundle) as archive:
        infos = archive.infolist()
        entries = [info.filename.replace("\\", "/") for info in infos]
        if entries != expected_entries:
            raise VerificationError(f"Plugin marketplace bundle must contain the ordered recursive allowlist; found {entries}.")
        if archive.comment:
            raise VerificationError("Plugin marketplace bundle must not contain a ZIP comment.")
        for info in infos:
            if info.date_time != ZIP_TIMESTAMP or info.compress_type != zipfile.ZIP_DEFLATED:
                raise VerificationError(f"Plugin marketplace bundle metadata is not deterministic: {info.filename}")
            if info.create_system != 3 or (info.external_attr >> 16) & 0o777 != 0o644:
                raise VerificationError(f"Plugin marketplace bundle permissions are not deterministic: {info.filename}")
        for relative_path in BUNDLE_FILES:
            archived = archive.read(relative_path)
            if archived != resources[relative_path].read_bytes():
                raise VerificationError(f"Bundled file differs byte-for-byte from the canonical marketplace source: {relative_path}")


def check_checksums(directory: Path) -> None:
    manifest = directory / "SHA256SUMS"
    if not manifest.is_file():
        raise VerificationError(f"Release checksum manifest is missing: {manifest}")

    artifacts = sorted(
        {
            path
            for pattern in ("*.whl", "*.tar.gz", "*.zip")
            for path in directory.glob(pattern)
            if path.is_file()
        },
        key=lambda path: path.name,
    )
    if not artifacts:
        raise VerificationError(f"No release artifacts found for checksum verification in {directory}.")

    recorded: dict[str, str] = {}
    for line_number, line in enumerate(manifest.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2 or re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]) is None:
            raise VerificationError(f"Invalid SHA256SUMS line {line_number}: {line!r}")
        filename = parts[1].lstrip("*")
        if not filename or Path(filename).name != filename:
            raise VerificationError(f"SHA256SUMS line {line_number} must name one artifact in the manifest directory.")
        if filename in recorded:
            raise VerificationError(f"SHA256SUMS contains duplicate artifact: {filename}")
        recorded[filename] = parts[0].lower()

    expected_names = {path.name for path in artifacts}
    if set(recorded) != expected_names:
        missing = sorted(expected_names - set(recorded))
        unexpected = sorted(set(recorded) - expected_names)
        raise VerificationError(f"SHA256SUMS artifact set mismatch; missing={missing}, unexpected={unexpected}.")

    for artifact in artifacts:
        digest = hashlib.sha256()
        with artifact.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != recorded[artifact.name]:
            raise VerificationError(f"SHA256 checksum mismatch: {artifact.name}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify release metadata and artifacts.")
    parser.add_argument("--tag", help="Release tag to compare with package and plugin versions.")
    parser.add_argument("--artifacts-dir", type=Path, help="Directory containing wheel and optional sdist artifacts.")
    parser.add_argument("--require-sdist", action="store_true", help="Require exactly one .tar.gz source distribution.")
    parser.add_argument("--smoke-wheel", action="store_true", help="Install the wheel into a temporary environment and load its entrypoint.")
    parser.add_argument("--bundle-dir", type=Path, help="Directory containing the Codex plugin zip.")
    parser.add_argument("--checksums-dir", type=Path, help="Directory containing release artifacts and SHA256SUMS.")
    arguments = parser.parse_args()

    try:
        version = check_repository()
        if arguments.tag is not None:
            check_versions(arguments.tag)
        if arguments.artifacts_dir is not None:
            check_artifacts(arguments.artifacts_dir, version, arguments.require_sdist, arguments.smoke_wheel)
        elif arguments.require_sdist or arguments.smoke_wheel:
            raise VerificationError("--require-sdist and --smoke-wheel require --artifacts-dir.")
        if arguments.bundle_dir is not None:
            check_bundle(arguments.bundle_dir, version)
        if arguments.checksums_dir is not None:
            check_checksums(arguments.checksums_dir)
    except (OSError, subprocess.CalledProcessError, tarfile.TarError, zipfile.BadZipFile, VerificationError) as exc:
        print(f"release verification failed: {exc}", file=sys.stderr)
        return 1

    print(f"release verification passed for {PROJECT_NAME} {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
