from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from obsidian_vault_mcp import tools as default_tools


def _check(name: str, required: bool, func) -> dict[str, Any]:
    try:
        data = func()
        ok = bool(data.get("ok", True)) if isinstance(data, dict) else True
        status = "passed" if ok else ("failed" if required else "warning")
        return {"name": name, "required": required, "status": status, "data": data}
    except Exception as exc:
        return {
            "name": name,
            "required": required,
            "status": "failed" if required else "warning",
            "error": str(exc),
        }


def _summarize_zotero_items(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    summary = []
    for item in items:
        if not isinstance(item, dict):
            continue
        summary.append(
            {
                key: item.get(key)
                for key in ["key", "itemType", "title", "parentItem", "doi"]
                if item.get(key) not in ("", None)
            }
        )
    return summary


def _normalize_path_text(value: str) -> str:
    return str(Path(value.strip()).expanduser()).replace("\\", "/").rstrip("/").lower()


def _summarize_obsidian_cli_vault(result: dict[str, Any], expected_vault: str) -> dict[str, Any]:
    active_vault = str(result.get("stdout") or "").strip()
    summary = {
        "ok": bool(result.get("ok")),
        "command": result.get("command", []),
        "returnCode": result.get("returnCode"),
        "activeVault": active_vault,
        "matchesExpectedVault": False,
    }
    if result.get("stderr"):
        summary["stderr"] = result.get("stderr")
    if active_vault:
        summary["matchesExpectedVault"] = _normalize_path_text(active_vault) == _normalize_path_text(expected_vault)
    summary["ok"] = bool(result.get("ok")) and summary["matchesExpectedVault"]
    if result.get("ok") and not summary["matchesExpectedVault"]:
        summary["warning"] = "Obsidian CLI is available, but its active vault differs from the requested smoke vault."
    return summary


def run_smoke(vault_path: str, tools=default_tools) -> dict[str, Any]:
    """Run read-only/dry-run integration checks for local optional services."""
    checks = [
        _check("vault_status", True, lambda: tools.obsidian_vault_status(vault_path)),
        _check(
            "dry_run_note_create",
            True,
            lambda: tools.obsidian_create_note(
                ".obsidian-vault-smoke.md",
                title="Obsidian Vault Smoke",
                body="Dry-run smoke check.",
                properties_json=json.dumps({"type": "smoke", "tags": ["smoke"]}),
                vault_path=vault_path,
                overwrite=True,
                dry_run=True,
            ),
        ),
    ]

    zotero_ping = _check("zotero_ping", False, tools.obsidian_zotero_ping)
    checks.append(zotero_ping)
    if zotero_ping["status"] == "passed":
        checks.append(_check("zotero_search", False, lambda: _summarize_zotero_items(tools.obsidian_zotero_search_items("", limit=1))))

    checks.append(
        _check(
            "obsidian_cli_vault",
            False,
            lambda: _summarize_obsidian_cli_vault(
                tools.obsidian_cli("vault", params_json=json.dumps({"info": "path"}), timeout_seconds=10),
                vault_path,
            ),
        )
    )

    summary = {
        "passed": sum(1 for check in checks if check["status"] == "passed"),
        "warning": sum(1 for check in checks if check["status"] == "warning"),
        "failed": sum(1 for check in checks if check["status"] == "failed"),
    }
    return {
        "ok": summary["failed"] == 0,
        "vaultPath": vault_path,
        "summary": summary,
        "checks": checks,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Obsidian Vault local integration smoke checks.")
    parser.add_argument("--vault", required=True, help="Vault path to check.")
    args = parser.parse_args()
    result = run_smoke(args.vault)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
