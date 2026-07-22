"""Strict, deterministic YAML frontmatter handling for literature notes."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .errors import FrontmatterError

MANAGED_FIELD_ORDER: tuple[str, ...] = (
    "title",
    "itemType",
    "year",
    "journal",
    "tags",
    "doi",
    "url",
    "abstract",
    "zoteroKey",
    "zoteroPdfLink",
    "attachmentPdfLink",
    "attachmentMinerULink",
)


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(
    loader: yaml.SafeLoader,
    node: yaml.nodes.MappingNode,
    deep: bool = False,
) -> dict[Any, Any]:
    loader.flatten_mapping(node)
    result: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise FrontmatterError(f"duplicate frontmatter field: {key}")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


class _IndentedDumper(yaml.SafeDumper):
    def increase_indent(self, flow: bool = False, indentless: bool = False) -> None:
        return super().increase_indent(flow, False)


@dataclass(frozen=True)
class FrontmatterDocument:
    """A parsed Markdown document without modifying its body."""

    fields: dict[str, Any]
    body: str
    has_frontmatter: bool


def parse_frontmatter(text: str) -> FrontmatterDocument:
    """Parse a UTF-8 Markdown string and return its YAML mapping and body."""

    if not isinstance(text, str):
        raise FrontmatterError("Markdown content must be text decoded as UTF-8")
    if text.startswith("\ufeff"):
        text = text[1:]
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return FrontmatterDocument({}, text, False)

    closing_index: int | None = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            closing_index = index
            break
    if closing_index is None:
        raise FrontmatterError("frontmatter starts with '---' but has no closing delimiter")

    raw_yaml = "".join(lines[1:closing_index])
    body = "".join(lines[closing_index + 1 :])
    try:
        parsed = yaml.load(raw_yaml, Loader=_UniqueKeyLoader) if raw_yaml.strip() else {}
    except FrontmatterError:
        raise
    except yaml.YAMLError as exc:
        raise FrontmatterError(f"invalid YAML frontmatter: {exc}") from exc
    if parsed is None:
        parsed = {}
    if not isinstance(parsed, dict):
        raise FrontmatterError("frontmatter must be a YAML mapping")
    if any(not isinstance(key, str) for key in parsed):
        raise FrontmatterError("frontmatter field names must be strings")
    return FrontmatterDocument(dict(parsed), body, True)


def split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Compatibility tuple form of :func:`parse_frontmatter`."""

    document = parse_frontmatter(text)
    return document.fields, document.body


def merge_frontmatter(
    existing_fields: Mapping[str, Any] | None,
    managed_fields: Mapping[str, Any],
    *,
    omit_empty: bool = True,
    preserve_unknown_fields: bool = True,
    field_order: Sequence[str] = MANAGED_FIELD_ORDER,
) -> dict[str, Any]:
    """Merge plugin-managed values ahead of preserved user fields.

    Managed values explicitly supplied by the caller replace (or, when empty,
    remove) old managed values. Managed values omitted by the caller remain
    unchanged, allowing safe partial updates. Unknown existing fields are never
    overwritten by plugin input.
    """

    existing = _mapping(existing_fields or {}, "existing_fields")
    updates = _mapping(managed_fields, "managed_fields")
    order = _validate_field_order(field_order)
    managed_names = set(order)
    result: dict[str, Any] = {}

    for name in order:
        if name in updates:
            value = updates[name]
        elif name in existing:
            value = existing[name]
        else:
            continue
        if omit_empty and is_empty(value):
            continue
        result[name] = _yaml_value(value)

    if preserve_unknown_fields:
        for name, value in existing.items():
            if name not in managed_names:
                result[name] = _yaml_value(value)
        for name, value in updates.items():
            if name not in managed_names and name not in result:
                if not (omit_empty and is_empty(value)):
                    result[name] = _yaml_value(value)
    return result


def order_frontmatter(
    fields: Mapping[str, Any],
    *,
    omit_empty: bool = True,
    field_order: Sequence[str] = MANAGED_FIELD_ORDER,
) -> dict[str, Any]:
    """Order managed fields first and retain unknown fields afterward."""

    values = _mapping(fields, "fields")
    order = _validate_field_order(field_order)
    result: dict[str, Any] = {}
    for name in order:
        if name in values and not (omit_empty and is_empty(values[name])):
            result[name] = _yaml_value(values[name])
    for name, value in values.items():
        if name not in result and name not in order and not (omit_empty and is_empty(value)):
            result[name] = _yaml_value(value)
    return result


def dump_frontmatter(
    fields: Mapping[str, Any],
    *,
    omit_empty: bool = True,
    field_order: Sequence[str] = MANAGED_FIELD_ORDER,
) -> str:
    """Serialize only the YAML payload with deterministic order and LF lines."""

    ordered = order_frontmatter(fields, omit_empty=omit_empty, field_order=field_order)
    if not ordered:
        return ""
    try:
        rendered = yaml.dump(
            ordered,
            Dumper=_IndentedDumper,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
            width=10_000,
        )
    except yaml.YAMLError as exc:
        raise FrontmatterError(f"could not serialize frontmatter: {exc}") from exc
    return rendered.rstrip("\n")


def compose_frontmatter(
    fields: Mapping[str, Any],
    body: str = "",
    *,
    omit_empty: bool = True,
    field_order: Sequence[str] = MANAGED_FIELD_ORDER,
) -> str:
    """Compose a Markdown document with canonical frontmatter and unchanged body."""

    if not isinstance(body, str):
        raise FrontmatterError("Markdown body must be text")
    yaml_text = dump_frontmatter(fields, omit_empty=omit_empty, field_order=field_order)
    if not yaml_text:
        return body
    separator = "" if body.startswith(("\n", "\r")) or not body else "\n"
    return f"---\n{yaml_text}\n---\n{separator}{body}"


def update_frontmatter(
    text: str,
    managed_fields: Mapping[str, Any],
    *,
    omit_empty: bool = True,
    preserve_unknown_fields: bool = True,
    field_order: Sequence[str] = MANAGED_FIELD_ORDER,
) -> str:
    """Update frontmatter without modifying any Markdown body content."""

    document = parse_frontmatter(text)
    merged = merge_frontmatter(
        document.fields,
        managed_fields,
        omit_empty=omit_empty,
        preserve_unknown_fields=preserve_unknown_fields,
        field_order=field_order,
    )
    return compose_frontmatter(merged, document.body, omit_empty=False, field_order=field_order)


def read_frontmatter(path: str | Path) -> FrontmatterDocument:
    """Read a Markdown file strictly as UTF-8 and parse its frontmatter."""

    try:
        text = Path(path).read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise FrontmatterError(f"frontmatter file is not valid UTF-8: {path}") from exc
    return parse_frontmatter(text)


def is_empty(value: Any) -> bool:
    """Return whether a value should be omitted by ``omitEmpty``."""

    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) == 0
    return False


def _mapping(value: Mapping[str, Any], label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise FrontmatterError(f"{label} must be a mapping")
    result = dict(value)
    if any(not isinstance(key, str) for key in result):
        raise FrontmatterError(f"{label} field names must be strings")
    return result


def _validate_field_order(value: Sequence[str]) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)):
        raise FrontmatterError("field_order must be a sequence of field names")
    order = tuple(value)
    if any(not isinstance(name, str) for name in order) or len(set(order)) != len(order):
        raise FrontmatterError("field_order must contain unique string field names")
    return order


def _yaml_value(value: Any) -> Any:
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return sorted(value, key=str)
    return value


# Familiar aliases used by renderers.
render_frontmatter = dump_frontmatter
join_frontmatter = compose_frontmatter
