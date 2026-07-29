from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MARKETPLACE_ROOT = ROOT / "src" / "obsidian_vault_mcp" / "resources" / "agent_marketplace"
PLUGIN_NAME = "obsidian-literature"
AGENT_SKILL_NAMES = (
    "analyze-figures",
    "compare-papers",
    "evidence-based-qa",
    "literature-review",
    "structured-paper-note",
    "theory-note-synthesis",
    "topic-note-synthesis",
    "uncertainty-audit",
    "verify-paper-claims",
)
BUNDLE_FILES = (
    ".agents/plugins/marketplace.json",
    ".claude-plugin/marketplace.json",
    f"plugins/{PLUGIN_NAME}/.codex-plugin/plugin.json",
    f"plugins/{PLUGIN_NAME}/.claude-plugin/plugin.json",
    f"plugins/{PLUGIN_NAME}/.mcp.json",
    f"plugins/{PLUGIN_NAME}/assets/icon.svg",
    *(f"plugins/{PLUGIN_NAME}/skills/{name}/SKILL.md" for name in AGENT_SKILL_NAMES),
)
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


class BuildError(RuntimeError):
    pass


def _read_json(relative_path: str) -> dict[str, Any]:
    path = MARKETPLACE_ROOT / relative_path
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BuildError(f"Cannot read valid JSON from {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise BuildError(f"Expected a JSON object in {path}.")
    return value


def project_version() -> str:
    try:
        text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    except OSError as exc:
        raise BuildError(f"Cannot read pyproject.toml: {exc}") from exc
    project = re.search(r"(?ms)^\[project\]\s*(.*?)(?=^\[|\Z)", text)
    match = None if project is None else re.search(r'(?m)^version\s*=\s*"([^"]+)"\s*$', project.group(1))
    if match is None:
        raise BuildError("pyproject.toml is missing [project].version.")
    version = match.group(1)
    if re.fullmatch(r"\d+\.\d+\.\d+", version) is None:
        raise BuildError(f"Project version must use MAJOR.MINOR.PATCH: {version}")
    return version


def validate_inputs(version: str) -> dict[str, Path]:
    resources = {relative_path: MARKETPLACE_ROOT / relative_path for relative_path in BUNDLE_FILES}
    missing = [relative_path for relative_path, path in resources.items() if not path.is_file()]
    if missing:
        raise BuildError(f"Release bundle inputs are missing: {missing}")

    codex = _read_json(f"plugins/{PLUGIN_NAME}/.codex-plugin/plugin.json")
    claude = _read_json(f"plugins/{PLUGIN_NAME}/.claude-plugin/plugin.json")
    claude_marketplace = _read_json(".claude-plugin/marketplace.json")
    versioned_values = {
        "Codex plugin": codex.get("version"),
        "Claude plugin": claude.get("version"),
        "Claude marketplace metadata": (claude_marketplace.get("metadata") or {}).get("version"),
    }
    plugins = claude_marketplace.get("plugins")
    versioned_values["Claude marketplace plugin"] = plugins[0].get("version") if isinstance(plugins, list) and len(plugins) == 1 and isinstance(plugins[0], dict) else None
    mismatches = {name: value for name, value in versioned_values.items() if value != version}
    if mismatches:
        raise BuildError(f"Release bundle versions do not match {version}: {mismatches}")
    return resources


def build_bundle(output_dir: Path, requested_version: str | None = None) -> Path:
    version = project_version()
    if requested_version is not None and requested_version != version:
        raise BuildError(f"Requested version {requested_version} does not match project version {version}.")
    resources = validate_inputs(version)

    output_dir = output_dir.expanduser()
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / f"obsidian-vault-mcp-{version}-plugins.zip"

    handle, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=output_dir)
    os.close(handle)
    temporary = Path(temporary_name)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for relative_path in sorted(resources):
                info = zipfile.ZipInfo(relative_path, date_time=ZIP_TIMESTAMP)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = (0o100644 & 0xFFFF) << 16
                archive.writestr(info, resources[relative_path].read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
        os.replace(temporary, destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the deterministic Codex and Claude plugin marketplace bundle.")
    parser.add_argument("--version", help="Expected MAJOR.MINOR.PATCH project version.")
    parser.add_argument("--output-dir", type=Path, default=Path("dist"), help="Output directory (default: dist).")
    arguments = parser.parse_args()
    try:
        bundle = build_bundle(arguments.output_dir, arguments.version)
    except (BuildError, OSError, zipfile.BadZipFile) as exc:
        parser.exit(1, f"release bundle build failed: {exc}\n")
    print(bundle)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
