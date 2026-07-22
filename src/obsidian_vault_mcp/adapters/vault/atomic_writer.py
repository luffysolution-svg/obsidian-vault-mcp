"""Crash-safe same-directory atomic file replacement."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import BinaryIO, Callable

from ...domain.errors import AtomicWriteError


def atomic_write_bytes(path: str | os.PathLike[str], data: bytes) -> Path:
    if not isinstance(data, bytes):
        raise TypeError("atomic_write_bytes data must be bytes")
    return _atomic_write(Path(path), lambda stream: stream.write(data))


def atomic_write_text(
    path: str | os.PathLike[str],
    text: str,
    *,
    encoding: str = "utf-8",
) -> Path:
    if not isinstance(text, str):
        raise TypeError("atomic_write_text text must be a string")
    return atomic_write_bytes(path, text.encode(encoding))


def atomic_copy(source: str | os.PathLike[str], destination: str | os.PathLike[str]) -> Path:
    source_path = Path(source)
    if not source_path.is_file():
        raise AtomicWriteError(f"copy source is not a file: {source_path}")

    def copy(stream: BinaryIO) -> int:
        with source_path.open("rb") as source_stream:
            shutil.copyfileobj(source_stream, stream, length=1024 * 1024)
        return 0

    return _atomic_write(Path(destination), copy)


def atomic_replace(staged_path: str | os.PathLike[str], destination: str | os.PathLike[str]) -> Path:
    """Replace a destination with an already flushed staged file."""

    source = Path(staged_path)
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.replace(source, target)
        _fsync_directory(target.parent)
    except OSError as exc:
        raise AtomicWriteError(f"atomic replace failed for {target}: {exc}") from exc
    return target


def _atomic_write(path: Path, write: Callable[[BinaryIO], int]) -> Path:
    target = path.expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor = -1
    temporary: Path | None = None
    try:
        file_descriptor, raw_temporary = tempfile.mkstemp(
            prefix=f".{target.name}.",
            suffix=".tmp",
            dir=target.parent,
        )
        temporary = Path(raw_temporary)
        with os.fdopen(file_descriptor, "wb") as stream:
            file_descriptor = -1
            write(stream)
            stream.flush()
            os.fsync(stream.fileno())
        if target.exists():
            os.chmod(temporary, target.stat().st_mode)
        os.replace(temporary, target)
        temporary = None
        _fsync_directory(target.parent)
        return target
    except (OSError, ValueError) as exc:
        raise AtomicWriteError(f"atomic write failed for {target}: {exc}") from exc
    finally:
        if file_descriptor >= 0:
            os.close(file_descriptor)
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def _fsync_directory(directory: Path) -> None:
    if os.name == "nt":
        return
    descriptor = -1
    try:
        descriptor = os.open(directory, os.O_RDONLY)
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        if descriptor >= 0:
            os.close(descriptor)


class AtomicWriter:
    write_bytes = staticmethod(atomic_write_bytes)
    write_text = staticmethod(atomic_write_text)
    copy = staticmethod(atomic_copy)
    replace = staticmethod(atomic_replace)
