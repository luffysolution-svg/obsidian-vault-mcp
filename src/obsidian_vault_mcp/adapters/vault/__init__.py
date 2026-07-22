"""Safe Vault filesystem adapters."""

from .atomic_writer import AtomicWriter, atomic_copy, atomic_replace, atomic_write_bytes, atomic_write_text
from .filesystem import VaultFileSystem, VaultFilesystem
from .lock import FileLock, GlobalLock, ItemLock

__all__ = [
    "AtomicWriter",
    "FileLock",
    "GlobalLock",
    "ItemLock",
    "VaultFileSystem",
    "VaultFilesystem",
    "atomic_copy",
    "atomic_replace",
    "atomic_write_bytes",
    "atomic_write_text",
]
