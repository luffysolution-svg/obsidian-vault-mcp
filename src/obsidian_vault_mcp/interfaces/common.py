from __future__ import annotations

import os
from pathlib import Path


def resolve_vault(vault_path: str = "") -> Path:
    """Resolve an explicit/environment/current-directory Obsidian Vault."""
    selected = vault_path or os.environ.get("OBSIDIAN_VAULT_PATH", "")
    if not selected or selected.strip().lower() == "auto":
        current = Path.cwd().resolve()
        candidates = [current, *current.parents]
        match = next((path for path in candidates if (path / ".obsidian").is_dir()), None)
        if match is None:
            raise RuntimeError(
                "Could not resolve an Obsidian Vault. Pass vault_path, set "
                "OBSIDIAN_VAULT_PATH, or run inside a Vault containing .obsidian."
            )
        return match
    root = Path(selected).expanduser().resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"Vault path is not a directory: {root}")
    if not (root / ".obsidian").is_dir() and os.environ.get("OBSIDIAN_ALLOW_NON_VAULT", "").lower() not in {"1", "true", "yes"}:
        raise ValueError(f"Vault path has no .obsidian directory: {root}")
    return root
