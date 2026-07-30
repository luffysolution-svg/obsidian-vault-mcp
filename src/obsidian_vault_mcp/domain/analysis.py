"""Stable identity and strict frontmatter contracts for V3 Analysis notes."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .identity import validate_zotero_key

ANALYSIS_SCHEMA_VERSION = 1
ANALYSIS_TYPES = frozenset(
    {
        "full_read",
        "literature_review",
        "passage_qa",
        "figure_qa",
        "concept",
    }
)
ANALYSIS_STATUSES = frozenset({"draft", "ready", "reviewed", "needs_update", "archived"})
REMOVED_ANALYSIS_FIELDS = frozenset(
    {
        "analysisstatus",
        "assetid",
        "assetids",
        "coveragestatus",
        "coverageledger",
        "evidenceid",
        "evidenceids",
        "evidencestatus",
        "uncertainties",
        "uncertaintycount",
        "uncertaintystatus",
        "verificationstatus",
        "visualstatus",
    }
)
ANALYSIS_PROFILES = frozenset(
    {
        "general",
        "medicine",
        "chemistry",
        "materials",
        "catalysis",
        "physics",
        "mathematics",
    }
)

PAPER_KINDS = frozenset(
    {
        "experimental",
        "theoretical",
        "computational",
        "methodological",
        "clinical",
        "observational",
        "review",
        "dataset",
        "benchmark",
        "mixed",
        "other",
    }
)
REVIEW_MODES = frozenset({"thematic", "comparative", "narrative", "systematic", "scoping"})
LOCATOR_QUALITIES = frozenset({"exact", "section_only", "approximate"})
TARGET_TYPES = frozenset({"figure", "table", "scheme", "equation"})
VISUAL_MODES = frozenset({"image", "table_text", "caption_context", "equation_text"})
CONCEPT_KINDS = frozenset(
    {
        "theory",
        "mechanism",
        "method",
        "metric",
        "model",
        "material",
        "equation",
        "phenomenon",
    }
)

COMMON_ANALYSIS_FIELDS: tuple[str, ...] = (
    "analysisSchemaVersion",
    "analysisId",
    "analysisType",
    "analysisProfile",
    "secondaryProfiles",
    "title",
    "status",
    "analysisFocus",
    "primarySourceKey",
    "primarySource",
    "sourceKeys",
    "sourceCount",
    "summary",
    "sourceFingerprint",
    "skillName",
    "skillVersion",
    "createdAt",
    "updatedAt",
    "tags",
)

TYPE_ANALYSIS_FIELDS: dict[str, tuple[str, ...]] = {
    "full_read": (
        "paperTitle",
        "year",
        "journal",
        "paperKind",
        "researchQuestion",
        "coreContribution",
        "methodSummary",
        "mainFinding",
        "limitationSummary",
    ),
    "literature_review": (
        "reviewMode",
        "reviewQuestion",
        "scopeSummary",
        "timeRange",
        "taxonomySummary",
        "consensusSummary",
        "controversySummary",
        "gapSummary",
        "conclusionSummary",
    ),
    "passage_qa": (
        "question",
        "answerSummary",
        "sourceSection",
        "sourceSubsection",
        "sourceParagraph",
        "sourceLink",
        "locatorQuality",
        "quoteFingerprint",
    ),
    "figure_qa": (
        "question",
        "answerSummary",
        "targetType",
        "targetLabel",
        "targetPanel",
        "page",
        "imagePath",
        "imageExists",
        "visualMode",
        "sourceLink",
        "captionSummary",
    ),
    "concept": (
        "conceptName",
        "conceptKind",
        "aliases",
        "definitionSummary",
        "relationSummary",
        "useSummary",
        "prerequisites",
        "relatedConcepts",
    ),
}

_ordered_analysis_fields = list(COMMON_ANALYSIS_FIELDS)
for _analysis_type in ("full_read", "literature_review", "passage_qa", "figure_qa", "concept"):
    for _field in TYPE_ANALYSIS_FIELDS[_analysis_type]:
        if _field not in _ordered_analysis_fields:
            _ordered_analysis_fields.append(_field)
ANALYSIS_FIELD_ORDER = tuple(_ordered_analysis_fields)
del _analysis_type, _field, _ordered_analysis_fields

SUMMARY_FIELDS = frozenset(
    {
        "summary",
        "researchQuestion",
        "coreContribution",
        "methodSummary",
        "mainFinding",
        "limitationSummary",
        "reviewQuestion",
        "scopeSummary",
        "taxonomySummary",
        "consensusSummary",
        "controversySummary",
        "gapSummary",
        "conclusionSummary",
        "answerSummary",
        "definitionSummary",
        "relationSummary",
        "useSummary",
        "captionSummary",
    }
)

ANALYSIS_START_MARKER = "<!-- ovm:analysis:start -->"
ANALYSIS_END_MARKER = "<!-- ovm:analysis:end -->"

_SHA256_RE = re.compile(r"^[A-Fa-f0-9]{64}$")
_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_TARGET_LABEL_RE = re.compile(
    r"^\s*(fig(?:ure)?|table|scheme|eq(?:uation)?)\.?\s*[-:#]?\s*(\d+)"
    r"(?:\s*[\(\[]?([A-Za-z](?:\s*-\s*[A-Za-z])?)[\)\]]?)?\s*$",
    re.IGNORECASE,
)


class AnalysisValidationError(ValueError):
    """Raised when an Analysis payload violates the persisted contract."""


@dataclass(frozen=True)
class AnalysisIdentity:
    """One stable Analysis id and its matching portable filename."""

    analysis_id: str
    filename: str


def normalize_identity_text(value: Any) -> str:
    """Normalize identity input without erasing meaningful punctuation."""

    normalized = unicodedata.normalize("NFKC", str(value or ""))
    return " ".join(normalized.strip().split()).casefold()


def stable_id6(*parts: Any) -> str:
    """Return the first six uppercase SHA-256 characters for canonical parts."""

    canonical = "\0".join(normalize_identity_text(part) for part in parts)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:6].upper()


def slugify_analysis(value: Any, *, max_length: int = 24) -> str:
    """Return a deterministic Unicode-safe filename slug."""

    normalized = normalize_identity_text(value).replace("_", "-")
    slug = re.sub(r"[^\w-]+", "-", normalized, flags=re.UNICODE)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return (slug[:max_length].rstrip("-") or "analysis")


def normalize_target_token(
    target_label: Any,
    *,
    target_type: Any = "",
    target_panel: Any = "",
) -> str:
    """Normalize an explicit figure/table/scheme/equation label for filenames."""

    label = unicodedata.normalize("NFKC", str(target_label or "")).strip()
    match = _TARGET_LABEL_RE.fullmatch(label)
    if match is None:
        raise AnalysisValidationError(
            "targetLabel must explicitly contain a figure, table, scheme, or equation number"
        )
    raw_kind, raw_number, inline_panel = match.groups()
    kind = {
        "fig": "FIG",
        "figure": "FIG",
        "table": "TABLE",
        "scheme": "SCHEME",
        "eq": "EQ",
        "equation": "EQ",
    }[raw_kind.casefold()]
    requested_type = str(target_type or "").strip().casefold()
    expected_kind = {
        "figure": "FIG",
        "table": "TABLE",
        "scheme": "SCHEME",
        "equation": "EQ",
        "": kind,
    }.get(requested_type)
    if expected_kind is None or expected_kind != kind:
        raise AnalysisValidationError("targetType must agree with the explicit targetLabel")
    number = str(int(raw_number)).zfill(max(2, len(raw_number)))
    panel = str(target_panel or inline_panel or "")
    panel = re.sub(r"\s+", "", unicodedata.normalize("NFKC", panel)).upper()
    if panel and not re.fullmatch(r"[A-Z](?:-[A-Z])?", panel):
        raise AnalysisValidationError("targetPanel must be empty, a letter, or a letter range")
    if target_panel and inline_panel:
        normalized_inline = re.sub(
            r"\s+",
            "",
            unicodedata.normalize("NFKC", inline_panel),
        ).upper()
        if panel != normalized_inline:
            raise AnalysisValidationError(
                "targetPanel must agree with the panel in targetLabel"
            )
    return f"{kind}{number}{panel}"


def build_analysis_identity(fields: Mapping[str, Any]) -> AnalysisIdentity:
    """Build the expected stable identity from an Analysis frontmatter mapping."""

    if not isinstance(fields, Mapping):
        raise TypeError("analysis fields must be a mapping")
    analysis_type = str(fields.get("analysisType") or "")
    if analysis_type not in ANALYSIS_TYPES:
        raise AnalysisValidationError(f"unsupported analysisType: {analysis_type or '<empty>'}")
    source_keys = _identity_source_keys(fields.get("sourceKeys", ()))
    primary = str(fields.get("primarySourceKey") or "")

    if analysis_type == "full_read":
        key = _identity_primary_key(primary)
        analysis_id = f"FR-{key}"
    elif analysis_type == "literature_review":
        question = fields.get("reviewQuestion")
        slug = slugify_analysis(question)
        analysis_id = f"RV-{slug}-{stable_id6(question, *sorted(source_keys))}"
    elif analysis_type == "passage_qa":
        key = _identity_primary_key(primary)
        question = fields.get("question")
        analysis_id = f"PQ-{key}-{stable_id6(key, question)}"
    elif analysis_type == "figure_qa":
        key = _identity_primary_key(primary)
        token = normalize_target_token(
            fields.get("targetLabel"),
            target_type=fields.get("targetType"),
            target_panel=fields.get("targetPanel"),
        )
        analysis_id = f"FQ-{key}-{token}-{stable_id6(key, fields.get('targetLabel'), fields.get('targetPanel'), fields.get('question'))}"
    else:
        concept_name = fields.get("conceptName")
        slug = slugify_analysis(concept_name)
        analysis_id = f"CP-{slug}-{stable_id6(concept_name, *sorted(source_keys))}"
    return AnalysisIdentity(analysis_id=analysis_id, filename=f"{analysis_id}.md")


def validate_analysis_fields(
    fields: Mapping[str, Any],
    *,
    allow_reviewed: bool = False,
) -> dict[str, Any]:
    """Validate and normalize all common and type-specific Analysis fields."""

    if not isinstance(fields, Mapping):
        raise AnalysisValidationError("analysis fields must be an object")
    values = dict(fields)
    missing_common = [name for name in COMMON_ANALYSIS_FIELDS if name not in values]
    if missing_common:
        raise AnalysisValidationError(f"missing common Analysis field: {missing_common[0]}")

    if values["analysisSchemaVersion"] != ANALYSIS_SCHEMA_VERSION or isinstance(
        values["analysisSchemaVersion"], bool
    ):
        raise AnalysisValidationError(f"analysisSchemaVersion must be {ANALYSIS_SCHEMA_VERSION}")
    analysis_type = _enum(values, "analysisType", ANALYSIS_TYPES)
    _enum(values, "analysisProfile", ANALYSIS_PROFILES)
    status = _enum(values, "status", ANALYSIS_STATUSES)
    if status == "reviewed" and not allow_reviewed:
        raise AnalysisValidationError("status reviewed requires explicit user confirmation")

    for name in (
        "analysisId",
        "title",
        "analysisFocus",
        "summary",
        "sourceFingerprint",
        "skillName",
        "skillVersion",
        "createdAt",
        "updatedAt",
    ):
        _text(values, name)
    if not _SHA256_RE.fullmatch(str(values["sourceFingerprint"])):
        raise AnalysisValidationError("sourceFingerprint must be a SHA-256 hexadecimal digest")
    _iso_timestamp(values["createdAt"], "createdAt")
    _iso_timestamp(values["updatedAt"], "updatedAt")

    primary_key = _optional_text(values, "primarySourceKey")
    primary_source = _optional_text(values, "primarySource")
    source_keys = _string_list(values, "sourceKeys", allow_empty=False, zotero_keys=True)
    if len(source_keys) != len(set(source_keys)):
        raise AnalysisValidationError("sourceKeys must not contain duplicates")
    values["sourceKeys"] = source_keys
    if type(values["sourceCount"]) is not int or values["sourceCount"] != len(source_keys):
        raise AnalysisValidationError("sourceCount must equal the number of sourceKeys")
    if analysis_type == "literature_review" and len(source_keys) < 2:
        raise AnalysisValidationError("literature_review requires at least two sourceKeys")
    if analysis_type in {"full_read", "passage_qa", "figure_qa"} and not primary_key:
        raise AnalysisValidationError(f"{analysis_type} requires primarySourceKey")
    if primary_key:
        try:
            validate_zotero_key(primary_key)
        except ValueError as exc:
            raise AnalysisValidationError(str(exc)) from exc
        if primary_key not in source_keys:
            raise AnalysisValidationError("primarySourceKey must belong to sourceKeys")
        if not primary_source:
            raise AnalysisValidationError("primarySource is required when primarySourceKey is set")
    elif primary_source:
        raise AnalysisValidationError("primarySource must be empty when primarySourceKey is empty")

    profiles = _string_list(values, "secondaryProfiles", allow_empty=True)
    if len(profiles) != len(set(profiles)):
        raise AnalysisValidationError("secondaryProfiles must not contain duplicates")
    invalid_profiles = [profile for profile in profiles if profile not in ANALYSIS_PROFILES]
    if invalid_profiles:
        raise AnalysisValidationError(f"unsupported secondaryProfiles value: {invalid_profiles[0]}")
    if values["analysisProfile"] in profiles:
        raise AnalysisValidationError("secondaryProfiles must not repeat analysisProfile")
    values["secondaryProfiles"] = profiles
    values["tags"] = _string_list(values, "tags", allow_empty=True)

    required_type_fields = TYPE_ANALYSIS_FIELDS[analysis_type]
    missing_type = [name for name in required_type_fields if name not in values]
    if missing_type:
        raise AnalysisValidationError(
            f"missing {analysis_type} Analysis field: {missing_type[0]}"
        )
    _validate_type_fields(values, analysis_type)

    for name in SUMMARY_FIELDS:
        if name in values and isinstance(values[name], str) and values[name].strip():
            _validate_summary_length(name, values[name])

    expected = build_analysis_identity(values)
    if values["analysisId"] != expected.analysis_id:
        raise AnalysisValidationError(
            f"analysisId must match stable identity {expected.analysis_id}"
        )
    return values


def normalize_source_markdown(value: str) -> str:
    """Normalize Markdown line endings and trailing whitespace for hashing."""

    normalized = unicodedata.normalize("NFC", value).replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in normalized.split("\n")).strip() + "\n"


def markdown_source_fingerprint(value: str) -> str:
    return hashlib.sha256(normalize_source_markdown(value).encode("utf-8")).hexdigest()


def metadata_source_fingerprint(fields: Mapping[str, Any]) -> str:
    """Hash the stable metadata subset used when full text is unavailable."""

    canonical = json.dumps(
        {
            "title": normalize_identity_text(fields.get("title")),
            "abstract": normalize_identity_text(fields.get("abstract")),
            "year": normalize_identity_text(fields.get("year")),
            "doi": normalize_identity_text(fields.get("doi")),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def combined_source_fingerprint(source_fingerprints: Mapping[str, str]) -> str:
    """Combine sorted per-source fingerprints; preserve a single source hash."""

    if not isinstance(source_fingerprints, Mapping) or not source_fingerprints:
        raise AnalysisValidationError("at least one source fingerprint is required")
    normalized: list[tuple[str, str]] = []
    for key, fingerprint in source_fingerprints.items():
        try:
            validated_key = validate_zotero_key(str(key))
        except ValueError as exc:
            raise AnalysisValidationError(str(exc)) from exc
        value = str(fingerprint)
        if not _SHA256_RE.fullmatch(value):
            raise AnalysisValidationError(f"invalid source fingerprint for {validated_key}")
        normalized.append((validated_key, value.lower()))
    normalized.sort(key=lambda item: item[0])
    if len(normalized) == 1:
        return normalized[0][1]
    canonical = "\n".join(f"{key}:{fingerprint}" for key, fingerprint in normalized)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate_type_fields(values: dict[str, Any], analysis_type: str) -> None:
    if analysis_type == "full_read":
        for name in (
            "paperTitle",
            "journal",
            "researchQuestion",
            "coreContribution",
            "methodSummary",
            "mainFinding",
            "limitationSummary",
        ):
            _text(values, name)
        if values["year"] is None or values["year"] == "" or isinstance(values["year"], bool):
            raise AnalysisValidationError("year cannot be empty")
        _enum(values, "paperKind", PAPER_KINDS)
    elif analysis_type == "literature_review":
        _enum(values, "reviewMode", REVIEW_MODES)
        for name in (
            "reviewQuestion",
            "scopeSummary",
            "taxonomySummary",
            "consensusSummary",
            "controversySummary",
            "gapSummary",
            "conclusionSummary",
        ):
            _text(values, name)
        _optional_text(values, "timeRange")
    elif analysis_type == "passage_qa":
        for name in (
            "question",
            "answerSummary",
            "sourceSection",
            "sourceLink",
            "quoteFingerprint",
        ):
            _text(values, name)
        _optional_text(values, "sourceSubsection")
        _positive_integer_or_empty(values, "sourceParagraph")
        _enum(values, "locatorQuality", LOCATOR_QUALITIES)
    elif analysis_type == "figure_qa":
        for name in (
            "question",
            "answerSummary",
            "targetLabel",
            "sourceLink",
            "captionSummary",
        ):
            _text(values, name)
        target_type = _enum(values, "targetType", TARGET_TYPES)
        visual_mode = _enum(values, "visualMode", VISUAL_MODES)
        _optional_text(values, "targetPanel")
        _positive_integer_or_empty(values, "page")
        _optional_text(values, "imagePath")
        if type(values["imageExists"]) is not bool:
            raise AnalysisValidationError("imageExists must be a boolean")
        if not values["imageExists"] and visual_mode == "image":
            raise AnalysisValidationError("visualMode image requires imageExists true")
        if target_type == "table" and visual_mode == "equation_text":
            raise AnalysisValidationError("table targets cannot use equation_text")
        if target_type == "equation" and visual_mode == "table_text":
            raise AnalysisValidationError("equation targets cannot use table_text")
        normalize_target_token(
            values["targetLabel"],
            target_type=target_type,
            target_panel=values["targetPanel"],
        )
    else:
        for name in ("conceptName", "definitionSummary", "relationSummary", "useSummary"):
            _text(values, name)
        _enum(values, "conceptKind", CONCEPT_KINDS)
        for name in ("aliases", "prerequisites", "relatedConcepts"):
            values[name] = _string_list(values, name, allow_empty=True)


def _identity_source_keys(value: Any) -> list[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise AnalysisValidationError("sourceKeys must be an array of Zotero keys")
    result: list[str] = []
    for item in value:
        try:
            result.append(validate_zotero_key(str(item)))
        except ValueError as exc:
            raise AnalysisValidationError(str(exc)) from exc
    return result


def _identity_primary_key(value: str) -> str:
    try:
        return validate_zotero_key(value)
    except ValueError as exc:
        raise AnalysisValidationError(str(exc)) from exc


def _enum(values: Mapping[str, Any], name: str, allowed: frozenset[str]) -> str:
    value = values.get(name)
    if not isinstance(value, str) or value not in allowed:
        raise AnalysisValidationError(
            f"{name} must be one of: {', '.join(sorted(allowed))}"
        )
    return value


def _text(values: Mapping[str, Any], name: str) -> str:
    value = values.get(name)
    if not isinstance(value, str) or not value.strip():
        raise AnalysisValidationError(f"{name} must be a non-empty string")
    return value


def _optional_text(values: Mapping[str, Any], name: str) -> str:
    value = values.get(name)
    if not isinstance(value, str):
        raise AnalysisValidationError(f"{name} must be a string")
    return value.strip()


def _string_list(
    values: Mapping[str, Any],
    name: str,
    *,
    allow_empty: bool,
    zotero_keys: bool = False,
) -> list[str]:
    value = values.get(name)
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise AnalysisValidationError(f"{name} must be an array of strings")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise AnalysisValidationError(f"{name} must contain non-empty strings")
        normalized = item.strip()
        if zotero_keys:
            try:
                normalized = validate_zotero_key(normalized)
            except ValueError as exc:
                raise AnalysisValidationError(str(exc)) from exc
        result.append(normalized)
    if not result and not allow_empty:
        raise AnalysisValidationError(f"{name} cannot be empty")
    return result


def _positive_integer_or_empty(values: Mapping[str, Any], name: str) -> None:
    value = values.get(name)
    if value is None or value == "":
        return
    if type(value) is not int or value < 1:
        raise AnalysisValidationError(f"{name} must be empty or a positive integer")


def _validate_summary_length(name: str, value: str) -> None:
    limit = 180 if _CJK_RE.search(value) else 300
    if len(value) > limit:
        raise AnalysisValidationError(f"{name} must not exceed {limit} characters")


def _iso_timestamp(value: Any, name: str) -> None:
    try:
        datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise AnalysisValidationError(f"{name} must be an ISO-8601 timestamp") from exc
