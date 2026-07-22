"""Canonical defaults for the one V2 Vault configuration file."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from ..domain.frontmatter import MANAGED_FIELD_ORDER

CONFIG_FILENAME = ".obsidian-vault-mcp.json"
SCHEMA_VERSION = 2
SCHEMA_URL = (
    "https://raw.githubusercontent.com/luffysolution-svg/"
    "obsidian-vault-mcp/main/obsidian-vault-mcp.schema.json"
)

DEFAULT_CONFIG: dict[str, Any] = {
    "$schema": SCHEMA_URL,
    "schemaVersion": SCHEMA_VERSION,
    "literature": {
        "root": "Literature",
        "index": "Literature/index.md",
        "base": "Literature/Literature.base",
        "wikiFolder": "Literature/Wiki",
    },
    "identity": {"strategy": "zoteroKey"},
    "naming": {
        "note": "{zoteroKey}.md",
        "pdf": "{zoteroKey}.pdf",
        "mineruMarkdown": "{zoteroKey}.md",
        "mineruImage": "{zoteroKey}-fig{index:02d}.{ext}",
    },
    "attachments": {
        "pdfFolder": "Literature/attachment",
        "copyPdf": True,
        "overwritePolicy": "if-source-changed",
    },
    "frontmatter": {
        "omitEmpty": True,
        "preserveUnknownFields": True,
        "fieldOrder": list(MANAGED_FIELD_ORDER),
    },
    "note": {
        "omitEmptySections": True,
        "preserveUserSections": True,
        "readingNotesHeading": "Reading Notes",
        "embedPdf": True,
        "embedMineruMarkdown": True,
    },
    "zotero": {
        "apiBase": "http://127.0.0.1:23119/api",
        "linkedAttachmentBaseDir": "",
        "syncNotes": True,
        "syncAnnotations": True,
        "syncTags": True,
        "paginationSize": 100,
    },
    "bibtex": {
        "enabled": True,
        "provider": "auto",
        "fallback": "builtin",
    },
    "mineru": {
        "enabled": True,
        "mode": "auto",
        "markdownFolder": "Literature/attachment/MinerU",
        "imageFolder": "Literature/attachment/MinerU/image",
        "imageLinkStyle": "markdown-relative",
        "replacePreviousOutput": True,
        "maxConcurrentJobs": 2,
    },
    "index": {
        "autoRebuild": True,
        "recentLimit": 20,
        "groupBy": ["year", "journal", "tags"],
    },
    "base": {
        "autoRebuild": True,
        "name": "Literature Matrix",
    },
    "safety": {
        "atomicWrites": True,
        "backupBeforeReplace": True,
        "retainBackups": 10,
        "defaultDryRunForMigration": True,
        "lockPerItem": True,
    },
}


def default_config() -> dict[str, Any]:
    """Return an independent mutable copy of the canonical defaults."""

    return deepcopy(DEFAULT_CONFIG)
