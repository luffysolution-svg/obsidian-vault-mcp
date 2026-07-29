"""Structured-analysis and uncertainty contracts for literature notes."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from .identity import validate_zotero_key


class ClaimType(str, Enum):
    SOURCE_FACT = "source_fact"
    AUTHOR_INTERPRETATION = "author_interpretation"
    AGENT_INFERENCE = "agent_inference"
    USER_NOTE = "user_note"


class VerificationStatus(str, Enum):
    VERIFIED = "verified"
    PARTIAL = "partial"
    UNVERIFIED = "unverified"


class UncertaintyStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    REVISED = "revised"
    UNRESOLVED = "unresolved"


ANALYSIS_FIELD_ORDER: tuple[str, ...] = (
    "title",
    "zoteroKey",
    "sourceNote",
    "analysisStatus",
    "evidenceStatus",
    "uncertaintyCount",
    "updatedAt",
)


STRUCTURED_READING_SECTIONS: tuple[tuple[str, str], ...] = (
    ("bibliographic-information", "文献基本信息"),
    ("research-background", "研究背景"),
    ("research-question", "核心研究问题"),
    ("key-concepts", "主要概念"),
    ("theoretical-foundation", "理论基础"),
    ("mechanisms", "核心观点与作用机制"),
    ("research-methods", "研究设计与研究方法"),
    ("findings", "主要研究结论"),
    ("theoretical-contributions", "理论贡献"),
    ("practical-implications", "实践启示"),
    ("limitations", "研究局限"),
    ("review-relevance", "可用于文献综述的内容"),
    ("further-questions", "后续需要继续思考的问题"),
)

STRUCTURED_READING_SECTION_IDS = frozenset(section_id for section_id, _title in STRUCTURED_READING_SECTIONS)
ACTIVE_UNCERTAINTY_STATUSES = frozenset({UncertaintyStatus.PENDING.value, UncertaintyStatus.UNRESOLVED.value})


@dataclass(frozen=True)
class AnalysisClaim:
    """One typed statement written by an external Agent or the user."""

    claim_type: ClaimType
    content: str
    evidence_ids: tuple[str, ...] = ()
    asset_ids: tuple[str, ...] = ()
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "AnalysisClaim":
        if not isinstance(value, Mapping):
            raise TypeError("analysis claim must be an object")
        content = str(value.get("content") or "").strip()
        if not content:
            raise ValueError("analysis claim content cannot be empty")
        try:
            claim_type = ClaimType(str(value.get("claimType") or ClaimType.AGENT_INFERENCE.value))
        except ValueError as exc:
            raise ValueError("invalid analysis claimType") from exc
        try:
            verification = VerificationStatus(
                str(value.get("verificationStatus") or VerificationStatus.UNVERIFIED.value)
            )
        except ValueError as exc:
            raise ValueError("invalid analysis verificationStatus") from exc
        return cls(
            claim_type=claim_type,
            content=content,
            evidence_ids=_string_tuple(value.get("evidenceIds", ()), "evidenceIds"),
            asset_ids=_string_tuple(value.get("assetIds", ()), "assetIds"),
            verification_status=verification,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "claimType": self.claim_type.value,
            "content": self.content,
            "evidenceIds": list(self.evidence_ids),
            "assetIds": list(self.asset_ids),
            "verificationStatus": self.verification_status.value,
        }


@dataclass(frozen=True)
class UncertaintyItem:
    """A durable claim-verification item with a stable identity."""

    uncertainty_id: str
    zotero_key: str
    claim: str
    reason: str
    verification_target: Mapping[str, Any]
    status: UncertaintyStatus = UncertaintyStatus.PENDING
    evidence_ids: tuple[str, ...] = ()
    asset_ids: tuple[str, ...] = ()
    original_claim: str = ""
    revised_claim: str = ""
    resolution_note: str = ""
    created_at: str = ""
    resolved_at: str = ""

    def __post_init__(self) -> None:
        validate_zotero_key(self.zotero_key)
        if not self.uncertainty_id or not self.uncertainty_id.startswith(f"U-{self.zotero_key}-"):
            raise ValueError("uncertaintyId must be scoped to zoteroKey")
        if not self.claim.strip():
            raise ValueError("uncertainty claim cannot be empty")
        if not self.reason.strip():
            raise ValueError("uncertainty reason cannot be empty")
        for name, value in (("createdAt", self.created_at), ("resolvedAt", self.resolved_at)):
            if not value:
                continue
            try:
                datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError(f"uncertainty {name} must be an ISO-8601 timestamp") from exc
        if self.status is UncertaintyStatus.PENDING and self.resolved_at:
            raise ValueError("pending uncertainty cannot have resolvedAt")
        if self.status is not UncertaintyStatus.PENDING and not self.resolved_at:
            raise ValueError("resolved uncertainty requires resolvedAt")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any], *, zotero_key: str | None = None) -> "UncertaintyItem":
        if not isinstance(value, Mapping):
            raise TypeError("uncertainty item must be an object")
        key = validate_zotero_key(str(zotero_key or value.get("zoteroKey") or ""))
        claim = str(value.get("claim") or "").strip()
        reason = str(value.get("reason") or "").strip()
        target = value.get("verificationTarget") or {}
        if not isinstance(target, Mapping):
            raise TypeError("verificationTarget must be an object")
        uncertainty_id = str(value.get("uncertaintyId") or stable_uncertainty_id(key, claim, reason, target))
        try:
            status = UncertaintyStatus(str(value.get("status") or UncertaintyStatus.PENDING.value))
        except ValueError as exc:
            raise ValueError("invalid uncertainty status") from exc
        return cls(
            uncertainty_id=uncertainty_id,
            zotero_key=key,
            claim=claim,
            reason=reason,
            verification_target=dict(target),
            status=status,
            evidence_ids=_string_tuple(value.get("evidenceIds", ()), "evidenceIds"),
            asset_ids=_string_tuple(value.get("assetIds", ()), "assetIds"),
            original_claim=str(value.get("originalClaim") or ""),
            revised_claim=str(value.get("revisedClaim") or ""),
            resolution_note=str(value.get("resolutionNote") or ""),
            created_at=str(value.get("createdAt") or ""),
            resolved_at=str(value.get("resolvedAt") or ""),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "uncertaintyId": self.uncertainty_id,
            "zoteroKey": self.zotero_key,
            "claim": self.claim,
            "reason": self.reason,
            "verificationTarget": dict(self.verification_target),
            "status": self.status.value,
            "evidenceIds": list(self.evidence_ids),
            "assetIds": list(self.asset_ids),
            "originalClaim": self.original_claim,
            "revisedClaim": self.revised_claim,
            "resolutionNote": self.resolution_note,
            "createdAt": self.created_at,
            "resolvedAt": self.resolved_at,
        }


def stable_uncertainty_id(
    zotero_key: str,
    claim: str,
    reason: str,
    verification_target: Mapping[str, Any] | None = None,
) -> str:
    """Create a deterministic id without relying on list order or line numbers."""

    key = validate_zotero_key(zotero_key)
    canonical = json.dumps(
        {
            "claim": " ".join(str(claim).split()),
            "reason": " ".join(str(reason).split()),
            "verificationTarget": dict(verification_target or {}),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(f"{key}\0{canonical}".encode()).hexdigest()[:12].upper()
    return f"U-{key}-{digest}"


def evidence_status(claims: Sequence[AnalysisClaim]) -> str:
    evidence_claims = [claim for claim in claims if claim.claim_type is not ClaimType.USER_NOTE]
    if not evidence_claims:
        return "unverified"
    if all(
        claim.verification_status is VerificationStatus.VERIFIED and claim.evidence_ids
        for claim in evidence_claims
    ):
        return "complete"
    if any(
        claim.evidence_ids
        and claim.verification_status in {VerificationStatus.VERIFIED, VerificationStatus.PARTIAL}
        for claim in evidence_claims
    ):
        return "partial"
    return "unverified"


def analysis_status(claims: Sequence[AnalysisClaim], uncertainty_count: int) -> str:
    if uncertainty_count or evidence_status(claims) != "complete":
        return "draft"
    return "verified"


def active_uncertainty_count(items: Sequence[UncertaintyItem | Mapping[str, Any]]) -> int:
    count = 0
    for item in items:
        status = item.status.value if isinstance(item, UncertaintyItem) else str(item.get("status") or "")
        count += status in ACTIVE_UNCERTAINTY_STATUSES
    return count


def _string_tuple(value: Any, label: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError(f"{label} must be an array of strings")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{label} must contain non-empty strings")
        if item not in result:
            result.append(item)
    return tuple(result)
