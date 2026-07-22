from __future__ import annotations

import os
import posixpath
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import yaml

from ...domain.identity import validate_zotero_key

_MARKDOWN_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_WIKI_IMAGE_RE = re.compile(r"!\[\[([^\]]+)\]\]")
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"}
_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")


class MinerUNormalizationError(ValueError):
    """Staged MinerU output is incomplete or contains an unsafe path."""


@dataclass(frozen=True)
class NormalizedImage:
    source: Path
    filename: str
    content: bytes


@dataclass(frozen=True)
class NormalizedMineru:
    source_markdown: Path
    markdown: str
    images: tuple[NormalizedImage, ...]


def _split_destination(destination: str) -> tuple[str, str]:
    normalized = destination.replace("\\", "/")
    match = re.match(r"^(.*?)(?:\s+(['\"]).*\2)?$", normalized)
    path = (match.group(1) if match else normalized).strip().strip("<>")
    suffix = normalized[len(match.group(1)) :] if match else ""
    return path, suffix


def _safe_image_path(staging_root: Path, markdown_parent: Path, raw_path: str) -> Path:
    value = raw_path.strip()
    if not value or value.startswith(("/", "\\", "file://", "http://", "https://")) or _DRIVE_RE.match(value):
        raise MinerUNormalizationError(f"unsafe MinerU image path: {raw_path}")
    portable = value.replace("\\", "/")
    if ".." in PurePosixPath(portable).parts:
        raise MinerUNormalizationError(f"MinerU image path traverses staging: {raw_path}")
    resolved = markdown_parent.joinpath(*PurePosixPath(portable).parts).resolve()
    try:
        resolved.relative_to(staging_root)
    except ValueError as exc:
        raise MinerUNormalizationError(f"MinerU image is outside staging: {raw_path}") from exc
    if not resolved.is_file():
        raise MinerUNormalizationError(f"referenced MinerU image does not exist: {raw_path}")
    if resolved.suffix.lower() not in _IMAGE_EXTENSIONS:
        raise MinerUNormalizationError(f"unsupported MinerU image type: {resolved.suffix}")
    return resolved


def _strip_frontmatter(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if not normalized.startswith("---\n"):
        return normalized
    end = normalized.find("\n---\n", 4)
    return normalized[end + 5 :] if end >= 0 else normalized


def normalize_mineru_output(
    staging_dir: str | os.PathLike[str],
    *,
    zotero_key: str,
    title: str,
    source_pdf_path: str,
    markdown_path: str | os.PathLike[str] | None = None,
    image_namer: Callable[[int, str], str] | None = None,
    image_link_prefix: str = "image",
) -> NormalizedMineru:
    """Validate and normalize a complete staged MinerU result in memory."""
    key = validate_zotero_key(zotero_key)
    root = Path(staging_dir).expanduser().resolve()
    if not root.is_dir():
        raise MinerUNormalizationError(f"MinerU staging directory does not exist: {root}")
    if markdown_path is None:
        candidates = sorted(
            (path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in {".md", ".markdown"}),
            key=lambda path: (len(path.relative_to(root).parts), path.relative_to(root).as_posix()),
        )
        if not candidates:
            raise MinerUNormalizationError("MinerU produced no Markdown file")
        source_markdown = candidates[0]
    else:
        candidate = Path(markdown_path)
        source_markdown = (candidate if candidate.is_absolute() else root / candidate).resolve()
        try:
            source_markdown.relative_to(root)
        except ValueError as exc:
            raise MinerUNormalizationError("MinerU Markdown is outside staging") from exc
        if not source_markdown.is_file():
            raise MinerUNormalizationError("MinerU Markdown does not exist")

    raw_body = _strip_frontmatter(source_markdown.read_text(encoding="utf-8-sig"))
    portable_image_prefix = str(image_link_prefix).replace("\\", "/").rstrip("/")
    if (
        not portable_image_prefix
        or portable_image_prefix.startswith("/")
        or portable_image_prefix.startswith(("file:", "http:", "https:"))
        or _DRIVE_RE.match(portable_image_prefix)
    ):
        raise MinerUNormalizationError(f"unsafe normalized image link prefix: {image_link_prefix}")
    image_names: dict[Path, str] = {}
    normalized_images: list[NormalizedImage] = []

    def image_name(raw_path: str) -> tuple[str, str]:
        path_part, suffix = _split_destination(raw_path)
        source = _safe_image_path(root, source_markdown.parent, path_part)
        if source not in image_names:
            index = len(image_names) + 1
            extension = source.suffix.lower().lstrip(".")
            filename = image_namer(index, extension) if image_namer else f"{key}-fig{index:02d}.{extension}"
            if "/" in filename or "\\" in filename or not Path(filename).suffix:
                raise MinerUNormalizationError(f"invalid normalized image filename: {filename}")
            image_names[source] = filename
            normalized_images.append(NormalizedImage(source=source, filename=filename, content=source.read_bytes()))
        return image_names[source], suffix

    def replace_markdown(match: re.Match[str]) -> str:
        filename, _suffix = image_name(match.group(2))
        return f"![{match.group(1)}]({_image_link(portable_image_prefix, filename)})"

    def replace_wiki(match: re.Match[str]) -> str:
        filename, _suffix = image_name(match.group(1))
        return f"![]({_image_link(portable_image_prefix, filename)})"

    body = _MARKDOWN_IMAGE_RE.sub(replace_markdown, raw_body)
    body = _WIKI_IMAGE_RE.sub(replace_wiki, body)
    clean_title = " ".join(str(title).split()) or key
    if re.search(r"(?m)^# [^#].*$", body):
        body = re.sub(r"(?m)^# [^#].*$", f"# {clean_title}", body, count=1)
    else:
        body = f"# {clean_title}\n\n{body.lstrip()}"

    frontmatter = {
        "title": clean_title,
        "zoteroKey": key,
        "sourcePdf": source_pdf_path.replace("\\", "/"),
    }
    header = yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False, width=1000).rstrip()
    markdown = f"---\n{header}\n---\n\n{body.strip()}\n"

    forbidden = (str(root).replace("\\", "/"), "file:///")
    if any(value and value in markdown.replace("\\", "/") for value in forbidden):
        raise MinerUNormalizationError("normalized MinerU Markdown exposes a staging or file URL path")
    return NormalizedMineru(source_markdown, markdown, tuple(normalized_images))


def _image_link(prefix: str, filename: str) -> str:
    return filename if prefix == "." else posixpath.join(prefix, filename)


def relative_source_pdf(mineru_markdown_path: str, pdf_path: str) -> str:
    """Return the portable PDF path relative to the MinerU Markdown folder."""
    start = PurePosixPath(mineru_markdown_path.replace("\\", "/")).parent.as_posix()
    return posixpath.relpath(pdf_path.replace("\\", "/"), start=start)
