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
CODE_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
INDEX_START = "<!-- obsidian-vault:index:start -->"
INDEX_END = "<!-- obsidian-vault:index:end -->"
GENERATED_START = "<!-- obsidian-vault:generated:start -->"
GENERATED_END = "<!-- obsidian-vault:generated:end -->"



REGISTERED_TOOLS: list[Any] = []


def tool():
    def decorator(func):
        REGISTERED_TOOLS.append(func)
        return func
    return decorator


def get_registered_tools() -> list[Any]:
    return list(REGISTERED_TOOLS)


def get_registered_tool_names() -> list[str]:
    return [func.__name__ for func in REGISTERED_TOOLS]
