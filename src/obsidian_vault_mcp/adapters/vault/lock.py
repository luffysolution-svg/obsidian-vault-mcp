"""Portable exclusive lock files, including one lock per Zotero item."""

from __future__ import annotations

import json
import os
import socket
import time
import uuid
from pathlib import Path

from ...domain.errors import LockError, LockTimeoutError
from ...domain.paths import VaultPaths


class FileLock:
    def __init__(self, path: str | os.PathLike[str], *, timeout: float = 10.0, poll_interval: float = 0.05) -> None:
        if timeout < 0 or poll_interval <= 0:
            raise ValueError("timeout must be non-negative and poll_interval positive")
        self.path = Path(path)
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.token = uuid.uuid4().hex
        self.acquired = False

    def acquire(self) -> "FileLock":
        if self.acquired:
            return self
        self.path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + self.timeout
        payload = json.dumps(
            {"token": self.token, "pid": os.getpid(), "host": socket.gethostname(), "createdAt": time.time()},
            separators=(",", ":"),
        ).encode("utf-8")
        while True:
            descriptor = -1
            try:
                descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(descriptor, payload)
                os.fsync(descriptor)
                self.acquired = True
                return self
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise LockTimeoutError(f"timed out waiting for lock: {self.path}")
                time.sleep(min(self.poll_interval, max(0.0, deadline - time.monotonic())))
            except OSError as exc:
                raise LockError(f"could not acquire lock {self.path}: {exc}") from exc
            finally:
                if descriptor >= 0:
                    os.close(descriptor)

    def release(self) -> None:
        if not self.acquired:
            return
        try:
            current = json.loads(self.path.read_text(encoding="utf-8"))
            if current.get("token") != self.token:
                raise LockError(f"lock ownership changed before release: {self.path}")
            self.path.unlink()
            self.acquired = False
        except FileNotFoundError:
            self.acquired = False
        except (OSError, ValueError, AttributeError) as exc:
            raise LockError(f"could not release lock {self.path}: {exc}") from exc

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
        super().__init__(paths.resolve(paths.item_lock(zotero_key)), timeout=timeout, poll_interval=poll_interval)


class GlobalLock(FileLock):
    def __init__(self, vault_root: str | os.PathLike[str], name: str, *, timeout: float = 10.0) -> None:
        paths = VaultPaths(vault_root)
        super().__init__(paths.resolve(paths.global_lock(name)), timeout=timeout)
