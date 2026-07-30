"""Filesystem adapter constrained to one Vault root."""

from __future__ import annotations

import hashlib
import io
import os
import stat
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO

from ...domain.paths import normalize_vault_relative, resolve_vault_path, to_vault_relative


class VaultPathSafetyError(OSError):
    """A Vault-internal path contains a link, reparse point, or invalid component."""

    def __init__(self, relative_path: str, message: str) -> None:
        self.relative_path = relative_path
        super().__init__(message)


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
        return self.is_file_owned(relative_path)

    def read_bytes(self, relative_path: str | os.PathLike[str]) -> bytes:
        return self.read_bytes_owned(relative_path)

    def read_text(self, relative_path: str | os.PathLike[str]) -> str:
        return self.read_text_owned(relative_path)

    def owned_path(self, relative_path: str | os.PathLike[str]) -> Path:
        """Return a lexical Vault child after rejecting every linked component."""

        relative = normalize_vault_relative(relative_path)
        target = self.root.joinpath(*PurePosixPath(relative).parts)
        current = self.root
        parts = PurePosixPath(relative).parts
        for index, part in enumerate(parts):
            current /= part
            try:
                metadata = current.lstat()
            except FileNotFoundError:
                continue
            current_relative = current.relative_to(self.root).as_posix()
            if _is_link_or_reparse(metadata):
                raise VaultPathSafetyError(
                    current_relative,
                    f"Vault path contains a linked or reparse component: {current_relative}",
                )
            if index < len(parts) - 1 and not stat.S_ISDIR(metadata.st_mode):
                raise VaultPathSafetyError(
                    current_relative,
                    f"Vault path crosses a non-directory component: {current_relative}",
                )
        return target

    def read_text_owned(self, relative_path: str | os.PathLike[str]) -> str:
        """Read UTF-8 text only through a lexical, non-linked Vault path."""

        return self.read_bytes_owned(relative_path).decode("utf-8")

    def read_bytes_owned(self, relative_path: str | os.PathLike[str]) -> bytes:
        """Read one regular file through a pinned, no-follow parent path."""

        with self.open_binary_owned(relative_path) as stream:
            return stream.read()

    def sha256_owned(self, relative_path: str | os.PathLike[str]) -> str:
        """Hash one regular file through a pinned, no-follow parent path."""

        digest = hashlib.sha256()
        with self.open_binary_owned(relative_path) as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def atomic_write_bytes_owned(
        self,
        relative_path: str | os.PathLike[str],
        data: bytes,
    ) -> Path:
        """Atomically write bytes using handle-relative, no-follow I/O."""

        if not isinstance(data, bytes):
            raise TypeError("atomic_write_bytes_owned data must be bytes")
        return self.atomic_copy_stream_owned(relative_path, io.BytesIO(data))

    def atomic_copy_stream_owned(
        self,
        relative_path: str | os.PathLike[str],
        source: BinaryIO,
    ) -> Path:
        """Atomically copy an open stream to one owned Vault path."""

        relative = normalize_vault_relative(relative_path)
        if os.name == "nt":
            _windows_atomic_copy_stream(
                self.root,
                relative,
                source,
            )
        else:
            _posix_atomic_copy_stream(
                self.root,
                relative,
                source,
            )
        return self.root.joinpath(*PurePosixPath(relative).parts)

    def atomic_copy_owned(
        self,
        source_relative: str | os.PathLike[str],
        destination_relative: str | os.PathLike[str],
    ) -> Path:
        """Atomically copy one owned regular file to another owned path."""

        with self.open_binary_owned(source_relative) as source:
            return self.atomic_copy_stream_owned(destination_relative, source)

    def atomic_replace_owned(
        self,
        source_relative: str | os.PathLike[str],
        destination_relative: str | os.PathLike[str],
    ) -> Path:
        """Move one owned staged file to an owned destination by parent handle."""

        source = normalize_vault_relative(source_relative)
        destination = normalize_vault_relative(destination_relative)
        if os.name == "nt":
            _windows_replace_relative(self.root, source, destination)
        else:
            _posix_replace_relative(self.root, source, destination)
        return self.root.joinpath(*PurePosixPath(destination).parts)

    def unlink_owned(
        self,
        relative_path: str | os.PathLike[str],
        *,
        missing_ok: bool = True,
    ) -> None:
        """Delete one owned file without following its final component."""

        relative = normalize_vault_relative(relative_path)
        if os.name == "nt":
            _windows_unlink_relative(self.root, relative, missing_ok=missing_ok)
        else:
            _posix_unlink_relative(self.root, relative, missing_ok=missing_ok)

    def rmdir_owned(
        self,
        relative_path: str | os.PathLike[str],
        *,
        missing_ok: bool = True,
    ) -> None:
        """Remove one empty owned directory without following links."""

        relative = normalize_vault_relative(relative_path)
        if os.name == "nt":
            _windows_rmdir_relative(self.root, relative, missing_ok=missing_ok)
        else:
            _posix_rmdir_relative(self.root, relative, missing_ok=missing_ok)

    @contextmanager
    def open_binary_owned(
        self,
        relative_path: str | os.PathLike[str],
    ) -> Iterator[BinaryIO]:
        """Open one regular file without allowing a parent-link swap."""

        relative = normalize_vault_relative(relative_path)
        parts = PurePosixPath(relative).parts
        if os.name == "nt":
            with _open_windows_parent(
                self.root,
                parts[:-1],
                create=False,
                relative=relative,
            ) as parent:
                with _open_windows_regular_file(parent, parts[-1], relative) as stream:
                    yield stream
            return

        parent = _open_posix_directory_chain(
            self.root,
            parts[:-1],
            create=False,
            relative=relative,
        )
        descriptor = -1
        try:
            flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
            flags |= getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(parts[-1], flags, dir_fd=parent)
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise VaultPathSafetyError(
                    relative,
                    f"Vault path is not a regular file: {relative}",
                )
            with os.fdopen(descriptor, "rb") as stream:
                descriptor = -1
                yield stream
        except OSError as exc:
            if isinstance(exc, (FileNotFoundError, VaultPathSafetyError)):
                raise
            raise VaultPathSafetyError(
                relative,
                f"could not safely open Vault file: {relative}",
            ) from exc
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            os.close(parent)

    @contextmanager
    def pin_owned_path(
        self,
        relative_path: str | os.PathLike[str],
        *,
        create_parent: bool = False,
    ) -> Iterator[Path]:
        """Pin a file's parent so a concurrent link swap cannot redirect I/O."""

        relative = normalize_vault_relative(relative_path)
        parts = PurePosixPath(relative).parts
        target = self.root.joinpath(*parts)
        parent_parts = parts[:-1]
        if os.name == "nt":
            with _open_windows_parent(
                self.root,
                parent_parts,
                create=create_parent,
                relative=relative,
            ):
                _reject_final_link(target, relative)
                yield target
            return

        descriptor = _open_posix_directory_chain(
            self.root,
            parent_parts,
            create=create_parent,
            relative=relative,
        )
        try:
            descriptor_root = _descriptor_root()
            pinned = descriptor_root / str(descriptor) / parts[-1]
            _reject_final_link(pinned, relative)
            yield pinned
        finally:
            os.close(descriptor)

    def is_file_owned(self, relative_path: str | os.PathLike[str]) -> bool:
        """Check a file without resolving through Vault-internal links."""

        try:
            with self.open_binary_owned(relative_path):
                return True
        except FileNotFoundError:
            return False

    def scan_owned_files(
        self,
        relative_folder: str | os.PathLike[str] | None = None,
        *,
        recursive: bool = True,
    ) -> tuple[list[str], list[str]]:
        """Enumerate regular files without following links or reparse points."""

        if relative_folder is None:
            folder = self.root
        else:
            folder = self.owned_path(relative_folder)
        try:
            folder_metadata = folder.lstat()
        except FileNotFoundError:
            return [], []
        if _is_link_or_reparse(folder_metadata):
            relative = folder.relative_to(self.root).as_posix()
            raise VaultPathSafetyError(
                relative,
                f"Vault scan root is linked or reparse-backed: {relative}",
            )
        if not stat.S_ISDIR(folder_metadata.st_mode):
            relative = folder.relative_to(self.root).as_posix()
            raise VaultPathSafetyError(relative, f"Vault scan root is not a directory: {relative}")

        files: list[str] = []
        rejected: list[str] = []
        pending = [folder]
        while pending:
            directory = pending.pop()
            with os.scandir(directory) as entries:
                for entry in entries:
                    child = Path(entry.path)
                    relative = normalize_vault_relative(child.relative_to(self.root).as_posix())
                    try:
                        metadata = entry.stat(follow_symlinks=False)
                    except FileNotFoundError:
                        rejected.append(relative)
                        continue
                    if _is_link_or_reparse(metadata):
                        rejected.append(relative)
                    elif stat.S_ISDIR(metadata.st_mode):
                        if recursive:
                            pending.append(child)
                    elif stat.S_ISREG(metadata.st_mode):
                        files.append(relative)
                    else:
                        rejected.append(relative)
        return (
            sorted(files, key=lambda value: (value.casefold(), value)),
            sorted(set(rejected), key=lambda value: (value.casefold(), value)),
        )

    def write_bytes(self, relative_path: str | os.PathLike[str], data: bytes) -> Path:
        return self.atomic_write_bytes_owned(relative_path, data)

    def write_text(self, relative_path: str | os.PathLike[str], text: str) -> Path:
        return self.atomic_write_bytes_owned(relative_path, text.encode("utf-8"))

    def copy_from(self, source: str | os.PathLike[str], relative_path: str | os.PathLike[str]) -> Path:
        with Path(source).open("rb") as stream:
            return self.atomic_copy_stream_owned(relative_path, stream)

    def remove(self, relative_path: str | os.PathLike[str], *, missing_ok: bool = True) -> None:
        self.unlink_owned(relative_path, missing_ok=missing_ok)

    def sha256(self, relative_path: str | os.PathLike[str]) -> str:
        return self.sha256_owned(relative_path)

    def list_files(self, relative_folder: str | os.PathLike[str]) -> list[str]:
        files, rejected = self.scan_owned_files(relative_folder, recursive=True)
        if rejected:
            raise VaultPathSafetyError(
                rejected[0],
                f"Vault file listing contains an unsafe path: {rejected[0]}",
            )
        return files


VaultFileSystem = VaultFilesystem


def _is_link_or_reparse(metadata: os.stat_result) -> bool:
    return stat.S_ISLNK(metadata.st_mode) or bool(
        getattr(metadata, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def _reject_final_link(path: Path, relative: str) -> None:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return
    if _is_link_or_reparse(metadata):
        raise VaultPathSafetyError(
            relative,
            f"Vault path is linked or reparse-backed: {relative}",
        )


def _descriptor_root() -> Path:
    for candidate in (Path("/proc/self/fd"), Path("/dev/fd")):
        if candidate.is_dir():
            return candidate
    raise VaultPathSafetyError(
        "",
        "this platform cannot expose a pinned directory descriptor safely",
    )


def _assert_posix_path(
    descriptor: int,
    expected: Path,
    relative: str,
) -> None:
    """Verify that a pinned directory has not been moved from its Vault path."""

    try:
        pinned = os.fstat(descriptor)
        lexical = os.stat(expected, follow_symlinks=False)
    except OSError as exc:
        raise VaultPathSafetyError(
            relative,
            f"could not verify pinned Vault path: {relative}",
        ) from exc
    if (
        not stat.S_ISDIR(pinned.st_mode)
        or not stat.S_ISDIR(lexical.st_mode)
        or _is_link_or_reparse(lexical)
        or (pinned.st_dev, pinned.st_ino) != (lexical.st_dev, lexical.st_ino)
    ):
        raise VaultPathSafetyError(
            relative,
            f"owned Vault parent moved during I/O: {relative}",
        )


def _open_posix_directory_chain(
    root: Path,
    parts: tuple[str, ...],
    *,
    create: bool,
    relative: str,
) -> int:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(root, flags)
    except OSError as exc:
        raise VaultPathSafetyError(
            relative,
            f"could not pin Vault root for: {relative}",
        ) from exc
    try:
        current = root
        _assert_posix_path(descriptor, current, relative)
        for part in parts:
            try:
                next_descriptor = os.open(part, flags, dir_fd=descriptor)
            except FileNotFoundError:
                if not create:
                    raise
                try:
                    os.mkdir(part, dir_fd=descriptor)
                except FileExistsError:
                    pass
                next_descriptor = os.open(part, flags, dir_fd=descriptor)
            metadata = os.fstat(next_descriptor)
            if not stat.S_ISDIR(metadata.st_mode):
                os.close(next_descriptor)
                raise VaultPathSafetyError(
                    relative,
                    f"Vault path crosses a non-directory component: {relative}",
                )
            os.close(descriptor)
            descriptor = next_descriptor
            current /= part
            _assert_posix_path(descriptor, current, relative)
        return descriptor
    except (OSError, ValueError) as exc:
        os.close(descriptor)
        if isinstance(exc, (FileNotFoundError, VaultPathSafetyError)):
            raise
        raise VaultPathSafetyError(
            relative,
            f"could not pin Vault parent for: {relative}",
        ) from exc


def _posix_atomic_copy_stream(
    root: Path,
    relative: str,
    source: BinaryIO,
) -> None:
    parts = PurePosixPath(relative).parts
    parent = _open_posix_directory_chain(
        root,
        parts[:-1],
        create=True,
        relative=relative,
    )
    temporary_name = f".{parts[-1]}.{uuid.uuid4().hex}.tmp"
    rollback_name: str | None = None
    descriptor = -1
    created = False
    renamed = False
    verified = False
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(temporary_name, flags, 0o600, dir_fd=parent)
        created = True
        try:
            target_metadata = os.stat(
                parts[-1],
                dir_fd=parent,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            target_metadata = None
        if target_metadata is not None:
            if _is_link_or_reparse(target_metadata) or not stat.S_ISREG(
                target_metadata.st_mode
            ):
                raise VaultPathSafetyError(
                    relative,
                    f"Vault destination is not a regular owned file: {relative}",
                )
            os.fchmod(descriptor, stat.S_IMODE(target_metadata.st_mode))
            rollback_name = f".ovm-{uuid.uuid4().hex}.rollback"
            os.link(
                parts[-1],
                rollback_name,
                src_dir_fd=parent,
                dst_dir_fd=parent,
                follow_symlinks=False,
            )
        with os.fdopen(descriptor, "wb") as destination:
            descriptor = -1
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                destination.write(chunk)
            destination.flush()
            os.fsync(destination.fileno())
        expected_parent = root.joinpath(*parts[:-1])
        _assert_posix_path(parent, expected_parent, relative)
        os.replace(
            temporary_name,
            parts[-1],
            src_dir_fd=parent,
            dst_dir_fd=parent,
        )
        created = False
        renamed = True
        try:
            _assert_posix_path(parent, expected_parent, relative)
        except BaseException:
            recovery_errors: list[BaseException] = []
            try:
                os.replace(
                    parts[-1],
                    temporary_name,
                    src_dir_fd=parent,
                    dst_dir_fd=parent,
                )
                created = True
            except BaseException as exc:
                recovery_errors.append(exc)
            if rollback_name is not None:
                try:
                    os.replace(
                        rollback_name,
                        parts[-1],
                        src_dir_fd=parent,
                        dst_dir_fd=parent,
                    )
                    rollback_name = None
                except BaseException as exc:
                    recovery_errors.append(exc)
            elif recovery_errors:
                try:
                    os.unlink(parts[-1], dir_fd=parent)
                except BaseException as exc:
                    recovery_errors.append(exc)
            os.fsync(parent)
            if recovery_errors:
                raise VaultPathSafetyError(
                    relative,
                    f"could not restore unsafe owned rename: {relative}",
                ) from recovery_errors[0]
            raise
        verified = True
        if rollback_name is not None:
            os.unlink(rollback_name, dir_fd=parent)
            rollback_name = None
        os.fsync(parent)
    except (OSError, ValueError) as exc:
        if isinstance(exc, (FileNotFoundError, VaultPathSafetyError)):
            raise
        raise VaultPathSafetyError(
            relative,
            f"could not atomically write owned Vault file: {relative}",
        ) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if created:
            try:
                os.unlink(temporary_name, dir_fd=parent)
            except OSError:
                pass
        if rollback_name is not None and (not renamed or verified):
            try:
                os.unlink(rollback_name, dir_fd=parent)
            except OSError:
                pass
        os.close(parent)


def _posix_replace_relative(root: Path, source: str, destination: str) -> None:
    source_parts = PurePosixPath(source).parts
    destination_parts = PurePosixPath(destination).parts
    source_parent = _open_posix_directory_chain(
        root,
        source_parts[:-1],
        create=False,
        relative=source,
    )
    destination_parent = -1
    rollback_name: str | None = None
    renamed = False
    verified = False
    try:
        metadata = os.stat(
            source_parts[-1],
            dir_fd=source_parent,
            follow_symlinks=False,
        )
        if _is_link_or_reparse(metadata) or not stat.S_ISREG(metadata.st_mode):
            raise VaultPathSafetyError(
                source,
                f"Vault source is not a regular owned file: {source}",
            )
        destination_parent = _open_posix_directory_chain(
            root,
            destination_parts[:-1],
            create=True,
            relative=destination,
        )
        try:
            target_metadata = os.stat(
                destination_parts[-1],
                dir_fd=destination_parent,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            target_metadata = None
        if target_metadata is not None and (
            _is_link_or_reparse(target_metadata)
            or not stat.S_ISREG(target_metadata.st_mode)
        ):
            raise VaultPathSafetyError(
                destination,
                f"Vault destination is not a regular owned file: {destination}",
            )
        if target_metadata is not None:
            rollback_name = f".ovm-{uuid.uuid4().hex}.rollback"
            os.link(
                destination_parts[-1],
                rollback_name,
                src_dir_fd=destination_parent,
                dst_dir_fd=destination_parent,
                follow_symlinks=False,
            )
        expected_source_parent = root.joinpath(*source_parts[:-1])
        expected_destination_parent = root.joinpath(*destination_parts[:-1])
        _assert_posix_path(source_parent, expected_source_parent, source)
        _assert_posix_path(
            destination_parent,
            expected_destination_parent,
            destination,
        )
        os.replace(
            source_parts[-1],
            destination_parts[-1],
            src_dir_fd=source_parent,
            dst_dir_fd=destination_parent,
        )
        renamed = True
        try:
            _assert_posix_path(source_parent, expected_source_parent, source)
            _assert_posix_path(
                destination_parent,
                expected_destination_parent,
                destination,
            )
        except BaseException:
            recovery_errors: list[BaseException] = []
            try:
                os.replace(
                    destination_parts[-1],
                    source_parts[-1],
                    src_dir_fd=destination_parent,
                    dst_dir_fd=source_parent,
                )
            except BaseException as exc:
                recovery_errors.append(exc)
            if rollback_name is not None:
                try:
                    os.replace(
                        rollback_name,
                        destination_parts[-1],
                        src_dir_fd=destination_parent,
                        dst_dir_fd=destination_parent,
                    )
                    rollback_name = None
                except BaseException as exc:
                    recovery_errors.append(exc)
            elif recovery_errors:
                try:
                    os.unlink(
                        destination_parts[-1],
                        dir_fd=destination_parent,
                    )
                except BaseException as exc:
                    recovery_errors.append(exc)
            os.fsync(destination_parent)
            if recovery_errors:
                raise VaultPathSafetyError(
                    destination,
                    f"could not restore unsafe owned rename: {destination}",
                ) from recovery_errors[0]
            raise
        verified = True
        if rollback_name is not None:
            os.unlink(rollback_name, dir_fd=destination_parent)
            rollback_name = None
        os.fsync(destination_parent)
    finally:
        if (
            destination_parent >= 0
            and rollback_name is not None
            and (not renamed or verified)
        ):
            try:
                os.unlink(rollback_name, dir_fd=destination_parent)
            except OSError:
                pass
        if destination_parent >= 0:
            os.close(destination_parent)
        os.close(source_parent)


def _posix_unlink_relative(
    root: Path,
    relative: str,
    *,
    missing_ok: bool,
) -> None:
    parts = PurePosixPath(relative).parts
    try:
        parent = _open_posix_directory_chain(
            root,
            parts[:-1],
            create=False,
            relative=relative,
        )
    except FileNotFoundError:
        if missing_ok:
            return
        raise
    rollback_name: str | None = None
    deleted = False
    try:
        try:
            metadata = os.stat(
                parts[-1],
                dir_fd=parent,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            if missing_ok:
                return
            raise
        if _is_link_or_reparse(metadata) or not stat.S_ISREG(metadata.st_mode):
            raise VaultPathSafetyError(
                relative,
                f"Vault path is not a regular owned file: {relative}",
            )
        rollback_name = f".ovm-{uuid.uuid4().hex}.rollback"
        os.link(
            parts[-1],
            rollback_name,
            src_dir_fd=parent,
            dst_dir_fd=parent,
            follow_symlinks=False,
        )
        expected_parent = root.joinpath(*parts[:-1])
        _assert_posix_path(parent, expected_parent, relative)
        os.unlink(parts[-1], dir_fd=parent)
        deleted = True
        try:
            _assert_posix_path(parent, expected_parent, relative)
        except BaseException:
            recovery_errors: list[BaseException] = []
            try:
                os.link(
                    rollback_name,
                    parts[-1],
                    src_dir_fd=parent,
                    dst_dir_fd=parent,
                    follow_symlinks=False,
                )
                os.unlink(rollback_name, dir_fd=parent)
                rollback_name = None
                deleted = False
                os.fsync(parent)
            except BaseException as exc:
                recovery_errors.append(exc)
            if recovery_errors:
                raise VaultPathSafetyError(
                    relative,
                    f"could not restore unsafe owned delete: {relative}",
                ) from recovery_errors[0]
            raise
        os.unlink(rollback_name, dir_fd=parent)
        rollback_name = None
        os.fsync(parent)
    finally:
        if rollback_name is not None and not deleted:
            try:
                os.unlink(rollback_name, dir_fd=parent)
            except OSError:
                pass
        os.close(parent)


def _posix_rmdir_relative(
    root: Path,
    relative: str,
    *,
    missing_ok: bool,
) -> None:
    parts = PurePosixPath(relative).parts
    try:
        parent = _open_posix_directory_chain(
            root,
            parts[:-1],
            create=False,
            relative=relative,
        )
    except FileNotFoundError:
        if missing_ok:
            return
        raise
    try:
        try:
            metadata = os.stat(
                parts[-1],
                dir_fd=parent,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            if missing_ok:
                return
            raise
        if _is_link_or_reparse(metadata) or not stat.S_ISDIR(metadata.st_mode):
            raise VaultPathSafetyError(
                relative,
                f"Vault path is not an owned directory: {relative}",
            )
        expected_parent = root.joinpath(*parts[:-1])
        _assert_posix_path(parent, expected_parent, relative)
        os.rmdir(parts[-1], dir_fd=parent)
        try:
            _assert_posix_path(parent, expected_parent, relative)
        except BaseException:
            try:
                os.mkdir(
                    parts[-1],
                    stat.S_IMODE(metadata.st_mode),
                    dir_fd=parent,
                )
                os.fsync(parent)
            except BaseException as exc:
                raise VaultPathSafetyError(
                    relative,
                    f"could not restore unsafe owned directory delete: {relative}",
                ) from exc
            raise
        os.fsync(parent)
    finally:
        os.close(parent)


_WINDOWS_NATIVE: Any | None = None


class _WindowsNative:
    def __init__(self) -> None:
        import ctypes
        from ctypes import wintypes

        self.ctypes = ctypes
        self.wintypes = wintypes

        class UnicodeString(ctypes.Structure):
            _fields_ = [
                ("length", wintypes.USHORT),
                ("maximum_length", wintypes.USHORT),
                ("buffer", wintypes.LPWSTR),
            ]

        class ObjectAttributes(ctypes.Structure):
            _fields_ = [
                ("length", wintypes.ULONG),
                ("root_directory", wintypes.HANDLE),
                ("object_name", ctypes.POINTER(UnicodeString)),
                ("attributes", wintypes.ULONG),
                ("security_descriptor", wintypes.LPVOID),
                ("security_quality_of_service", wintypes.LPVOID),
            ]

        class IoStatusBlock(ctypes.Structure):
            _fields_ = [
                ("status", wintypes.LPVOID),
                ("information", ctypes.c_size_t),
            ]

        class FileInformation(ctypes.Structure):
            _fields_ = [
                ("file_attributes", wintypes.DWORD),
                ("creation_time", wintypes.FILETIME),
                ("last_access_time", wintypes.FILETIME),
                ("last_write_time", wintypes.FILETIME),
                ("volume_serial_number", wintypes.DWORD),
                ("file_size_high", wintypes.DWORD),
                ("file_size_low", wintypes.DWORD),
                ("number_of_links", wintypes.DWORD),
                ("file_index_high", wintypes.DWORD),
                ("file_index_low", wintypes.DWORD),
            ]

        class RenameInformation(ctypes.Structure):
            _fields_ = [
                ("replace_if_exists", wintypes.BOOLEAN),
                ("root_directory", wintypes.HANDLE),
                ("file_name_length", wintypes.ULONG),
                ("file_name", wintypes.WCHAR * 1),
            ]

        class DispositionInformation(ctypes.Structure):
            _fields_ = [("delete_file", wintypes.BOOLEAN)]

        self.UnicodeString = UnicodeString
        self.ObjectAttributes = ObjectAttributes
        self.IoStatusBlock = IoStatusBlock
        self.FileInformation = FileInformation
        self.RenameInformation = RenameInformation
        self.DispositionInformation = DispositionInformation

        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.ntdll = ctypes.WinDLL("ntdll", use_last_error=True)
        self.create_file = self.kernel32.CreateFileW
        self.create_file.argtypes = (
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HANDLE,
        )
        self.create_file.restype = wintypes.HANDLE
        self.close_handle = self.kernel32.CloseHandle
        self.close_handle.argtypes = (wintypes.HANDLE,)
        self.close_handle.restype = wintypes.BOOL
        self.get_information = self.kernel32.GetFileInformationByHandle
        self.get_information.argtypes = (wintypes.HANDLE, wintypes.LPVOID)
        self.get_information.restype = wintypes.BOOL
        self.get_final_path = self.kernel32.GetFinalPathNameByHandleW
        self.get_final_path.argtypes = (
            wintypes.HANDLE,
            wintypes.LPWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
        )
        self.get_final_path.restype = wintypes.DWORD
        self.write_file = self.kernel32.WriteFile
        self.write_file.argtypes = (
            wintypes.HANDLE,
            wintypes.LPCVOID,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
            wintypes.LPVOID,
        )
        self.write_file.restype = wintypes.BOOL
        self.read_file = self.kernel32.ReadFile
        self.read_file.argtypes = (
            wintypes.HANDLE,
            wintypes.LPVOID,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
            wintypes.LPVOID,
        )
        self.read_file.restype = wintypes.BOOL
        self.flush_file = self.kernel32.FlushFileBuffers
        self.flush_file.argtypes = (wintypes.HANDLE,)
        self.flush_file.restype = wintypes.BOOL
        self.nt_create_file = self.ntdll.NtCreateFile
        self.nt_create_file.argtypes = (
            ctypes.POINTER(wintypes.HANDLE),
            wintypes.DWORD,
            ctypes.POINTER(ObjectAttributes),
            ctypes.POINTER(IoStatusBlock),
            wintypes.LPVOID,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
        )
        self.nt_create_file.restype = ctypes.c_long
        self.nt_set_information = self.ntdll.NtSetInformationFile
        self.nt_set_information.argtypes = (
            wintypes.HANDLE,
            ctypes.POINTER(IoStatusBlock),
            wintypes.LPVOID,
            wintypes.ULONG,
            wintypes.INT,
        )
        self.nt_set_information.restype = ctypes.c_long
        self.status_to_error = self.ntdll.RtlNtStatusToDosError
        self.status_to_error.argtypes = (ctypes.c_long,)
        self.status_to_error.restype = wintypes.ULONG

        self.invalid_handle = wintypes.HANDLE(-1).value
        self.synchronize = 0x00100000
        self.delete = 0x00010000
        self.file_read_attributes = 0x00000080
        self.file_list_directory = 0x00000001
        self.file_add_file = 0x00000002
        self.file_add_subdirectory = 0x00000004
        self.file_traverse = 0x00000020
        self.generic_read = 0x80000000
        self.generic_write = 0x40000000
        self.share_all = 0x00000007
        self.open_existing = 3
        self.file_open = 1
        self.file_create = 2
        self.file_open_if = 3
        self.file_directory_file = 0x00000001
        self.file_non_directory_file = 0x00000040
        self.file_synchronous_io_nonalert = 0x00000020
        self.file_open_reparse_point = 0x00200000
        self.file_attribute_directory = 0x00000010
        self.file_attribute_normal = 0x00000080
        self.file_attribute_reparse_point = 0x00000400
        self.file_flag_open_reparse_point = 0x00200000
        self.file_flag_backup_semantics = 0x02000000
        self.obj_case_insensitive = 0x00000040
        self.file_rename_information = 10
        self.file_disposition_information = 13

    def directory_access(self, *, writable: bool) -> int:
        desired = (
            self.synchronize
            | self.file_read_attributes
            | self.file_list_directory
            | self.file_traverse
        )
        if writable:
            desired |= self.file_add_file | self.file_add_subdirectory
        return desired

    def open_root(self, root: Path, relative: str, *, writable: bool) -> int:
        desired = self.directory_access(writable=writable)
        handle = self.create_file(
            str(root),
            desired,
            self.share_all,
            None,
            self.open_existing,
            self.file_flag_open_reparse_point | self.file_flag_backup_semantics,
            None,
        )
        if handle == self.invalid_handle:
            raise VaultPathSafetyError(
                relative,
                f"could not safely open Vault root for: {relative}",
            )
        try:
            self.require_directory(handle, relative)
            self.assert_path(handle, root, relative)
        except BaseException:
            self.close_handle(handle)
            raise
        return int(handle)

    def open_relative(
        self,
        parent: int,
        name: str,
        *,
        desired_access: int,
        disposition: int,
        options: int,
        attributes: int,
        relative: str,
    ) -> int:
        buffer = self.ctypes.create_unicode_buffer(name)
        encoded_length = len(name.encode("utf-16-le"))
        unicode_name = self.UnicodeString(
            encoded_length,
            encoded_length,
            self.ctypes.cast(buffer, self.wintypes.LPWSTR),
        )
        object_attributes = self.ObjectAttributes(
            self.ctypes.sizeof(self.ObjectAttributes),
            parent,
            self.ctypes.pointer(unicode_name),
            self.obj_case_insensitive,
            None,
            None,
        )
        status_block = self.IoStatusBlock()
        handle = self.wintypes.HANDLE()
        status = self.nt_create_file(
            self.ctypes.byref(handle),
            desired_access,
            self.ctypes.byref(object_attributes),
            self.ctypes.byref(status_block),
            None,
            attributes,
            self.share_all,
            disposition,
            options,
            None,
            0,
        )
        if status < 0:
            error = int(self.status_to_error(status))
            if error in {2, 3}:
                raise FileNotFoundError(error, relative)
            if error in {80, 183}:
                raise FileExistsError(error, relative)
            raise OSError(error, relative)
        return int(handle.value)

    def require_directory(self, handle: int, relative: str) -> None:
        attributes = self.attributes(handle, relative)
        if (
            not attributes & self.file_attribute_directory
            or attributes & self.file_attribute_reparse_point
        ):
            raise VaultPathSafetyError(
                relative,
                f"Vault path contains a linked or non-directory component: {relative}",
            )

    def require_regular(self, handle: int, relative: str) -> None:
        attributes = self.attributes(handle, relative)
        if (
            attributes & self.file_attribute_directory
            or attributes & self.file_attribute_reparse_point
        ):
            raise VaultPathSafetyError(
                relative,
                f"Vault path is not a regular owned file: {relative}",
            )

    def attributes(self, handle: int, relative: str) -> int:
        information = self.FileInformation()
        if not self.get_information(handle, self.ctypes.byref(information)):
            raise OSError(
                self.ctypes.get_last_error(),
                f"could not inspect Vault handle: {relative}",
            )
        return int(information.file_attributes)

    def assert_path(self, handle: int, expected: Path, relative: str) -> None:
        buffer = self.ctypes.create_unicode_buffer(32768)
        length = self.get_final_path(handle, buffer, len(buffer), 0)
        if length == 0 or length >= len(buffer):
            raise VaultPathSafetyError(
                relative,
                f"could not verify pinned Vault path: {relative}",
            )
        actual = buffer.value
        if actual.startswith("\\\\?\\UNC\\"):
            actual = f"\\\\{actual[8:]}"
        elif actual.startswith("\\\\?\\"):
            actual = actual[4:]
        if os.path.normcase(os.path.normpath(actual)) != os.path.normcase(
            os.path.normpath(str(expected))
        ):
            raise VaultPathSafetyError(
                relative,
                f"owned Vault parent moved during I/O: {relative}",
            )

    def write_all(self, handle: int, source: BinaryIO, relative: str) -> None:
        while True:
            chunk = source.read(1024 * 1024)
            if not chunk:
                break
            if not isinstance(chunk, bytes):
                raise TypeError("owned binary copy source must return bytes")
            written = self.wintypes.DWORD()
            if not self.write_file(
                handle,
                chunk,
                len(chunk),
                self.ctypes.byref(written),
                None,
            ) or written.value != len(chunk):
                raise OSError(
                    self.ctypes.get_last_error(),
                    f"could not write owned Vault file: {relative}",
                )
        if not self.flush_file(handle):
            raise OSError(
                self.ctypes.get_last_error(),
                f"could not flush owned Vault file: {relative}",
            )

    def copy_all(self, source: int, destination: int, relative: str) -> None:
        buffer = self.ctypes.create_string_buffer(1024 * 1024)
        while True:
            read = self.wintypes.DWORD()
            if not self.read_file(
                source,
                buffer,
                len(buffer),
                self.ctypes.byref(read),
                None,
            ):
                raise OSError(
                    self.ctypes.get_last_error(),
                    f"could not read owned Vault file: {relative}",
                )
            if read.value == 0:
                break
            written = self.wintypes.DWORD()
            if not self.write_file(
                destination,
                buffer,
                read.value,
                self.ctypes.byref(written),
                None,
            ) or written.value != read.value:
                raise OSError(
                    self.ctypes.get_last_error(),
                    f"could not copy owned Vault file: {relative}",
                )
        if not self.flush_file(destination):
            raise OSError(
                self.ctypes.get_last_error(),
                f"could not flush owned Vault file: {relative}",
            )

    def rename(
        self,
        handle: int,
        destination_parent: int,
        destination_name: str,
        *,
        expected_parent: Path,
        relative: str,
    ) -> None:
        self.assert_path(destination_parent, expected_parent, relative)
        self.rename_relative(
            handle,
            destination_parent,
            destination_name,
            relative=relative,
        )

    def rename_relative(
        self,
        handle: int,
        destination_parent: int,
        destination_name: str,
        *,
        relative: str,
        replace_if_exists: bool = True,
    ) -> None:
        """Rename through a pinned parent without a lexical-path check."""

        encoded_name = destination_name.encode("utf-16-le")
        size = self.RenameInformation.file_name.offset + len(encoded_name)
        raw = self.ctypes.create_string_buffer(size)
        information = self.ctypes.cast(
            raw,
            self.ctypes.POINTER(self.RenameInformation),
        ).contents
        information.replace_if_exists = int(replace_if_exists)
        information.root_directory = destination_parent
        information.file_name_length = len(encoded_name)
        self.ctypes.memmove(
            self.ctypes.addressof(raw) + self.RenameInformation.file_name.offset,
            encoded_name,
            len(encoded_name),
        )
        status_block = self.IoStatusBlock()
        status = self.nt_set_information(
            handle,
            self.ctypes.byref(status_block),
            raw,
            size,
            self.file_rename_information,
        )
        if status < 0:
            raise OSError(
                int(self.status_to_error(status)),
                f"could not rename owned Vault file: {relative}",
            )

    def set_delete(self, handle: int, delete: bool, relative: str) -> None:
        information = self.DispositionInformation(int(delete))
        status_block = self.IoStatusBlock()
        status = self.nt_set_information(
            handle,
            self.ctypes.byref(status_block),
            self.ctypes.byref(information),
            self.ctypes.sizeof(information),
            self.file_disposition_information,
        )
        if status < 0:
            raise OSError(
                int(self.status_to_error(status)),
                (
                    f"could not delete owned Vault file: {relative}"
                    if delete
                    else f"could not cancel owned Vault deletion: {relative}"
                ),
            )

    def mark_delete(self, handle: int, relative: str) -> None:
        self.set_delete(handle, True, relative)

    def clear_delete(self, handle: int, relative: str) -> None:
        self.set_delete(handle, False, relative)


def _windows_native() -> _WindowsNative:
    global _WINDOWS_NATIVE
    if _WINDOWS_NATIVE is None:
        _WINDOWS_NATIVE = _WindowsNative()
    return _WINDOWS_NATIVE


@contextmanager
def _open_windows_parent(
    root: Path,
    parts: tuple[str, ...],
    *,
    create: bool,
    relative: str,
    writable: bool | None = None,
) -> Iterator[int]:
    api = _windows_native()
    writable = create if writable is None else writable
    handle = api.open_root(
        root,
        relative,
        writable=create or (writable and not parts),
    )
    current = root
    try:
        for index, part in enumerate(parts):
            desired_access = api.directory_access(writable=create)
            if writable and not create and index == len(parts) - 1:
                desired_access |= api.file_add_file
            next_handle = api.open_relative(
                handle,
                part,
                desired_access=desired_access,
                disposition=api.file_open_if if create else api.file_open,
                options=(
                    api.file_directory_file
                    | api.file_synchronous_io_nonalert
                    | api.file_open_reparse_point
                ),
                attributes=api.file_attribute_directory,
                relative=relative,
            )
            api.close_handle(handle)
            handle = next_handle
            current /= part
            api.require_directory(handle, relative)
            api.assert_path(handle, current, relative)
        api.assert_path(handle, current, relative)
        yield handle
    except (OSError, ValueError) as exc:
        if isinstance(exc, (FileNotFoundError, VaultPathSafetyError)):
            raise
        raise VaultPathSafetyError(
            relative,
            f"could not pin Vault parent for: {relative}",
        ) from exc
    finally:
        api.close_handle(handle)


@contextmanager
def _open_windows_regular_file(
    parent: int,
    name: str,
    relative: str,
) -> Iterator[BinaryIO]:
    import msvcrt

    api = _windows_native()
    handle = api.open_relative(
        parent,
        name,
        desired_access=api.generic_read | api.synchronize | api.file_read_attributes,
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
        descriptor = msvcrt.open_osfhandle(
            handle,
            os.O_RDONLY | getattr(os, "O_BINARY", 0),
        )
        handle = api.invalid_handle
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = -1
            yield stream
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if handle != api.invalid_handle:
            api.close_handle(handle)


def _windows_backup_handle(
    api: _WindowsNative,
    parent: int,
    source_handle: int,
    relative: str,
) -> str:
    rollback_name = f".ovm-{uuid.uuid4().hex}.rollback"
    rollback_handle = api.invalid_handle
    keep_rollback = False
    try:
        api.require_regular(source_handle, relative)
        rollback_handle = api.open_relative(
            parent,
            rollback_name,
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
        api.require_regular(rollback_handle, relative)
        api.copy_all(source_handle, rollback_handle, relative)
        keep_rollback = True
        return rollback_name
    finally:
        if rollback_handle != api.invalid_handle:
            if not keep_rollback:
                try:
                    api.mark_delete(rollback_handle, relative)
                except OSError:
                    pass
            api.close_handle(rollback_handle)


def _windows_backup_destination(
    api: _WindowsNative,
    parent: int,
    destination_name: str,
    relative: str,
) -> str | None:
    try:
        source_handle = api.open_relative(
            parent,
            destination_name,
            desired_access=(
                api.generic_read | api.synchronize | api.file_read_attributes
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
    except FileNotFoundError:
        return None

    try:
        api.require_regular(source_handle, relative)
        return _windows_backup_handle(
            api,
            parent,
            source_handle,
            relative,
        )
    finally:
        api.close_handle(source_handle)


def _windows_delete_named(
    api: _WindowsNative,
    parent: int,
    name: str,
    relative: str,
) -> None:
    try:
        handle = api.open_relative(
            parent,
            name,
            desired_access=api.delete | api.synchronize | api.file_read_attributes,
            disposition=api.file_open,
            options=(
                api.file_non_directory_file
                | api.file_synchronous_io_nonalert
                | api.file_open_reparse_point
            ),
            attributes=api.file_attribute_normal,
            relative=relative,
        )
    except FileNotFoundError:
        return
    try:
        api.require_regular(handle, relative)
        api.mark_delete(handle, relative)
    finally:
        api.close_handle(handle)


def _windows_restore_deleted_file(
    api: _WindowsNative,
    parent: int,
    rollback_name: str,
    destination_name: str,
    relative: str,
) -> None:
    rollback_handle = api.open_relative(
        parent,
        rollback_name,
        desired_access=api.delete | api.synchronize | api.file_read_attributes,
        disposition=api.file_open,
        options=(
            api.file_non_directory_file
            | api.file_synchronous_io_nonalert
            | api.file_open_reparse_point
        ),
        attributes=api.file_attribute_normal,
        relative=relative,
    )
    try:
        api.require_regular(rollback_handle, relative)
        api.rename_relative(
            rollback_handle,
            parent,
            destination_name,
            relative=relative,
            replace_if_exists=False,
        )
    finally:
        api.close_handle(rollback_handle)


def _windows_recreate_deleted_directory(
    api: _WindowsNative,
    parent: int,
    name: str,
    relative: str,
) -> None:
    handle = api.open_relative(
        parent,
        name,
        desired_access=api.directory_access(writable=False),
        disposition=api.file_create,
        options=(
            api.file_directory_file
            | api.file_synchronous_io_nonalert
            | api.file_open_reparse_point
        ),
        attributes=api.file_attribute_directory,
        relative=relative,
    )
    try:
        api.require_directory(handle, relative)
    finally:
        api.close_handle(handle)


def _windows_restore_unsafe_rename(
    api: _WindowsNative,
    moved_handle: int,
    source_parent: int,
    source_name: str,
    destination_parent: int,
    destination_name: str,
    rollback_name: str | None,
    relative: str,
) -> None:
    recovery_errors: list[BaseException] = []
    moved_back = False
    try:
        api.rename_relative(
            moved_handle,
            source_parent,
            source_name,
            relative=relative,
        )
        moved_back = True
    except BaseException as exc:
        recovery_errors.append(exc)

    if rollback_name is not None:
        try:
            rollback_handle = api.open_relative(
                destination_parent,
                rollback_name,
                desired_access=(
                    api.delete | api.synchronize | api.file_read_attributes
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
            try:
                api.require_regular(rollback_handle, relative)
                api.rename_relative(
                    rollback_handle,
                    destination_parent,
                    destination_name,
                    relative=relative,
                )
            finally:
                api.close_handle(rollback_handle)
        except BaseException as exc:
            recovery_errors.append(exc)
    elif not moved_back:
        try:
            api.mark_delete(moved_handle, relative)
        except BaseException as exc:
            recovery_errors.append(exc)

    if recovery_errors:
        raise VaultPathSafetyError(
            relative,
            f"could not restore unsafe owned rename: {relative}",
        ) from recovery_errors[0]


def _windows_atomic_copy_stream(
    root: Path,
    relative: str,
    source: BinaryIO,
) -> None:
    parts = PurePosixPath(relative).parts
    api = _windows_native()
    with _open_windows_parent(
        root,
        parts[:-1],
        create=True,
        relative=relative,
    ) as parent:
        temporary_name = f".{parts[-1]}.{uuid.uuid4().hex}.tmp"
        handle = api.open_relative(
            parent,
            temporary_name,
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
        rollback_name: str | None = None
        renamed = False
        verified = False
        try:
            api.require_regular(handle, relative)
            api.write_all(handle, source, relative)
            rollback_name = _windows_backup_destination(
                api,
                parent,
                parts[-1],
                relative,
            )
            api.rename(
                handle,
                parent,
                parts[-1],
                expected_parent=root.joinpath(*parts[:-1]),
                relative=relative,
            )
            renamed = True
            try:
                api.assert_path(
                    parent,
                    root.joinpath(*parts[:-1]),
                    relative,
                )
            except BaseException:
                _windows_restore_unsafe_rename(
                    api,
                    handle,
                    parent,
                    temporary_name,
                    parent,
                    parts[-1],
                    rollback_name,
                    relative,
                )
                raise
            verified = True
        finally:
            if not verified:
                try:
                    api.mark_delete(handle, relative)
                except OSError:
                    pass
            if rollback_name is not None:
                if not renamed or verified:
                    try:
                        _windows_delete_named(
                            api,
                            parent,
                            rollback_name,
                            relative,
                        )
                    except OSError:
                        pass
            api.close_handle(handle)


def _windows_replace_relative(root: Path, source: str, destination: str) -> None:
    source_parts = PurePosixPath(source).parts
    destination_parts = PurePosixPath(destination).parts
    api = _windows_native()
    with _open_windows_parent(
        root,
        source_parts[:-1],
        create=False,
        relative=source,
        writable=True,
    ) as source_parent:
        source_handle = api.open_relative(
            source_parent,
            source_parts[-1],
            desired_access=api.delete | api.synchronize | api.file_read_attributes,
            disposition=api.file_open,
            options=(
                api.file_non_directory_file
                | api.file_synchronous_io_nonalert
                | api.file_open_reparse_point
            ),
            attributes=api.file_attribute_normal,
            relative=source,
        )
        try:
            api.require_regular(source_handle, source)
            with _open_windows_parent(
                root,
                destination_parts[:-1],
                create=True,
                relative=destination,
            ) as destination_parent:
                rollback_name = _windows_backup_destination(
                    api,
                    destination_parent,
                    destination_parts[-1],
                    destination,
                )
                renamed = False
                verified = False
                try:
                    api.assert_path(
                        source_parent,
                        root.joinpath(*source_parts[:-1]),
                        source,
                    )
                    api.rename(
                        source_handle,
                        destination_parent,
                        destination_parts[-1],
                        expected_parent=root.joinpath(*destination_parts[:-1]),
                        relative=destination,
                    )
                    renamed = True
                    try:
                        api.assert_path(
                            source_parent,
                            root.joinpath(*source_parts[:-1]),
                            source,
                        )
                        api.assert_path(
                            destination_parent,
                            root.joinpath(*destination_parts[:-1]),
                            destination,
                        )
                    except BaseException:
                        _windows_restore_unsafe_rename(
                            api,
                            source_handle,
                            source_parent,
                            source_parts[-1],
                            destination_parent,
                            destination_parts[-1],
                            rollback_name,
                            destination,
                        )
                        raise
                    verified = True
                finally:
                    if rollback_name is not None:
                        if not renamed or verified:
                            try:
                                _windows_delete_named(
                                    api,
                                    destination_parent,
                                    rollback_name,
                                    destination,
                                )
                            except OSError:
                                pass
        finally:
            api.close_handle(source_handle)


def _windows_unlink_relative(
    root: Path,
    relative: str,
    *,
    missing_ok: bool,
) -> None:
    parts = PurePosixPath(relative).parts
    api = _windows_native()
    try:
        with _open_windows_parent(
            root,
            parts[:-1],
            create=False,
            relative=relative,
            writable=True,
        ) as parent:
            rollback_name: str | None = None
            handle = api.invalid_handle
            delete_pending = False
            deleted = False
            try:
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
            except FileNotFoundError:
                if missing_ok:
                    return
                raise
            try:
                api.require_regular(handle, relative)
                rollback_name = _windows_backup_handle(
                    api,
                    parent,
                    handle,
                    relative,
                )
                expected_parent = root.joinpath(*parts[:-1])
                api.assert_path(parent, expected_parent, relative)
                api.mark_delete(handle, relative)
                delete_pending = True
                try:
                    api.assert_path(parent, expected_parent, relative)
                except BaseException:
                    recovery_errors: list[BaseException] = []
                    try:
                        api.clear_delete(handle, relative)
                        delete_pending = False
                    except BaseException as exc:
                        recovery_errors.append(exc)
                    api.close_handle(handle)
                    handle = api.invalid_handle
                    if delete_pending:
                        deleted = True
                        try:
                            _windows_restore_deleted_file(
                                api,
                                parent,
                                rollback_name,
                                parts[-1],
                                relative,
                            )
                            rollback_name = None
                            deleted = False
                        except BaseException as exc:
                            recovery_errors.append(exc)
                    if recovery_errors:
                        raise VaultPathSafetyError(
                            relative,
                            f"could not restore unsafe owned delete: {relative}",
                        ) from recovery_errors[0]
                    raise
                api.close_handle(handle)
                handle = api.invalid_handle
                delete_pending = False
                deleted = True
                try:
                    api.assert_path(parent, expected_parent, relative)
                except BaseException:
                    try:
                        _windows_restore_deleted_file(
                            api,
                            parent,
                            rollback_name,
                            parts[-1],
                            relative,
                        )
                        rollback_name = None
                        deleted = False
                    except BaseException as exc:
                        raise VaultPathSafetyError(
                            relative,
                            f"could not restore unsafe owned delete: {relative}",
                        ) from exc
                    raise
                _windows_delete_named(api, parent, rollback_name, relative)
                rollback_name = None
            finally:
                if handle != api.invalid_handle:
                    if delete_pending:
                        try:
                            api.clear_delete(handle, relative)
                            delete_pending = False
                        except OSError:
                            pass
                    api.close_handle(handle)
                if rollback_name is not None and not deleted:
                    try:
                        _windows_delete_named(
                            api,
                            parent,
                            rollback_name,
                            relative,
                        )
                    except OSError:
                        pass
    except FileNotFoundError:
        if missing_ok:
            return
        raise


def _windows_rmdir_relative(
    root: Path,
    relative: str,
    *,
    missing_ok: bool,
) -> None:
    parts = PurePosixPath(relative).parts
    api = _windows_native()
    try:
        with _open_windows_parent(
            root,
            parts[:-1],
            create=False,
            relative=relative,
            writable=True,
        ) as parent:
            handle = api.invalid_handle
            delete_pending = False
            deleted = False
            try:
                handle = api.open_relative(
                    parent,
                    parts[-1],
                    desired_access=(
                        api.delete | api.synchronize | api.file_read_attributes
                    ),
                    disposition=api.file_open,
                    options=(
                        api.file_directory_file
                        | api.file_synchronous_io_nonalert
                        | api.file_open_reparse_point
                    ),
                    attributes=api.file_attribute_directory,
                    relative=relative,
                )
            except FileNotFoundError:
                if missing_ok:
                    return
                raise
            try:
                api.require_directory(handle, relative)
                expected_parent = root.joinpath(*parts[:-1])
                api.assert_path(parent, expected_parent, relative)
                api.mark_delete(handle, relative)
                delete_pending = True
                try:
                    api.assert_path(parent, expected_parent, relative)
                except BaseException:
                    try:
                        api.clear_delete(handle, relative)
                        delete_pending = False
                    except BaseException as exc:
                        raise VaultPathSafetyError(
                            relative,
                            f"could not restore unsafe owned directory delete: {relative}",
                        ) from exc
                    raise
                api.close_handle(handle)
                handle = api.invalid_handle
                delete_pending = False
                deleted = True
                try:
                    api.assert_path(parent, expected_parent, relative)
                except BaseException:
                    try:
                        _windows_recreate_deleted_directory(
                            api,
                            parent,
                            parts[-1],
                            relative,
                        )
                        deleted = False
                    except BaseException as exc:
                        raise VaultPathSafetyError(
                            relative,
                            f"could not restore unsafe owned directory delete: {relative}",
                        ) from exc
                    raise
            finally:
                if handle != api.invalid_handle:
                    if delete_pending:
                        try:
                            api.clear_delete(handle, relative)
                            delete_pending = False
                        except OSError:
                            pass
                    api.close_handle(handle)
                if deleted:
                    # The directory was empty and deletion completed. A later
                    # lexical move happened after both handle-relative checks,
                    # so there is no operation left to compensate here.
                    deleted = False
    except FileNotFoundError:
        if missing_ok:
            return
        raise
