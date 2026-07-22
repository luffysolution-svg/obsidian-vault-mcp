from __future__ import annotations

import json
import os
from collections.abc import Iterable, Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from ..adapters.obsidian.index_renderer import render_index
from ..adapters.vault.filesystem import VaultFilesystem
from ..adapters.vault.lock import GlobalLock
from ..config.loader import load_config
from ..domain.frontmatter import parse_frontmatter
from ..domain.paths import VaultPaths
from .transaction_service import TransactionService


class IndexService:
    def __init__(self, vault_path: str | os.PathLike[str], config: Mapping[str, Any] | None = None) -> None:
        self.vault_path = Path(vault_path).expanduser().resolve()
        self.config = dict(config) if config is not None else load_config(self.vault_path, require_exists=False)
        self.fs = VaultFilesystem(self.vault_path)
        self.paths = VaultPaths(self.vault_path, self.config)

    @property
    def index_path(self) -> str:
        return str(self.config["literature"]["index"])

    def records(self, overlays: Iterable[Mapping[str, Any]] = ()) -> list[dict[str, Any]]:
        """Read canonical top-level literature notes and merge in-memory overlays."""
        root_rel = str(self.config["literature"]["root"])
        root = self.paths.resolve(root_rel)
        index_path = self.paths.resolve(self.index_path)
        records: list[dict[str, Any]] = []
        if root.is_dir():
            for path in sorted(root.glob("*.md"), key=lambda item: item.name.casefold()):
                if path.resolve() == index_path.resolve():
                    continue
                document = parse_frontmatter(path.read_text(encoding="utf-8-sig"))
                key = str(document.fields.get("zoteroKey") or "").strip()
                if not key:
                    continue
                record = dict(document.fields)
                record["notePath"] = self.fs.relative(path)
                state_path = self.paths.resolve(self.paths.state(key))
                if state_path.is_file():
                    try:
                        state = json.loads(state_path.read_text(encoding="utf-8"))
                    except (OSError, UnicodeError, json.JSONDecodeError):
                        state = {}
                    if isinstance(state, dict):
                        record["lastImportedAt"] = state.get("lastImportedAt") or ""
                records.append(record)

        overlay_by_key = {
            str(record.get("zoteroKey") or ""): dict(record)
            for record in overlays
            if str(record.get("zoteroKey") or "")
        }
        if overlay_by_key:
            records = [record for record in records if str(record.get("zoteroKey") or "") not in overlay_by_key]
            records.extend(overlay_by_key.values())
        return records

    def wiki_topics(self) -> list[str]:
        folder = self.paths.resolve(str(self.config["literature"]["wikiFolder"]))
        if not folder.is_dir():
            return []
        return sorted((path.stem for path in folder.glob("*.md") if path.is_file()), key=str.casefold)

    def render(self, overlays: Iterable[Mapping[str, Any]] = ()) -> str:
        return render_index(
            self.records(overlays),
            self.wiki_topics(),
            recent_limit=int(self.config["index"]["recentLimit"]),
            base_path=str(self.config["literature"]["base"]),
            wiki_folder=str(self.config["literature"]["wikiFolder"]),
        )

    def rebuild(
        self,
        *,
        dry_run: bool = False,
        transaction_id: str | None = None,
        conflict_policy: str = "preserve-user",
    ) -> dict[str, Any]:
        del conflict_policy
        records = self.records()
        transaction = TransactionService(self.vault_path).begin(transaction_id=transaction_id, dry_run=dry_run)
        transaction.write_text(self.index_path, render_index(
            records,
            self.wiki_topics(),
            recent_limit=int(self.config["index"]["recentLimit"]),
            base_path=str(self.config["literature"]["base"]),
            wiki_folder=str(self.config["literature"]["wikiFolder"]),
        ))
        if dry_run:
            result = transaction.commit()
        else:
            with GlobalLock(self.vault_path, "index"):
                result = transaction.commit()
        return {**result, "path": self.index_path, "items": len(records)}


def note_stem(note_path: str) -> str:
    return PurePosixPath(note_path).stem
