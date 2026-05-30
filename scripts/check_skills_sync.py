from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
AUTHORITATIVE_SKILLS = ROOT / "skills"
PACKAGE_SKILLS = ROOT / "scripts" / "obsidian_vault_mcp" / "skills"
SUMMARY_SKILLS = ROOT / ".claude" / "skills"
TOOL_CALL_RE = re.compile(r"`(obsidian_[A-Za-z0-9_]+)(?:\(([^`]*)\))?`")
FORBIDDEN_PROFILE_RE = re.compile(r"(`full`|`legacy`|full/legacy|full or legacy|legacy tool profile|full tool profile)", re.IGNORECASE)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative_files(base: Path) -> dict[str, Path]:
    if not base.exists():
        return {}
    return {
        path.relative_to(base).as_posix(): path
        for path in sorted(base.rglob("*"))
        if path.is_file()
    }


def _registered_tools() -> dict[str, inspect.Signature]:
    sys.path.insert(0, str(ROOT / "scripts"))
    import obsidian_vault_mcp.tools  # noqa: F401
    from obsidian_vault_mcp.common import get_registered_tools

    return {func.__name__: inspect.signature(func) for func in get_registered_tools()}


def _skill_names() -> list[str]:
    return sorted(path.parent.name for path in AUTHORITATIVE_SKILLS.glob("*/SKILL.md"))


def _check_mirrors(errors: list[str], warnings: list[str]) -> None:
    names = _skill_names()
    if not names:
        errors.append(f"No authoritative skills found under {AUTHORITATIVE_SKILLS}.")
        return

    package_names = sorted(path.parent.name for path in PACKAGE_SKILLS.glob("*/SKILL.md"))
    for missing in sorted(set(names) - set(package_names)):
        errors.append(f"Missing packaged skill directory: scripts/obsidian_vault_mcp/skills/{missing}")
    for extra in sorted(set(package_names) - set(names)):
        warnings.append(f"Extra packaged skill directory without authoritative source: {extra}")

    for name in names:
        auth_dir = AUTHORITATIVE_SKILLS / name
        pkg_dir = PACKAGE_SKILLS / name
        summary = SUMMARY_SKILLS / f"{name}.md"
        if not summary.exists():
            errors.append(f"Missing summary skill: .claude/skills/{name}.md")
        if not (auth_dir / "agents" / "openai.yaml").exists():
            errors.append(f"Missing authoritative agent descriptor: skills/{name}/agents/openai.yaml")
        if not (pkg_dir / "agents" / "openai.yaml").exists():
            errors.append(f"Missing packaged agent descriptor: scripts/obsidian_vault_mcp/skills/{name}/agents/openai.yaml")

        auth_files = _relative_files(auth_dir)
        pkg_files = _relative_files(pkg_dir)
        for rel, auth_path in auth_files.items():
            pkg_path = pkg_files.get(rel)
            if pkg_path is None:
                errors.append(f"Missing packaged mirror file for {name}: {rel}")
                continue
            if _sha256(auth_path) != _sha256(pkg_path):
                errors.append(f"Packaged mirror differs for {name}: {rel}")
        for rel in sorted(set(pkg_files) - set(auth_files)):
            warnings.append(f"Extra packaged mirror file for {name}: {rel}")


def _parse_kwargs(args: str) -> list[str]:
    if not args.strip():
        return []
    kwargs: list[str] = []
    for part in args.split(","):
        if "=" in part:
            kwargs.append(part.split("=", 1)[0].strip())
    return [name for name in kwargs if name]


def _check_skill_lint(errors: list[str]) -> None:
    tools = _registered_tools()
    for skill_path in sorted(AUTHORITATIVE_SKILLS.glob("*/SKILL.md")):
        text = skill_path.read_text(encoding="utf-8")
        rel = skill_path.relative_to(ROOT).as_posix()
        for match in FORBIDDEN_PROFILE_RE.finditer(text):
            errors.append(f"{rel}: forbidden legacy profile reference: {match.group(0)}")
        for tool_match in TOOL_CALL_RE.finditer(text):
            tool_name = tool_match.group(1)
            if tool_name not in tools:
                errors.append(f"{rel}: references unregistered MCP tool `{tool_name}`")
                continue
            signature = tools[tool_name]
            valid_params = set(signature.parameters)
            for kwarg in _parse_kwargs(tool_match.group(2) or ""):
                if kwarg not in valid_params:
                    errors.append(f"{rel}: `{tool_name}` references unknown parameter `{kwarg}`")


def check() -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    _check_mirrors(errors, warnings)
    _check_skill_lint(errors)
    return {
        "ok": not errors,
        "authoritativeDir": AUTHORITATIVE_SKILLS.relative_to(ROOT).as_posix(),
        "packageDir": PACKAGE_SKILLS.relative_to(ROOT).as_posix(),
        "summaryDir": SUMMARY_SKILLS.relative_to(ROOT).as_posix(),
        "skills": _skill_names(),
        "errors": errors,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Obsidian Vault skill mirrors and skill-doc tool references.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    args = parser.parse_args()
    result = check()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        status = "OK" if result["ok"] else "FAILED"
        print(f"Skill sync check: {status}")
        print(f"Authoritative: {result['authoritativeDir']}")
        print(f"Package:       {result['packageDir']}")
        print(f"Summary:       {result['summaryDir']}")
        for warning in result["warnings"]:
            print(f"WARN: {warning}")
        for error in result["errors"]:
            print(f"ERROR: {error}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
