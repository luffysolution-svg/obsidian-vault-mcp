"""Transactional uncertainty listing, resolution, and audit history."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from ..config.loader import ConfigLoader
from ..config.schema import validate_config
from ..domain.analysis import (
    ANALYSIS_FIELD_ORDER,
    UncertaintyItem,
    UncertaintyStatus,
    active_uncertainty_count,
)
from ..domain.frontmatter import compose_frontmatter, merge_frontmatter, parse_frontmatter
from ..domain.identity import validate_zotero_key
from .analysis_service import (
    UNCERTAINTY_BLOCK,
    AnalysisService,
    _json_text,
    _load_uncertainty_state,
    _uncertainty_state_path,
    _utc_now,
    _validate_asset_paths,
    _validate_conflict_policy,
    _validated_timestamp,
    render_uncertainty_block,
    replace_managed_block,
)
from .transaction_service import TransactionService

_RESOLUTION_STATUSES = {
    UncertaintyStatus.CONFIRMED,
    UncertaintyStatus.REJECTED,
    UncertaintyStatus.REVISED,
    UncertaintyStatus.UNRESOLVED,
}
_RELIABLE_VISUAL_STATUSES = {"pdf_crop_available", "visual_verified"}


class UncertaintyService:
    """Maintain one hidden, append-audited uncertainty state per paper."""

    def __init__(
        self,
        vault_path: str | Path,
        config: Mapping[str, Any] | None = None,
    ) -> None:
        self.vault_path = Path(vault_path).expanduser().resolve()
        self.config = (
            validate_config(config)
            if config is not None
            else ConfigLoader(self.vault_path).load(require_exists=False)
        )
        self.analysis = AnalysisService(self.vault_path, self.config)
        self.fs = self.analysis.fs
        self.transactions = TransactionService(self.vault_path)

    def list(
        self,
        zotero_key: str,
        *,
        statuses: Sequence[str] = (),
        include_history: bool = True,
    ) -> dict[str, Any]:
        key = validate_zotero_key(zotero_key)
        selected = _validated_status_filter(statuses)
        state = _load_uncertainty_state(self.fs, key)
        items = [UncertaintyItem.from_mapping(item, zotero_key=key) for item in state.get("items", [])]
        if selected:
            items = [item for item in items if item.status in selected]
        items.sort(key=lambda item: item.uncertainty_id)
        return {
            "ok": True,
            "zoteroKey": key,
            "items": [item.as_dict() for item in items],
            "count": len(items),
            "pendingCount": active_uncertainty_count(items),
            "history": list(state.get("history") or []) if include_history else [],
            "updatedAt": str(state.get("updatedAt") or ""),
        }

    def resolve(
        self,
        zotero_key: str,
        uncertainty_id: str,
        status: str,
        *,
        evidence_ids: Sequence[str] = (),
        asset_ids: Sequence[str] = (),
        revised_claim: str = "",
        resolution_note: str = "",
        resolved_at: str | None = None,
        dry_run: bool = False,
        transaction_id: str | None = None,
        conflict_policy: str = "preserve-user",
    ) -> dict[str, Any]:
        """Resolve one item while preserving its original claim and every prior audit event."""

        key = validate_zotero_key(zotero_key)
        _validate_conflict_policy(conflict_policy)
        self.analysis._main_note(key)
        try:
            next_status = UncertaintyStatus(status)
        except ValueError as exc:
            raise ValueError("invalid uncertainty resolution status") from exc
        if next_status not in _RESOLUTION_STATUSES:
            raise ValueError("resolve status must be confirmed, rejected, revised, or unresolved")
        state = _load_uncertainty_state(self.fs, key)
        raw_items = list(state.get("items") or [])
        items = [UncertaintyItem.from_mapping(item, zotero_key=key) for item in raw_items]
        matching = [item for item in items if item.uncertainty_id == uncertainty_id]
        if not matching:
            raise KeyError(f"unknown uncertaintyId: {uncertainty_id}")
        if len(matching) > 1:
            raise ValueError(f"duplicate uncertaintyId in state: {uncertainty_id}")
        current = matching[0]

        evidence_state, _warnings = self.analysis._load_evidence_state(
            key,
            require_persisted_current=True,
        )
        evidence_by_id = {
            str(item.get("evidenceId")): item
            for item in evidence_state.get("chunks", evidence_state.get("evidenceChunks", []))
            if isinstance(item, Mapping) and item.get("evidenceId")
        }
        manifest, _manifest_warnings = self.analysis._load_manifest(key, require_current=True)
        asset_by_id = {
            str(item.get("assetId")): item
            for item in manifest.get("assets", [])
            if isinstance(item, Mapping) and item.get("assetId")
        }
        selected_evidence = _deduplicated_strings(evidence_ids) or list(current.evidence_ids)
        selected_assets = _deduplicated_strings(asset_ids) or list(current.asset_ids)
        if evidence_state.get("stale") is True and selected_evidence:
            raise ValueError("cannot resolve against stale EvidenceChunk state")
        _validate_references(selected_evidence, selected_assets, evidence_by_id, asset_by_id)
        if next_status is UncertaintyStatus.CONFIRMED:
            if not selected_evidence:
                raise ValueError("confirmed uncertainties require original-text evidenceIds")
            if _is_visual_item(current, selected_assets):
                if not selected_assets:
                    raise ValueError("confirmed visual uncertainties require image assetIds")
                for asset_id in selected_assets:
                    asset = asset_by_id[asset_id]
                    if str(asset.get("status") or "") == "unlinked_candidate":
                        raise ValueError("unlinked_candidate is insufficient to confirm a visual claim")
                    if str(asset.get("visualStatus") or "") not in _RELIABLE_VISUAL_STATUSES:
                        raise ValueError("visual confirmation requires pdf_crop_available or visual_verified evidence")
        revised = revised_claim.strip()
        if next_status is UncertaintyStatus.REVISED and not revised:
            raise ValueError("revised resolution requires revised_claim")
        note = resolution_note.strip()
        candidate = {
            **current.as_dict(),
            "status": next_status.value,
            "evidenceIds": selected_evidence,
            "assetIds": selected_assets,
            "originalClaim": current.original_claim or current.claim,
            "revisedClaim": revised if next_status is UncertaintyStatus.REVISED else "",
            "resolutionNote": note,
        }
        unchanged = _same_resolution(current, candidate)
        timestamp = (
            current.resolved_at
            if unchanged and current.resolved_at
            else _validated_timestamp(resolved_at) if resolved_at is not None else _utc_now()
        )
        candidate["resolvedAt"] = timestamp
        resolved = UncertaintyItem.from_mapping(candidate, zotero_key=key)
        next_items = [resolved if item.uncertainty_id == uncertainty_id else item for item in items]
        next_items.sort(key=lambda item: item.uncertainty_id)
        history = list(state.get("history") or [])
        if not unchanged:
            history.append(
                {
                    "uncertaintyId": uncertainty_id,
                    "fromStatus": current.status.value,
                    "toStatus": next_status.value,
                    "evidenceIds": selected_evidence,
                    "assetIds": selected_assets,
                    "revisedClaim": resolved.revised_claim,
                    "resolutionNote": resolved.resolution_note,
                    "resolvedAt": timestamp,
                }
            )
        next_state = {
            "schemaVersion": 1,
            "zoteroKey": key,
            "items": [item.as_dict() for item in next_items],
            "history": history,
            "updatedAt": str(state.get("updatedAt") or "") if unchanged else timestamp,
        }

        transaction = self.transactions.begin(item_key=key, transaction_id=transaction_id, dry_run=dry_run)
        transaction.write_text(_uncertainty_state_path(key), _json_text(next_state))
        analysis_path = self.analysis.analysis_path(key)
        if self.fs.exists(analysis_path):
            document = parse_frontmatter(self.fs.read_text(analysis_path))
            body = replace_managed_block(document.body, UNCERTAINTY_BLOCK, render_uncertainty_block(next_items))
            active_count = active_uncertainty_count(next_items)
            evidence_state_name = str(document.fields.get("evidenceStatus") or "unverified")
            analysis_state_name = "verified" if active_count == 0 and evidence_state_name == "complete" else "draft"
            fields = merge_frontmatter(
                document.fields,
                {
                    "analysisStatus": analysis_state_name,
                    "uncertaintyCount": active_count,
                    "updatedAt": str(document.fields.get("updatedAt") or "") if unchanged else timestamp,
                },
                omit_empty=False,
                preserve_unknown_fields=True,
                field_order=ANALYSIS_FIELD_ORDER,
            )
            transaction.write_text(
                analysis_path,
                compose_frontmatter(fields, body, omit_empty=False, field_order=ANALYSIS_FIELD_ORDER),
            )
        result = transaction.commit()
        return {
            **result,
            "zoteroKey": key,
            "uncertainty": resolved.as_dict(),
            "pendingCount": active_uncertainty_count(next_items),
            "historyCount": len(history),
        }

    def rollback(
        self,
        transaction_id: str,
        *,
        dry_run: bool = False,
        conflict_policy: str = "preserve-user",
    ) -> dict[str, Any]:
        return self.transactions.rollback(transaction_id, dry_run=dry_run, conflict_policy=conflict_policy)


def _validated_status_filter(values: Sequence[str]) -> set[UncertaintyStatus]:
    if isinstance(values, (str, bytes)):
        raise TypeError("statuses must be an array")
    result: set[UncertaintyStatus] = set()
    for value in values:
        try:
            result.add(UncertaintyStatus(str(value)))
        except ValueError as exc:
            raise ValueError(f"invalid uncertainty status filter: {value}") from exc
    return result


def _deduplicated_strings(values: Sequence[str]) -> list[str]:
    if isinstance(values, (str, bytes)):
        raise TypeError("reference ids must be arrays")
    result: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value:
            raise ValueError("reference ids must be non-empty strings")
        if value not in result:
            result.append(value)
    return result


def _validate_references(
    evidence_ids: Sequence[str],
    asset_ids: Sequence[str],
    evidence_by_id: Mapping[str, Mapping[str, Any]],
    asset_by_id: Mapping[str, Mapping[str, Any]],
) -> None:
    for evidence_id in evidence_ids:
        if evidence_id not in evidence_by_id:
            raise ValueError(f"unknown evidenceId: {evidence_id}")
    for asset_id in asset_ids:
        if asset_id not in asset_by_id:
            raise ValueError(f"unknown assetId: {asset_id}")
        _validate_asset_paths(asset_by_id[asset_id])


def _is_visual_item(item: UncertaintyItem, selected_assets: Sequence[str]) -> bool:
    target = item.verification_target
    return bool(
        selected_assets
        or item.asset_ids
        or target.get("figure")
        or target.get("assetId")
        or target.get("visual")
    )


def _same_resolution(current: UncertaintyItem, candidate: Mapping[str, Any]) -> bool:
    return (
        current.status.value == candidate.get("status")
        and list(current.evidence_ids) == candidate.get("evidenceIds")
        and list(current.asset_ids) == candidate.get("assetIds")
        and current.original_claim == candidate.get("originalClaim")
        and current.revised_claim == candidate.get("revisedClaim")
        and current.resolution_note == candidate.get("resolutionNote")
    )
