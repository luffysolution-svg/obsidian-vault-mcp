from __future__ import annotations

import argparse
import json

from .server import main as run_server
from .tools import obsidian_doctor


def _doctor_check_status(name: str, check: dict) -> str:
    if check.get("ok"):
        return "OK"
    if name in {"obsidian_cli", "zotero_api", "mineru_cli", "pypdf"}:
        return "WARN"
    return "FAIL"


def _doctor_check_detail(name: str, check: dict) -> str:
    if name == "vault":
        return str(check.get("path") or check.get("error") or "")
    if name == "vault_config":
        config = check.get("config")
        if isinstance(config, dict):
            return f"{len(config)} setting(s)"
    if name == "templates":
        return f"{check.get('count', 0)} template(s)"
    if name == "obsidian_cli":
        return "available" if check.get("ok") else "not available"
    if name == "mineru_cli":
        if check.get("available"):
            token_text = "token detected" if check.get("tokenAvailable") else "no token detected"
            return f"available, {token_text}"
        return str(check.get("installHint") or check.get("error") or "not available")
    if name == "zotero_api":
        if check.get("ok"):
            return f"reachable, sample count {check.get('sampleCount', 0)}"
        return str(check.get("error") or "not reachable")
    if name == "pyyaml":
        return "available" if check.get("ok") else str(check.get("error") or "not available")
    if name == "pypdf":
        return "available" if check.get("ok") else str(check.get("error") or "not available")
    return str(check.get("error") or check.get("warning") or "")


def format_doctor_text(result: dict) -> str:
    lines = [
        "Obsidian Vault doctor",
        f"Overall: {'OK' if result.get('ok') else 'FAILED'}",
    ]
    checks = result.get("checks") if isinstance(result, dict) else []
    if isinstance(checks, list):
        for check in checks:
            if not isinstance(check, dict):
                continue
            name = str(check.get("name") or check.get("cli") or "check")
            status = _doctor_check_status(name, check)
            detail = _doctor_check_detail(name, check)
            suffix = f" - {detail}" if detail else ""
            lines.append(f"[{status}] {name}{suffix}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Obsidian Vault MCP server.")
    parser.add_argument("--doctor", action="store_true", help="Check local readiness without starting the MCP server.")
    parser.add_argument("--vault", default="", help="Vault path to check when using --doctor.")
    parser.add_argument("--doctor-format", choices=["json", "text"], default="json", help="Output format for --doctor. Defaults to json for compatibility.")
    args = parser.parse_args()

    if args.doctor:
        result = obsidian_doctor(args.vault)
        if args.doctor_format == "text":
            print(format_doctor_text(result))
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    run_server()


if __name__ == "__main__":
    main()
