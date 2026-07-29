"""Structured records describing what a caller actually read."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .identity import validate_zotero_key

SOURCE_KINDS = frozenset(
    {
        "zotero_metadata",
        "abstract",
        "zotero_notes",
        "zotero_annotations",
        "mineru",
        "evidence_index",
        "mineru_image",
        "pdf_crop",
        "pdf_visual",
        "analysis_note",
        "analysis_index",
    }
)
GRANULARITIES = frozenset({"metadata", "abstract", "overview", "section", "passage", "figure", "visual_page", "full"})
COVERAGE_LEVELS = frozenset({"listed", "partial", "targeted", "broad", "complete"})
CONFIDENCE_LEVELS = frozenset({"low", "medium", "high"})


@dataclass(frozen=True)
class CoverageRecord:
    """One auditable, non-evidentiary read-coverage observation."""

    resource_key: str
    source_kind: str
    topic: str
    granularity: str
    coverage: str
    confidence: str
    content_hash: str
    tool_name: str
    evidence_refs: tuple[str, ...] = ()
    asset_refs: tuple[str, ...] = ()
    count: int = 1
    updated_at: str = ""
    stale: bool = False
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.resource_key.startswith("paper:"):
            raise ValueError("coverage resourceKey must use the paper:<zoteroKey> form")
        validate_zotero_key(self.resource_key[6:])
        if self.source_kind not in SOURCE_KINDS:
            raise ValueError(f"unsupported coverage sourceKind: {self.source_kind}")
        if self.granularity not in GRANULARITIES:
            raise ValueError(f"unsupported coverage granularity: {self.granularity}")
        if self.coverage not in COVERAGE_LEVELS:
            raise ValueError(f"unsupported coverage value: {self.coverage}")
        if self.confidence not in CONFIDENCE_LEVELS:
            raise ValueError(f"unsupported coverage confidence: {self.confidence}")
        if type(self.count) is not int or self.count < 1:
            raise ValueError("coverage count must be a positive integer")
        if self.granularity in {"metadata", "abstract", "overview"} and self.coverage == "complete":
            raise ValueError(f"{self.granularity} coverage cannot be marked complete")
        if self.granularity == "full" and self.details.get("truncated") and self.coverage != "partial":
            raise ValueError("truncated full coverage must be marked partial")
        if self.source_kind == "mineru_image" and self.details.get("visualStatus") == "visual_verified":
            raise ValueError("a MinerU image candidate cannot be marked visual_verified")
        object.__setattr__(self, "evidence_refs", tuple(sorted(set(self.evidence_refs))))
        object.__setattr__(self, "asset_refs", tuple(sorted(set(self.asset_refs))))
        object.__setattr__(self, "details", dict(self.details))

    @property
    def zotero_key(self) -> str:
        return self.resource_key[6:]

    @property
    def identity(self) -> tuple[Any, ...]:
        """Fields whose equality means another read can increment this record."""

        return (
            self.resource_key,
            self.source_kind,
            self.topic,
            self.granularity,
            self.coverage,
            self.confidence,
            self.content_hash,
            self.tool_name,
            self.evidence_refs,
            self.asset_refs,
            self.stale,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "resourceKey": self.resource_key,
            "sourceKind": self.source_kind,
            "topic": self.topic,
            "granularity": self.granularity,
            "coverage": self.coverage,
            "confidence": self.confidence,
            "contentHash": self.content_hash,
            "toolName": self.tool_name,
            "evidenceRefs": list(self.evidence_refs),
            "assetRefs": list(self.asset_refs),
            "count": self.count,
            "updatedAt": self.updated_at,
            "stale": self.stale,
            "details": dict(self.details),
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "CoverageRecord":
        return cls(
            resource_key=str(value.get("resourceKey") or ""),
            source_kind=str(value.get("sourceKind") or ""),
            topic=str(value.get("topic") or ""),
            granularity=str(value.get("granularity") or ""),
            coverage=str(value.get("coverage") or ""),
            confidence=str(value.get("confidence") or ""),
            content_hash=str(value.get("contentHash") or ""),
            tool_name=str(value.get("toolName") or ""),
            evidence_refs=tuple(str(item) for item in value.get("evidenceRefs") or ()),
            asset_refs=tuple(str(item) for item in value.get("assetRefs") or ()),
            count=value.get("count", 1),
            updated_at=str(value.get("updatedAt") or ""),
            stale=bool(value.get("stale", False)),
            details=dict(value.get("details") or {}),
        )
