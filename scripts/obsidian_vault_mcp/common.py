from __future__ import annotations

import html
import json
import math
import os
import re
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from difflib import unified_diff
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlencode, urlparse
from urllib.request import Request, urlopen

DEFAULT_EXCLUDES = {".git", ".obsidian", ".trash", "node_modules", ".DS_Store"}
BACKUP_DIR = ".obsidian-vault-backups"
ZOTERO_API_BASE = os.environ.get("ZOTERO_LOCAL_API", "http://127.0.0.1:23119/api").rstrip("/")
ZOTERO_TIMEOUT = float(os.environ.get("ZOTERO_TIMEOUT", "20"))
MINERU_CLI_COMMAND = os.environ.get("MINERU_CLI_COMMAND", "mineru-open-api")
MINERU_TIMEOUT = int(os.environ.get("MINERU_TIMEOUT", "600"))
WIKILINK_RE = re.compile(r"(?<!!)\[\[([^\]\n]+)\]\]")
EMBED_RE = re.compile(r"!\[\[([^\]\n]+)\]\]")
INLINE_TAG_RE = re.compile(r"(?<![\w/])#([^\s#.,;:!?()\[\]{}<>\"'`]+)")
MARKDOWN_LINK_RE = re.compile(r"(?<!!)\[[^\]\n]+\]\(([^)\n]+)\)")
BIBTEX_ENTRY_RE = re.compile(r"@(?P<type>[A-Za-z]+)\s*\{\s*(?P<key>[^,\s]+)\s*,(?P<body>.*?)(?=^\s*@|\Z)", re.DOTALL | re.MULTILINE)
BIBTEX_FIELD_RE = re.compile(r"(?P<name>[A-Za-z][A-Za-z0-9_-]*)\s*=\s*(?P<value>\{(?:[^{}]|\{[^{}]*\})*\}|\"(?:[^\"\\]|\\.)*\"|[^,\n]+)\s*,?", re.DOTALL)
CODE_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
INDEX_START = "<!-- obsidian-vault:index:start -->"
INDEX_END = "<!-- obsidian-vault:index:end -->"
GENERATED_START = "<!-- obsidian-vault:generated:start -->"
GENERATED_END = "<!-- obsidian-vault:generated:end -->"



DEFAULT_TOOL_PROFILE = "literature"
FULL_TOOL_PROFILES = {"full", "legacy"}
KNOWN_TOOL_PROFILES = {DEFAULT_TOOL_PROFILE, *FULL_TOOL_PROFILES}
LITERATURE_PROFILE_TOOLS = {
    "obsidian_pipeline_doctor",
    "obsidian_pipeline_config",
    "obsidian_pipeline_migrate_layout",
    "obsidian_search",
    "obsidian_read_file",
    "obsidian_write_file",
    "obsidian_update_properties",
    "obsidian_zotero_ping",
    "obsidian_zotero_search_items",
    "obsidian_zotero_list_collections",
    "obsidian_zotero_get_item",
    "obsidian_zotero_get_children",
    "obsidian_zotero_list_pdf_attachments",
    "obsidian_pipeline_ingest_item",
    "obsidian_pipeline_ingest_collection",
    "obsidian_pipeline_parse_with_mineru",
    "obsidian_pipeline_rename_mineru_images",
}

REGISTERED_TOOLS: list[Any] = []
REGISTERED_TOOL_PROFILES: dict[str, set[str]] = {}


def _normalize_tool_profile(profile: str = "") -> str:
    normalized = (profile or DEFAULT_TOOL_PROFILE).strip().lower()
    if normalized not in KNOWN_TOOL_PROFILES:
        raise ValueError(f"Unknown tool profile: {profile}. Expected one of: {', '.join(sorted(KNOWN_TOOL_PROFILES))}.")
    return normalized


def tool(*profiles: str):
    selected_profiles = {profile.strip().lower() for profile in profiles if str(profile).strip()}

    def decorator(func):
        REGISTERED_TOOLS.append(func)
        effective = set(selected_profiles)
        if not effective:
            effective = set(FULL_TOOL_PROFILES)
            if func.__name__ in LITERATURE_PROFILE_TOOLS:
                effective.add(DEFAULT_TOOL_PROFILE)
        REGISTERED_TOOL_PROFILES[func.__name__] = effective
        return func

    return decorator


def get_registered_tools(profile: str = DEFAULT_TOOL_PROFILE) -> list[Any]:
    selected = _normalize_tool_profile(profile)
    if selected in FULL_TOOL_PROFILES:
        selected = "full"
    return [
        func for func in REGISTERED_TOOLS
        if selected in REGISTERED_TOOL_PROFILES.get(func.__name__, set())
        or (selected == "full" and REGISTERED_TOOL_PROFILES.get(func.__name__, set()) & FULL_TOOL_PROFILES)
    ]


def get_registered_tool_names(profile: str = DEFAULT_TOOL_PROFILE) -> list[str]:
    return [func.__name__ for func in get_registered_tools(profile)]
