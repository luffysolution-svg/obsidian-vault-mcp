"""Small domain models shared by application services and adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from .identity import item_id, validate_zotero_key
from .paths import normalize_vault_relative


class ChangeAction(str, Enum):
    CREATE = "create"
    REPLACE = "replace"
    DELETE = "delete"
    NOOP = "noop"


@dataclass(frozen=True)
class ZoteroItem:
    """Normalized metadata for one Zotero parent item."""

    zotero_key: str
    title: str
    item_type: str = ""
    year: int | None = None
    journal: str = ""
    tags: tuple[str, ...] = ()
    doi: str = ""
    url: str = ""
    abstract: str = ""
    zotero_pdf_link: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "zotero_key", validate_zotero_key(self.zotero_key))
        object.__setattr__(self, "tags", tuple(self.tags))

    @property
    def item_id(self) -> str:
        return item_id(self.zotero_key)

    def managed_frontmatter(self) -> dict[str, Any]:
        """Return plugin-managed fields; empty values are omitted by the renderer."""

        return {
            "title": self.title,
            "itemType": self.item_type,
            "year": self.year,
            "journal": self.journal,
            "tags": list(self.tags),
            "doi": self.doi,
            "url": self.url,
            "abstract": self.abstract,
            "zoteroKey": self.zotero_key,
            "zoteroPdfLink": self.zotero_pdf_link,
        }


@dataclass(frozen=True)
class AssetPaths:
    """Vault-relative assets belonging to one stable item."""

    note: str
    pdf: str = ""
    mineru_markdown: str = ""
    mineru_images: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "note", normalize_vault_relative(self.note))
        if self.pdf:
            object.__setattr__(self, "pdf", normalize_vault_relative(self.pdf))
        if self.mineru_markdown:
            object.__setattr__(
                self,
                "mineru_markdown",
                normalize_vault_relative(self.mineru_markdown),
            )
        object.__setattr__(
            self,
            "mineru_images",
            tuple(normalize_vault_relative(path) for path in self.mineru_images),
        )


@dataclass(frozen=True)
class FileChange:
    """Preview information for one transaction destination."""

    path: str
    action: ChangeAction
    before_sha256: str | None = None
    after_sha256: str | None = None
    size: int = 0
    diff: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "action": self.action.value,
            "changed": self.action is not ChangeAction.NOOP,
            "beforeSha256": self.before_sha256,
            "afterSha256": self.after_sha256,
            "bytes": self.size,
            "diff": self.diff,
        }


@dataclass
class ItemState:
    """Internal, hidden synchronization state for one item."""

    zotero_key: str
    zotero_version: int | None = None
    note_path: str = ""
    pdf_path: str = ""
    mineru_path: str = ""
    collection_keys: list[str] = field(default_factory=list)
    source_pdf_path: str = ""
    source_pdf_sha256: str = ""
    copied_pdf_sha256: str = ""
    mineru_source_sha256: str = ""
    last_imported_at: str = ""
    last_mineru_at: str = ""
    last_transaction_id: str = ""
    status: str = "pending"
    errors: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.zotero_key = validate_zotero_key(self.zotero_key)
        for name in ("note_path", "pdf_path", "mineru_path"):
            value = getattr(self, name)
            if value:
                setattr(self, name, normalize_vault_relative(value))
        self.collection_keys = sorted(
            set(str(value) for value in self.collection_keys if str(value))
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": 2,
            "zoteroKey": self.zotero_key,
            "zoteroVersion": self.zotero_version,
            "notePath": self.note_path or None,
            "pdfPath": self.pdf_path or None,
            "mineruPath": self.mineru_path or None,
            "collectionKeys": self.collection_keys,
            "sourcePdfPath": self.source_pdf_path or None,
            "sourcePdfSha256": self.source_pdf_sha256 or None,
            "copiedPdfSha256": self.copied_pdf_sha256 or None,
            "mineruSourceSha256": self.mineru_source_sha256 or None,
            "lastImportedAt": self.last_imported_at or None,
            "lastMineruAt": self.last_mineru_at or None,
            "lastTransactionId": self.last_transaction_id or None,
            "status": self.status,
            "errors": self.errors,
        }

    @staticmethod
    def utc_now() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


LiteratureItem = ZoteroItem
