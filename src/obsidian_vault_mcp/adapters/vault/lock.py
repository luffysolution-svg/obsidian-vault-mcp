"""Portable exclusive lock files, including one lock per Zotero item."""

from __future__ import annotations

import hashlib
import io
import json
import os
import socket
import stat
import time
import uuid
from pathlib import Path, PurePosixPath

from ...domain.errors import LockError, LockTimeoutError
from ...domain.paths import VaultPaths, normalize_vault_relative
from . import filesystem as filesystem_module
from .filesystem import VaultPathSafetyError


class FileLock:
    def __init__(
        self,
        path: str | os.PathLike[str],
        *,
        timeout: float = 10.0,
        poll_interval: float = 0.05,
        safety_root: str | os.PathLike[str] | None = None,
    ) -> None:
        if timeout < 0 or poll_interval <= 0:
            raise ValueError("timeout must be non-negative and poll_interval positive")
        if safety_root is None:
            self.path, self.safety_root = _default_owned_location(path)
        else:
            self.path = Path(path)
            self.safety_root = Path(safety_root).expanduser().resolve()
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.token = uuid.uuid4().hex
        self.acquired = False

    def acquire(self) -> "FileLock":
        if self.acquired:
            return self
        self._validate_safe_path()
        deadline = time.monotonic() + self.timeout
        payload = json.dumps(
            {"token": self.token, "pid": os.getpid(), "host": socket.gethostname(), "createdAt": time.time()},
            separators=(",", ":"),
        ).encode("utf-8")
        while True:
            try:
                self._validate_safe_path()
                _write_exclusive_owned(
                    self.safety_root,
                    self._owned_relative(),
                    payload,
                )
                self.acquired = True
                return self
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise LockTimeoutError(f"timed out waiting for lock: {self.path}")
                time.sleep(min(self.poll_interval, max(0.0, deadline - time.monotonic())))
            except OSError as exc:
                raise LockError(f"could not acquire lock {self.path}: {exc}") from exc

    def release(self) -> None:
        if not self.acquired:
            return
        try:
            self._validate_safe_path()
            _release_owned(
                self.safety_root,
                self._owned_relative(),
                self.token,
                self.path,
            )
            self.acquired = False
        except FileNotFoundError:
            self.acquired = False
        except (OSError, ValueError, AttributeError) as exc:
            raise LockError(f"could not release lock {self.path}: {exc}") from exc

    def _validate_safe_path(self) -> None:
        try:
            relative = self.path.relative_to(self.safety_root)
        except ValueError as exc:
            raise LockError(
                f"lock path is outside its safety root: {self.path}"
            ) from exc
        current = self.safety_root
        parts = PurePosixPath(relative.as_posix()).parts
        for index, part in enumerate(parts):
            current /= part
            try:
                metadata = current.lstat()
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(metadata.st_mode) or bool(
                getattr(metadata, "st_file_attributes", 0)
                & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
            ):
                raise LockError(
                    f"lock path contains a linked or reparse component: {current}"
                )
            if index < len(parts) - 1 and not stat.S_ISDIR(metadata.st_mode):
                raise LockError(
                    f"lock path crosses a non-directory component: {current}"
                )

    def _owned_relative(self) -> str:
        try:
            relative = self.path.relative_to(self.safety_root)
        except ValueError as exc:
            raise LockError(
                f"lock path is outside its safety root: {self.path}"
            ) from exc
        return normalize_vault_relative(relative.as_posix())

    def __enter__(self) -> "FileLock":
        return self.acquire()

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.release()


class ItemLock(FileLock):
    def __init__(
        self,
        vault_root: str | os.PathLike[str],
        zotero_key: str,
        *,
        timeout: float = 10.0,
        poll_interval: float = 0.05,
    ) -> None:
        paths = VaultPaths(vault_root)
        relative = paths.item_lock(zotero_key)
        path = paths.root.joinpath(*PurePosixPath(relative).parts)
        super().__init__(
            path,
            timeout=timeout,
            poll_interval=poll_interval,
            safety_root=paths.root,
        )


class TargetLock(FileLock):
    """Serialize transactions that mutate the same Vault-relative target."""

    def __init__(
        self,
        vault_root: str | os.PathLike[str],
        relative_path: str | os.PathLike[str],
        *,
        timeout: float = 10.0,
        poll_interval: float = 0.05,
    ) -> None:
        paths = VaultPaths(vault_root)
        target = normalize_vault_relative(relative_path)
        digest = hashlib.sha256(target.casefold().encode("utf-8")).hexdigest()
        relative = f"{paths.internal_root}/locks/targets/{digest}.lock"
        path = paths.root.joinpath(*PurePosixPath(relative).parts)
        super().__init__(
            path,
            timeout=timeout,
            poll_interval=poll_interval,
            safety_root=paths.root,
        )


class GlobalLock(FileLock):
    def __init__(self, vault_root: str | os.PathLike[str], name: str, *, timeout: float = 10.0) -> None:
        paths = VaultPaths(vault_root)
        relative = paths.global_lock(name)
        path = paths.root.joinpath(*PurePosixPath(relative).parts)
        super().__init__(path, timeout=timeout, safety_root=paths.root)


def _default_owned_location(
    path: str | os.PathLike[str],
) -> tuple[Path, Path]:
    absolute = Path(os.path.abspath(Path(path).expanduser()))
    canonical_parent = absolute.parent.resolve()
    safety_root = canonical_parent
    while not safety_root.exists():
        if safety_root == safety_root.parent:
            break
        safety_root = safety_root.parent
    return canonical_parent / absolute.name, safety_root.resolve()


def _write_exclusive_owned(root: Path, relative: str, payload: bytes) -> None:
    if os.name == "nt":
        _write_exclusive_windows(root, relative, payload)
    else:
        _write_exclusive_posix(root, relative, payload)


def _write_exclusive_posix(root: Path, relative: str, payload: bytes) -> None:
    parts = PurePosixPath(relative).parts
    parent = filesystem_module._open_posix_directory_chain(
        root,
        parts[:-1],
        create=True,
        relative=relative,
    )
    descriptor = -1
    created = False
    try:
        _require_posix_parent_identity(root, parts[:-1], parent, relative)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(parts[-1], flags, 0o600, dir_fd=parent)
        created = True
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise VaultPathSafetyError(
                relative,
                f"lock path is not a regular owned file: {relative}",
            )
        remaining = memoryview(payload)
        while remaining:
            written = os.write(descriptor, remaining)
            if written <= 0:
                raise OSError(f"could not write owned lock file: {relative}")
            remaining = remaining[written:]
        os.fsync(descriptor)
        _require_posix_parent_identity(root, parts[:-1], parent, relative)
        current = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
        if (
            not stat.S_ISREG(current.st_mode)
            or (current.st_dev, current.st_ino)
            != (metadata.st_dev, metadata.st_ino)
        ):
            raise VaultPathSafetyError(
                relative,
                f"lock ownership changed while acquiring: {relative}",
            )
        os.fsync(parent)
    except BaseException:
        if created:
            _unlink_posix_if_same(parent, parts[-1], descriptor)
        raise
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(parent)


def _write_exclusive_windows(root: Path, relative: str, payload: bytes) -> None:
    parts = PurePosixPath(relative).parts
    api = filesystem_module._windows_native()
    expected_parent = root.joinpath(*parts[:-1])
    try:
        with filesystem_module._open_windows_parent(
            root,
            parts[:-1],
            create=True,
            relative=relative,
        ) as parent:
            api.assert_path(parent, expected_parent, relative)
            try:
                handle = api.open_relative(
                    parent,
                    parts[-1],
                    desired_access=(
                        api.generic_write
                        | api.delete
                        | api.synchronize
                        | api.file_read_attributes
                    ),
                    disposition=api.file_create,
                    options=(
                        api.file_non_directory_file
                        | api.file_synchronous_io_nonalert
                        | api.file_open_reparse_point
                    ),
                    attributes=api.file_attribute_normal,
                    relative=relative,
                )
            except FileExistsError as exc:
                raise _OwnedLockExists from exc
            acquired = False
            try:
                api.require_regular(handle, relative)
                api.write_all(handle, io.BytesIO(payload), relative)
                api.assert_path(parent, expected_parent, relative)
                api.assert_path(
                    handle,
                    root.joinpath(*parts),
                    relative,
                )
                acquired = True
            finally:
                if not acquired:
                    try:
                        api.mark_delete(handle, relative)
                    except OSError:
                        pass
                api.close_handle(handle)
    except _OwnedLockExists as exc:
        raise FileExistsError(relative) from exc


def _release_owned(
    root: Path,
    relative: str,
    token: str,
    display_path: Path,
) -> None:
    if os.name == "nt":
        _release_owned_windows(root, relative, token, display_path)
    else:
        _release_owned_posix(root, relative, token, display_path)


def _release_owned_posix(
    root: Path,
    relative: str,
    token: str,
    display_path: Path,
) -> None:
    parts = PurePosixPath(relative).parts
    parent = filesystem_module._open_posix_directory_chain(
        root,
        parts[:-1],
        create=False,
        relative=relative,
    )
    descriptor = -1
    try:
        _require_posix_parent_identity(root, parts[:-1], parent, relative)
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(parts[-1], flags, dir_fd=parent)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise VaultPathSafetyError(
                relative,
                f"lock path is not a regular owned file: {relative}",
            )
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            current = json.loads(stream.read().decode("utf-8"))
        if current.get("token") != token:
            raise LockError(f"lock ownership changed before release: {display_path}")
        _require_posix_parent_identity(root, parts[:-1], parent, relative)
        current_metadata = os.stat(
            parts[-1],
            dir_fd=parent,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISREG(current_metadata.st_mode)
            or (current_metadata.st_dev, current_metadata.st_ino)
            != (metadata.st_dev, metadata.st_ino)
        ):
            raise LockError(f"lock ownership changed before release: {display_path}")
        os.unlink(parts[-1], dir_fd=parent)
        os.fsync(parent)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(parent)


def _release_owned_windows(
    root: Path,
    relative: str,
    token: str,
    display_path: Path,
) -> None:
    import msvcrt

    parts = PurePosixPath(relative).parts
    api = filesystem_module._windows_native()
    expected_parent = root.joinpath(*parts[:-1])
    with filesystem_module._open_windows_parent(
        root,
        parts[:-1],
        create=False,
        relative=relative,
    ) as parent:
        api.assert_path(parent, expected_parent, relative)
        handle = api.open_relative(
            parent,
            parts[-1],
            desired_access=(
                api.generic_read
                | api.delete
                | api.synchronize
                | api.file_read_attributes
            ),
            disposition=api.file_open,
            options=(
                api.file_non_directory_file
                | api.file_synchronous_io_nonalert
                | api.file_open_reparse_point
            ),
            attributes=api.file_attribute_normal,
            relative=relative,
        )
        descriptor = -1
        try:
            api.require_regular(handle, relative)
            api.assert_path(handle, root.joinpath(*parts), relative)
            raw_handle = handle
            descriptor = msvcrt.open_osfhandle(
                raw_handle,
                os.O_RDONLY | getattr(os, "O_BINARY", 0),
            )
            handle = api.invalid_handle
            with os.fdopen(descriptor, "rb") as stream:
                descriptor = -1
                current = json.loads(stream.read().decode("utf-8"))
                if current.get("token") != token:
                    raise LockError(
                        f"lock ownership changed before release: {display_path}"
                    )
                api.assert_path(parent, expected_parent, relative)
                api.mark_delete(raw_handle, relative)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            if handle != api.invalid_handle:
                api.close_handle(handle)


def _require_posix_parent_identity(
    root: Path,
    parts: tuple[str, ...],
    parent: int,
    relative: str,
) -> None:
    current = filesystem_module._open_posix_directory_chain(
        root,
        parts,
        create=False,
        relative=relative,
    )
    try:
        expected = os.fstat(parent)
        actual = os.fstat(current)
        if (expected.st_dev, expected.st_ino) != (actual.st_dev, actual.st_ino):
            raise VaultPathSafetyError(
                relative,
                f"owned lock parent moved during I/O: {relative}",
            )
    finally:
        os.close(current)


def _unlink_posix_if_same(parent: int, name: str, descriptor: int) -> None:
    try:
        expected = os.fstat(descriptor)
        current = os.stat(name, dir_fd=parent, follow_symlinks=False)
        if (expected.st_dev, expected.st_ino) == (current.st_dev, current.st_ino):
            os.unlink(name, dir_fd=parent)
    except OSError:
        pass


class _OwnedLockExists(Exception):
    pass
