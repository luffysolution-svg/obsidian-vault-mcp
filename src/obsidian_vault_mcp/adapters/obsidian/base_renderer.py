from __future__ import annotations

from copy import deepcopy
from typing import Any

import yaml

BASE_TEMPLATE_VERSION = 1


def base_document(literature_root: str = "Literature", name: str = "Literature Matrix") -> dict[str, Any]:
    """Return the versioned Obsidian Bases document for V2 literature notes."""
    root = literature_root.replace("\\", "/").strip("/")
    if not root or root.startswith(".") or "/../" in f"/{root}/":
        raise ValueError("literature_root must be a safe vault-relative folder")

    columns = [
        "file.name",
        "note.title",
        "note.itemType",
        "note.year",
        "note.journal",
        "note.tags",
        "note.doi",
        "note.url",
        "note.zoteroPdfLink",
        "note.attachmentPdfLink",
        "note.attachmentMinerULink",
    ]
    document: dict[str, Any] = {
        "filters": {
            "and": [
                f'file.folder == "{root}"',
                'zoteroKey != null',
            ]
        },
        "properties": {
            "file.name": {"displayName": "File"},
            "note.title": {"displayName": "Title"},
            "note.itemType": {"displayName": "Type"},
            "note.year": {"displayName": "Year"},
            "note.journal": {"displayName": "Journal"},
            "note.tags": {"displayName": "Tags"},
            "note.doi": {"displayName": "DOI"},
            "note.url": {"displayName": "URL"},
            "note.zoteroPdfLink": {"displayName": "Zotero"},
            "note.attachmentPdfLink": {"displayName": "PDF"},
            "note.attachmentMinerULink": {"displayName": "MinerU"},
        },
        "views": [
            {"type": "table", "name": name, "order": columns},
            {
                "type": "table",
                "name": "By Year",
                "groupBy": {"property": "note.year", "direction": "DESC"},
                "order": columns,
            },
            {
                "type": "table",
                "name": "By Journal",
                "groupBy": {"property": "note.journal", "direction": "ASC"},
                "order": columns,
            },
            {
                "type": "table",
                "name": "By Tag",
                "groupBy": {"property": "note.tags", "direction": "ASC"},
                "order": columns,
            },
            {
                "type": "table",
                "name": "MinerU Complete",
                "filters": {"and": ["attachmentMinerULink != null"]},
                "order": columns,
            },
            {
                "type": "table",
                "name": "Missing PDF",
                "filters": {"and": ["attachmentPdfLink == null"]},
                "order": columns,
            },
            {
                "type": "table",
                "name": "Missing DOI",
                "filters": {"and": ["doi == null"]},
                "order": columns,
            },
        ],
    }
    return deepcopy(document)


def render_base(literature_root: str = "Literature", name: str = "Literature Matrix") -> str:
    """Render a valid, deterministic ``.base`` YAML document."""
    return yaml.safe_dump(
        base_document(literature_root, name),
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        width=1000,
    )
