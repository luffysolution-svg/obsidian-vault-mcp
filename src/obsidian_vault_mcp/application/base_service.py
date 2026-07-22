from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ..adapters.obsidian.base_renderer import BASE_TEMPLATE_VERSION, render_base
from ..adapters.vault.lock import GlobalLock
from ..config.loader import load_config
from .transaction_service import TransactionService


class BaseService:
    def __init__(self, vault_path: str | os.PathLike[str], config: Mapping[str, Any] | None = None) -> None:
        self.vault_path = Path(vault_path).expanduser().resolve()
        self.config = dict(config) if config is not None else load_config(self.vault_path, require_exists=False)

    @property
    def base_path(self) -> str:
        return str(self.config["literature"]["base"])

    def render(self) -> str:
        return render_base(
            literature_root=str(self.config["literature"]["root"]),
            name=str(self.config["base"]["name"]),
        )

    def rebuild(
        self,
        *,
        dry_run: bool = False,
        transaction_id: str | None = None,
        conflict_policy: str = "preserve-user",
    ) -> dict[str, Any]:
        del conflict_policy
        transaction = TransactionService(self.vault_path).begin(transaction_id=transaction_id, dry_run=dry_run)
        transaction.write_text(self.base_path, self.render())
        if dry_run:
            result = transaction.commit()
        else:
            with GlobalLock(self.vault_path, "base"):
                result = transaction.commit()
        return {**result, "path": self.base_path, "templateVersion": BASE_TEMPLATE_VERSION}
