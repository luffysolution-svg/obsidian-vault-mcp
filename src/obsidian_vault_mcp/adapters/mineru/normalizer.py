from __future__ import annotations

import os
import posixpath
import re
import stat
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import yaml

from ...domain.identity import validate_zotero_key

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")
_URI_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
_REFERENCE_DEFINITION_RE = re.compile(
    r"(?m)^[ \t]{0,3}\[([^\]\n]+)\]:[ \t]*(<[^>\n]+>|\S+)(?:[ \t]+.*)?$"
)
_DESTINATION_TITLE_RE = re.compile(
    r"^(.*?)(\s+(?:\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'|\([^)]*\)))\s*$"
)
_HTML_IMAGE_RE = re.compile(r"<img\b", re.IGNORECASE)


class MinerUNormalizationError(ValueError):
    """Staged MinerU output is incomplete or contains an unsafe path."""


@dataclass(frozen=True)
class MinerUImageReference:
    """One Markdown or Wiki image reference in source order."""

    start: int
    end: int
    alt: str
    destination: str
    syntax: str
    destination_start: int | None = None
    destination_end: int | None = None


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


def parse_image_references(text: str) -> tuple[MinerUImageReference, ...]:
    """Parse inline, reference-style, and Wiki image links without resolving them."""

    definitions: dict[str, tuple[str, int | None, int | None]] = {}
    for match in _REFERENCE_DEFINITION_RE.finditer(text):
        destination, _suffix, local_start, local_end = _split_destination_with_span(
            match.group(2)
        )
        definitions[_normalize_reference_label(match.group(1))] = (
            destination,
            match.start(2) + local_start if local_start is not None else None,
            match.start(2) + local_end if local_end is not None else None,
        )
    references: list[MinerUImageReference] = []
    index = 0
    while index < len(text):
        if text.startswith("![[", index):
            end = text.find("]]", index + 3)
            if end >= 0:
                raw = text[index + 3 : end]
                target_with_fragment, _, alias = raw.partition("|")
                target_segment = target_with_fragment.split("#", 1)[0]
                leading = len(target_segment) - len(target_segment.lstrip())
                target = target_segment.strip()
                destination_start = index + 3 + leading
                references.append(
                    MinerUImageReference(
                        index,
                        end + 2,
                        alias.strip(),
                        target,
                        "wiki",
                        destination_start,
                        destination_start + len(target),
                    )
                )
                index = end + 2
                continue
        if not text.startswith("![", index):
            index += 1
            continue
        alt_end = _matching_square_bracket(text, index + 1)
        if alt_end < 0:
            index += 2
            continue
        alt = text[index + 2 : alt_end]
        marker = alt_end + 1
        while marker < len(text) and text[marker] in " \t":
            marker += 1
        if marker < len(text) and text[marker] == "(":
            destination_end = _matching_parenthesis(text, marker)
            if destination_end >= 0:
                raw_destination = text[marker + 1 : destination_end]
                _path, _suffix, local_start, local_end = _split_destination_with_span(
                    raw_destination
                )
                references.append(
                    MinerUImageReference(
                        index,
                        destination_end + 1,
                        alt,
                        raw_destination,
                        "markdown",
                        marker + 1 + local_start if local_start is not None else None,
                        marker + 1 + local_end if local_end is not None else None,
                    )
                )
                index = destination_end + 1
                continue
        if marker < len(text) and text[marker] == "[":
            label_end = _matching_square_bracket(text, marker)
            if label_end >= 0:
                label = text[marker + 1 : label_end] or alt
                destination, destination_start, destination_end = definitions.get(
                    _normalize_reference_label(label),
                    ("", None, None),
                )
                references.append(
                    MinerUImageReference(
                        index,
                        label_end + 1,
                        alt,
                        destination,
                        "markdown-reference",
                        destination_start,
                        destination_end,
                    )
                )
                index = label_end + 1
                continue
        destination = definitions.get(_normalize_reference_label(alt))
        if destination is not None:
            value, destination_start, destination_end = destination
            references.append(
                MinerUImageReference(
                    index,
                    alt_end + 1,
                    alt,
                    value,
                    "markdown-shortcut",
                    destination_start,
                    destination_end,
                )
            )
        index = alt_end + 1
    return tuple(references)


def resolve_image_reference(source_markdown: str, destination: str) -> str:
    """Resolve one safe image destination to a vault-relative Markdown path."""

    path, _suffix = _split_destination(destination)
    portable = path.strip().replace("\\", "/")
    if (
        not portable
        or portable.startswith(("/", "\\"))
        or _DRIVE_RE.match(portable)
        or _URI_SCHEME_RE.match(portable)
    ):
        raise MinerUNormalizationError(f"unsafe MinerU image path: {destination}")
    parent = PurePosixPath(source_markdown.replace("\\", "/")).parent
    combined = posixpath.normpath(posixpath.join(parent.as_posix(), portable))
    if combined == ".." or combined.startswith("../"):
        raise MinerUNormalizationError(f"image path escapes the Vault: {destination}")
    if PurePosixPath(combined).suffix.lower() not in _IMAGE_EXTENSIONS:
        raise MinerUNormalizationError(
            f"unsupported MinerU image type: {PurePosixPath(combined).suffix}"
        )
    return combined


def _split_destination(destination: str) -> tuple[str, str]:
    path, suffix, _start, _end = _split_destination_with_span(destination)
    return path, suffix


def _split_destination_with_span(
    destination: str,
) -> tuple[str, str, int | None, int | None]:
    leading = len(destination) - len(destination.lstrip())
    stripped = destination.strip()
    if not stripped:
        return "", "", None, None
    if stripped.startswith("<"):
        closing = stripped.find(">", 1)
        if closing >= 0:
            return (
                stripped[1:closing].replace("\\", "/"),
                stripped[closing + 1 :].replace("\\", "/"),
                leading + 1,
                leading + closing,
            )
    match = _DESTINATION_TITLE_RE.match(stripped)
    if match:
        raw_path = match.group(1)
        path_leading = len(raw_path) - len(raw_path.lstrip())
        path = raw_path.strip()
        start = leading + match.start(1) + path_leading
        return path.replace("\\", "/"), match.group(2), start, start + len(path)

    start = leading
    end = leading + len(stripped)
    while start < end and destination[start] == "<":
        start += 1
    while end > start and destination[end - 1] == ">":
        end -= 1
    return destination[start:end].replace("\\", "/"), "", start, end


def _validate_relative_image_destination(raw_path: str) -> str:
    value = raw_path.strip().replace("\\", "/")
    if (
        not value
        or value.startswith(("/", "\\"))
        or _DRIVE_RE.match(value)
        or _URI_SCHEME_RE.match(value)
    ):
        raise MinerUNormalizationError(f"unsafe MinerU image path: {raw_path}")
    parts = PurePosixPath(value).parts
    if ".." in parts:
        raise MinerUNormalizationError(f"MinerU image path traverses staging: {raw_path}")
    return PurePosixPath(*parts).as_posix()


def _safe_image_path(staging_root: Path, markdown_parent: Path, raw_path: str) -> Path:
    portable = _validate_relative_image_destination(raw_path)
    lexical = markdown_parent.joinpath(*PurePosixPath(portable).parts)
    if _path_uses_link_or_reparse_point(lexical, stop=staging_root):
        raise MinerUNormalizationError(
            f"MinerU image path uses a symbolic link or reparse point: {raw_path}"
        )
    resolved = lexical.resolve()
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
    image_link_prefix: str | None = None,
) -> NormalizedMineru:
    """Validate and normalize a complete staged MinerU result in memory."""

    key = validate_zotero_key(zotero_key)
    requested_root = Path(os.path.abspath(Path(staging_dir).expanduser()))
    if _is_link_or_reparse_point(requested_root):
        raise MinerUNormalizationError(
            "MinerU staging directory cannot be a symbolic link or reparse point"
        )
    try:
        root = requested_root.resolve(strict=True)
        parent = requested_root.parent.resolve(strict=True)
    except OSError as exc:
        raise MinerUNormalizationError(
            f"MinerU staging directory does not exist: {requested_root}"
        ) from exc
    if root != parent / requested_root.name or not root.is_dir():
        raise MinerUNormalizationError(
            "MinerU staging directory cannot resolve through a symbolic link or reparse point"
        )

    source_markdown = _select_markdown(root, markdown_path)
    try:
        raw_body = _strip_frontmatter(source_markdown.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError) as exc:
        raise MinerUNormalizationError(f"cannot read MinerU Markdown: {exc}") from exc
    if _HTML_IMAGE_RE.search(raw_body):
        raise MinerUNormalizationError("HTML image syntax is unsupported")

    portable_image_prefix = (
        f"image/{key}" if image_link_prefix is None else str(image_link_prefix)
    ).replace("\\", "/").rstrip("/")
    if (
        not portable_image_prefix
        or portable_image_prefix.startswith(("/", "\\"))
        or _DRIVE_RE.match(portable_image_prefix)
        or _URI_SCHEME_RE.match(portable_image_prefix)
    ):
        raise MinerUNormalizationError(
            f"unsafe normalized image link prefix: {image_link_prefix}"
        )

    image_names: dict[Path, str] = {}
    normalized_images: list[NormalizedImage] = []
    replacements: dict[tuple[int, int], str] = {}
    for reference in parse_image_references(raw_body):
        if not reference.destination:
            raise MinerUNormalizationError("unresolved MinerU image reference")
        path_part, _suffix = _split_destination(reference.destination)
        source = _safe_image_path(root, source_markdown.parent, path_part)
        if source not in image_names:
            index = len(image_names) + 1
            extension = source.suffix.lower().lstrip(".")
            filename = (
                image_namer(index, extension)
                if image_namer
                else f"{key}-fig{index:02d}.{extension}"
            )
            if (
                "/" in filename
                or "\\" in filename
                or PurePosixPath(filename).name != filename
                or Path(filename).suffix.lower() not in _IMAGE_EXTENSIONS
            ):
                raise MinerUNormalizationError(
                    f"invalid normalized image filename: {filename}"
                )
            image_names[source] = filename
            normalized_images.append(
                NormalizedImage(source=source, filename=filename, content=source.read_bytes())
            )
        filename = image_names[source]
        if reference.destination_start is None or reference.destination_end is None:
            raise MinerUNormalizationError("MinerU image reference cannot be rewritten safely")
        marker = (reference.destination_start, reference.destination_end)
        replacement = _image_link(portable_image_prefix, filename)
        existing = replacements.get(marker)
        if existing is not None and existing != replacement:
            raise MinerUNormalizationError(
                "shared MinerU image reference resolves to conflicting images"
            )
        replacements[marker] = replacement

    body = raw_body
    for (start, end), replacement in sorted(
        replacements.items(),
        key=lambda item: item[0][0],
        reverse=True,
    ):
        body = f"{body[:start]}{replacement}{body[end:]}"

    clean_title = " ".join(str(title).split()) or key
    if re.search(r"(?m)^# [^#].*$", body):
        body = re.sub(r"(?m)^# [^#].*$", f"# {clean_title}", body, count=1)
    else:
        body = f"# {clean_title}\n\n{body.lstrip()}"

    frontmatter = {
        "title": clean_title,
        "zoteroKey": key,
        "sourcePdf": _safe_output_reference(source_pdf_path, "source PDF"),
    }
    header = yaml.safe_dump(
        frontmatter,
        allow_unicode=True,
        sort_keys=False,
        width=1000,
    ).rstrip()
    markdown = f"---\n{header}\n---\n\n{body.strip()}\n"

    forbidden = (str(root).replace("\\", "/"), "file:///")
    if any(value and value in markdown.replace("\\", "/") for value in forbidden):
        raise MinerUNormalizationError(
            "normalized MinerU Markdown exposes a staging or file URL path"
        )
    return NormalizedMineru(source_markdown, markdown, tuple(normalized_images))


def _select_markdown(root: Path, markdown_path: str | os.PathLike[str] | None) -> Path:
    if markdown_path is None:
        candidates = sorted(
            (
                path
                for path in root.rglob("*")
                if path.is_file()
                and path.suffix.lower() in {".md", ".markdown"}
                and not _path_uses_link_or_reparse_point(path, stop=root)
            ),
            key=lambda path: (
                len(path.relative_to(root).parts),
                path.relative_to(root).as_posix(),
            ),
        )
        if not candidates:
            raise MinerUNormalizationError("MinerU produced no Markdown file")
        return candidates[0]
    candidate = Path(markdown_path)
    lexical = candidate if candidate.is_absolute() else root / candidate
    if _path_uses_link_or_reparse_point(lexical, stop=root):
        raise MinerUNormalizationError(
            "MinerU Markdown cannot be a symbolic link or reparse point"
        )
    source_markdown = lexical.resolve()
    try:
        source_markdown.relative_to(root)
    except ValueError as exc:
        raise MinerUNormalizationError("MinerU Markdown is outside staging") from exc
    if not source_markdown.is_file():
        raise MinerUNormalizationError("MinerU Markdown does not exist")
    return source_markdown


def _image_link(prefix: str, filename: str) -> str:
    return filename if prefix == "." else posixpath.join(prefix, filename)


def relative_source_pdf(mineru_markdown_path: str, pdf_path: str) -> str:
    """Return the portable PDF path relative to the MinerU Markdown folder."""

    start = PurePosixPath(mineru_markdown_path.replace("\\", "/")).parent.as_posix()
    return posixpath.relpath(pdf_path.replace("\\", "/"), start=start)


def _matching_square_bracket(text: str, opening: int) -> int:
    depth = 0
    escaped = False
    for index in range(opening, len(text)):
        if escaped:
            escaped = False
            continue
        if text[index] == "\\":
            escaped = True
        elif text[index] == "[":
            depth += 1
        elif text[index] == "]":
            depth -= 1
            if depth == 0:
                return index
    return -1


def _matching_parenthesis(text: str, opening: int) -> int:
    depth = 0
    escaped = False
    angle = False
    quote = ""
    for index in range(opening, len(text)):
        character = text[index]
        if escaped:
            escaped = False
            continue
        if character == "\\":
            escaped = True
            continue
        if quote:
            if character == quote:
                quote = ""
            continue
        if character in "\"'" and depth == 1:
            quote = character
            continue
        if character == "<" and depth == 1:
            angle = True
            continue
        if character == ">" and angle:
            angle = False
            continue
        if angle:
            continue
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth == 0:
                return index
    return -1


def _normalize_reference_label(value: str) -> str:
    return " ".join(value.split()).casefold()


def _is_link_or_reparse_point(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except OSError:
        return False
    return stat.S_ISLNK(metadata.st_mode) or bool(
        getattr(metadata, "st_file_attributes", 0) & 0x400
    )


def _path_uses_link_or_reparse_point(path: Path, *, stop: Path | None = None) -> bool:
    current = path
    while True:
        if _is_link_or_reparse_point(current):
            return True
        if current == stop or current == current.parent:
            return False
        if stop is not None and current != stop and stop not in current.parents:
            return False
        current = current.parent


def _safe_output_reference(value: str, description: str) -> str:
    portable = str(value).strip().replace("\\", "/")
    if (
        not portable
        or portable.startswith(("/", "\\"))
        or _DRIVE_RE.match(portable)
        or _URI_SCHEME_RE.match(portable)
    ):
        raise MinerUNormalizationError(f"unsafe {description} path: {value}")
    return portable
