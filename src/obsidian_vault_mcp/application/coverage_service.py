"""Transactional hidden-state ledger for actual literature read coverage."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from ..adapters.vault.filesystem import VaultFilesystem
from ..config.loader import load_config
from ..domain.coverage import CoverageRecord
from ..domain.identity import validate_zotero_key
from ..domain.paths import VaultPaths
from .transaction_service import TransactionService

_MAX_RECORDS_PER_PAPER = 256


class CoverageService:
    """Read and update coverage state without touching user-authored notes."""

    def __init__(self, vault_path: str | os.PathLike[str], config: dict[str, Any] | None = None) -> None:
        self.vault_path = Path(vault_path).expanduser().resolve()
        self.config = config or load_config(self.vault_path, require_exists=False)
        self.fs = VaultFilesystem(self.vault_path)
        self.paths = VaultPaths(self.vault_path, self.config)
        self.transactions = TransactionService(self.vault_path)

    def state_path(self, zotero_key: str) -> str:
        return self.paths.coverage_state(zotero_key)

    def load(self, zotero_key: str) -> dict[str, Any]:
        """Return a valid ledger or a non-fatal warning when it cannot be read."""

        key = validate_zotero_key(zotero_key)
        path = self.state_path(key)
        if not self.fs.exists(path):
            return {"schemaVersion": 1, "zoteroKey": key, "records": [], "warnings": []}
        try:
            raw = json.loads(self.fs.read_text(path))
            if not isinstance(raw, dict) or raw.get("zoteroKey") != key or raw.get("schemaVersion") != 1:
                raise ValueError("coverage state identity or schema mismatch")
            records = [CoverageRecord.from_dict(item).as_dict() for item in raw.get("records", [])]
            return {"schemaVersion": 1, "zoteroKey": key, "records": records, "warnings": []}
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            return {
                "schemaVersion": 1,
                "zoteroKey": key,
                "records": [],
                "warnings": [{"code": "invalid-coverage-state", "message": str(exc), "path": path}],
            }

    def record(
        self,
        zotero_key: str,
        *,
        source_kind: str,
        topic: str,
        granularity: str,
        coverage: str,
        confidence: str,
        content_hash: str,
        tool_name: str,
        evidence_refs: Iterable[str] = (),
        asset_refs: Iterable[str] = (),
        valid_evidence_ids: set[str] | None = None,
        valid_asset_ids: set[str] | None = None,
        details: dict[str, Any] | None = None,
        dry_run: bool = False,
        transaction_id: str | None = None,
        now: str | None = None,
    ) -> dict[str, Any]:
        """Add or increment one record through the repository transaction engine."""

        key = validate_zotero_key(zotero_key)
        evidence = tuple(sorted(set(str(item) for item in evidence_refs)))
        assets = tuple(sorted(set(str(item) for item in asset_refs)))
        if valid_evidence_ids is not None and not set(evidence) <= valid_evidence_ids:
            raise ValueError("coverage evidenceRefs contain an unknown evidenceId")
        if valid_asset_ids is not None and not set(assets) <= valid_asset_ids:
            raise ValueError("coverage assetRefs contain an unknown assetId")

        loaded = self.load(key)
        if loaded["warnings"] and self.fs.exists(self.state_path(key)):
            raise ValueError(loaded["warnings"][0]["message"])
        timestamp = now or _utc_now()
        incoming = CoverageRecord(
            resource_key=f"paper:{key}",
            source_kind=source_kind,
            topic=" ".join(topic.split()),
            granularity=granularity,
            coverage=coverage,
            confidence=confidence,
            content_hash=content_hash,
            tool_name=tool_name,
            evidence_refs=evidence,
            asset_refs=assets,
            updated_at=timestamp,
            details=details or {},
        )
        records = [CoverageRecord.from_dict(item) for item in loaded["records"]]

        current_family = (incoming.resource_key, incoming.source_kind, incoming.topic, incoming.granularity, incoming.tool_name)
        normalized: list[CoverageRecord] = []
        matched = False
        for record in records:
            family = (record.resource_key, record.source_kind, record.topic, record.granularity, record.tool_name)
            if family == current_family and record.content_hash != incoming.content_hash and not record.stale:
                record = CoverageRecord(**{**record.__dict__, "stale": True})
            if record.identity == incoming.identity:
                incoming = CoverageRecord(**{**incoming.__dict__, "count": record.count + 1})
                matched = True
                continue
            normalized.append(record)
        normalized.append(incoming)
        normalized.sort(key=lambda item: (not item.stale, item.updated_at, item.source_kind, item.topic, item.granularity, item.content_hash))
        if len(normalized) > _MAX_RECORDS_PER_PAPER:
            normalized = normalized[-_MAX_RECORDS_PER_PAPER:]

        state = {
            "schemaVersion": 1,
            "zoteroKey": key,
            "records": [record.as_dict() for record in normalized],
        }
        transaction = self.transactions.begin(item_key=key, transaction_id=transaction_id, dry_run=dry_run)
        transaction.write_text(self.state_path(key), json.dumps(state, ensure_ascii=False, indent=2) + "\n")
        result = transaction.commit()
        return {
            **result,
            "zoteroKey": key,
            "coverageRecord": incoming.as_dict(),
            "incremented": matched,
            "recordCount": len(normalized),
        }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
