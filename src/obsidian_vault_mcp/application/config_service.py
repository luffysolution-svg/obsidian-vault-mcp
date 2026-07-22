from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ..config.defaults import CONFIG_FILENAME, default_config
from ..config.loader import config_path, load_config
from ..config.schema import validate_config
from .transaction_service import TransactionService


class ConfigService:
    """Application boundary for the Vault's single V2 configuration."""

    def __init__(self, vault_path: str | os.PathLike[str]) -> None:
        self.vault_path = Path(vault_path).expanduser().resolve()

    def get(self) -> dict[str, Any]:
        path = config_path(self.vault_path)
        return {
            "ok": True,
            "path": CONFIG_FILENAME,
            "exists": path.is_file(),
            "config": load_config(self.vault_path, require_exists=False),
        }

    def validate(self, value: str | Mapping[str, Any] | None = None) -> dict[str, Any]:
        if isinstance(value, str) and value:
            raw = json.loads(value)
            normalized = validate_config(raw)
        elif isinstance(value, Mapping):
            normalized = validate_config(value)
        else:
            normalized = load_config(self.vault_path, require_exists=True)
        return {"ok": True, "schemaVersion": normalized["schemaVersion"], "config": normalized}

    def initialize(
        self,
        *,
        dry_run: bool = False,
        transaction_id: str | None = None,
        conflict_policy: str = "preserve-user",
    ) -> dict[str, Any]:
        path = config_path(self.vault_path)
        if path.exists() and conflict_policy != "overwrite-managed":
            raise FileExistsError(f"configuration already exists: {path}")
        transaction = TransactionService(self.vault_path).begin(transaction_id=transaction_id, dry_run=dry_run)
        transaction.write_text(CONFIG_FILENAME, json.dumps(default_config(), ensure_ascii=False, indent=2) + "\n")
        return {**transaction.commit(), "path": CONFIG_FILENAME}
