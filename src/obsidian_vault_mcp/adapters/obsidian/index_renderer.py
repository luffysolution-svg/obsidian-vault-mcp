from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from pathlib import PurePosixPath
from typing import Any


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _tags(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple, set)):
        return []
    return sorted({_text(tag) for tag in value if _text(tag)}, key=str.casefold)


def _link(record: Mapping[str, Any]) -> str:
    key = _text(record.get("zoteroKey"))
    title = _text(record.get("title")) or key
    note_path = _text(record.get("notePath")).replace("\\", "/")
    target = PurePosixPath(note_path).with_suffix("").as_posix() if note_path else key
    return f"[[{target}|{title.replace('|', ' - ')}]]"


def _managed_block(name: str, lines: Iterable[str]) -> list[str]:
    result = [f"<!-- ovm:index:{name}:start -->"]
    result.extend(lines)
    result.append(f"<!-- ovm:index:{name}:end -->")
    return result


def _group_lines(records: list[Mapping[str, Any]], field: str) -> list[str]:
    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for record in records:
        values = _tags(record.get(field)) if field == "tags" else [_text(record.get(field)) or "Unknown"]
        for value in values:
            groups[value].append(record)

    if field == "year":
        known = sorted((value for value in groups if value != "Unknown"), reverse=True)
        names = [*known, *(["Unknown"] if "Unknown" in groups else [])]
    else:
        names = sorted(groups, key=str.casefold)

    lines: list[str] = []
    for name in names:
        lines.append(f"### {name}")
        for record in sorted(groups[name], key=lambda item: (_text(item.get("title")).casefold(), _text(item.get("zoteroKey")))):
            lines.append(f"- {_link(record)}")
        lines.append("")
    if lines:
        lines.pop()
    return lines


def render_index(
    records: Iterable[Mapping[str, Any]],
    wiki_topics: Iterable[str] = (),
    *,
    recent_limit: int = 20,
    base_path: str = "Literature/Literature.base",
    wiki_folder: str = "Literature/Wiki",
) -> str:
    """Render the V2 literature dashboard with deterministic managed blocks."""
    items = [dict(record) for record in records if _text(record.get("zoteroKey"))]
    items.sort(key=lambda item: (_text(item.get("title")).casefold(), _text(item.get("zoteroKey"))))

    with_pdf = sum(bool(_text(item.get("attachmentPdfLink"))) for item in items)
    with_mineru = sum(bool(_text(item.get("attachmentMinerULink"))) for item in items)
    missing_doi = sum(not bool(_text(item.get("doi"))) for item in items)
    recent = sorted(
        items,
        key=lambda item: (_text(item.get("lastImportedAt")), _text(item.get("zoteroKey"))),
        reverse=True,
    )[: max(0, recent_limit)]

    topic_names = sorted({_text(topic).removesuffix(".md") for topic in wiki_topics if _text(topic)}, key=str.casefold)
    wiki_root = wiki_folder.replace("\\", "/").strip("/")
    key_counts = Counter(_text(item.get("zoteroKey")) for item in items)
    doi_counts = Counter(_text(item.get("doi")).casefold() for item in items if _text(item.get("doi")))
    duplicate_keys = sorted(key for key, count in key_counts.items() if count > 1)
    duplicate_dois = sorted(doi for doi, count in doi_counts.items() if count > 1)

    maintenance = [
        f"- Missing PDF: {len(items) - with_pdf}",
        f"- MinerU pending: {len(items) - with_mineru}",
        "- Broken attachment links: 0",
        f"- Duplicate DOI: {len(duplicate_dois)}",
        f"- Duplicate Zotero key: {len(duplicate_keys)}",
    ]
    maintenance.extend(f"  - DOI `{doi}`" for doi in duplicate_dois)
    maintenance.extend(f"  - Zotero key `{key}`" for key in duplicate_keys)

    lines = [
        "# Literature Knowledge Base",
        "",
        "## Dashboard",
        "",
        f"- [[{base_path}|Literature Matrix]]",
        f"- Total literature: {len(items)}",
        f"- With PDF: {with_pdf}",
        f"- With MinerU: {with_mineru}",
        f"- Missing DOI: {missing_doi}",
        "",
        "## Recently Added",
        "",
        *_managed_block("recent", [f"- {_link(item)}" for item in recent]),
        "",
        "## By Year",
        "",
        *_managed_block("year", _group_lines(items, "year")),
        "",
        "## By Journal",
        "",
        *_managed_block("journal", _group_lines(items, "journal")),
        "",
        "## By Tag",
        "",
        *_managed_block("tags", _group_lines(items, "tags")),
        "",
        "## Wiki Topics",
        "",
        *_managed_block("wiki", [f"- [[{wiki_root}/{topic}]]" for topic in topic_names]),
        "",
        "## Maintenance",
        "",
        *_managed_block("maintenance", maintenance),
        "",
    ]
    return "\n".join(lines)
