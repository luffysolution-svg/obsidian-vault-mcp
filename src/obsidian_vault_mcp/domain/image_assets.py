"""Deterministic MinerU image asset identities and manifest contracts."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import PurePosixPath
from typing import Any

from .identity import validate_zotero_key
from .paths import normalize_vault_relative

IMAGE_MANIFEST_SCHEMA_VERSION = 1
SUPPORTED_IMAGE_EXTENSIONS = frozenset({"png", "jpg", "jpeg", "gif", "webp", "bmp", "svg"})
ASSET_STATUSES = frozenset({"referenced", "unlinked_candidate", "invalid"})
VISUAL_STATUSES = frozenset(
    {"mineru_candidate", "referenced", "caption_only", "pdf_crop_available", "visual_verified", "unavailable"}
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ASSET_SUFFIX_RE = re.compile(r"^[0-9a-f]{12}$")


class ImageAssetValidationError(ValueError):
    """An image asset or manifest violates the portable JSON contract."""


def make_asset_id(zotero_key: str, sha256: str) -> str:
    """Return a stable content-derived asset identity."""

    key = validate_zotero_key(zotero_key)
    digest = _validate_sha256(sha256)
    return f"IMG-{key}-{digest[:12]}"


@dataclass(frozen=True)
class ImageReference:
    syntax: str
    alt: str | None
    source_offset: int
    source_relative_path: str

    def __post_init__(self) -> None:
        if self.syntax not in {"markdown", "markdown-reference", "wiki"}:
            raise ImageAssetValidationError(f"unsupported image reference syntax: {self.syntax}")
        if not isinstance(self.source_offset, int) or isinstance(self.source_offset, bool) or self.source_offset < 0:
            raise ImageAssetValidationError("image reference sourceOffset must be a non-negative integer")
        object.__setattr__(self, "source_relative_path", _normalize_source_relative(self.source_relative_path))

    def as_dict(self) -> dict[str, Any]:
        return {
            "syntax": self.syntax,
            "alt": self.alt,
            "sourceOffset": self.source_offset,
            "sourceRelativePath": self.source_relative_path,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ImageReference":
        if not isinstance(value, Mapping):
            raise ImageAssetValidationError("image reference must be an object")
        alt = value.get("alt")
        if alt is not None and not isinstance(alt, str):
            raise ImageAssetValidationError("image reference alt must be text or null")
        return cls(
            syntax=str(value.get("syntax") or ""),
            alt=alt,
            source_offset=value.get("sourceOffset"),
            source_relative_path=str(value.get("sourceRelativePath") or ""),
        )


@dataclass(frozen=True)
class ImageAsset:
    asset_id: str
    zotero_key: str
    source_relative_path: str
    source_relative_paths: tuple[str, ...]
    status: str
    extension: str
    size_bytes: int
    sha256: str | None
    normalized_path: str | None
    cache_path: str | None
    references: tuple[ImageReference, ...] = ()
    caption_evidence_id: str | None = None
    context_evidence_ids: tuple[str, ...] = ()
    figure_label: str | None = None
    page: int | None = None
    visual_status: str = "unavailable"
    pdf_crop_path: str | None = None

    def __post_init__(self) -> None:
        key = validate_zotero_key(self.zotero_key)
        object.__setattr__(self, "zotero_key", key)
        asset_prefix = f"IMG-{key}-"
        if not self.asset_id.startswith(asset_prefix) or not _ASSET_SUFFIX_RE.fullmatch(self.asset_id[len(asset_prefix) :]):
            raise ImageAssetValidationError(f"invalid image assetId for {key}: {self.asset_id}")
        if self.status not in ASSET_STATUSES:
            raise ImageAssetValidationError(f"invalid image asset status: {self.status}")
        extension = self.extension.lower().lstrip(".")
        if extension not in SUPPORTED_IMAGE_EXTENSIONS:
            raise ImageAssetValidationError(f"unsupported image asset extension: {self.extension}")
        object.__setattr__(self, "extension", extension)
        if not isinstance(self.size_bytes, int) or isinstance(self.size_bytes, bool) or self.size_bytes < 0:
            raise ImageAssetValidationError("image asset sizeBytes must be a non-negative integer")
        digest = _validate_sha256(self.sha256) if self.sha256 is not None else None
        object.__setattr__(self, "sha256", digest)
        if digest is not None and self.asset_id != make_asset_id(key, digest):
            raise ImageAssetValidationError(f"image assetId does not match sha256: {self.asset_id}")

        primary = _normalize_source_relative(self.source_relative_path)
        sources = tuple(dict.fromkeys(_normalize_source_relative(path) for path in self.source_relative_paths or (primary,)))
        if primary not in sources:
            sources = (primary, *sources)
        object.__setattr__(self, "source_relative_path", primary)
        object.__setattr__(self, "source_relative_paths", sources)
        object.__setattr__(self, "references", tuple(self.references))
        object.__setattr__(self, "context_evidence_ids", tuple(str(value) for value in self.context_evidence_ids))

        normalized = normalize_vault_relative(self.normalized_path) if self.normalized_path else None
        cache = normalize_vault_relative(self.cache_path) if self.cache_path else None
        crop = normalize_vault_relative(self.pdf_crop_path) if self.pdf_crop_path else None
        object.__setattr__(self, "normalized_path", normalized)
        object.__setattr__(self, "cache_path", cache)
        object.__setattr__(self, "pdf_crop_path", crop)
        if self.status == "referenced" and (not normalized or cache):
            raise ImageAssetValidationError("referenced image assets require normalizedPath and no cachePath")
        if self.status == "unlinked_candidate" and (normalized or not cache):
            raise ImageAssetValidationError("unlinked candidates require cachePath and no normalizedPath")
        if self.status == "invalid" and (normalized or cache):
            raise ImageAssetValidationError("invalid image assets cannot name normalized or cache files")
        if self.status != "invalid" and digest is None:
            raise ImageAssetValidationError(f"{self.status} image asset requires sha256")
        if self.visual_status not in VISUAL_STATUSES:
            raise ImageAssetValidationError(f"invalid visualStatus: {self.visual_status}")
        if self.page is not None and (
            not isinstance(self.page, int) or isinstance(self.page, bool) or self.page < 1
        ):
            raise ImageAssetValidationError("image asset page must be a positive integer or null")

    def as_dict(self) -> dict[str, Any]:
        return {
            "assetId": self.asset_id,
            "zoteroKey": self.zotero_key,
            "sourceRelativePath": self.source_relative_path,
            "sourceRelativePaths": list(self.source_relative_paths),
            "status": self.status,
            "extension": self.extension,
            "sizeBytes": self.size_bytes,
            "sha256": self.sha256,
            "normalizedPath": self.normalized_path,
            "cachePath": self.cache_path,
            "references": [reference.as_dict() for reference in self.references],
            "captionEvidenceId": self.caption_evidence_id,
            "contextEvidenceIds": list(self.context_evidence_ids),
            "figureLabel": self.figure_label,
            "page": self.page,
            "visualStatus": self.visual_status,
            "pdfCropPath": self.pdf_crop_path,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any], *, zotero_key: str = "") -> "ImageAsset":
        if not isinstance(value, Mapping):
            raise ImageAssetValidationError("image asset must be an object")
        references = value.get("references", [])
        source_paths = value.get("sourceRelativePaths")
        if source_paths is None:
            source_paths = [value.get("sourceRelativePath")]
        if not isinstance(references, Sequence) or isinstance(references, (str, bytes)):
            raise ImageAssetValidationError("image asset references must be an array")
        if not isinstance(source_paths, Sequence) or isinstance(source_paths, (str, bytes)):
            raise ImageAssetValidationError("image asset sourceRelativePaths must be an array")
        context_ids = value.get("contextEvidenceIds", [])
        if not isinstance(context_ids, Sequence) or isinstance(context_ids, (str, bytes)):
            raise ImageAssetValidationError("image asset contextEvidenceIds must be an array")
        return cls(
            asset_id=str(value.get("assetId") or ""),
            zotero_key=str(value.get("zoteroKey") or zotero_key),
            source_relative_path=str(value.get("sourceRelativePath") or ""),
            source_relative_paths=tuple(str(path) for path in source_paths),
            status=str(value.get("status") or ""),
            extension=str(value.get("extension") or ""),
            size_bytes=value.get("sizeBytes"),
            sha256=value.get("sha256"),
            normalized_path=value.get("normalizedPath"),
            cache_path=value.get("cachePath"),
            references=tuple(ImageReference.from_dict(reference) for reference in references),
            caption_evidence_id=value.get("captionEvidenceId"),
            context_evidence_ids=tuple(str(item) for item in context_ids),
            figure_label=value.get("figureLabel"),
            page=value.get("page"),
            visual_status=str(value.get("visualStatus") or _default_visual_status(str(value.get("status") or ""))),
            pdf_crop_path=value.get("pdfCropPath"),
        )


@dataclass(frozen=True)
class ImageAssetManifest:
    zotero_key: str
    source_markdown: str
    source_markdown_sha256: str
    generated_at: str
    assets: tuple[ImageAsset, ...]
    warnings: tuple[dict[str, Any], ...] = ()
    schema_version: int = IMAGE_MANIFEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        key = validate_zotero_key(self.zotero_key)
        object.__setattr__(self, "zotero_key", key)
        if (
            not isinstance(self.schema_version, int)
            or isinstance(self.schema_version, bool)
            or self.schema_version != IMAGE_MANIFEST_SCHEMA_VERSION
        ):
            raise ImageAssetValidationError(f"unsupported image manifest schemaVersion: {self.schema_version}")
        object.__setattr__(self, "source_markdown", normalize_vault_relative(self.source_markdown))
        object.__setattr__(self, "source_markdown_sha256", _validate_sha256(self.source_markdown_sha256))
        if not isinstance(self.generated_at, str):
            raise ImageAssetValidationError("image manifest generatedAt must be text")
        assets = tuple(self.assets)
        if any(asset.zotero_key != key for asset in assets):
            raise ImageAssetValidationError("image manifest contains an asset for another zoteroKey")
        identities = [asset.asset_id for asset in assets]
        if len(identities) != len(set(identities)):
            raise ImageAssetValidationError("image manifest contains duplicate assetId values")
        destinations = [
            path.casefold()
            for asset in assets
            for path in (asset.normalized_path, asset.cache_path)
            if path is not None
        ]
        if len(destinations) != len(set(destinations)):
            raise ImageAssetValidationError("image manifest contains duplicate asset file paths")
        object.__setattr__(self, "assets", assets)
        object.__setattr__(self, "warnings", tuple(dict(warning) for warning in self.warnings))

    @property
    def counts(self) -> dict[str, int]:
        return {
            "total": len(self.assets),
            "referenced": sum(asset.status == "referenced" for asset in self.assets),
            "unlinkedCandidates": sum(asset.status == "unlinked_candidate" for asset in self.assets),
            "invalid": sum(asset.status == "invalid" for asset in self.assets),
        }

    def with_generated_at(self, value: str) -> "ImageAssetManifest":
        return replace(self, generated_at=value)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "zoteroKey": self.zotero_key,
            "sourceMarkdown": self.source_markdown,
            "sourceMarkdownSha256": self.source_markdown_sha256,
            "generatedAt": self.generated_at,
            "assets": [asset.as_dict() for asset in self.assets],
            "counts": self.counts,
            "warnings": [dict(warning) for warning in self.warnings],
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ImageAssetManifest":
        if not isinstance(value, Mapping):
            raise ImageAssetValidationError("image manifest must be an object")
        assets = value.get("assets")
        warnings = value.get("warnings", [])
        if not isinstance(assets, Sequence) or isinstance(assets, (str, bytes)):
            raise ImageAssetValidationError("image manifest assets must be an array")
        if not isinstance(warnings, Sequence) or isinstance(warnings, (str, bytes)):
            raise ImageAssetValidationError("image manifest warnings must be an array")
        if any(not isinstance(warning, Mapping) for warning in warnings):
            raise ImageAssetValidationError("every image manifest warning must be an object")
        generated_at = value.get("generatedAt")
        if not isinstance(generated_at, str) or not generated_at.strip():
            raise ImageAssetValidationError("image manifest generatedAt must be non-empty text")
        key = str(value.get("zoteroKey") or "")
        manifest = cls(
            zotero_key=key,
            source_markdown=str(value.get("sourceMarkdown") or ""),
            source_markdown_sha256=str(value.get("sourceMarkdownSha256") or ""),
            generated_at=generated_at,
            assets=tuple(ImageAsset.from_dict(asset, zotero_key=key) for asset in assets),
            warnings=tuple(dict(warning) for warning in warnings),
            schema_version=value.get("schemaVersion"),
        )
        counts = value.get("counts")
        if (
            not isinstance(counts, Mapping)
            or any(not isinstance(count, int) or isinstance(count, bool) for count in counts.values())
            or dict(counts) != manifest.counts
        ):
            raise ImageAssetValidationError("image manifest counts do not match assets")
        return manifest


def render_image_manifest(manifest: ImageAssetManifest) -> str:
    """Serialize a manifest with deterministic field order and UTF-8 content."""

    return json.dumps(manifest.as_dict(), ensure_ascii=False, indent=2) + "\n"


def parse_image_manifest(text: str) -> ImageAssetManifest:
    try:
        value = json.loads(text)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ImageAssetValidationError(f"invalid image manifest JSON: {exc}") from exc
    return ImageAssetManifest.from_dict(value)


def _validate_sha256(value: Any) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value.lower()):
        raise ImageAssetValidationError("sha256 must contain 64 hexadecimal characters")
    return value.lower()


def _normalize_source_relative(value: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ImageAssetValidationError("sourceRelativePath must be non-empty text")
    portable = value.replace("\\", "/")
    path = PurePosixPath(portable)
    if path.is_absolute() or ".." in path.parts:
        raise ImageAssetValidationError(f"sourceRelativePath must remain inside staging: {value}")
    parts = tuple(part for part in path.parts if part not in {"", "."})
    if not parts:
        raise ImageAssetValidationError("sourceRelativePath cannot be empty")
    return PurePosixPath(*parts).as_posix()


def _default_visual_status(status: str) -> str:
    if status == "referenced":
        return "referenced"
    if status == "unlinked_candidate":
        return "mineru_candidate"
    return "unavailable"
