"""Zotero local API adapter with complete pagination and typed failures."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, TypeAlias
from urllib.error import HTTPError
from urllib.parse import unquote, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from ...domain.errors import ObsidianVaultMcpError
from .bibtex import (
    BibTeXError,
    BibTeXResult,
    generate_builtin_bibtex,
    is_bibtex,
    sanitize_bibtex,
)
from .pagination import iter_items

DEFAULT_API_BASE = "http://127.0.0.1:23119/api"
DEFAULT_PAGE_SIZE = 100
DEFAULT_TIMEOUT = 10.0
_YEAR_RE = re.compile(r"(?<!\d)(\d{4})(?!\d)")
_CITATION_KEY_RE = re.compile(r"(?im)^\s*citation\s+key\s*:\s*(\S+)\s*$")


@dataclass(frozen=True)
class TransportResponse:
    """Minimal response contract used by injectable HTTP transports."""

    status: int
    body: bytes
    headers: Mapping[str, str] = field(default_factory=dict)


class HttpTransport(Protocol):
    """Protocol implemented by test and production HTTP transports."""

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        timeout: float,
    ) -> TransportResponse:
        """Perform one HTTP request."""


TransportCallable: TypeAlias = Callable[..., TransportResponse]


class UrllibTransport:
    """Standard-library transport used unless a caller injects another one."""

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        timeout: float,
    ) -> TransportResponse:
        request = Request(url, method=method, headers=dict(headers))
        try:
            with urlopen(request, timeout=timeout) as response:  # noqa: S310 - user-configured local Zotero endpoint
                return TransportResponse(
                    status=int(response.status),
                    body=response.read(),
                    headers=dict(response.headers.items()),
                )
        except HTTPError as exc:
            return TransportResponse(
                status=int(exc.code),
                body=exc.read(),
                headers=dict(exc.headers.items()) if exc.headers is not None else {},
            )


class ZoteroClientError(ObsidianVaultMcpError):
    """Base class for structured Zotero adapter failures."""

    def __init__(
        self,
        message: str,
        *,
        code: str,
        operation: str,
        url: str = "",
        status: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.operation = operation
        self.url = url
        self.status = status
        self.details = details or {}

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable error payload."""

        return {
            "ok": False,
            "code": self.code,
            "message": str(self),
            "operation": self.operation,
            "url": self.url,
            "status": self.status,
            "details": dict(self.details),
        }


class ZoteroNetworkError(ZoteroClientError, OSError):
    """The configured Zotero endpoint could not be reached."""


class ZoteroHTTPError(ZoteroClientError):
    """Zotero returned a non-success HTTP status."""


class ZoteroJSONError(ZoteroClientError, ValueError):
    """A JSON endpoint returned invalid JSON or invalid text encoding."""


class ZoteroResponseError(ZoteroClientError, ValueError):
    """A decoded response did not match the Zotero API contract."""


class ZoteroClient:
    """Read-only Zotero adapter for the local Web API and Better BibTeX.

    Every multi-object method uses the same ``start``/``limit`` iterator. The
    optional ``transport`` is the sole HTTP seam needed by unit tests.
    """

    def __init__(
        self,
        api_base: str | None = None,
        *,
        page_size: int = DEFAULT_PAGE_SIZE,
        timeout: float = DEFAULT_TIMEOUT,
        transport: HttpTransport | TransportCallable | None = None,
        storage_dir: str | Path | None = None,
        bbt_base: str | None = None,
        bbt_library_id: int = 1,
    ) -> None:
        resolved_api_base = api_base or os.environ.get("ZOTERO_LOCAL_API") or DEFAULT_API_BASE
        if not isinstance(page_size, int) or page_size <= 0:
            raise ValueError("page_size must be a positive integer")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        if not isinstance(bbt_library_id, int) or bbt_library_id <= 0:
            raise ValueError("bbt_library_id must be a positive integer")

        self.api_base = resolved_api_base.rstrip("/")
        self.page_size = page_size
        self.timeout = float(timeout)
        self.transport = transport or UrllibTransport()
        configured_storage = storage_dir or os.environ.get("ZOTERO_STORAGE_DIR")
        self._storage_dir = Path(configured_storage).expanduser() if configured_storage else Path.home() / "Zotero" / "storage"
        self.bbt_base = (bbt_base or _origin(self.api_base)).rstrip("/")
        self.bbt_library_id = bbt_library_id
        self._attachment_paths: dict[str, Path] = {}

    def ping(self) -> dict[str, Any]:
        """Verify that the local API can return one JSON item."""

        payload = self._request_json(
            "users/0/items",
            {"format": "json", "start": 0, "limit": 1},
            operation="zotero_ping",
        )
        if not isinstance(payload, list):
            raise self._response_error(
                "Zotero ping expected a JSON list",
                operation="zotero_ping",
                response=payload,
            )
        return {"ok": True, "api": self.api_base, "sampleCount": len(payload)}

    def iter_search_items(
        self,
        query: str = "",
        *,
        item_type: str = "",
        tag: str = "",
        top: bool = True,
        limit: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Iterate every item matching a Zotero quick search."""

        params: dict[str, Any] = {"format": "json"}
        if query:
            params["q"] = query
        if item_type:
            params["itemType"] = item_type
        if tag:
            params["tag"] = tag
        path = "users/0/items/top" if top else "users/0/items"
        for raw_item in self._iter_endpoint(path, params, operation="zotero_search_items", limit=limit):
            yield self._normalize_item(raw_item)

    def search_items(
        self,
        query: str = "",
        *,
        item_type: str = "",
        tag: str = "",
        top: bool = True,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Return all items matching a Zotero quick search."""

        return list(
            self.iter_search_items(
                query,
                item_type=item_type,
                tag=tag,
                top=top,
                limit=limit,
            )
        )

    def iter_collections(self, *, limit: int | None = None) -> Iterator[dict[str, Any]]:
        """Iterate every Zotero collection."""

        for collection in self._iter_endpoint(
            "users/0/collections",
            {"format": "json"},
            operation="zotero_list_collections",
            limit=limit,
        ):
            yield self._normalize_collection(collection)

    def list_collections(self, *, limit: int | None = None) -> list[dict[str, Any]]:
        """Return every collection sorted by its human-readable name."""

        collections = list(self.iter_collections(limit=limit))
        collections.sort(key=lambda collection: str(collection.get("name") or "").casefold())
        return collections

    def iter_collection_items(
        self,
        collection_key: str,
        *,
        top: bool = True,
        limit: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Iterate every item in a collection without a 100-item cap."""

        suffix = "/top" if top else ""
        path = f"users/0/collections/{_path_key(collection_key)}/items{suffix}"
        for raw_item in self._iter_endpoint(
            path,
            {"format": "json"},
            operation="zotero_list_collection_items",
            limit=limit,
        ):
            yield self._normalize_item(raw_item)

    def list_collection_items(
        self,
        collection_key: str,
        *,
        top: bool = True,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Return every item in one collection."""

        return list(self.iter_collection_items(collection_key, top=top, limit=limit))

    def get_item(self, key: str) -> dict[str, Any]:
        """Return one normalized Zotero parent or child item."""

        payload = self._request_json(
            f"users/0/items/{_path_key(key)}",
            {"format": "json"},
            operation="zotero_get_item",
        )
        if not isinstance(payload, Mapping):
            raise self._response_error(
                "Zotero item endpoint expected a JSON object",
                operation="zotero_get_item",
                response=payload,
            )
        return self._normalize_item(payload)

    def get_children(
        self,
        parent_key: str,
        *,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Return normalized direct children and nested PDF annotations.

        Direct children are fully paginated. Zotero stores PDF annotations
        under attachment keys, so the global annotation query is independently
        paginated and filtered against every attachment returned above.
        """

        parent = _path_key(parent_key)
        direct_raw = list(
            self._iter_endpoint(
                f"users/0/items/{parent}/children",
                {"format": "json"},
                operation="zotero_get_children",
                limit=limit,
            )
        )
        direct = [self._normalize_item(item) for item in direct_raw]
        grouped: dict[str, Any] = {
            "parentKey": parent,
            "notes": [],
            "annotations": [],
            "attachments": [],
            "other": [],
        }
        annotation_keys: set[str] = set()
        attachment_keys: set[str] = set()
        for child in direct:
            item_type = child.get("itemType")
            if item_type == "note":
                grouped["notes"].append(child)
            elif item_type == "annotation":
                grouped["annotations"].append(child)
                annotation_keys.add(str(child.get("key") or ""))
            elif item_type == "attachment":
                grouped["attachments"].append(child)
                if child.get("key"):
                    attachment_keys.add(str(child["key"]))
            else:
                grouped["other"].append(child)

        if attachment_keys:
            for annotation in self.iter_annotations(limit=limit):
                if annotation.get("parentKey") not in attachment_keys:
                    continue
                annotation_key = str(annotation.get("key") or "")
                if annotation_key and annotation_key in annotation_keys:
                    continue
                grouped["annotations"].append(annotation)
                if annotation_key:
                    annotation_keys.add(annotation_key)
        return grouped

    def get_item_tree(self, key: str, *, limit: int | None = None) -> dict[str, Any]:
        """Return the canonical ``parent``/``children`` adapter payload."""

        parent = self.get_item(key)
        parent_key = str(parent.get("key") or _path_key(key))
        return {"parent": parent, "children": self.get_children(parent_key, limit=limit)}

    def iter_annotations(
        self,
        parent_key: str = "",
        *,
        limit: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Iterate all annotations, optionally those belonging to an item.

        For a bibliographic parent, both its direct annotations and annotations
        nested below any of its attachments are included.
        """

        if not parent_key:
            for raw_item in self._iter_endpoint(
                "users/0/items",
                {"format": "json", "itemType": "annotation"},
                operation="zotero_list_annotations",
                limit=limit,
            ):
                yield self._normalize_item(raw_item)
            return

        parent = _path_key(parent_key)
        direct = list(
            self._iter_endpoint(
                f"users/0/items/{parent}/children",
                {"format": "json"},
                operation="zotero_list_annotations",
                limit=limit,
            )
        )
        attachment_keys = {str(_raw_key(item)) for item in direct if _raw_item_type(item) == "attachment" and _raw_key(item)}
        emitted: set[str] = set()
        for raw_item in direct:
            if _raw_item_type(raw_item) != "annotation":
                continue
            normalized = self._normalize_item(raw_item)
            key = str(normalized.get("key") or "")
            if key:
                emitted.add(key)
            yield normalized
        if attachment_keys:
            for annotation in self.iter_annotations(limit=limit):
                if annotation.get("parentKey") not in attachment_keys:
                    continue
                key = str(annotation.get("key") or "")
                if key and key in emitted:
                    continue
                if key:
                    emitted.add(key)
                yield annotation

    def list_annotations(
        self,
        parent_key: str = "",
        *,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Return all annotations, optionally scoped to one parent item."""

        return list(self.iter_annotations(parent_key, limit=limit))

    def iter_attachments(
        self,
        parent_key: str = "",
        *,
        query: str = "",
        pdf_only: bool = False,
        limit: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Iterate every attachment globally or below one parent item."""

        params: dict[str, Any] = {"format": "json"}
        if parent_key:
            path = f"users/0/items/{_path_key(parent_key)}/children"
        else:
            path = "users/0/items"
            params["itemType"] = "attachment"
            if query:
                params["q"] = query
        for raw_item in self._iter_endpoint(
            path,
            params,
            operation="zotero_list_attachments",
            limit=limit,
        ):
            if _raw_item_type(raw_item) != "attachment":
                continue
            attachment = self._normalize_item(raw_item)
            if pdf_only and not _is_pdf_attachment(attachment):
                continue
            yield attachment

    def list_attachments(
        self,
        parent_key: str = "",
        *,
        query: str = "",
        pdf_only: bool = False,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Return every attachment globally or below one parent item."""

        return list(
            self.iter_attachments(
                parent_key,
                query=query,
                pdf_only=pdf_only,
                limit=limit,
            )
        )

    def get_bibtex(
        self,
        key: str,
        *,
        item: Mapping[str, Any] | None = None,
        provider: str = "auto",
        fallback: bool = True,
    ) -> BibTeXResult:
        """Return BibTeX in Better BibTeX -> Zotero export -> builtin order.

        Provider failures remain available in ``BibTeXResult.errors`` when a
        later provider succeeds; they are never silently discarded.
        """

        metadata = dict(item) if item is not None else self.get_item(key)
        normalized_provider = provider.strip().lower().replace("_", "-")
        if normalized_provider in {"auto", ""}:
            providers = ("better-bibtex", "zotero-export", "builtin")
        elif normalized_provider in {"better-bibtex", "bbt"}:
            providers = ("better-bibtex", "builtin") if fallback else ("better-bibtex",)
        elif normalized_provider in {"zotero", "zotero-export"}:
            providers = ("zotero-export", "builtin") if fallback else ("zotero-export",)
        elif normalized_provider == "builtin":
            providers = ("builtin",)
        else:
            raise BibTeXError(
                f"unsupported BibTeX provider: {provider}",
                code="unsupported_bibtex_provider",
                provider=normalized_provider,
            )

        errors: list[dict[str, Any]] = []
        for candidate in providers:
            try:
                if candidate == "better-bibtex":
                    bibtex = self._better_bibtex(metadata)
                elif candidate == "zotero-export":
                    bibtex = self._zotero_bibtex_export(key)
                else:
                    bibtex = generate_builtin_bibtex(metadata)
                bibtex = sanitize_bibtex(bibtex)
                if not is_bibtex(bibtex):
                    raise BibTeXError(
                        f"{candidate} returned text without a BibTeX entry",
                        code="invalid_bibtex_response",
                        provider=candidate,
                    )
                return BibTeXResult(
                    provider=candidate,
                    bibtex=bibtex.strip(),
                    errors=tuple(errors),
                )
            except (ZoteroClientError, BibTeXError) as exc:
                error = exc.as_dict()
                error["provider"] = candidate
                errors.append(error)

        raise BibTeXError(
            "all configured BibTeX providers failed",
            code="all_bibtex_providers_failed",
            provider=normalized_provider or "auto",
            details={"errors": errors},
        )

    def _better_bibtex(self, item: Mapping[str, Any]) -> str:
        citation_key = str(item.get("citationKey") or item.get("citekey") or "").strip()
        if not citation_key:
            extra = str(item.get("extra") or "")
            match = _CITATION_KEY_RE.search(extra)
            citation_key = match.group(1) if match else ""
        if not citation_key:
            raise BibTeXError(
                "Better BibTeX export requires a citation key",
                code="missing_citation_key",
                provider="better-bibtex",
            )
        return self._request_text(
            "better-bibtex/export/item",
            {
                "libraryID": self.bbt_library_id,
                "citationKeys": citation_key,
                "translator": "bibtex",
            },
            operation="zotero_get_bibtex_better_bibtex",
            base=self.bbt_base,
        )

    def _zotero_bibtex_export(self, key: str) -> str:
        return self._request_text(
            f"users/0/items/{_path_key(key)}",
            {"format": "bibtex"},
            operation="zotero_get_bibtex_export",
        )

    def _iter_endpoint(
        self,
        path: str,
        params: Mapping[str, Any],
        *,
        operation: str,
        limit: int | None,
    ) -> Iterator[Mapping[str, Any]]:
        page_limit = self.page_size if limit is None else limit

        def fetch_page(start: int, requested_limit: int) -> Sequence[Mapping[str, Any]]:
            page_params = dict(params)
            page_params["start"] = start
            page_params["limit"] = requested_limit
            payload = self._request_json(path, page_params, operation=operation)
            if not isinstance(payload, list):
                raise self._response_error(
                    "paginated Zotero endpoint expected a JSON list",
                    operation=operation,
                    response=payload,
                )
            if not all(isinstance(item, Mapping) for item in payload):
                raise self._response_error(
                    "paginated Zotero endpoint returned a non-object item",
                    operation=operation,
                    response=payload,
                )
            return payload

        yield from iter_items(
            fetch_page,
            start=0,
            limit=page_limit,
            identity=lambda item: _raw_key(item),
        )

    def _request_json(
        self,
        path: str,
        params: Mapping[str, Any],
        *,
        operation: str,
    ) -> Any:
        response, url = self._send(path, params, operation=operation)
        try:
            text = response.body.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ZoteroJSONError(
                "Zotero JSON response is not valid UTF-8",
                code="invalid_json_encoding",
                operation=operation,
                url=url,
                status=response.status,
                details={"responseBytes": len(response.body)},
            ) from exc
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise ZoteroJSONError(
                "Zotero returned invalid JSON",
                code="invalid_json",
                operation=operation,
                url=url,
                status=response.status,
                details={
                    "line": exc.lineno,
                    "column": exc.colno,
                    "responseBytes": len(response.body),
                },
            ) from exc

    def _request_text(
        self,
        path: str,
        params: Mapping[str, Any],
        *,
        operation: str,
        base: str | None = None,
    ) -> str:
        response, url = self._send(path, params, operation=operation, base=base)
        try:
            return response.body.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ZoteroResponseError(
                "Zotero text response is not valid UTF-8",
                code="invalid_text_encoding",
                operation=operation,
                url=url,
                status=response.status,
                details={"responseBytes": len(response.body)},
            ) from exc

    def _send(
        self,
        path: str,
        params: Mapping[str, Any],
        *,
        operation: str,
        base: str | None = None,
    ) -> tuple[TransportResponse, str]:
        url = _build_url(base or self.api_base, path, params)
        headers = {"Accept": "application/json", "Zotero-API-Version": "3"}
        try:
            request_method = getattr(self.transport, "request", None)
            if request_method is not None:
                response = request_method("GET", url, headers=headers, timeout=self.timeout)
            elif callable(self.transport):
                response = self.transport("GET", url, headers=headers, timeout=self.timeout)
            else:
                raise TypeError("transport must be callable or provide request()")
        except ZoteroClientError:
            raise
        except Exception as exc:
            raise ZoteroNetworkError(
                "could not reach the Zotero HTTP endpoint",
                code="network_error",
                operation=operation,
                url=url,
                details={"exceptionType": type(exc).__name__, "reason": str(exc)},
            ) from exc
        if not isinstance(response, TransportResponse):
            raise ZoteroResponseError(
                "HTTP transport returned an invalid response object",
                code="invalid_transport_response",
                operation=operation,
                url=url,
                details={"responseType": type(response).__name__},
            )
        if response.status < 200 or response.status >= 300:
            raise ZoteroHTTPError(
                f"Zotero HTTP request failed with status {response.status}",
                code="http_error",
                operation=operation,
                url=url,
                status=response.status,
                details={"responseBytes": len(response.body)},
            )
        return response, url

    def _response_error(
        self,
        message: str,
        *,
        operation: str,
        response: Any,
    ) -> ZoteroResponseError:
        return ZoteroResponseError(
            message,
            code="invalid_response_shape",
            operation=operation,
            details={"responseType": type(response).__name__},
        )

    def _normalize_item(self, item: Mapping[str, Any]) -> dict[str, Any]:
        data_value = item.get("data")
        data = data_value if isinstance(data_value, Mapping) else item
        key = str(item.get("key") or data.get("key") or "").strip()
        if not key:
            raise self._response_error(
                "Zotero item is missing its key",
                operation="zotero_normalize_item",
                response=item,
            )

        item_type = str(data.get("itemType") or "")
        creators = _normalize_creators(data.get("creators"))
        tags = _normalize_tags(data.get("tags"))
        citation_key = str(data.get("citationKey") or data.get("citekey") or "").strip()
        if not citation_key:
            match = _CITATION_KEY_RE.search(str(data.get("extra") or ""))
            citation_key = match.group(1) if match else ""

        normalized: dict[str, Any] = {
            "key": key,
            "version": item.get("version") or data.get("version"),
            "itemType": item_type,
            "title": data.get("title") or "",
            "date": data.get("date") or "",
            "year": _extract_year(data.get("date")),
            "creators": creators,
            "publicationTitle": data.get("publicationTitle") or data.get("conferenceName") or "",
            "journal": data.get("publicationTitle") or "",
            "doi": data.get("DOI") or data.get("doi") or "",
            "url": data.get("url") or "",
            "abstract": data.get("abstractNote") or data.get("abstract") or "",
            "tags": tags,
            "collections": _string_list(data.get("collections")),
            "relations": _normalize_relations(data.get("relations")),
            "citationKey": citation_key,
            "language": data.get("language") or "",
            "parentKey": data.get("parentItem") or "",
            "zoteroSelectLink": f"zotero://select/library/items/{key}",
        }
        passthrough_fields = (
            "volume",
            "issue",
            "pages",
            "publisher",
            "ISBN",
            "journalAbbreviation",
            "conferenceName",
            "proceedingsTitle",
            "bookTitle",
            "university",
            "thesisType",
            "patentNumber",
            "applicationNumber",
            "assignee",
            "country",
            "reportNumber",
            "reportType",
            "institution",
            "place",
            "edition",
            "numPages",
            "series",
            "repository",
            "archive",
            "archiveID",
            "archiveLocation",
            "language",
        )
        for field_name in passthrough_fields:
            value = data.get(field_name)
            if value not in (None, "", [], {}):
                normalized[field_name] = value

        if item_type == "note":
            normalized["note"] = _plain_note(data.get("note"))
        elif item_type == "annotation":
            for field_name in (
                "annotationText",
                "annotationComment",
                "annotationType",
                "annotationColor",
                "annotationPageLabel",
                "annotationPosition",
            ):
                normalized[field_name] = data.get(field_name) or ""
        elif item_type == "attachment":
            raw_path = _raw_attachment_path(item, data)
            self._remember_attachment_path(key, raw_path)
            filename = str(data.get("filename") or "").strip()
            if not filename and raw_path:
                filename = raw_path.replace("\\", "/").rsplit("/", 1)[-1]
                if filename.startswith("storage:"):
                    filename = filename.removeprefix("storage:")
            normalized.update(
                {
                    "filename": filename,
                    "contentType": data.get("contentType") or "",
                    "linkMode": data.get("linkMode") or "",
                    "md5": data.get("md5") or "",
                    "mtime": data.get("mtime"),
                }
            )
            if _is_pdf_attachment(normalized):
                normalized["zoteroPdfLink"] = f"zotero://open-pdf/library/items/{key}"
        return normalized

    def _normalize_collection(self, collection: Mapping[str, Any]) -> dict[str, Any]:
        data_value = collection.get("data")
        data = data_value if isinstance(data_value, Mapping) else collection
        meta_value = collection.get("meta")
        meta = meta_value if isinstance(meta_value, Mapping) else {}
        key = str(collection.get("key") or data.get("key") or "").strip()
        if not key:
            raise self._response_error(
                "Zotero collection is missing its key",
                operation="zotero_normalize_collection",
                response=collection,
            )
        return {
            "key": key,
            "version": collection.get("version") or data.get("version"),
            "name": data.get("name") or "",
            "parentKey": data.get("parentCollection") or None,
            "numItems": meta.get("numItems", 0),
        }

    def _remember_attachment_path(self, key: str, raw_path: str) -> None:
        if not raw_path:
            return
        if raw_path.startswith("storage:"):
            relative_name = raw_path.removeprefix("storage:").replace("\\", "/").lstrip("/")
            self._attachment_paths[key] = (self._storage_dir / key / relative_name).resolve(strict=False)
            return
        if raw_path.startswith("file:"):
            parsed = urlsplit(raw_path)
            if parsed.netloc:
                path = Path(f"//{parsed.netloc}{unquote(parsed.path)}")
            else:
                decoded = unquote(parsed.path)
                if re.match(r"^/[A-Za-z]:/", decoded):
                    decoded = decoded[1:]
                path = Path(decoded)
        else:
            path = Path(raw_path).expanduser()
        if path.is_absolute():
            self._attachment_paths[key] = path.resolve(strict=False)

    def resolve_attachment_source(
        self,
        attachment_or_key: Mapping[str, Any] | str,
    ) -> Path | None:
        """Resolve an attachment source for internal application operations.

        This is intentionally a Python-only adapter boundary: callers may use
        the returned absolute ``Path`` to copy the file, but must never place it
        in a user-facing dictionary, Markdown document or ``to_dict`` payload.
        A cache miss by key performs one item lookup so application services do
        not need access to private normalization state.
        """

        if isinstance(attachment_or_key, Mapping):
            key_value = _raw_key(attachment_or_key)
            if not key_value:
                return None
            key = str(key_value)
            data_value = attachment_or_key.get("data")
            data = data_value if isinstance(data_value, Mapping) else attachment_or_key
            raw_path = _raw_attachment_path(attachment_or_key, data)
            if raw_path:
                self._remember_attachment_path(key, raw_path)
        else:
            key = _path_key(attachment_or_key)

        cached = self._attachment_paths.get(key)
        if cached is not None:
            return cached
        item = self.get_item(key)
        if item.get("itemType") != "attachment":
            return None
        return self._attachment_paths.get(key)

    def _attachment_source_path(self, key: str) -> Path | None:
        """Return a cached source path for internal adapter/application use."""

        return self._attachment_paths.get(key)


def _build_url(base: str, path: str, params: Mapping[str, Any]) -> str:
    pairs: list[tuple[str, Any]] = []
    for key, value in params.items():
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            pairs.extend((key, element) for element in value)
        else:
            pairs.append((key, value))
    query = urlencode(pairs, doseq=True)
    url = f"{base.rstrip('/')}/{path.lstrip('/')}"
    return f"{url}?{query}" if query else url


def _origin(url: str) -> str:
    parts = urlsplit(url)
    if not parts.scheme or not parts.netloc:
        raise ValueError("api_base must be an absolute HTTP URL")
    return urlunsplit((parts.scheme, parts.netloc, "", "", ""))


def _path_key(key: str) -> str:
    normalized = str(key).strip()
    if not normalized or "/" in normalized or "\\" in normalized or normalized in {".", ".."}:
        raise ValueError("Zotero key must be a non-empty path-safe value")
    return normalized


def _raw_key(item: Mapping[str, Any]) -> str | None:
    data = item.get("data")
    data_key = data.get("key") if isinstance(data, Mapping) else None
    value = item.get("key") or data_key
    return str(value) if value else None


def _raw_item_type(item: Mapping[str, Any]) -> str:
    data = item.get("data")
    if isinstance(data, Mapping):
        return str(data.get("itemType") or "")
    return str(item.get("itemType") or "")


def _raw_attachment_path(item: Mapping[str, Any], data: Mapping[str, Any]) -> str:
    direct = str(data.get("path") or "").strip()
    if direct:
        return direct
    links = item.get("links")
    if not isinstance(links, Mapping):
        return ""
    enclosure = links.get("enclosure")
    if not isinstance(enclosure, Mapping):
        return ""
    href = enclosure.get("href")
    return str(href).strip() if href else ""


def _normalize_creators(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    creators: list[dict[str, str]] = []
    for creator in value:
        if not isinstance(creator, Mapping):
            continue
        normalized = {
            field_name: str(creator[field_name]) for field_name in ("creatorType", "firstName", "lastName", "name") if creator.get(field_name) not in (None, "")
        }
        if normalized:
            creators.append(normalized)
    return creators


def _normalize_tags(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    tags: list[str] = []
    for tag in value:
        if isinstance(tag, Mapping):
            text = str(tag.get("tag") or "").strip()
        else:
            text = str(tag).strip()
        if text:
            tags.append(text)
    return tags


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [str(element) for element in value if element not in (None, "")]


def _normalize_relations(value: Any) -> list[str]:
    if not isinstance(value, Mapping):
        return []
    relation = value.get("dc:relation")
    if relation is None:
        return []
    if isinstance(relation, str):
        return [relation]
    return _string_list(relation)


def _extract_year(value: Any) -> str:
    match = _YEAR_RE.search(str(value or ""))
    return match.group(1) if match else ""


def _plain_note(value: Any) -> str:
    text = str(value or "")
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def _is_pdf_attachment(attachment: Mapping[str, Any]) -> bool:
    content_type = str(attachment.get("contentType") or "").lower()
    filename = str(attachment.get("filename") or "").lower()
    return content_type == "application/pdf" or filename.endswith(".pdf")
