from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ..adapters.mineru.client import MinerUClient
from ..adapters.zotero.client import ZoteroClient
from ..config.defaults import CONFIG_FILENAME, default_config
from ..config.loader import config_path, load_config


class DoctorService:
    """Probe local V2 configuration and external adapter readiness."""

    def __init__(self, vault_path: str | os.PathLike[str]) -> None:
        self.vault_path = Path(vault_path).expanduser().resolve()

    def run(self, *, tool_names: list[str] | None = None) -> dict[str, Any]:
        path = config_path(self.vault_path)
        try:
            config = load_config(self.vault_path, require_exists=False)
            config_status: dict[str, Any] = {
                "ok": True,
                "exists": path.is_file(),
                "path": CONFIG_FILENAME,
                "schemaVersion": config["schemaVersion"],
            }
        except Exception as exc:
            config = default_config()
            config_status = {"ok": False, "exists": path.is_file(), "path": CONFIG_FILENAME, "error": str(exc)}

        try:
            client = ZoteroClient(
                api_base=os.environ.get("ZOTERO_LOCAL_API") or str(config["zotero"]["apiBase"]),
                page_size=int(config["zotero"]["paginationSize"]),
            )
            zotero = client.ping()
        except Exception as exc:
            zotero = {"ok": False, "error": str(exc)}

        mineru_client = MinerUClient()
        mineru = {
            "available": mineru_client.available(),
            "command": mineru_client.command,
            "enabled": config["mineru"]["enabled"],
        }
        return {
            "ok": bool(config_status["ok"]),
            "vaultPath": str(self.vault_path),
            "config": config_status,
            "zotero": zotero,
            "mineru": mineru,
            "tools": tool_names or [],
        }
