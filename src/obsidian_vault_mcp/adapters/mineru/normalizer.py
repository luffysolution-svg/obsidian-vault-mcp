from __future__ import annotations

import hashlib
import os
import posixpath
import re
import stat
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import yaml

from ...domain.identity import validate_zotero_key
from ...domain.image_assets import (
    SUPPORTED_IMAGE_EXTENSIONS,
    ImageAsset,
    ImageAssetManifest,
    ImageReference,
    make_asset_id,
)
from ...domain.paths import normalize_vault_relative

_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")
_URI_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
_REFERENCE_DEFINITION_RE = re.compile(
    r"(?m)^[ \t]{0,3}\[([^\]\n]+)\]:[ \t]*(<[^>\n]+>|\S+)(?:[ \t]+.*)?$"
)
_HTML_IMAGE_RE = re.compile(r"<img\b", re.IGNORECASE)


class MinerUNormalizationError(ValueError):
    """Staged MinerU output is incomplete or contains an unsafe path."""


@dataclass(frozen=True)
class ParsedImageReference:
    start: int
    end: int
    syntax: str
    alt: str | None
    destination: str


@dataclass(frozen=True)
class NormalizedImage:
    source: Path
    filename: str
    content: bytes
    asset_id: str = ""
    sha256: str = ""


@dataclass(frozen=True)
class NormalizedCandidate:
    source: Path
    filename: str
    content: bytes
    asset_id: str
    sha256: str


@dataclass(frozen=True)
class NormalizedMineru:
    source_markdown: Path
    markdown: str
    images: tuple[NormalizedImage, ...]
    candidate_images: tuple[NormalizedCandidate, ...]
    manifest: ImageAssetManifest


@dataclass(frozen=True)
class _ScannedImage:
    source: Path
    relative_path: str
    extension: str
    content: bytes | None
    sha256: str | None
    size_bytes: int
    error: str | None = None


def parse_image_destination(destination: str) -> tuple[str, str]:
    """Split a Markdown destination from its optional title suffix."""

    normalized = destination.replace("\\", "/").strip()
    if normalized.startswith("<"):
        closing = _find_unescaped(normalized, ">", 1)
        if closing >= 0:
            return normalized[1:closing], normalized[closing + 1 :]
    match = re.match(
        r"^(.*?)(\s+(?:\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'|\([^)]*\)))\s*$",
        normalized,
    )
    if match:
        return match.group(1).strip(), match.group(2)
    return normalized.strip().strip("<>"), ""


def parse_image_references(text: str) -> tuple[ParsedImageReference, ...]:
    """Parse inline, reference-style, and Wiki image links without fragile parenthesis regexes."""

    definitions = _reference_definitions(text)
    references: list[ParsedImageReference] = []
    index = 0
    while index < len(text):
        if text.startswith("![[", index):
            end = text.find("]]", index + 3)
            if end >= 0:
                raw = text[index + 3 : end]
                target, _, alias = raw.partition("|")
                target = target.split("#", 1)[0].strip()
                if target:
                    references.append(
                        ParsedImageReference(index, end + 2, "wiki", alias.strip() or None, target)
                    )
                index = end + 2
                continue
        if text.startswith("![", index):
            alt_end = _matching_square_bracket(text, index + 1)
            if alt_end >= 0:
                alt = text[index + 2 : alt_end]
                marker = alt_end + 1
                while marker < len(text) and text[marker] in " \t":
                    marker += 1
                if marker < len(text) and text[marker] == "(":
                    destination_end = _matching_parenthesis(text, marker)
                    if destination_end >= 0:
                        references.append(
                            ParsedImageReference(
                                index,
                                destination_end + 1,
                                "markdown",
                                alt,
                                text[marker + 1 : destination_end],
                            )
                        )
                        index = destination_end + 1
                        continue
                if marker < len(text) and text[marker] == "[":
                    label_end = _matching_square_bracket(text, marker)
                    if label_end >= 0:
                        label = text[marker + 1 : label_end] or alt
                        destination = definitions.get(_normalize_reference_label(label))
                        if destination:
                            references.append(
                                ParsedImageReference(
                                    index,
                                    label_end + 1,
                                    "markdown-reference",
                                    alt,
                                    destination,
                                )
                            )
                            index = label_end + 1
                            continue
        index += 1
    return tuple(references)


def find_unsupported_image_syntax(text: str) -> tuple[dict[str, int | str], ...]:
    """Return stable warnings for image syntax intentionally left unsupported."""

    findings: list[dict[str, int | str]] = [
        {"syntax": "html", "sourceOffset": match.start()} for match in _HTML_IMAGE_RE.finditer(text)
    ]
    definitions = _reference_definitions(text)
    index = 0
    while index < len(text):
        if text.startswith("![", index) and not text.startswith("![[", index):
            alt_end = _matching_square_bracket(text, index + 1)
            if alt_end >= 0:
                marker = alt_end + 1
                while marker < len(text) and text[marker] in " \t":
                    marker += 1
                if marker < len(text) and text[marker] == "[":
                    label_end = _matching_square_bracket(text, marker)
                    if label_end >= 0:
                        label = text[marker + 1 : label_end] or text[index + 2 : alt_end]
                        if _normalize_reference_label(label) not in definitions:
                            findings.append({"syntax": "markdown-reference", "sourceOffset": index})
                        index = label_end + 1
                        continue
        index += 1
    return tuple(sorted(findings, key=lambda item: (int(item["sourceOffset"]), str(item["syntax"]))))


def normalize_mineru_output(
    staging_dir: str | os.PathLike[str],
    *,
    zotero_key: str,
    title: str,
    source_pdf_path: str,
    markdown_path: str | os.PathLike[str] | None = None,
    image_namer: Callable[[int, str], str] | None = None,
    image_link_prefix: str = "image",
    output_markdown_path: str | None = None,
    normalized_image_folder: str = "image",
    candidate_cache_folder: str | None = None,
    generated_at: str = "",
) -> NormalizedMineru:
    """Validate, classify, and normalize a complete staged MinerU result in memory."""

    key = validate_zotero_key(zotero_key)
    requested_root = Path(os.path.abspath(Path(staging_dir).expanduser()))
    if _is_link_or_reparse_point(requested_root) or _is_link_or_reparse_point(requested_root.parent):
        raise MinerUNormalizationError(
            "MinerU staging directory cannot be a symbolic link or reparse point"
        )
    try:
        root = requested_root.resolve(strict=True)
    except OSError as exc:
        raise MinerUNormalizationError(f"MinerU staging directory does not exist: {requested_root}") from exc
    if root != requested_root.parent.resolve(strict=True) / requested_root.name:
        raise MinerUNormalizationError(
            "MinerU staging directory cannot resolve through a symbolic link or reparse point"
        )
    if not root.is_dir():
        raise MinerUNormalizationError(f"MinerU staging directory does not exist: {root}")
    source_markdown = _select_markdown(root, markdown_path)
    raw_body = _strip_frontmatter(_read_markdown(source_markdown))
    portable_image_prefix = _validate_link_prefix(image_link_prefix)
    output_path = normalize_vault_relative(output_markdown_path or f"{key}.md")
    normalized_folder = normalize_vault_relative(normalized_image_folder)
    expected_prefix = posixpath.relpath(
        normalized_folder,
        start=PurePosixPath(output_path).parent.as_posix(),
    )
    if portable_image_prefix != expected_prefix:
        raise MinerUNormalizationError(
            "normalized image link prefix does not match the configured Markdown and image folders"
        )
    candidate_folder = normalize_vault_relative(
        candidate_cache_folder or f".obsidian-vault-mcp/cache/mineru-assets/{key}/assets"
    )

    scanned = _scan_supported_images(root)
    scanned_by_relative = {image.relative_path: image for image in scanned}
    scanned_by_folded: dict[str, list[_ScannedImage]] = defaultdict(list)
    for image in scanned:
        scanned_by_folded[image.relative_path.casefold()].append(image)
    parsed_references = parse_image_references(raw_body)
    resolved_references: list[tuple[ParsedImageReference, _ScannedImage, str]] = []
    for reference in parsed_references:
        raw_path, suffix = parse_image_destination(reference.destination)
        relative = _safe_referenced_path(root, source_markdown.parent, raw_path)
        image = scanned_by_relative.get(relative)
        if image is None:
            folded_matches = scanned_by_folded.get(relative.casefold(), [])
            if len(folded_matches) == 1:
                image = folded_matches[0]
            elif len(folded_matches) > 1:
                raise MinerUNormalizationError(f"ambiguous case-insensitive MinerU image path: {raw_path}")
        if image is None:
            raise MinerUNormalizationError(f"referenced MinerU image does not exist: {raw_path}")
        if image.error:
            raise MinerUNormalizationError(f"invalid referenced MinerU image ({image.error}): {raw_path}")
        resolved_references.append((reference, image, suffix))

    referenced_by_sha: dict[str, list[tuple[ParsedImageReference, _ScannedImage, str]]] = defaultdict(list)
    for reference, image, suffix in resolved_references:
        if image.sha256 is None:
            raise MinerUNormalizationError(f"referenced MinerU image cannot be hashed: {image.relative_path}")
        referenced_by_sha[image.sha256].append((reference, image, suffix))
    valid_by_sha: dict[str, list[_ScannedImage]] = defaultdict(list)
    invalid_images: list[_ScannedImage] = []
    for image in scanned:
        if image.error or image.sha256 is None or image.content is None:
            invalid_images.append(image)
        else:
            valid_by_sha[image.sha256].append(image)

    referenced_order = sorted(
        referenced_by_sha,
        key=lambda digest: min(item[0].start for item in referenced_by_sha[digest]),
    )
    unlinked_order = sorted(
        (digest for digest in valid_by_sha if digest not in referenced_by_sha),
        key=lambda digest: _path_sort_key(_sorted_sources(valid_by_sha[digest])[0].relative_path),
    )
    assets: list[ImageAsset] = []
    normalized_images: list[NormalizedImage] = []
    candidates: list[NormalizedCandidate] = []
    replacements: dict[int, tuple[int, str]] = {}
    normalized_paths: set[str] = set()

    for image_index, digest in enumerate(referenced_order, start=1):
        entries = valid_by_sha[digest]
        references = sorted(referenced_by_sha[digest], key=lambda item: item[0].start)
        primary = references[0][1]
        extension = primary.extension
        filename = image_namer(image_index, extension) if image_namer else f"{key}-fig{image_index:02d}.{extension}"
        _validate_normalized_filename(filename, extension)
        asset_id = make_asset_id(key, digest)
        normalized_path = normalize_vault_relative(f"{normalized_folder}/{filename}")
        if normalized_path.casefold() in normalized_paths:
            raise MinerUNormalizationError(f"duplicate normalized image destination: {normalized_path}")
        normalized_paths.add(normalized_path.casefold())
        source_paths = tuple(image.relative_path for image in _sorted_sources(entries))
        asset_references = tuple(
            ImageReference(
                syntax=reference.syntax,
                alt=reference.alt,
                source_offset=reference.start,
                source_relative_path=image.relative_path,
            )
            for reference, image, _suffix in references
        )
        assets.append(
            ImageAsset(
                asset_id=asset_id,
                zotero_key=key,
                source_relative_path=primary.relative_path,
                source_relative_paths=source_paths,
                status="referenced",
                extension=extension,
                size_bytes=len(primary.content or b""),
                sha256=digest,
                normalized_path=normalized_path,
                cache_path=None,
                references=asset_references,
                visual_status="referenced",
            )
        )
        normalized_images.append(
            NormalizedImage(primary.source, filename, primary.content or b"", asset_id=asset_id, sha256=digest)
        )
        link = _image_link(portable_image_prefix, filename)
        for reference, _image, suffix in references:
            replacements[reference.start] = (
                reference.end,
                f"![{reference.alt or ''}]({link}{suffix})",
            )

    for digest in unlinked_order:
        entries = valid_by_sha[digest]
        primary = _sorted_sources(entries)[0]
        asset_id = make_asset_id(key, digest)
        filename = f"{asset_id}.{primary.extension}"
        cache_path = normalize_vault_relative(f"{candidate_folder}/{filename}")
        assets.append(
            ImageAsset(
                asset_id=asset_id,
                zotero_key=key,
                source_relative_path=primary.relative_path,
                source_relative_paths=tuple(image.relative_path for image in _sorted_sources(entries)),
                status="unlinked_candidate",
                extension=primary.extension,
                size_bytes=len(primary.content or b""),
                sha256=digest,
                normalized_path=None,
                cache_path=cache_path,
                visual_status="mineru_candidate",
            )
        )
        candidates.append(
            NormalizedCandidate(primary.source, filename, primary.content or b"", asset_id=asset_id, sha256=digest)
        )

    warnings: list[dict[str, object]] = [
        {
            "code": "unsupported-image-syntax",
            "syntax": finding["syntax"],
            "sourceOffset": finding["sourceOffset"],
        }
        for finding in find_unsupported_image_syntax(raw_body)
    ]
    for image in sorted(invalid_images, key=lambda item: _path_sort_key(item.relative_path)):
        identity_digest = hashlib.sha256(f"{key}\0invalid\0{image.relative_path}".encode()).hexdigest()
        asset_id = f"IMG-{key}-{identity_digest[:12]}"
        assets.append(
            ImageAsset(
                asset_id=asset_id,
                zotero_key=key,
                source_relative_path=image.relative_path,
                source_relative_paths=(image.relative_path,),
                status="invalid",
                extension=image.extension,
                size_bytes=image.size_bytes,
                sha256=None,
                normalized_path=None,
                cache_path=None,
                visual_status="unavailable",
            )
        )
        warnings.append(
            {"code": "invalid-unlinked-image", "path": image.relative_path, "reason": image.error or "invalid"}
        )

    body = _apply_replacements(raw_body, replacements)
    clean_title = " ".join(str(title).split()) or key
    if re.search(r"(?m)^# [^#].*$", body):
        body = re.sub(r"(?m)^# [^#].*$", f"# {clean_title}", body, count=1)
    else:
        body = f"# {clean_title}\n\n{body.lstrip()}"
    frontmatter = {"title": clean_title, "zoteroKey": key, "sourcePdf": source_pdf_path.replace("\\", "/")}
    header = yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False, width=1000).rstrip()
    markdown = f"---\n{header}\n---\n\n{body.strip()}\n"
    forbidden = (str(root).replace("\\", "/"), "file:///")
    if any(value and value.casefold() in markdown.replace("\\", "/").casefold() for value in forbidden):
        raise MinerUNormalizationError("normalized MinerU Markdown exposes a staging or file URL path")
    manifest = ImageAssetManifest(
        zotero_key=key,
        source_markdown=output_path,
        source_markdown_sha256=hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
        generated_at=generated_at,
        assets=tuple(assets),
        warnings=tuple(warnings),
    )
    return NormalizedMineru(
        source_markdown,
        markdown,
        tuple(normalized_images),
        tuple(candidates),
        manifest,
    )


def _is_link_or_reparse_point(path: Path) -> bool:
    """Detect POSIX symlinks and Windows junction/reparse-point directories."""

    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISLNK(metadata.st_mode) or bool(
        getattr(metadata, "st_file_attributes", 0) & 0x400
    )


def _select_markdown(root: Path, markdown_path: str | os.PathLike[str] | None) -> Path:
    if markdown_path is None:
        candidates = sorted(
            (
                path
                for path in root.rglob("*")
                if (path.is_file() or path.is_symlink()) and path.suffix.lower() in {".md", ".markdown"}
            ),
            key=lambda path: (len(path.relative_to(root).parts), path.relative_to(root).as_posix()),
        )
        if not candidates:
            raise MinerUNormalizationError("MinerU produced no Markdown file")
        candidate = candidates[0]
    else:
        supplied = Path(markdown_path)
        candidate = supplied if supplied.is_absolute() else root / supplied
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise MinerUNormalizationError("MinerU Markdown is outside staging or does not exist") from exc
    if not resolved.is_file():
        raise MinerUNormalizationError("MinerU Markdown does not exist")
    return resolved


def _read_markdown(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise MinerUNormalizationError("MinerU Markdown cannot be read as UTF-8") from exc


def _scan_supported_images(root: Path) -> tuple[_ScannedImage, ...]:
    paths = sorted(
        (
            path
            for path in root.rglob("*")
            if path.suffix.lower().lstrip(".") in SUPPORTED_IMAGE_EXTENSIONS
            and (path.is_file() or path.is_symlink())
        ),
        key=lambda path: _path_sort_key(path.relative_to(root).as_posix()),
    )
    scanned: list[_ScannedImage] = []
    for path in paths:
        relative = path.relative_to(root).as_posix()
        extension = path.suffix.lower().lstrip(".")
        try:
            resolved = path.resolve(strict=True)
            resolved.relative_to(root)
        except (OSError, ValueError):
            scanned.append(_ScannedImage(path, relative, extension, None, None, 0, "outside-staging"))
            continue
        if not resolved.is_file():
            scanned.append(_ScannedImage(resolved, relative, extension, None, None, 0, "not-a-file"))
            continue
        try:
            content = resolved.read_bytes()
        except OSError:
            try:
                size = resolved.stat().st_size
            except OSError:
                size = 0
            scanned.append(_ScannedImage(resolved, relative, extension, None, None, size, "unreadable"))
            continue
        if not content:
            scanned.append(_ScannedImage(resolved, relative, extension, None, None, 0, "empty-file"))
            continue
        scanned.append(
            _ScannedImage(
                resolved,
                relative,
                extension,
                content,
                hashlib.sha256(content).hexdigest(),
                len(content),
            )
        )
    return tuple(scanned)


def _safe_referenced_path(root: Path, markdown_parent: Path, raw_path: str) -> str:
    value = raw_path.strip()
    casefolded = value.casefold()
    if (
        not value
        or value.startswith(("/", "\\"))
        or _DRIVE_RE.match(value)
        or _URI_SCHEME_RE.match(value)
        or casefolded.startswith(("file://", "http://", "https://"))
    ):
        raise MinerUNormalizationError(f"unsafe MinerU image path: {raw_path}")
    portable = value.replace("\\", "/")
    if ".." in PurePosixPath(portable).parts:
        raise MinerUNormalizationError(f"MinerU image path traverses staging: {raw_path}")
    if PurePosixPath(portable).suffix.lower().lstrip(".") not in SUPPORTED_IMAGE_EXTENSIONS:
        raise MinerUNormalizationError(f"unsupported MinerU image type: {PurePosixPath(portable).suffix}")
    lexical = markdown_parent.joinpath(*PurePosixPath(portable).parts)
    try:
        relative = lexical.relative_to(root).as_posix()
        resolved = lexical.resolve(strict=False)
        resolved.relative_to(root)
    except ValueError as exc:
        raise MinerUNormalizationError(f"MinerU image is outside staging: {raw_path}") from exc
    return relative


def _strip_frontmatter(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if not normalized.startswith("---\n"):
        return normalized
    end = normalized.find("\n---\n", 4)
    return normalized[end + 5 :] if end >= 0 else normalized


def _validate_link_prefix(value: str) -> str:
    portable = str(value).replace("\\", "/").rstrip("/")
    if not portable or portable.startswith("/") or _DRIVE_RE.match(portable) or _URI_SCHEME_RE.match(portable):
        raise MinerUNormalizationError(f"unsafe normalized image link prefix: {value}")
    normalized = posixpath.normpath(portable)
    if normalized == ".." or normalized.startswith("../"):
        # Relative links may legitimately walk from a custom Markdown folder to
        # another Vault folder. They remain safe because the service supplies a
        # separately validated Vault destination.
        return normalized
    return normalized


def _validate_normalized_filename(filename: str, extension: str) -> None:
    if (
        not filename
        or "/" in filename
        or "\\" in filename
        or PurePosixPath(filename).suffix.lower() != f".{extension}"
    ):
        raise MinerUNormalizationError(f"invalid normalized image filename: {filename}")


def _apply_replacements(text: str, replacements: dict[int, tuple[int, str]]) -> str:
    if not replacements:
        return text
    chunks: list[str] = []
    cursor = 0
    for start in sorted(replacements):
        end, replacement = replacements[start]
        if start < cursor:
            continue
        chunks.extend((text[cursor:start], replacement))
        cursor = end
    chunks.append(text[cursor:])
    return "".join(chunks)


def _reference_definitions(text: str) -> dict[str, str]:
    definitions: dict[str, str] = {}
    for match in _REFERENCE_DEFINITION_RE.finditer(text):
        label = _normalize_reference_label(match.group(1))
        definitions.setdefault(label, match.group(2).strip().strip("<>"))
    return definitions


def _normalize_reference_label(value: str) -> str:
    return " ".join(value.split()).casefold()


def _matching_square_bracket(text: str, opening: int) -> int:
    if opening >= len(text) or text[opening] != "[":
        return -1
    depth = 1
    escaped = False
    for index in range(opening + 1, len(text)):
        character = text[index]
        if escaped:
            escaped = False
            continue
        if character == "\\":
            escaped = True
        elif character == "[":
            depth += 1
        elif character == "]":
            depth -= 1
            if depth == 0:
                return index
        elif character == "\n" and depth == 1:
            return -1
    return -1


def _matching_parenthesis(text: str, opening: int) -> int:
    depth = 1
    escaped = False
    quote = ""
    angle = False
    for index in range(opening + 1, len(text)):
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
        if character in {'"', "'"} and depth == 1 and text[index - 1].isspace():
            quote = character
        elif character == "<" and depth == 1:
            angle = True
        elif character == ">" and angle:
            angle = False
        elif not angle and character == "(":
            depth += 1
        elif not angle and character == ")":
            depth -= 1
            if depth == 0:
                return index
        elif character == "\n" and depth == 1:
            return -1
    return -1


def _find_unescaped(text: str, needle: str, start: int) -> int:
    escaped = False
    for index in range(start, len(text)):
        if escaped:
            escaped = False
            continue
        if text[index] == "\\":
            escaped = True
        elif text[index] == needle:
            return index
    return -1


def _sorted_sources(images: list[_ScannedImage]) -> list[_ScannedImage]:
    return sorted(images, key=lambda image: _path_sort_key(image.relative_path))


def _path_sort_key(value: str) -> tuple[str, str]:
    return value.casefold(), value


def _image_link(prefix: str, filename: str) -> str:
    return filename if prefix == "." else posixpath.join(prefix, filename)


def relative_source_pdf(mineru_markdown_path: str, pdf_path: str) -> str:
    """Return the portable PDF path relative to the MinerU Markdown folder."""

    start = PurePosixPath(mineru_markdown_path.replace("\\", "/")).parent.as_posix()
    return posixpath.relpath(pdf_path.replace("\\", "/"), start=start)
