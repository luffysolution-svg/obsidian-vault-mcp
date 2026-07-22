from __future__ import annotations

from typing import Any

from .import_service import ImportService


class SyncService(ImportService):
    """Incremental sync uses the import pipeline but requires existing identity."""

    def sync_item(self, zotero_key: str, **kwargs: Any) -> dict[str, Any]:
        return self.import_item(zotero_key, require_existing=True, **kwargs)

    def sync_collection(self, collection_key: str, **kwargs: Any) -> dict[str, Any]:
        return self.import_collection(collection_key, require_existing=True, **kwargs)
