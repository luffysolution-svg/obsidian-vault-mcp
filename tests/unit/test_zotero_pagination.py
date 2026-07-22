from __future__ import annotations

import json
from collections import defaultdict
from urllib.parse import parse_qs, urlsplit

import pytest

from obsidian_vault_mcp.adapters.zotero.client import (
    TransportResponse,
    ZoteroClient,
    ZoteroHTTPError,
    ZoteroJSONError,
    ZoteroNetworkError,
)
from obsidian_vault_mcp.adapters.zotero.pagination import PaginationError, collect_items


class FakeTransport:
    def __init__(self, responder):
        self.responder = responder
        self.calls: list[tuple[str, dict[str, list[str]]]] = []

    def request(self, method, url, *, headers, timeout):
        del method, headers, timeout
        parsed = urlsplit(url)
        query = parse_qs(parsed.query)
        self.calls.append((parsed.path, query))
        result = self.responder(parsed.path, query)
        if isinstance(result, TransportResponse):
            return result
        return TransportResponse(200, json.dumps(result).encode("utf-8"))


def _item(index: int, item_type: str = "journalArticle", **values):
    data = {
        "key": f"ITEM{index:04d}",
        "itemType": item_type,
        "title": f"Item {index}",
        **values,
    }
    return {"key": data["key"], "version": index + 1, "data": data}


def _slice(values, query):
    start = int(query["start"][0])
    limit = int(query["limit"][0])
    return values[start : start + limit]


def test_collection_items_returns_all_500_without_gaps_or_duplicates():
    records = [_item(index) for index in range(500)]

    def respond(path, query):
        assert path == "/api/users/0/collections/COLLECTION/items/top"
        return _slice(records, query)

    transport = FakeTransport(respond)
    client = ZoteroClient(transport=transport, page_size=100)

    items = client.list_collection_items("COLLECTION")

    assert len(items) == 500
    assert [item["key"] for item in items] == [f"ITEM{index:04d}" for index in range(500)]
    assert [int(query["start"][0]) for _path, query in transport.calls] == [0, 100, 200, 300, 400, 500]
    assert {int(query["limit"][0]) for _path, query in transport.calls} == {100}


def test_search_collections_children_annotations_and_attachments_share_pagination():
    search = [_item(index) for index in range(205)]
    collections = [
        {
            "key": f"COL{index:04d}",
            "data": {"key": f"COL{index:04d}", "name": f"Collection {index:04d}"},
            "meta": {"numItems": index},
        }
        for index in range(205)
    ]
    children = [_item(index, "note", note=f"<p>Note {index}</p>") for index in range(205)]
    annotations = [_item(index, "annotation", parentItem="PDF0001", annotationText=f"A{index}") for index in range(205)]
    attachments = [_item(index, "attachment", contentType="application/pdf", path=f"storage:paper-{index}.pdf") for index in range(205)]
    starts: dict[str, list[int]] = defaultdict(list)

    def respond(path, query):
        item_type = query.get("itemType", [""])[0]
        route = f"{path}|{item_type}"
        starts[route].append(int(query["start"][0]))
        if path == "/api/users/0/items/top":
            return _slice(search, query)
        if path == "/api/users/0/collections":
            return _slice(collections, query)
        if path == "/api/users/0/items/PARENT/children":
            return _slice(children, query)
        if item_type == "annotation":
            return _slice(annotations, query)
        if item_type == "attachment":
            return _slice(attachments, query)
        raise AssertionError(f"unexpected route: {route}")

    client = ZoteroClient(transport=FakeTransport(respond), page_size=100)

    assert len(client.search_items("paper")) == 205
    assert len(client.list_collections()) == 205
    assert len(client.get_children("PARENT")["notes"]) == 205
    assert len(client.list_annotations()) == 205
    assert len(client.list_attachments()) == 205

    assert set(starts) == {
        "/api/users/0/items/top|",
        "/api/users/0/collections|",
        "/api/users/0/items/PARENT/children|",
        "/api/users/0/items|annotation",
        "/api/users/0/items|attachment",
    }
    assert all(offsets == [0, 100, 200] for offsets in starts.values())


def test_get_children_paginates_direct_children_and_nested_annotations(tmp_path):
    attachments = [
        _item(
            index,
            "attachment",
            parentItem="PARENT",
            contentType="application/pdf",
            path=f"storage:paper-{index}.pdf",
        )
        for index in range(150)
    ]
    annotations = [
        _item(
            1000 + index,
            "annotation",
            parentItem=f"ITEM{index % 150:04d}",
            annotationText=f"Annotation {index}",
        )
        for index in range(250)
    ]

    def respond(path, query):
        if path == "/api/users/0/items/PARENT/children":
            return _slice(attachments, query)
        if path == "/api/users/0/items" and query.get("itemType") == ["annotation"]:
            return _slice(annotations, query)
        raise AssertionError(f"unexpected route: {path} {query}")

    client = ZoteroClient(
        transport=FakeTransport(respond),
        page_size=100,
        storage_dir=tmp_path / "Zotero storage",
    )
    result = client.get_children("PARENT")

    assert result["parentKey"] == "PARENT"
    assert len(result["attachments"]) == 150
    assert len(result["annotations"]) == 250
    assert len({item["key"] for item in result["annotations"]}) == 250
    serialized = json.dumps(result)
    assert str(tmp_path) not in serialized
    assert "attachmentPath" not in serialized
    assert "rawData" not in serialized
    assert client.resolve_attachment_source("ITEM0000") == (tmp_path / "Zotero storage" / "ITEM0000" / "paper-0.pdf").resolve()


def test_generic_paginator_rejects_repeated_item_identity():
    def fetch(start, limit):
        del limit
        if start == 0:
            return [{"key": "A"}, {"key": "B"}]
        return [{"key": "B"}]

    with pytest.raises(PaginationError) as error:
        collect_items(fetch, limit=2, identity=lambda item: item["key"])

    assert error.value.as_dict()["code"] == "duplicate_page_item"


def test_network_http_and_json_failures_are_structured():
    class BrokenTransport:
        def request(self, method, url, *, headers, timeout):
            del method, url, headers, timeout
            raise OSError("connection refused")

    with pytest.raises(ZoteroNetworkError) as network:
        ZoteroClient(transport=BrokenTransport()).search_items()
    assert network.value.as_dict()["code"] == "network_error"
    assert network.value.as_dict()["operation"] == "zotero_search_items"

    unavailable = FakeTransport(lambda path, query: TransportResponse(503, b"offline"))
    with pytest.raises(ZoteroHTTPError) as http:
        ZoteroClient(transport=unavailable).list_collections()
    assert http.value.as_dict()["status"] == 503

    invalid_json = FakeTransport(lambda path, query: TransportResponse(200, b"not-json"))
    with pytest.raises(ZoteroJSONError) as json_error:
        ZoteroClient(transport=invalid_json).list_annotations()
    assert json_error.value.as_dict()["code"] == "invalid_json"
    assert json_error.value.as_dict()["details"]["responseBytes"] == 8
