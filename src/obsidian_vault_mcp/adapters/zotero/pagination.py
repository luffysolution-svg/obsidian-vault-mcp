"""Shared ``start``/``limit`` pagination for Zotero list endpoints."""

from __future__ import annotations

from collections.abc import Callable, Hashable, Iterator, Sequence
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

T = TypeVar("T")


class PaginationError(RuntimeError):
    """Raised when a paginated endpoint cannot make safe forward progress."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "pagination_error",
        start: int | None = None,
        limit: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.start = start
        self.limit = limit
        self.details = details or {}

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable error payload."""

        return {
            "ok": False,
            "code": self.code,
            "message": str(self),
            "start": self.start,
            "limit": self.limit,
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class Page(Generic[T]):
    """One page returned by a ``start``/``limit`` endpoint."""

    start: int
    limit: int
    items: tuple[T, ...]

    @property
    def next_start(self) -> int:
        """Return the offset immediately following this page."""

        return self.start + len(self.items)

    @property
    def exhausted(self) -> bool:
        """Whether a short page proves the endpoint is exhausted."""

        return len(self.items) < self.limit


PageFetcher = Callable[[int, int], Sequence[T]]
Identity = Callable[[T], Hashable | None]


def iter_pages(
    fetch_page: PageFetcher[T],
    *,
    start: int = 0,
    limit: int = 100,
    identity: Identity[T] | None = None,
) -> Iterator[Page[T]]:
    """Yield every page until an empty or short page is returned.

    The next offset advances by the number of records actually returned, not
    by the requested limit.  When ``identity`` is supplied, a repeated object
    is treated as a protocol error instead of being silently emitted twice.
    """

    if not isinstance(start, int) or start < 0:
        raise PaginationError(
            "pagination start must be a non-negative integer",
            code="invalid_pagination_start",
            start=start if isinstance(start, int) else None,
            limit=limit if isinstance(limit, int) else None,
        )
    if not isinstance(limit, int) or limit <= 0:
        raise PaginationError(
            "pagination limit must be a positive integer",
            code="invalid_pagination_limit",
            start=start,
            limit=limit if isinstance(limit, int) else None,
        )

    offset = start
    seen: set[Hashable] = set()
    while True:
        raw_items = fetch_page(offset, limit)
        if isinstance(raw_items, (str, bytes, bytearray)) or not isinstance(raw_items, Sequence):
            raise PaginationError(
                "paginated endpoint must return a sequence of items",
                code="invalid_page",
                start=offset,
                limit=limit,
                details={"responseType": type(raw_items).__name__},
            )

        items = tuple(raw_items)
        if len(items) > limit:
            raise PaginationError(
                "paginated endpoint returned more items than requested",
                code="oversized_page",
                start=offset,
                limit=limit,
                details={"itemCount": len(items)},
            )

        if identity is not None:
            page_identities: set[Hashable] = set()
            for item in items:
                item_identity = identity(item)
                if item_identity is None:
                    continue
                if item_identity in seen or item_identity in page_identities:
                    raise PaginationError(
                        "paginated endpoint repeated an item identity",
                        code="duplicate_page_item",
                        start=offset,
                        limit=limit,
                        details={"identity": str(item_identity)},
                    )
                page_identities.add(item_identity)
            seen.update(page_identities)

        page = Page(start=offset, limit=limit, items=items)
        yield page
        if page.exhausted:
            return
        if not items:
            return
        offset = page.next_start


def iter_items(
    fetch_page: PageFetcher[T],
    *,
    start: int = 0,
    limit: int = 100,
    identity: Identity[T] | None = None,
) -> Iterator[T]:
    """Yield all items from a paginated endpoint."""

    for page in iter_pages(fetch_page, start=start, limit=limit, identity=identity):
        yield from page.items


def collect_items(
    fetch_page: PageFetcher[T],
    *,
    start: int = 0,
    limit: int = 100,
    identity: Identity[T] | None = None,
) -> list[T]:
    """Collect all items from a paginated endpoint into one list."""

    return list(iter_items(fetch_page, start=start, limit=limit, identity=identity))
