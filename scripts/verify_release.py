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
BUNDLE_ROOT = "obsidian-literature"
BUNDLE_FILES = (".codex-plugin/plugin.json", ".mcp.json")
PLUGIN_FIELDS = {"name", "version", "description", "mcpServers"}
REMOVED_PATHS = (
    ".claude-plugin",
    ".claude/skills",
    "skills",
    "scripts/obsidian_vault_mcp/skills",
    "scripts/check_skills_sync.py",
    "scripts/obsidian_vault_mcp.py",
    "scripts/smoke_integrations.py",
    "tests/test_obsidian_vault_mcp.py",
    "docs/superpowers",
    "requirements.txt",
)


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
            has_lower = re.search(r">=?\s*[^,]+", specifier) is not None
            has_upper = re.search(r"<=?\s*[^,]+", specifier) is not None
            if not has_lower or not has_upper:
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


def check_versions(tag: str | None) -> str:
    project_name, version = project_metadata()
    if project_name != PROJECT_NAME:
        raise VerificationError(f"Unexpected Python project name: {project_name}")
    if re.fullmatch(r"2\.\d+\.\d+", version) is None:
        raise VerificationError(f"V2 release version must use 2.MINOR.PATCH, found {version}.")

    package_version = python_string_constant("src/obsidian_vault_mcp/__init__.py", "__version__")
    if package_version != version:
        raise VerificationError(f"Python project version {version} does not match package __version__ {package_version}.")
    check_installer_version_binding()

    plugin = read_json(".codex-plugin/plugin.json")
    if set(plugin) != PLUGIN_FIELDS:
        raise VerificationError(f"Codex plugin manifest must contain only {sorted(PLUGIN_FIELDS)}.")
    if plugin.get("version") != version:
        raise VerificationError(f"Python version {version} does not match plugin version {plugin.get('version')}.")
    expected_plugin = {
        "name": "obsidian-literature",
        "version": version,
        "description": "Zotero, MinerU and Obsidian literature pipeline",
        "mcpServers": "./.mcp.json",
    }
    if plugin != expected_plugin:
        raise VerificationError("Codex plugin manifest does not match the minimal V2 manifest.")

    pi_package = read_json("adapters/pi/package.json")
    if pi_package.get("version") != version:
        raise VerificationError(f"Python version {version} does not match Pi package version {pi_package.get('version')}.")

    if tag is not None:
        if not re.fullmatch(r"v\d+\.\d+\.\d+", tag):
            raise VerificationError(f"Release tag must use vMAJOR.MINOR.PATCH: {tag}")
        if tag != f"v{version}":
            raise VerificationError(f"Release tag {tag} does not match package version {version}.")
        tag_commit = git("rev-list", "-n", "1", tag)
        head_commit = git("rev-parse", "HEAD")
        if tag_commit != head_commit:
            raise VerificationError(f"Checked-out commit {head_commit} is not release tag {tag} ({tag_commit}).")

    return version


def check_adapter_configs() -> None:
    expected_mcp = {
        "mcpServers": {
            "obsidian-literature": {
                "type": "stdio",
                "command": "obsidian-vault-mcp",
                "args": ["serve", "--transport", "stdio"],
                "env": {"OBSIDIAN_VAULT_PATH": "auto"},
            }
        }
    }
    if read_json(".mcp.json") != expected_mcp:
        raise VerificationError(".mcp.json does not match the portable V2 stdio configuration.")

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
        raise VerificationError("opencode.json does not match the portable V2 stdio configuration.")


def check_repository() -> str:
    version = check_versions(None)
    check_dependency_bounds()
    check_adapter_configs()

    for relative_path in REMOVED_PATHS:
        if (ROOT / relative_path).exists():
            raise VerificationError(f"Removed V1/Skills path still exists: {relative_path}")

    for relative_path in BUNDLE_FILES:
        git("ls-files", "--error-unmatch", "--", relative_path)

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
            raise VerificationError("Wheel is missing the V2 CLI entrypoint module.")
        pi_resource = "obsidian_vault_mcp/interfaces/agent_install/pi_extension.ts"
        if pi_resource not in names:
            raise VerificationError("Wheel is missing the Pi installer Extension resource.")
        if not text_resource_matches(
            archive.read(pi_resource),
            (ROOT / "adapters" / "pi" / "index.ts").read_bytes(),
        ):
            raise VerificationError("Wheel Pi Extension resource differs from adapters/pi/index.ts.")
        forbidden = [name for name in names if "/skills/" in name.lower() or name.startswith("scripts/")]
        if forbidden:
            raise VerificationError(f"Wheel contains removed Skills/legacy files: {forbidden[0]}")


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
            raise VerificationError("Source distribution is missing the V2 CLI entrypoint module.")
        pi_resource = f"{expected_prefix}src/obsidian_vault_mcp/interfaces/agent_install/pi_extension.ts"
        if pi_resource not in names:
            raise VerificationError("Source distribution is missing the Pi installer Extension resource.")
        pi_resource_file = archive.extractfile(pi_resource)
        if pi_resource_file is None or not text_resource_matches(
            pi_resource_file.read(),
            (ROOT / "adapters" / "pi" / "index.ts").read_bytes(),
        ):
            raise VerificationError("Source distribution Pi Extension resource differs from adapters/pi/index.ts.")
        forbidden = [name for name in names if "/skills/" in name.lower()]
        if forbidden:
            raise VerificationError(f"Source distribution contains removed Skills files: {forbidden[0]}")
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
            "eps=[e for e in d.entry_points if e.group == 'console_scripts' and e.name == 'obsidian-vault-mcp']; "
            "assert len(eps) == 1 and callable(eps[0].load())"
        )
        subprocess.run([str(python), "-c", smoke_code], check=True, cwd=temporary_path, env=environment)

        executable = environment_path / ("Scripts/obsidian-vault-mcp.exe" if os.name == "nt" else "bin/obsidian-vault-mcp")
        if not executable.is_file():
            raise VerificationError("Installed wheel did not create the obsidian-vault-mcp console executable.")
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
            "assert len(create_server()._tool_manager.list_tools()) == 26; "
            f"assert mcp_stdio_handshake(command={str(executable)!r}, args=('serve','--transport','stdio'), timeout=15)"
        )
        subprocess.run([str(python), "-c", protocol_smoke], check=True, cwd=temporary_path, env=environment)


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
    bundle = directory / f"obsidian-vault-mcp-{version}.zip"
    if not bundle.is_file():
        raise VerificationError(f"Codex plugin bundle is missing: {bundle}")

    expected_entries = {f"{BUNDLE_ROOT}/{relative_path}" for relative_path in BUNDLE_FILES}
    with zipfile.ZipFile(bundle) as archive:
        entries = {name.replace("\\", "/") for name in archive.namelist() if not name.endswith("/")}
        if entries != expected_entries:
            raise VerificationError(f"Codex plugin bundle must contain only {sorted(expected_entries)}, found {sorted(entries)}.")
        for relative_path in BUNDLE_FILES:
            archived = archive.read(f"{BUNDLE_ROOT}/{relative_path}")
            if not text_resource_matches(archived, (ROOT / relative_path).read_bytes()):
                raise VerificationError(f"Bundled file differs from the tracked working-tree file: {relative_path}")


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
    parser = argparse.ArgumentParser(description="Verify V2 release metadata and artifacts.")
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
