"""Filesystem adapter constrained to one Vault root."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from ...domain.paths import normalize_vault_relative, resolve_vault_path, to_vault_relative
from .atomic_writer import atomic_copy, atomic_write_bytes, atomic_write_text


class VaultFilesystem:
    def __init__(self, vault_root: str | os.PathLike[str], *, create: bool = False) -> None:
        self.root = Path(vault_root).expanduser().resolve()
        if create:
            self.root.mkdir(parents=True, exist_ok=True)
        if not self.root.is_dir():
            raise NotADirectoryError(f"Vault root is not a directory: {self.root}")

    def resolve(self, relative_path: str | os.PathLike[str]) -> Path:
        return resolve_vault_path(self.root, relative_path)

    def relative(self, path: str | os.PathLike[str]) -> str:
        return to_vault_relative(self.root, path)

    def exists(self, relative_path: str | os.PathLike[str]) -> bool:
        return self.resolve(relative_path).exists()

    def read_bytes(self, relative_path: str | os.PathLike[str]) -> bytes:
        return self.resolve(relative_path).read_bytes()

    def read_text(self, relative_path: str | os.PathLike[str]) -> str:
        return self.resolve(relative_path).read_text(encoding="utf-8")

    def write_bytes(self, relative_path: str | os.PathLike[str], data: bytes) -> Path:
        return atomic_write_bytes(self.resolve(relative_path), data)

    def write_text(self, relative_path: str | os.PathLike[str], text: str) -> Path:
        return atomic_write_text(self.resolve(relative_path), text)

    def copy_from(self, source: str | os.PathLike[str], relative_path: str | os.PathLike[str]) -> Path:
        return atomic_copy(source, self.resolve(relative_path))

    def remove(self, relative_path: str | os.PathLike[str], *, missing_ok: bool = True) -> None:
        path = self.resolve(relative_path)
        if path.is_dir():
            raise IsADirectoryError(path)
        path.unlink(missing_ok=missing_ok)

    def sha256(self, relative_path: str | os.PathLike[str]) -> str:
        digest = hashlib.sha256()
        with self.resolve(relative_path).open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def list_files(self, relative_folder: str | os.PathLike[str]) -> list[str]:
        folder = self.resolve(normalize_vault_relative(relative_folder))
        if not folder.exists():
            return []
        return sorted(self.relative(path) for path in folder.rglob("*") if path.is_file())


VaultFileSystem = VaultFilesystem
