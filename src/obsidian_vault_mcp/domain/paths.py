"""Vault-relative POSIX paths and safe local path resolution."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from .errors import PathValidationError
from .identity import render_filename, validate_zotero_key

_DRIVE_RE = re.compile(r"^[A-Za-z]:($|[\\/])")
_CONTROL_OR_WINDOWS_INVALID_RE = re.compile(r'[<>:"|?*\x00-\x1f]')
_TRANSACTION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


def normalize_vault_relative(value: str | os.PathLike[str], *, allow_empty: bool = False) -> str:
    """Normalize a safe Vault-relative path to portable POSIX form.

    Absolute, drive-qualified, traversal, and Windows-incompatible paths are
    rejected before local filesystem resolution.
    """

    raw = os.fspath(value)
    if not isinstance(raw, str):
        raise PathValidationError("Vault path must be text")
    if "\x00" in raw:
        raise PathValidationError("Vault path cannot contain a NUL byte")
    if raw.startswith(("/", "\\", "//")) or _DRIVE_RE.match(raw):
        raise PathValidationError(f"Vault path must be relative: {raw!r}")

    portable = raw.replace("\\", "/")
    parts: list[str] = []
    for part in portable.split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            raise PathValidationError(f"Vault path cannot traverse outside the Vault: {raw!r}")
        _validate_portable_component(part)
        parts.append(part)
    if not parts:
        if allow_empty:
            return ""
        raise PathValidationError("Vault-relative path cannot be empty")
    return PurePosixPath(*parts).as_posix()


def validate_transaction_id(value: str) -> str:
    """Validate a transaction id before using it below internal directories."""

    if not isinstance(value, str) or not _TRANSACTION_ID_RE.fullmatch(value):
        raise PathValidationError(
            "transaction id must start with an ASCII letter or number and contain "
            "at most 128 letters, numbers, dots, underscores, or hyphens"
        )
    return value


def resolve_vault_path(vault_root: str | os.PathLike[str], relative_path: str | os.PathLike[str]) -> Path:
    """Resolve a portable relative path and prove it remains below ``vault_root``."""

    root = Path(vault_root).expanduser().resolve()
    relative = normalize_vault_relative(relative_path)
    candidate = root.joinpath(*PurePosixPath(relative).parts).resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise PathValidationError(f"Vault path escapes the Vault: {relative}") from exc
    return candidate


def to_vault_relative(vault_root: str | os.PathLike[str], path: str | os.PathLike[str]) -> str:
    """Convert a local path below a Vault to a normalized POSIX relative path."""

    root = Path(vault_root).expanduser().resolve()
    candidate = Path(path).expanduser().resolve(strict=False)
    try:
        relative = candidate.relative_to(root)
    except ValueError as exc:
        raise PathValidationError(f"path is outside the Vault: {candidate}") from exc
    return normalize_vault_relative(relative.as_posix())


class VaultPaths:
    """Build all V2 paths from one Vault root and one validated config mapping."""

    def __init__(
        self,
        vault_root: str | os.PathLike[str],
        config: Mapping[str, Any] | None = None,
    ) -> None:
        self.root = Path(vault_root).expanduser().resolve()
        self.config = config or {}

    def resolve(self, relative_path: str | os.PathLike[str]) -> Path:
        return resolve_vault_path(self.root, relative_path)

    @property
    def internal_root(self) -> str:
        return ".obsidian-vault-mcp"

    def note(self, zotero_key: str, **metadata: Any) -> str:
        return self._named_path("literature", "root", "Literature", "note", zotero_key, metadata)

    def pdf(self, zotero_key: str, **metadata: Any) -> str:
        return self._named_path("attachments", "pdfFolder", "Literature/attachment", "pdf", zotero_key, metadata)

    def mineru_markdown(self, zotero_key: str, **metadata: Any) -> str:
        return self._named_path(
            "mineru",
            "markdownFolder",
            "Literature/attachment/MinerU",
            "mineruMarkdown",
            zotero_key,
            metadata,
        )

    def mineru_image(self, zotero_key: str, index: int, ext: str, **metadata: Any) -> str:
        if not isinstance(index, int) or isinstance(index, bool) or index < 1:
            raise PathValidationError("MinerU image index must be a positive integer")
        values = dict(metadata)
        values.update(index=index, ext=ext.lstrip("."))
        return self._named_path(
            "mineru",
            "imageFolder",
            "Literature/attachment/MinerU/image",
            "mineruImage",
            zotero_key,
            values,
        )

    def state(self, zotero_key: str) -> str:
        key = validate_zotero_key(zotero_key)
        return f"{self.internal_root}/state/items/{key}.json"

    def item_lock(self, zotero_key: str) -> str:
        key = validate_zotero_key(zotero_key)
        return f"{self.internal_root}/locks/{key}.lock"

    def global_lock(self, name: str) -> str:
        if name not in {"index", "base"}:
            raise PathValidationError("global lock name must be 'index' or 'base'")
        return f"{self.internal_root}/locks/{name}.lock"

    def staging(self, transaction_id: str, relative_path: str | None = None) -> str:
        transaction = validate_transaction_id(transaction_id)
        base = f"{self.internal_root}/staging/{transaction}"
        return base if relative_path is None else f"{base}/{normalize_vault_relative(relative_path)}"

    def backup(self, transaction_id: str, relative_path: str | None = None) -> str:
        transaction = validate_transaction_id(transaction_id)
        base = f"{self.internal_root}/backups/{transaction}"
        return base if relative_path is None else f"{base}/{normalize_vault_relative(relative_path)}"

    def manifest(self, transaction_id: str) -> str:
        return f"{self.backup(transaction_id)}/manifest.json"

    def _named_path(
        self,
        section: str,
        folder_key: str,
        default_folder: str,
        naming_key: str,
        zotero_key: str,
        metadata: Mapping[str, Any],
    ) -> str:
        key = validate_zotero_key(zotero_key)
        folder = _nested_value(self.config, section, folder_key, default=default_folder)
        default_patterns = {
            "note": "{zoteroKey}.md",
            "pdf": "{zoteroKey}.pdf",
            "mineruMarkdown": "{zoteroKey}.md",
            "mineruImage": "{zoteroKey}-fig{index:02d}.{ext}",
        }
        pattern = _nested_value(self.config, "naming", naming_key, default=default_patterns[naming_key])
        aliases = {
            "first_author": "firstAuthor",
            "short_title": "shortTitle",
            "zotero_key": "zoteroKey",
        }
        values = {aliases.get(name, name): value for name, value in metadata.items()}
        values["zoteroKey"] = key
        filename = render_filename(str(pattern), values)
        return normalize_vault_relative(f"{folder}/{filename}")


def _nested_value(
    mapping: Mapping[str, Any],
    section: str,
    key: str,
    *,
    default: Any,
) -> Any:
    value = mapping.get(section, {})
    if not isinstance(value, Mapping):
        return default
    return value.get(key, default)


def _validate_portable_component(part: str) -> None:
    if _CONTROL_OR_WINDOWS_INVALID_RE.search(part):
        raise PathValidationError(f"path component is not portable: {part!r}")
    if part.endswith((" ", ".")):
        raise PathValidationError(f"path component cannot end in a space or dot: {part!r}")
    stem = part.split(".", 1)[0].upper()
    if stem in _WINDOWS_RESERVED_NAMES:
        raise PathValidationError(f"reserved Windows path component: {part!r}")


# Concise aliases for callers and tests.
normalize_relative_path = normalize_vault_relative
safe_resolve = resolve_vault_path
