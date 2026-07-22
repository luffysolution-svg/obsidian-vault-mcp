"""Stable Zotero identity and cross-platform filename handling."""

from __future__ import annotations

import os
import re
import string
import unicodedata
from collections.abc import Mapping
from typing import Any

from .errors import IdentityError

_ZOTERO_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_INVALID_FILENAME_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}
_ALLOWED_NAMING_FIELDS = {
    "zoteroKey",
    "firstAuthor",
    "year",
    "shortTitle",
    "index",
    "ext",
}


def validate_zotero_key(value: str) -> str:
    """Validate and return a Zotero parent-item key safe for internal paths."""

    if not isinstance(value, str):
        raise IdentityError("zoteroKey must be a string")
    key = value.strip()
    if not _ZOTERO_KEY_RE.fullmatch(key):
        raise IdentityError(
            "zoteroKey must contain only ASCII letters, numbers, '_' or '-', "
            "start with a letter or number, and be at most 64 characters"
        )
    return key


def item_id(zotero_key: str) -> str:
    """Return the permanent storage identity for a Zotero parent item."""

    return validate_zotero_key(zotero_key)


def sanitize_filename(
    value: str,
    *,
    replacement: str = "-",
    max_bytes: int = 240,
) -> str:
    """Return one filename component valid on Windows, macOS, and Linux.

    Invalid Windows characters and control characters are replaced, trailing
    dots/spaces are removed, Unicode is normalized to NFC, and device names are
    prefixed with an underscore. The result never contains a path separator.
    """

    if not isinstance(value, str):
        raise IdentityError("filename must be a string")
    if not replacement or _INVALID_FILENAME_CHARS_RE.search(replacement):
        raise IdentityError("replacement must be a non-empty safe filename string")
    if max_bytes < 16 or max_bytes > 255:
        raise IdentityError("max_bytes must be between 16 and 255")

    normalized = unicodedata.normalize("NFC", value)
    cleaned = _INVALID_FILENAME_CHARS_RE.sub(replacement, normalized)
    cleaned = re.sub(rf"(?:{re.escape(replacement)})+", replacement, cleaned)
    cleaned = cleaned.strip().rstrip(". ")
    if cleaned in {"", ".", ".."}:
        cleaned = "untitled"

    stem = cleaned.split(".", 1)[0].rstrip(". ").upper()
    if stem in _WINDOWS_RESERVED_NAMES:
        cleaned = f"_{cleaned}"

    encoded = cleaned.encode("utf-8")
    if len(encoded) > max_bytes:
        suffix = os.path.splitext(cleaned)[1]
        suffix_bytes = suffix.encode("utf-8")
        stem_value = cleaned[: -len(suffix)] if suffix else cleaned
        budget = max_bytes - len(suffix_bytes)
        if budget <= 0:
            raise IdentityError("filename extension exceeds the byte limit")
        stem_value = _truncate_utf8(stem_value, budget).rstrip(". ")
        cleaned = f"{stem_value or 'untitled'}{suffix}"

    return cleaned


def validate_naming_pattern(
    pattern: str,
    *,
    required_fields: tuple[str, ...] = ("zoteroKey",),
) -> str:
    """Validate a configurable filename pattern.

    Every storage naming pattern must retain ``{zoteroKey}``; this prevents a
    mutable title, author, year, or citekey from becoming item identity.
    """

    if not isinstance(pattern, str) or not pattern.strip():
        raise IdentityError("naming pattern must be a non-empty string")
    formatter = string.Formatter()
    fields: list[str] = []
    try:
        parsed = list(formatter.parse(pattern))
    except ValueError as exc:
        raise IdentityError(f"invalid naming pattern: {exc}") from exc
    for _literal, field_name, _format_spec, conversion in parsed:
        if field_name is None:
            continue
        if conversion:
            raise IdentityError("naming pattern conversions are not supported")
        if field_name not in _ALLOWED_NAMING_FIELDS:
            raise IdentityError(f"unsupported naming field: {field_name}")
        fields.append(field_name)
    missing = [field for field in required_fields if field not in fields]
    if missing:
        rendered = ", ".join(f"{{{field}}}" for field in missing)
        raise IdentityError(f"naming pattern must include {rendered}")
    return pattern


def render_filename(
    pattern: str,
    values: Mapping[str, Any] | None = None,
    *,
    zotero_key: str | None = None,
    first_author: str = "",
    year: str | int = "",
    short_title: str = "",
    index: int = 0,
    ext: str = "",
) -> str:
    """Render and sanitize a filename while retaining its stable key.

    ``values`` accepts the JSON-style camelCase names from the V2 config. The
    keyword arguments are a typed convenience for Python callers.
    """

    validate_naming_pattern(pattern)
    context: dict[str, Any] = {
        "zoteroKey": zotero_key,
        "firstAuthor": first_author,
        "year": year,
        "shortTitle": short_title,
        "index": index,
        "ext": ext.lstrip("."),
    }
    if values is not None:
        if not isinstance(values, Mapping):
            raise IdentityError("filename values must be a mapping")
        unknown = set(values) - _ALLOWED_NAMING_FIELDS
        if unknown:
            raise IdentityError(f"unsupported filename values: {', '.join(sorted(unknown))}")
        context.update(values)
    raw_key = context.get("zoteroKey")
    key = validate_zotero_key(raw_key) if isinstance(raw_key, str) else validate_zotero_key("")
    context["zoteroKey"] = key
    context["firstAuthor"] = _safe_metadata_value(context.get("firstAuthor"))
    context["year"] = _safe_metadata_value(context.get("year"))
    context["shortTitle"] = _safe_metadata_value(context.get("shortTitle"))
    context["ext"] = _safe_metadata_value(context.get("ext")).lstrip(".")
    try:
        rendered = pattern.format_map(context)
    except (KeyError, ValueError, TypeError) as exc:
        raise IdentityError(f"could not render naming pattern: {exc}") from exc
    filename = sanitize_filename(rendered)
    if key not in filename:
        raise IdentityError("rendered filename must retain the complete zoteroKey")
    return filename


def _safe_metadata_value(value: Any) -> str:
    if value is None:
        return ""
    return sanitize_filename(str(value), max_bytes=160)


def _truncate_utf8(value: str, byte_limit: int) -> str:
    encoded = value.encode("utf-8")[:byte_limit]
    while encoded:
        try:
            return encoded.decode("utf-8")
        except UnicodeDecodeError:
            encoded = encoded[:-1]
    return ""


# Descriptive aliases used by application services.
stable_item_id = item_id
build_filename = render_filename
