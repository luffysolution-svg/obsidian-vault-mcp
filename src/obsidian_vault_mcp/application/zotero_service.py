from __future__ import annotations

from typing import Any

from ..adapters.zotero.client import ZoteroClient


class ZoteroQueryService:
    """Read-only Zotero use cases shared by CLI and MCP adapters."""

    def __init__(self, api_base: str = "", *, client: ZoteroClient | Any | None = None) -> None:
        self.client = client or (ZoteroClient(api_base=api_base) if api_base else ZoteroClient())

    def ping(self) -> dict[str, Any]:
        return self.client.ping()

    def search_items(self, *, query: str = "", item_type: str = "", tag: str = "") -> list[dict[str, Any]]:
        return self.client.search_items(query=query, item_type=item_type, tag=tag)

    def list_collections(self) -> list[dict[str, Any]]:
        return self.client.list_collections()

    def get_item(self, key: str) -> dict[str, Any]:
        return self.client.get_item(key)

    def get_children(self, parent_key: str) -> dict[str, Any]:
        return self.client.get_children(parent_key)

    def get_bibtex(self, key: str, *, provider: str = "auto") -> dict[str, Any]:
        return self.client.get_bibtex(key, provider=provider).to_dict()
