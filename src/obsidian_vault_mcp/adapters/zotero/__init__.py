"""Explicit public API for the Zotero adapter."""

from .bibtex import (
    BibTeXError,
    BibTeXResult,
    build_builtin_bibtex,
    generate_builtin_bibtex,
    is_bibtex,
)
from .client import (
    DEFAULT_API_BASE,
    DEFAULT_PAGE_SIZE,
    DEFAULT_TIMEOUT,
    HttpTransport,
    TransportCallable,
    TransportResponse,
    UrllibTransport,
    ZoteroClient,
    ZoteroClientError,
    ZoteroHTTPError,
    ZoteroJSONError,
    ZoteroNetworkError,
    ZoteroResponseError,
)
from .pagination import Page, PaginationError, collect_items, iter_items, iter_pages

__all__ = [
    "DEFAULT_API_BASE",
    "DEFAULT_PAGE_SIZE",
    "DEFAULT_TIMEOUT",
    "BibTeXError",
    "BibTeXResult",
    "HttpTransport",
    "Page",
    "PaginationError",
    "TransportCallable",
    "TransportResponse",
    "UrllibTransport",
    "ZoteroClient",
    "ZoteroClientError",
    "ZoteroHTTPError",
    "ZoteroJSONError",
    "ZoteroNetworkError",
    "ZoteroResponseError",
    "build_builtin_bibtex",
    "collect_items",
    "generate_builtin_bibtex",
    "is_bibtex",
    "iter_items",
    "iter_pages",
]
