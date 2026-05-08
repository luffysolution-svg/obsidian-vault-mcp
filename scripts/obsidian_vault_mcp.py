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

from mcp.server.fastmcp import FastMCP


DEFAULT_EXCLUDES = {".git", ".obsidian", ".trash", "node_modules", ".DS_Store"}
BACKUP_DIR = ".obsidian-vault-backups"
ZOTERO_API_BASE = os.environ.get("ZOTERO_LOCAL_API", "http://127.0.0.1:23119/api").rstrip("/")
ZOTERO_TIMEOUT = float(os.environ.get("ZOTERO_TIMEOUT", "20"))
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

mcp = FastMCP("obsidian-vault")


def _json(value: str, default: Any) -> Any:
    if not value or not value.strip():
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Expected valid JSON: {exc}") from exc


def _vault(vault_path: str = "") -> Path:
    selected = vault_path or os.environ.get("OBSIDIAN_VAULT_PATH") or "auto"
    if selected.strip().lower() == "auto":
        selected = _active_cli_vault_path()
        if not selected:
            cwd = Path(os.getcwd()).resolve()
            if _is_vault_root(cwd):
                selected = str(cwd)
            else:
                raise RuntimeError(
                    "Could not resolve an Obsidian vault. Open Obsidian with a vault, "
                    "set OBSIDIAN_VAULT_PATH to a vault root, pass vault_path explicitly, "
                    "or run from a directory containing .obsidian."
                )
    path = Path(selected).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Vault path does not exist: {path}")
    if not path.is_dir():
        raise NotADirectoryError(f"Vault path is not a directory: {path}")
    if not _is_vault_root(path) and os.environ.get("OBSIDIAN_ALLOW_NON_VAULT", "").lower() not in {"1", "true", "yes"}:
        raise ValueError(
            f"Path does not look like an Obsidian vault root because it has no .obsidian folder: {path}. "
            "Set OBSIDIAN_ALLOW_NON_VAULT=true to allow plain folders."
        )
    return path


def _is_vault_root(path: Path) -> bool:
    return (path / ".obsidian").is_dir()


def _active_cli_vault_path() -> str:
    cli = os.environ.get("OBSIDIAN_CLI_COMMAND", "obsidian")
    if shutil.which(cli) is None:
        return ""
    try:
        completed = subprocess.run(
            [cli, "vault", "info=path"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
    except Exception:
        return ""
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


def _safe_path(vault: Path, rel_path: str) -> Path:
    if not rel_path:
        raise ValueError("A vault-relative path is required.")
    normalized = rel_path.replace("\\", "/").lstrip("/")
    candidate = Path(normalized)
    full = candidate if candidate.is_absolute() else vault / candidate
    full = full.expanduser().resolve()
    try:
        full.relative_to(vault)
    except ValueError as exc:
        raise ValueError(f"Path escapes the vault root: {rel_path}") from exc
    return full


def _rel(vault: Path, path: Path) -> str:
    return path.resolve().relative_to(vault).as_posix()


def _iter_files(vault: Path, folder: str = "", include_hidden: bool = False):
    root = _safe_path(vault, folder) if folder else vault
    if not root.exists():
        return
    if root.is_file():
        yield root
        return
    for path in root.rglob("*"):
        if not include_hidden and any(part in DEFAULT_EXCLUDES or part.startswith(".") for part in path.relative_to(vault).parts):
            continue
        if path.is_file():
            yield path


def _extension_set(extensions: str) -> set[str]:
    if not extensions.strip():
        return set()
    result = set()
    for part in extensions.split(","):
        ext = part.strip().lower()
        if not ext:
            continue
        result.add(ext if ext.startswith(".") else f".{ext}")
    return result


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def _diff_text(rel_path: str, before: str, after: str) -> str:
    if before == after:
        return ""
    lines = unified_diff(
        before.splitlines(),
        after.splitlines(),
        fromfile=f"a/{rel_path}",
        tofile=f"b/{rel_path}",
        lineterm="",
    )
    diff = "\n".join(lines)
    return f"{diff}\n" if diff else ""


def _write_result(vault: Path, full: Path, content: str, dry_run: bool = False) -> dict[str, Any]:
    old_content = _read_text(full) if full.exists() else ""
    rel_path = _rel(vault, full)
    diff = _diff_text(rel_path, old_content, content)
    result = {
        "ok": True,
        "path": rel_path,
        "dryRun": dry_run,
        "changed": old_content != content,
        "diff": diff,
        "bytes": len(content.encode("utf-8")),
    }
    if not dry_run and old_content != content:
        _write_text(full, content)
        result["bytes"] = full.stat().st_size
    return result


def _write_many(vault: Path, writes: list[tuple[Path, str]], dry_run: bool = False) -> dict[str, Any]:
    changes = [_write_result(vault, full, content, dry_run) for full, content in writes]
    return {
        "ok": all(change.get("ok", False) for change in changes),
        "dryRun": dry_run,
        "changed": any(change.get("changed", False) for change in changes),
        "changeCount": sum(1 for change in changes if change.get("changed")),
        "changes": changes,
    }


def _backup_path(vault: Path, transaction_id: str, rel_path: str) -> Path:
    return vault / BACKUP_DIR / transaction_id / rel_path


def _transaction_manifest_path(vault: Path, transaction_id: str) -> Path:
    return vault / BACKUP_DIR / transaction_id / "manifest.json"


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---"):
        return {}, text
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return {}, text
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            raw = "".join(lines[1:index])
            body = "".join(lines[index + 1 :])
            return _load_yaml(raw), body
    return {}, text


def _load_yaml(raw: str) -> dict[str, Any]:
    try:
        import yaml  # type: ignore

        value = yaml.safe_load(raw) if raw.strip() else {}
        return value if isinstance(value, dict) else {}
    except Exception:
        return _load_simple_yaml(raw)


def _load_simple_yaml(raw: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    current_key: str | None = None
    for line in raw.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith((" ", "\t")) and current_key:
            stripped = line.strip()
            if stripped.startswith("- "):
                data.setdefault(current_key, [])
                if isinstance(data[current_key], list):
                    data[current_key].append(_parse_scalar(stripped[2:].strip()))
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        current_key = key
        data[key] = [] if value == "" else _parse_scalar(value)
    return data


def _parse_scalar(value: str) -> Any:
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if value in {"null", "Null", "~"}:
        return None
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(part.strip()) for part in inner.split(",")]
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def _dump_yaml(data: dict[str, Any]) -> str:
    try:
        import yaml  # type: ignore

        return yaml.safe_dump(data, sort_keys=False, allow_unicode=True).strip()
    except Exception:
        return _dump_simple_yaml(data)


def _dump_simple_yaml(data: dict[str, Any]) -> str:
    lines: list[str] = []
    for key, value in data.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {_format_scalar(item)}")
        else:
            lines.append(f"{key}: {_format_scalar(value)}")
    return "\n".join(lines)


def _format_scalar(value: Any) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if not text or any(ch in text for ch in [":", "#", "[", "]", "{", "}", "\n"]) or text.strip() != text:
        return json.dumps(text, ensure_ascii=False)
    return text


def _join_frontmatter(properties: dict[str, Any], body: str) -> str:
    if not properties:
        return body.lstrip("\n")
    return f"---\n{_dump_yaml(properties)}\n---\n\n{body.lstrip()}"


def _note_title_from_path(rel_path: str) -> str:
    return Path(rel_path).stem.replace("_", " ").replace("-", " ").strip() or "Untitled"


def _listify(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        if "," in stripped:
            return [part.strip() for part in stripped.split(",") if part.strip()]
        return [stripped]
    return [value]


def _normalize_tag(value: Any) -> str:
    return str(value).strip().lstrip("#")


def _frontmatter_tags(props: dict[str, Any]) -> list[str]:
    return [tag for tag in (_normalize_tag(item) for item in _listify(props.get("tags"))) if tag]


def _frontmatter_aliases(props: dict[str, Any]) -> list[str]:
    return [str(item).strip() for item in _listify(props.get("aliases")) if str(item).strip()]


def _inline_tags(text: str) -> list[str]:
    without_code = INLINE_CODE_RE.sub("", CODE_FENCE_RE.sub("", text))
    return sorted({_normalize_tag(match.group(1)) for match in INLINE_TAG_RE.finditer(without_code) if _normalize_tag(match.group(1))})


def _target_from_link(link: str) -> str:
    target = link.split("|", 1)[0].split("#", 1)[0].strip()
    return target[:-3] if target.lower().endswith(".md") else target


def _normalize_note_key(path_or_name: str) -> str:
    value = path_or_name.replace("\\", "/").strip()
    if value.lower().endswith(".md"):
        value = value[:-3]
    return value.lower()


def _collect_markdown(vault: Path) -> list[Path]:
    return [path for path in _iter_files(vault) if path.suffix.lower() == ".md"]


def _add_note_key(index: dict[str, set[str]], key: str, rel_path: str) -> None:
    normalized = _normalize_note_key(key)
    if normalized:
        index.setdefault(normalized, set()).add(rel_path)


def _resolve_note_key(index: dict[str, set[str]], key: str) -> tuple[str | None, list[str]]:
    matches = sorted(index.get(_normalize_note_key(key), set()))
    if len(matches) == 1:
        return matches[0], []
    if len(matches) > 1:
        return None, matches
    return None, []


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _wikilink_target(rel_path: str) -> str:
    target = rel_path.replace("\\", "/")
    return target[:-3] if target.lower().endswith(".md") else target


def _wikilink(rel_path: str, label: str = "") -> str:
    target = _wikilink_target(rel_path)
    clean_label = label.strip()
    return f"[[{target}|{clean_label}]]" if clean_label and clean_label != target else f"[[{target}]]"


def _slug_filename(name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", name).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned or "Untitled"


def _ensure_md_path(path: str) -> str:
    cleaned = path.replace("\\", "/").strip().lstrip("/")
    return cleaned if cleaned.lower().endswith(".md") else f"{cleaned}.md"


def _item_name(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("name") or item.get("title") or "").strip()
    return str(item).strip()


def _item_summary(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("summary") or item.get("description") or "").strip()
    return ""


def _item_path(item: Any, folder: str) -> str:
    if isinstance(item, dict) and item.get("path"):
        return _ensure_md_path(str(item["path"]))
    return f"{folder.strip('/').replace('\\', '/')}/{_slug_filename(_item_name(item))}.md"


def _merge_unique(existing: Any, additions: list[str]) -> list[str]:
    seen: set[str] = set()
    merged: list[str] = []
    for value in _listify(existing) + additions:
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            merged.append(text)
    return merged


def _replace_block(text: str, start_marker: str, end_marker: str, block: str, default_title: str) -> str:
    if start_marker in text and end_marker in text:
        pattern = re.compile(rf"{re.escape(start_marker)}.*?{re.escape(end_marker)}", re.DOTALL)
        return pattern.sub(block.strip(), text, count=1).rstrip() + "\n"
    if text.strip():
        return text.rstrip() + "\n\n" + block.strip() + "\n"
    return f"# {default_title}\n\n{block.strip()}\n"


def _generated_block(lines: list[str], marker_name: str = "generated") -> str:
    if marker_name == "index":
        start, end = INDEX_START, INDEX_END
    else:
        start, end = GENERATED_START, GENERATED_END
    return "\n".join([start, *lines, end])


BASE_TEMPLATE_DESCRIPTIONS = {
    "literature": "Literature and paper notes with citation metadata.",
    "project_tasks": "Project tasks grouped by status and priority.",
    "equipment": "Equipment list with cost, owner, and status fields.",
    "utilities": "Utilities and public engineering streams.",
    "economics": "Economic estimate and cost-tracking notes.",
    "sources": "Source notes produced by wiki ingestion.",
}

DATAVIEW_TEMPLATE_DESCRIPTIONS = {
    "literature": "Dataview table for literature and paper notes.",
    "project_tasks": "Dataview task/project table grouped by status.",
    "equipment": "Dataview table for equipment registers.",
    "utilities": "Dataview table for public engineering and utility notes.",
    "economics": "Dataview table for cost and economics notes.",
    "sources": "Dataview table for ingested source notes.",
}

SCHEMA_PRESETS = {
    "source": {"required": {"title": "str", "type": "str", "tags": "list_or_str"}, "recommended": {"entities": "list", "concepts": "list"}},
    "entity": {"required": {"title": "str", "type": "str", "tags": "list_or_str", "sources": "list"}},
    "concept": {"required": {"title": "str", "type": "str", "tags": "list_or_str", "sources": "list"}},
    "project": {"required": {"title": "str", "status": "str", "tags": "list_or_str"}, "recommended": {"owner": "str"}},
    "task": {"required": {"title": "str", "status": "str", "tags": "list_or_str"}, "recommended": {"priority": "number", "due": "str"}},
    "literature": {"required": {"title": "str", "tags": "list_or_str"}, "recommended": {"authors": "list_or_str", "year": "number", "doi": "str"}},
    "equipment": {"required": {"title": "str", "tag_no": "str", "tags": "list_or_str"}, "recommended": {"status": "str", "cost": "number"}},
    "utility": {"required": {"title": "str", "type": "str", "tags": "list_or_str"}, "recommended": {"flowrate": "number"}},
    "economics": {"required": {"title": "str", "category": "str", "tags": "list_or_str"}, "recommended": {"capex": "number", "opex": "number"}},
}


def _base_filter(folder: str = "", tag: str = "", extra: str = "") -> dict[str, list[str]] | str:
    filters: list[str] = []
    if folder:
        filters.append(f'file.inFolder("{folder}")')
    if tag:
        filters.append(f'file.hasTag("{tag.lstrip("#")}")')
    if extra:
        filters.append(extra)
    if not filters:
        return {"and": []}
    if len(filters) == 1:
        return filters[0]
    return {"and": filters}


def _dataview_from_clause(folder: str = "", tag: str = "") -> str:
    parts: list[str] = []
    if tag:
        parts.append(f"#{tag.lstrip('#')}")
    if folder:
        parts.append(f'"{folder.strip("/")}"')
    return "FROM " + " AND ".join(parts) if parts else ""


def _dataview_template(template: str, options: dict[str, Any]) -> str:
    folder = str(options.get("folder") or "").strip("/")
    tag = str(options.get("tag") or "").strip().lstrip("#")
    title = str(options.get("title") or "").strip()
    sort = str(options.get("sort") or "file.mtime desc").strip()
    limit = int(options.get("limit") or 200)
    effective_title = title or template.replace("_", " ").title()
    defaults = {
        "literature": ("literature", "literature", "TABLE title, authors, year, doi, status, topics, rating"),
        "project_tasks": ("tasks", "task", "TABLE status, priority, owner, due, project"),
        "equipment": ("equipment", "equipment", "TABLE tag_no, service, area, status, cost, vendor"),
        "utilities": ("utilities", "utility", "TABLE type, supply_temp, return_temp, pressure, flowrate, cost_basis"),
        "economics": ("economics", "economics", "TABLE category, capex, opex, lifetime, basis"),
        "sources": ("sources", "source", "TABLE title, type, entities, concepts, doi, file.mtime AS updated"),
    }
    if template not in defaults:
        raise ValueError(f"Unknown Dataview template: {template}. Available templates: {', '.join(DATAVIEW_TEMPLATE_DESCRIPTIONS)}")
    default_folder, default_tag, query_head = defaults[template]
    from_clause = _dataview_from_clause(folder or default_folder, tag or default_tag)
    query = [query_head]
    if from_clause:
        query.append(from_clause)
    if sort:
        query.append(f"SORT {sort}")
    if limit:
        query.append(f"LIMIT {limit}")
    return "\n".join(
        [
            f"# {effective_title}",
            "",
            "```dataview",
            *query,
            "```",
            "",
        ]
    )


def _clean_bibtex_value(value: str) -> str:
    cleaned = value.strip().rstrip(",").strip()
    if (cleaned.startswith("{") and cleaned.endswith("}")) or (cleaned.startswith('"') and cleaned.endswith('"')):
        cleaned = cleaned[1:-1]
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    replacements = {
        r"\\&": "&",
        r"\\%": "%",
        r"\\_": "_",
        "{": "",
        "}": "",
    }
    for old, new in replacements.items():
        cleaned = cleaned.replace(old, new)
    return cleaned


def _split_authors(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"\s+and\s+", value) if part.strip()]


def _parse_bibtex_entries(raw: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for match in BIBTEX_ENTRY_RE.finditer(raw):
        body = match.group("body").strip()
        if body.endswith("}"):
            body = body[:-1]
        fields: dict[str, Any] = {}
        for field in BIBTEX_FIELD_RE.finditer(body):
            name = field.group("name").lower()
            fields[name] = _clean_bibtex_value(field.group("value"))
        if "author" in fields:
            fields["authors"] = _split_authors(str(fields["author"]))
        if "keywords" in fields:
            fields["keywords"] = [part.strip() for part in re.split(r"[,;]", str(fields["keywords"])) if part.strip()]
        if "year" in fields:
            try:
                fields["year"] = int(str(fields["year"])[:4])
            except ValueError:
                pass
        entries.append({"entryType": match.group("type").lower(), "citekey": match.group("key").strip(), **fields})
    return entries


def _metadata_from_reference(item: dict[str, Any]) -> dict[str, Any]:
    metadata = dict(item)
    if "authors" not in metadata and metadata.get("creators"):
        creators = metadata.get("creators")
        if isinstance(creators, list):
            names = []
            for creator in creators:
                if isinstance(creator, dict):
                    full_name = creator.get("name") or " ".join(str(creator.get(part) or "").strip() for part in ["firstName", "lastName"]).strip()
                    if full_name:
                        names.append(full_name)
                elif creator:
                    names.append(str(creator))
            metadata["authors"] = names
    if "title" not in metadata and metadata.get("itemTitle"):
        metadata["title"] = metadata["itemTitle"]
    if "year" not in metadata and metadata.get("date"):
        year_match = re.search(r"\d{4}", str(metadata["date"]))
        if year_match:
            metadata["year"] = int(year_match.group(0))
    return metadata


def _reference_filename(metadata: dict[str, Any]) -> str:
    citekey = str(metadata.get("citekey") or metadata.get("citationKey") or metadata.get("key") or "").strip()
    if citekey:
        return _slug_filename(citekey)
    title = str(metadata.get("title") or "Untitled Reference")
    year = str(metadata.get("year") or "").strip()
    first_author = ""
    authors = _listify(metadata.get("authors"))
    if authors:
        first_author = str(authors[0]).split(",")[0].split()[-1]
    pieces = [piece for piece in [first_author, year, title[:60]] if piece]
    return _slug_filename(" - ".join(pieces))


def _reference_source_body(metadata: dict[str, Any], abstract: str = "", notes: str = "", content: str = "", attachment_path: str = "") -> str:
    lines = [f"# {metadata.get('title') or 'Untitled Reference'}", ""]
    authors = _listify(metadata.get("authors"))
    if authors:
        lines.extend(["## Citation", "", f"- Authors: {', '.join(str(author) for author in authors)}"])
        if metadata.get("year"):
            lines.append(f"- Year: {metadata['year']}")
        if metadata.get("doi"):
            lines.append(f"- DOI: {metadata['doi']}")
        if metadata.get("url"):
            lines.append(f"- URL: {metadata['url']}")
        lines.append("")
    attachment_paths = [str(item) for item in _listify(metadata.get("attachments")) if str(item).strip()]
    if attachment_path and attachment_path not in attachment_paths:
        attachment_paths.insert(0, attachment_path)
    if attachment_paths:
        lines.extend(["## Attachments", ""])
        lines.extend(f"- ![[{path}]]" for path in attachment_paths)
        lines.append("")
    if abstract:
        lines.extend(["## Abstract", "", abstract.strip(), ""])
    if notes:
        lines.extend(["## Notes", "", notes.strip(), ""])
    if content:
        lines.extend(["## Extracted Content", "", content.strip(), ""])
    return "\n".join(lines).strip() + "\n"


def _plain_note(value: str | None) -> str:
    if not value:
        return ""
    text = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    text = re.sub(r"</p\s*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


def _zotero_path_from_file_url(href: str | None) -> str:
    if not href:
        return ""
    parsed = urlparse(href)
    if parsed.scheme != "file":
        return ""
    if parsed.netloc:
        return unquote(f"//{parsed.netloc}{parsed.path}")
    return unquote(parsed.path.lstrip("/"))


def _zotero_api(path: str, params: dict[str, Any] | None = None, api_base: str = "") -> Any:
    base = (api_base or ZOTERO_API_BASE).rstrip("/")
    query = f"?{urlencode(_clean_cli_params(params or {}), doseq=True)}" if params else ""
    request = Request(f"{base}/{path.lstrip('/')}{query}", headers={"Zotero-API-Version": "3"})
    with urlopen(request, timeout=ZOTERO_TIMEOUT) as response:  # noqa: S310 - local user-configured API endpoint
        payload = response.read()
    if not payload:
        return None
    return json.loads(payload.decode("utf-8"))


def _zotero_item_summary(item: dict[str, Any]) -> dict[str, Any]:
    data = item.get("data", {})
    links = item.get("links", {})
    enclosure_href = links.get("enclosure", {}).get("href")
    return {
        "key": item.get("key") or data.get("key"),
        "version": item.get("version") or data.get("version"),
        "itemType": data.get("itemType"),
        "title": data.get("title"),
        "date": data.get("date"),
        "creators": data.get("creators", []),
        "publicationTitle": data.get("publicationTitle") or data.get("conferenceName"),
        "doi": data.get("DOI") or data.get("doi"),
        "url": data.get("url"),
        "abstract": data.get("abstractNote"),
        "tags": [tag.get("tag") for tag in data.get("tags", []) if tag.get("tag")],
        "parentItem": data.get("parentItem"),
        "note": _plain_note(data.get("note")) if data.get("itemType") == "note" else "",
        "annotationText": data.get("annotationText"),
        "annotationComment": data.get("annotationComment"),
        "attachmentPath": data.get("path") or _zotero_path_from_file_url(enclosure_href),
        "contentType": data.get("contentType"),
        "links": links,
        "rawData": data,
    }


def _resolve_zotero_attachment_path(attachment: dict[str, Any]) -> Path:
    path_value = str(attachment.get("rawData", {}).get("path") or attachment.get("attachmentPath") or "")
    if not path_value:
        raise ValueError("Attachment does not expose a local path through the Zotero API.")
    if path_value.startswith("storage:"):
        storage_root = Path(os.environ.get("ZOTERO_STORAGE_DIR", Path.home() / "Zotero" / "storage"))
        return storage_root / str(attachment["key"]) / path_value.replace("storage:", "", 1)
    return Path(path_value).expanduser()


def _extract_pdf_text_from_path(pdf_path: Path, max_pages: int = 5) -> dict[str, Any]:
    if not pdf_path.exists():
        return {"ok": False, "path": str(pdf_path), "error": "PDF file was not found on disk."}
    try:
        try:
            from pypdf import PdfReader  # type: ignore
        except Exception:
            from PyPDF2 import PdfReader  # type: ignore
        reader = PdfReader(str(pdf_path))
        page_count = len(reader.pages)
        pages_to_read = min(max(1, max_pages), page_count)
        parts = []
        for index in range(pages_to_read):
            parts.append(reader.pages[index].extract_text() or "")
        return {"ok": True, "path": str(pdf_path), "pagesRead": pages_to_read, "pageCount": page_count, "text": "\n\n".join(parts).strip()}
    except Exception as exc:
        return {"ok": False, "path": str(pdf_path), "error": str(exc)}


def _zotero_notes_and_annotations(children: dict[str, list[dict[str, Any]]]) -> str:
    lines: list[str] = []
    notes = children.get("notes", [])
    annotations = children.get("annotations", [])
    if notes:
        lines.extend(["## Zotero Notes", ""])
        for note in notes:
            lines.extend([f"### Note {note.get('key')}", "", str(note.get("note") or "").strip(), ""])
    if annotations:
        lines.extend(["## Zotero Annotations", ""])
        for annotation in annotations:
            text = str(annotation.get("annotationText") or "").strip()
            comment = str(annotation.get("annotationComment") or "").strip()
            if text:
                lines.append(f"- {text}")
            if comment:
                lines.append(f"  - Comment: {comment}")
        lines.append("")
    return "\n".join(lines).strip()


def _markdown_excerpt(markdown: str, max_chars: int = 800) -> str:
    lines: list[str] = []
    for line in markdown.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("!") or stripped.startswith("|"):
            continue
        lines.append(stripped)
        if sum(len(item) for item in lines) >= max_chars:
            break
    return " ".join(lines)[:max_chars]


def _property_config(names: list[tuple[str, str]]) -> dict[str, dict[str, str]]:
    return {name: {"displayName": display} for name, display in names}


def _base_template(template: str, options: dict[str, Any]) -> dict[str, Any]:
    folder = str(options.get("folder") or "").strip("/")
    tag = str(options.get("tag") or "").strip().lstrip("#")
    title = str(options.get("title") or "").strip()
    limit = int(options.get("limit") or 200)

    if template == "literature":
        return {
            "filters": _base_filter(folder or "literature", tag or "literature"),
            "properties": _property_config(
                [
                    ("file.name", "File"),
                    ("title", "Title"),
                    ("authors", "Authors"),
                    ("year", "Year"),
                    ("doi", "DOI"),
                    ("status", "Status"),
                    ("topics", "Topics"),
                    ("rating", "Rating"),
                ]
            ),
            "views": [
                {
                    "type": "table",
                    "name": title or "Literature",
                    "limit": limit,
                    "order": ["file.name", "title", "authors", "year", "doi", "status", "topics", "rating"],
                },
                {
                    "type": "cards",
                    "name": "By topic",
                    "limit": limit,
                    "groupBy": {"property": "topics", "direction": "ASC"},
                    "order": ["title", "authors", "year", "status"],
                },
            ],
        }
    if template == "project_tasks":
        return {
            "filters": _base_filter(folder or "tasks", tag or "task"),
            "formulas": {"days_until_due": 'if(due, ((date(due) - today()) / 86400000).round(0))'},
            "properties": _property_config(
                [
                    ("file.name", "Task"),
                    ("status", "Status"),
                    ("priority", "Priority"),
                    ("owner", "Owner"),
                    ("due", "Due"),
                    ("formula.days_until_due", "Days Left"),
                    ("project", "Project"),
                ]
            ),
            "views": [
                {
                    "type": "table",
                    "name": title or "Project tasks",
                    "limit": limit,
                    "groupBy": {"property": "status", "direction": "ASC"},
                    "order": ["file.name", "status", "priority", "owner", "due", "formula.days_until_due", "project"],
                },
                {
                    "type": "cards",
                    "name": "By owner",
                    "limit": limit,
                    "groupBy": {"property": "owner", "direction": "ASC"},
                    "order": ["file.name", "status", "priority", "due"],
                },
            ],
        }
    if template == "equipment":
        return {
            "filters": _base_filter(folder or "equipment", tag or "equipment"),
            "summaries": {"total_cost": "values.sum()"},
            "properties": _property_config(
                [
                    ("file.name", "Equipment"),
                    ("tag_no", "Tag No."),
                    ("service", "Service"),
                    ("area", "Area"),
                    ("status", "Status"),
                    ("cost", "Cost"),
                    ("vendor", "Vendor"),
                ]
            ),
            "views": [
                {
                    "type": "table",
                    "name": title or "Equipment list",
                    "limit": limit,
                    "groupBy": {"property": "area", "direction": "ASC"},
                    "order": ["file.name", "tag_no", "service", "area", "status", "cost", "vendor"],
                    "summaries": {"cost": "total_cost"},
                }
            ],
        }
    if template == "utilities":
        return {
            "filters": _base_filter(folder or "utilities", tag or "utility"),
            "properties": _property_config(
                [
                    ("file.name", "Utility"),
                    ("type", "Type"),
                    ("supply_temp", "Supply Temp"),
                    ("return_temp", "Return Temp"),
                    ("pressure", "Pressure"),
                    ("flowrate", "Flowrate"),
                    ("cost_basis", "Cost Basis"),
                ]
            ),
            "views": [
                {
                    "type": "table",
                    "name": title or "Utilities",
                    "limit": limit,
                    "groupBy": {"property": "type", "direction": "ASC"},
                    "order": ["file.name", "type", "supply_temp", "return_temp", "pressure", "flowrate", "cost_basis"],
                }
            ],
        }
    if template == "economics":
        return {
            "filters": _base_filter(folder or "economics", tag or "economics"),
            "formulas": {"annualized_cost": "if(capex && lifetime, capex / lifetime + if(opex, opex, 0))"},
            "summaries": {"sum": "values.sum()"},
            "properties": _property_config(
                [
                    ("file.name", "Item"),
                    ("category", "Category"),
                    ("capex", "CAPEX"),
                    ("opex", "OPEX"),
                    ("lifetime", "Lifetime"),
                    ("formula.annualized_cost", "Annualized Cost"),
                    ("basis", "Basis"),
                ]
            ),
            "views": [
                {
                    "type": "table",
                    "name": title or "Economics",
                    "limit": limit,
                    "groupBy": {"property": "category", "direction": "ASC"},
                    "order": ["file.name", "category", "capex", "opex", "lifetime", "formula.annualized_cost", "basis"],
                    "summaries": {"capex": "sum", "opex": "sum"},
                }
            ],
        }
    if template == "sources":
        return {
            "filters": _base_filter(folder or "sources", tag or "source"),
            "properties": _property_config(
                [
                    ("file.name", "Source"),
                    ("title", "Title"),
                    ("type", "Type"),
                    ("entities", "Entities"),
                    ("concepts", "Concepts"),
                    ("doi", "DOI"),
                    ("file.mtime", "Updated"),
                ]
            ),
            "views": [
                {
                    "type": "table",
                    "name": title or "Sources",
                    "limit": limit,
                    "order": ["file.name", "title", "type", "entities", "concepts", "doi", "file.mtime"],
                },
                {
                    "type": "cards",
                    "name": "By type",
                    "limit": limit,
                    "groupBy": {"property": "type", "direction": "ASC"},
                    "order": ["title", "entities", "concepts"],
                },
            ],
        }
    raise ValueError(f"Unknown base template: {template}. Available templates: {', '.join(BASE_TEMPLATE_DESCRIPTIONS)}")


def _canvas_node_id(rel_path: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]+", "-", _wikilink_target(rel_path)).strip("-").lower()
    return f"note-{safe or 'root'}"


def _canvas_edge_id(source: str, target: str, index: int) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]+", "-", f"{source}-to-{target}-{index}").strip("-").lower()
    return f"edge-{safe or index}"


def _canvas_position(index: int, count: int, layout: str, width: int, height: int, spacing_x: int, spacing_y: int) -> tuple[int, int]:
    if layout == "radial":
        radius = max(spacing_x, int(count * 52))
        angle = (2 * math.pi * index) / max(1, count)
        return int(math.cos(angle) * radius), int(math.sin(angle) * radius)
    columns = max(1, math.ceil(math.sqrt(max(1, count))))
    row = index // columns
    column = index % columns
    return column * (width + spacing_x), row * (height + spacing_y)


def _canvas_group_key(node: dict[str, Any], mode: str) -> str:
    if mode == "folder":
        folder = Path(str(node["id"])).parent.as_posix()
        return folder if folder != "." else "Vault root"
    tags = [str(tag) for tag in node.get("tags", [])]
    for preferred in ["source", "entity", "concept", "task", "equipment", "economics", "literature", "utility"]:
        if preferred in tags:
            return preferred
    return tags[0] if tags else "untagged"


def _canvas_group_id(name: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]+", "-", name).strip("-").lower()
    return f"group-{safe or 'default'}"


def _canvas_color_for_tags(tags: list[str]) -> str:
    if any(tag in tags for tag in ["source", "literature"]):
        return "5"
    if "entity" in tags:
        return "4"
    if "concept" in tags:
        return "6"
    if "task" in tags:
        return "2"
    return "1"


def _schema_type_matches(value: Any, expected: str) -> bool:
    if expected == "any":
        return True
    if expected == "str":
        return isinstance(value, str) and bool(value.strip())
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "bool":
        return isinstance(value, bool)
    if expected == "list":
        return isinstance(value, list)
    if expected == "dict":
        return isinstance(value, dict)
    if expected == "list_or_str":
        return isinstance(value, (list, str)) and bool(_listify(value))
    return True


def _validate_schema_for_props(rel_path: str, props: dict[str, Any], schema: dict[str, Any], severity: str = "error") -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for section, default_severity in [("required", severity), ("recommended", "info")]:
        expected_fields = schema.get(section, {})
        if not isinstance(expected_fields, dict):
            continue
        for key, expected_type in expected_fields.items():
            if key not in props or props.get(key) in (None, ""):
                issues.append({"path": rel_path, "field": key, "expected": expected_type, "severity": default_severity, "message": f"Missing {section} property."})
                continue
            if not _schema_type_matches(props.get(key), str(expected_type)):
                issues.append(
                    {
                        "path": rel_path,
                        "field": key,
                        "expected": expected_type,
                        "actual": type(props.get(key)).__name__,
                        "severity": default_severity,
                        "message": "Property type does not match schema.",
                    }
                )
    return issues


def _infer_schema_key(rel_path: str, props: dict[str, Any]) -> str:
    explicit = str(props.get("type") or "").strip().lower()
    if explicit:
        return explicit
    parts = [part.lower() for part in Path(rel_path).parts[:-1]]
    folder_map = {
        "sources": "source",
        "source": "source",
        "literature": "literature",
        "papers": "literature",
        "zotero": "literature",
        "entities": "entity",
        "entity": "entity",
        "concepts": "concept",
        "concept": "concept",
        "projects": "project",
        "project": "project",
        "tasks": "task",
        "task": "task",
        "equipment": "equipment",
        "utilities": "utility",
        "utility": "utility",
        "economics": "economics",
    }
    for part in reversed(parts):
        if part in folder_map:
            return folder_map[part]
    return ""


def _schema_default_value(rel_path: str, schema_key: str, field: str, expected_type: str, defaults: dict[str, Any]) -> Any:
    for key in (f"{schema_key}.{field}", field):
        if key in defaults:
            return defaults[key]
    if field == "title":
        return _note_title_from_path(rel_path)
    if field == "type" and schema_key:
        return schema_key
    if field == "tags":
        return [schema_key] if schema_key else []
    if expected_type == "list":
        return []
    if expected_type == "number":
        return 0
    if expected_type == "bool":
        return False
    if expected_type == "dict":
        return {}
    return ""


def _validate_canvas_payload(rel_path: str, payload: Any) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if not isinstance(payload, dict):
        return [{"path": rel_path, "severity": "error", "message": "Canvas root must be an object."}]
    nodes = payload.get("nodes", [])
    edges = payload.get("edges", [])
    if not isinstance(nodes, list):
        issues.append({"path": rel_path, "severity": "error", "message": "Canvas nodes must be an array."})
        nodes = []
    if not isinstance(edges, list):
        issues.append({"path": rel_path, "severity": "error", "message": "Canvas edges must be an array."})
        edges = []
    node_ids: set[str] = set()
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            issues.append({"path": rel_path, "severity": "error", "message": f"Node {index} must be an object."})
            continue
        for key in ["id", "type", "x", "y", "width", "height"]:
            if key not in node:
                issues.append({"path": rel_path, "severity": "error", "node": node.get("id", index), "field": key, "message": "Canvas node is missing a required field."})
        if node.get("id") in node_ids:
            issues.append({"path": rel_path, "severity": "error", "node": node.get("id"), "message": "Duplicate Canvas node id."})
        if node.get("id"):
            node_ids.add(str(node["id"]))
    for index, edge in enumerate(edges):
        if not isinstance(edge, dict):
            issues.append({"path": rel_path, "severity": "error", "message": f"Edge {index} must be an object."})
            continue
        for key in ["id", "fromNode", "toNode"]:
            if key not in edge:
                issues.append({"path": rel_path, "severity": "error", "edge": edge.get("id", index), "field": key, "message": "Canvas edge is missing a required field."})
        if edge.get("fromNode") not in node_ids or edge.get("toNode") not in node_ids:
            issues.append({"path": rel_path, "severity": "error", "edge": edge.get("id", index), "message": "Canvas edge references a missing node."})
    return issues


def _validate_base_payload(rel_path: str, payload: Any) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if not isinstance(payload, dict):
        return [{"path": rel_path, "severity": "error", "message": "Base root must be a YAML object."}]
    views = payload.get("views")
    if not isinstance(views, list) or not views:
        issues.append({"path": rel_path, "severity": "error", "field": "views", "message": "Base must define at least one view."})
        return issues
    for index, view in enumerate(views):
        if not isinstance(view, dict):
            issues.append({"path": rel_path, "severity": "error", "view": index, "message": "Base view must be an object."})
            continue
        if view.get("type") not in {"table", "cards", "list", "map"}:
            issues.append({"path": rel_path, "severity": "error", "view": index, "field": "type", "message": "Base view type is invalid or missing."})
        if not view.get("name"):
            issues.append({"path": rel_path, "severity": "warning", "view": index, "field": "name", "message": "Base view should have a name."})
    return issues


def _plan_operations(plan_json: str) -> list[dict[str, Any]]:
    plan = _json(plan_json, [])
    if isinstance(plan, dict):
        operations = plan.get("operations", [])
    else:
        operations = plan
    if not isinstance(operations, list):
        raise ValueError("edit plan must be an array or an object with an operations array.")
    normalized: list[dict[str, Any]] = []
    for index, operation in enumerate(operations):
        if not isinstance(operation, dict):
            raise ValueError(f"Operation {index} must be an object.")
        op = str(operation.get("op") or operation.get("type") or "").strip().lower()
        path = str(operation.get("path") or "").strip()
        if op not in {"write", "update_properties", "append", "replace", "delete"}:
            raise ValueError(f"Operation {index} has unsupported op: {op}")
        if not path:
            raise ValueError(f"Operation {index} requires path.")
        normalized.append({**operation, "op": op, "path": path})
    return normalized


def _apply_operation_to_text(vault: Path, operation: dict[str, Any]) -> tuple[Path, str, str, bool]:
    full = _safe_path(vault, operation["path"])
    exists = full.exists()
    before = _read_text(full) if exists else ""
    op = operation["op"]
    if op == "write":
        if exists and not operation.get("overwrite", False):
            raise FileExistsError(f"{operation['path']} exists. Set overwrite=true for write operations.")
        after = str(operation.get("content") or "")
    elif op == "update_properties":
        props, body = _split_frontmatter(before)
        incoming = operation.get("properties", {})
        if not isinstance(incoming, dict):
            raise ValueError("update_properties operation requires object properties.")
        mode = str(operation.get("mode") or "merge")
        if mode == "replace":
            updated = incoming
        elif mode == "remove":
            updated = dict(props)
            for key in incoming:
                updated.pop(key, None)
        elif mode == "merge":
            updated = dict(props)
            updated.update(incoming)
        else:
            raise ValueError("update_properties mode must be merge, replace, or remove.")
        after = _join_frontmatter(updated, body)
    elif op == "append":
        separator = str(operation.get("separator", "\n"))
        after = before + separator + str(operation.get("content") or "") if before else str(operation.get("content") or "")
    elif op == "replace":
        old = str(operation.get("old") or "")
        new = str(operation.get("new") or "")
        if not old:
            raise ValueError("replace operation requires old.")
        count = int(operation.get("count") or -1)
        if old not in before and operation.get("required", True):
            raise ValueError(f"replace target not found in {operation['path']}")
        after = before.replace(old, new, count if count >= 0 else before.count(old))
    elif op == "delete":
        after = ""
    else:
        raise ValueError(f"Unsupported op: {op}")
    return full, before, after, exists


def _preview_edit_plan(vault: Path, operations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    previews: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    for index, operation in enumerate(operations):
        full, before, after, exists = _apply_operation_to_text(vault, operation)
        rel_path = _rel(vault, full)
        if rel_path in seen_paths:
            raise ValueError(f"Multiple operations target the same path in one plan: {rel_path}")
        seen_paths.add(rel_path)
        changed = (operation["op"] == "delete" and exists) or before != after
        previews.append(
            {
                "index": index,
                "op": operation["op"],
                "path": rel_path,
                "exists": exists,
                "changed": changed,
                "delete": operation["op"] == "delete",
                "diff": _diff_text(rel_path, before, "" if operation["op"] == "delete" else after),
            }
        )
    return previews


@mcp.tool()
def obsidian_vault_status(vault_path: str = "") -> dict[str, Any]:
    """Return basic information about a local Obsidian vault."""
    vault = _vault(vault_path)
    files = list(_iter_files(vault))
    md_count = sum(1 for path in files if path.suffix.lower() == ".md")
    canvas_count = sum(1 for path in files if path.suffix.lower() == ".canvas")
    base_count = sum(1 for path in files if path.suffix.lower() == ".base")
    return {
        "vaultPath": str(vault),
        "hasObsidianConfig": (vault / ".obsidian").exists(),
        "fileCount": len(files),
        "markdownCount": md_count,
        "canvasCount": canvas_count,
        "baseCount": base_count,
        "cliAvailable": shutil.which(os.environ.get("OBSIDIAN_CLI_COMMAND", "obsidian")) is not None,
    }


@mcp.tool()
def obsidian_list_files(
    vault_path: str = "",
    folder: str = "",
    extensions: str = ".md,.canvas,.base",
    include_hidden: bool = False,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """List vault files, optionally filtered by folder and comma-separated extensions."""
    vault = _vault(vault_path)
    wanted = _extension_set(extensions)
    rows: list[dict[str, Any]] = []
    for path in _iter_files(vault, folder, include_hidden):
        if wanted and path.suffix.lower() not in wanted:
            continue
        stat = path.stat()
        rows.append(
            {
                "path": _rel(vault, path),
                "name": path.name,
                "extension": path.suffix.lstrip("."),
                "size": stat.st_size,
                "modified": int(stat.st_mtime),
            }
        )
        if len(rows) >= max(1, limit):
            break
    return rows


@mcp.tool()
def obsidian_search(
    query: str,
    vault_path: str = "",
    folder: str = "",
    extensions: str = ".md",
    case_sensitive: bool = False,
    limit: int = 50,
    context_chars: int = 140,
) -> list[dict[str, Any]]:
    """Search text files in a vault and return matching line snippets."""
    vault = _vault(vault_path)
    wanted = _extension_set(extensions)
    needle = query if case_sensitive else query.lower()
    matches: list[dict[str, Any]] = []
    for path in _iter_files(vault, folder):
        if wanted and path.suffix.lower() not in wanted:
            continue
        try:
            lines = _read_text(path).splitlines()
        except UnicodeDecodeError:
            continue
        for number, line in enumerate(lines, start=1):
            haystack = line if case_sensitive else line.lower()
            index = haystack.find(needle)
            if index == -1:
                continue
            start = max(0, index - context_chars // 2)
            end = min(len(line), index + len(query) + context_chars // 2)
            matches.append({"path": _rel(vault, path), "line": number, "snippet": line[start:end].strip()})
            if len(matches) >= max(1, limit):
                return matches
    return matches


@mcp.tool()
def obsidian_read_file(path: str, vault_path: str = "", max_chars: int = 20000) -> dict[str, Any]:
    """Read a vault-relative file and parse Markdown frontmatter when present."""
    vault = _vault(vault_path)
    full = _safe_path(vault, path)
    if not full.exists():
        return {
            "path": _rel(vault, full),
            "exists": False,
            "properties": {},
            "content": "",
            "body": "",
            "truncated": False,
            "error": "File does not exist.",
        }
    text = _read_text(full)
    properties, body = _split_frontmatter(text) if full.suffix.lower() == ".md" else ({}, text)
    truncated = len(text) > max_chars
    return {
        "path": _rel(vault, full),
        "exists": full.exists(),
        "properties": properties,
        "content": text[:max_chars],
        "body": body[:max_chars] if full.suffix.lower() == ".md" else text[:max_chars],
        "truncated": truncated,
    }


@mcp.tool()
def obsidian_write_file(
    path: str,
    content: str,
    vault_path: str = "",
    overwrite: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Write a vault-relative file. Existing files require overwrite=true."""
    vault = _vault(vault_path)
    full = _safe_path(vault, path)
    if full.exists() and not overwrite:
        return {"ok": False, "path": _rel(vault, full), "error": "File exists. Pass overwrite=true to replace it."}
    return _write_result(vault, full, content, dry_run)


@mcp.tool()
def obsidian_create_note(
    path: str,
    title: str = "",
    body: str = "",
    properties_json: str = "{}",
    vault_path: str = "",
    overwrite: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Create a Markdown note with YAML properties."""
    vault = _vault(vault_path)
    rel_path = path if path.lower().endswith(".md") else f"{path}.md"
    full = _safe_path(vault, rel_path)
    if full.exists() and not overwrite:
        return {"ok": False, "path": _rel(vault, full), "error": "Note exists. Pass overwrite=true to replace it."}
    properties = _json(properties_json, {})
    if not isinstance(properties, dict):
        raise ValueError("properties_json must decode to an object.")
    note_title = title or properties.get("title") or _note_title_from_path(rel_path)
    properties.setdefault("title", note_title)
    content_body = body.strip()
    if content_body and not content_body.startswith("#"):
        content_body = f"# {note_title}\n\n{content_body}"
    elif not content_body:
        content_body = f"# {note_title}\n"
    content = _join_frontmatter(properties, content_body)
    result = _write_result(vault, full, content, dry_run)
    result["properties"] = properties
    return result


@mcp.tool()
def obsidian_update_properties(
    path: str,
    properties_json: str,
    vault_path: str = "",
    mode: str = "merge",
    dry_run: bool = False,
) -> dict[str, Any]:
    """Merge, replace, or remove YAML frontmatter properties on a Markdown note."""
    vault = _vault(vault_path)
    full = _safe_path(vault, path)
    text = _read_text(full)
    existing, body = _split_frontmatter(text)
    incoming = _json(properties_json, {})
    if not isinstance(incoming, dict):
        raise ValueError("properties_json must decode to an object.")
    if mode == "replace":
        updated = incoming
    elif mode == "remove":
        updated = dict(existing)
        for key in incoming:
            updated.pop(key, None)
    elif mode == "merge":
        updated = dict(existing)
        updated.update(incoming)
    else:
        raise ValueError("mode must be merge, replace, or remove.")
    result = _write_result(vault, full, _join_frontmatter(updated, body), dry_run)
    result["properties"] = updated
    return result


@mcp.tool()
def obsidian_add_wikilinks(
    path: str,
    links_json: str,
    vault_path: str = "",
    append_related: bool = True,
    replace_first_phrase: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Add wikilinks to a note by appending a related section or replacing exact phrases."""
    vault = _vault(vault_path)
    full = _safe_path(vault, path)
    text = _read_text(full)
    links = _json(links_json, [])
    if not isinstance(links, list):
        raise ValueError("links_json must decode to a list.")

    normalized_links: list[dict[str, str]] = []
    for item in links:
        if isinstance(item, str):
            normalized_links.append({"target": item, "label": ""})
        elif isinstance(item, dict) and item.get("target"):
            normalized_links.append({"target": str(item["target"]), "label": str(item.get("label") or ""), "phrase": str(item.get("phrase") or "")})

    changed = text
    replacements = 0
    if replace_first_phrase:
        for item in normalized_links:
            phrase = item.get("phrase") or item.get("label") or item["target"]
            link = f"[[{item['target']}|{phrase}]]" if phrase != item["target"] else f"[[{item['target']}]]"
            pattern = re.compile(rf"(?<!\[\[)\b{re.escape(phrase)}\b(?![^\[]*\]\])")
            changed, count = pattern.subn(link, changed, count=1)
            replacements += count

    appended: list[str] = []
    if append_related:
        existing_targets = {_target_from_link(match.group(1)).lower() for match in WIKILINK_RE.finditer(changed)}
        for item in normalized_links:
            target = item["target"]
            if _target_from_link(target).lower() in existing_targets:
                continue
            label = item.get("label") or target
            link = f"[[{target}|{label}]]" if label != target else f"[[{target}]]"
            appended.append(f"- {link}")
        if appended:
            section = "\n\n## Related\n\n" + "\n".join(appended) + "\n"
            changed = changed.rstrip() + section

    result = _write_result(vault, full, changed, dry_run)
    result["replacements"] = replacements
    result["appended"] = appended
    return result


@mcp.tool()
def obsidian_build_graph(
    vault_path: str = "",
    folder: str = "",
    include_tags: bool = True,
    write_json_path: str = "",
) -> dict[str, Any]:
    """Build graph data from Markdown wikilinks, embeds, frontmatter tags, and backlinks."""
    vault = _vault(vault_path)
    md_files = [path for path in _iter_files(vault, folder) if path.suffix.lower() == ".md"]
    known_by_key: dict[str, set[str]] = {}
    file_cache: dict[str, tuple[Path, str, dict[str, Any], str]] = {}
    for path in md_files:
        rel_path = _rel(vault, path)
        text = _read_text(path)
        props, body = _split_frontmatter(text)
        file_cache[rel_path] = (path, text, props, body)
        _add_note_key(known_by_key, rel_path, rel_path)
        _add_note_key(known_by_key, path.stem, rel_path)
        if props.get("title"):
            _add_note_key(known_by_key, str(props["title"]), rel_path)
        for alias in _frontmatter_aliases(props):
            _add_note_key(known_by_key, alias, rel_path)

    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    unresolved: dict[str, list[str]] = {}
    ambiguous: dict[str, list[dict[str, Any]]] = {}
    outgoing: dict[str, set[str]] = {}
    incoming: dict[str, set[str]] = {}
    tag_counts: dict[str, int] = {}

    for rel_path, (path, text, props, body) in file_cache.items():
        tags = sorted(set(_frontmatter_tags(props) + _inline_tags(body)))
        aliases = _frontmatter_aliases(props)
        nodes[rel_path] = {
            "id": rel_path,
            "type": "note",
            "title": props.get("title") or path.stem,
            "tags": tags,
            "aliases": aliases,
        }
        outgoing.setdefault(rel_path, set())
        incoming.setdefault(rel_path, set())
        for tag in tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
        for regex, kind in [(WIKILINK_RE, "wikilink"), (EMBED_RE, "embed")]:
            for match in regex.finditer(text):
                raw_target = _target_from_link(match.group(1))
                target_rel, ambiguous_targets = _resolve_note_key(known_by_key, raw_target)
                if target_rel:
                    edges.append({"source": rel_path, "target": target_rel, "kind": kind})
                    outgoing[rel_path].add(target_rel)
                    incoming.setdefault(target_rel, set()).add(rel_path)
                elif ambiguous_targets:
                    ambiguous.setdefault(raw_target, []).append({"source": rel_path, "matches": ambiguous_targets})
                else:
                    unresolved.setdefault(raw_target, []).append(rel_path)

    orphans = sorted([node_id for node_id in nodes if not incoming.get(node_id)])
    dead_ends = sorted([node_id for node_id in nodes if not outgoing.get(node_id)])
    backlinks = {node_id: sorted(incoming.get(node_id, set())) for node_id in nodes}
    duplicate_keys = {key: sorted(paths) for key, paths in sorted(known_by_key.items()) if len(paths) > 1}
    result: dict[str, Any] = {
        "vaultPath": str(vault),
        "nodeCount": len(nodes),
        "edgeCount": len(edges),
        "nodes": list(nodes.values()),
        "edges": edges,
        "backlinks": backlinks,
        "orphans": orphans,
        "deadEnds": dead_ends,
        "unresolved": unresolved,
        "ambiguous": ambiguous,
        "duplicateKeys": duplicate_keys,
    }
    if include_tags:
        result["tags"] = [{"tag": tag, "count": count} for tag, count in sorted(tag_counts.items())]
    if write_json_path:
        output = _safe_path(vault, write_json_path)
        _write_text(output, json.dumps(result, ensure_ascii=False, indent=2))
        result["writtenTo"] = _rel(vault, output)
    return result


@mcp.tool()
def obsidian_lint_vault(
    vault_path: str = "",
    folder: str = "",
    max_examples: int = 20,
    write_json_path: str = "",
) -> dict[str, Any]:
    """Check graph health, common wiki files, and frontmatter consistency."""
    vault = _vault(vault_path)
    graph = obsidian_build_graph(vault_path=str(vault), folder=folder, include_tags=True)
    md_files = [path for path in _iter_files(vault, folder) if path.suffix.lower() == ".md"]
    limit = max(1, max_examples)
    issues: list[dict[str, Any]] = []

    def add_issue(code: str, severity: str, message: str, examples: list[Any]) -> None:
        issues.append(
            {
                "code": code,
                "severity": severity,
                "message": message,
                "count": len(examples),
                "examples": examples[:limit],
            }
        )

    if graph["unresolved"]:
        examples = [{"target": target, "sources": sources[:limit]} for target, sources in graph["unresolved"].items()]
        add_issue("unresolved_links", "error", "Wikilinks point to notes that do not exist.", examples)

    if graph["ambiguous"]:
        examples = [{"target": target, "sources": entries[:limit]} for target, entries in graph["ambiguous"].items()]
        add_issue("ambiguous_links", "warning", "Wikilinks match multiple notes or aliases.", examples)

    if graph["duplicateKeys"]:
        examples = [{"key": key, "paths": paths} for key, paths in graph["duplicateKeys"].items()]
        add_issue("duplicate_note_keys", "warning", "Multiple notes share the same stem, title, or alias.", examples)

    if graph["orphans"]:
        add_issue("orphan_notes", "info", "Notes have no incoming wikilinks.", graph["orphans"])

    if graph["deadEnds"]:
        add_issue("dead_end_notes", "info", "Notes have no outgoing wikilinks or embeds.", graph["deadEnds"])

    missing_titles: list[str] = []
    missing_tags: list[str] = []
    empty_notes: list[str] = []
    invalid_tag_types: list[dict[str, str]] = []
    for path in md_files:
        rel_path = _rel(vault, path)
        text = _read_text(path)
        props, body = _split_frontmatter(text)
        if not props.get("title"):
            missing_titles.append(rel_path)
        if "tags" not in props and not _inline_tags(body):
            missing_tags.append(rel_path)
        elif "tags" in props and not isinstance(props.get("tags"), (list, str)):
            invalid_tag_types.append({"path": rel_path, "type": type(props.get("tags")).__name__})
        if not body.strip():
            empty_notes.append(rel_path)

    if missing_titles:
        add_issue("missing_titles", "info", "Notes do not define a title property.", missing_titles)
    if missing_tags:
        add_issue("missing_tags", "info", "Notes have no frontmatter tags or inline tags.", missing_tags)
    if invalid_tag_types:
        add_issue("invalid_tag_types", "warning", "Tag properties should be a string or list.", invalid_tag_types)
    if empty_notes:
        add_issue("empty_notes", "warning", "Notes have no body content after frontmatter.", empty_notes)

    root = _safe_path(vault, folder) if folder else vault
    missing_wiki_files = [name for name in ["index.md", "log.md"] if not (root / name).exists()]
    if missing_wiki_files:
        add_issue("missing_wiki_files", "info", "Karpathy-style wiki helpers are missing.", missing_wiki_files)

    summary = {
        "errorCount": sum(1 for issue in issues if issue["severity"] == "error"),
        "warningCount": sum(1 for issue in issues if issue["severity"] == "warning"),
        "infoCount": sum(1 for issue in issues if issue["severity"] == "info"),
    }
    result: dict[str, Any] = {
        "ok": summary["errorCount"] == 0,
        "vaultPath": str(vault),
        "folder": folder,
        "summary": summary,
        "issues": issues,
        "graph": {
            "nodeCount": graph["nodeCount"],
            "edgeCount": graph["edgeCount"],
            "tagCount": len(graph.get("tags", [])),
            "unresolvedCount": sum(len(sources) for sources in graph["unresolved"].values()),
            "ambiguousCount": sum(len(entries) for entries in graph["ambiguous"].values()),
            "orphanCount": len(graph["orphans"]),
            "deadEndCount": len(graph["deadEnds"]),
        },
    }
    if write_json_path:
        output = _safe_path(vault, write_json_path)
        _write_text(output, json.dumps(result, ensure_ascii=False, indent=2))
        result["writtenTo"] = _rel(vault, output)
    return result


@mcp.tool()
def obsidian_update_wiki_index(
    vault_path: str = "",
    folder: str = "",
    index_path: str = "index.md",
    dry_run: bool = False,
) -> dict[str, Any]:
    """Create or refresh a Karpathy-style wiki index with a generated note catalogue."""
    vault = _vault(vault_path)
    graph = obsidian_build_graph(vault_path=str(vault), folder=folder, include_tags=True)
    index_full = _safe_path(vault, index_path)
    index_rel = _rel(vault, index_full)
    log_rel = _ensure_md_path("log.md")
    excluded = {index_rel.lower(), log_rel.lower()}
    nodes = sorted(
        [node for node in graph["nodes"] if str(node["id"]).lower() not in excluded],
        key=lambda node: str(node["id"]).lower(),
    )
    tag_lines = [f"- `#{item['tag']}`: {item['count']}" for item in graph.get("tags", [])]
    note_lines: list[str] = []
    for node in nodes:
        tags = " ".join(f"`#{tag}`" for tag in node.get("tags", []))
        aliases = ", ".join(node.get("aliases", []))
        suffix_parts = [part for part in [tags, f"aliases: {aliases}" if aliases else ""] if part]
        suffix = f" - {'; '.join(suffix_parts)}" if suffix_parts else ""
        note_lines.append(f"- {_wikilink(str(node['id']), str(node.get('title') or Path(str(node['id'])).stem))}{suffix}")
    if not note_lines:
        note_lines = ["- No notes found yet."]
    if not tag_lines:
        tag_lines = ["- No tags found yet."]

    lines = [
        f"_Generated: {_utc_now()}_",
        "",
        "## Vault Summary",
        "",
        f"- Notes: {len(nodes)}",
        f"- Links: {graph['edgeCount']}",
        f"- Unresolved links: {sum(len(sources) for sources in graph['unresolved'].values())}",
        f"- Orphan notes: {len(graph['orphans'])}",
        f"- Dead ends: {len(graph['deadEnds'])}",
        "",
        "## Tags",
        "",
        *tag_lines,
        "",
        "## Notes",
        "",
        *note_lines,
    ]
    block = _generated_block(lines, marker_name="index")
    existing = _read_text(index_full) if index_full.exists() else ""
    content = _replace_block(existing, INDEX_START, INDEX_END, block, "Index")
    result = _write_result(vault, index_full, content, dry_run)
    result["noteCount"] = len(nodes)
    result["tagCount"] = len(graph.get("tags", []))
    return result


@mcp.tool()
def obsidian_append_wiki_log(
    message: str,
    vault_path: str = "",
    log_path: str = "log.md",
    event_type: str = "update",
    touched_paths_json: str = "[]",
    metadata_json: str = "{}",
    dry_run: bool = False,
) -> dict[str, Any]:
    """Append a chronological entry to a Karpathy-style wiki log."""
    vault = _vault(vault_path)
    full = _safe_path(vault, log_path)
    touched = _json(touched_paths_json, [])
    metadata = _json(metadata_json, {})
    if not isinstance(touched, list):
        raise ValueError("touched_paths_json must decode to an array.")
    if not isinstance(metadata, dict):
        raise ValueError("metadata_json must decode to an object.")

    timestamp = _utc_now()
    existing = _read_text(full) if full.exists() else "# Log\n"
    touched_links = ", ".join(_wikilink(_ensure_md_path(str(path))) for path in touched) if touched else "None"
    entry = [
        f"## {timestamp} - {event_type}",
        "",
        f"- Message: {message.strip()}",
        f"- Touched: {touched_links}",
    ]
    if metadata:
        entry.extend(["- Metadata:", ""])
        entry.extend(f"  - `{key}`: {value}" for key, value in metadata.items())
    content = existing.rstrip() + "\n\n" + "\n".join(entry).rstrip() + "\n"
    result = _write_result(vault, full, content, dry_run)
    result["timestamp"] = timestamp
    result["touched"] = touched
    return result


@mcp.tool()
def obsidian_ingest_source_note(
    source_path: str,
    content: str,
    vault_path: str = "",
    title: str = "",
    summary: str = "",
    metadata_json: str = "{}",
    entities_json: str = "[]",
    concepts_json: str = "[]",
    source_type: str = "source",
    entities_folder: str = "entities",
    concepts_folder: str = "concepts",
    index_path: str = "index.md",
    log_path: str = "log.md",
    overwrite: bool = False,
    update_index: bool = True,
    append_log: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Ingest a source note and link it to generated entity and concept pages."""
    vault = _vault(vault_path)
    source_rel = _ensure_md_path(source_path)
    source_full = _safe_path(vault, source_rel)
    if source_full.exists() and not overwrite:
        return {"ok": False, "path": _rel(vault, source_full), "error": "Source note exists. Pass overwrite=true to replace it."}

    metadata = _json(metadata_json, {})
    entities = _json(entities_json, [])
    concepts = _json(concepts_json, [])
    if not isinstance(metadata, dict):
        raise ValueError("metadata_json must decode to an object.")
    if not isinstance(entities, list) or not isinstance(concepts, list):
        raise ValueError("entities_json and concepts_json must decode to arrays.")

    source_title = title or str(metadata.get("title") or _note_title_from_path(source_rel))
    entity_items = [item for item in entities if _item_name(item)]
    concept_items = [item for item in concepts if _item_name(item)]
    entity_paths = [_item_path(item, entities_folder) for item in entity_items]
    concept_paths = [_item_path(item, concepts_folder) for item in concept_items]

    source_props = dict(metadata)
    source_props["title"] = source_title
    source_props["type"] = source_type
    source_props["tags"] = _merge_unique(source_props.get("tags"), ["source", source_type])
    if entity_paths:
        source_props["entities"] = entity_paths
    if concept_paths:
        source_props["concepts"] = concept_paths

    body_lines = [f"# {source_title}", ""]
    if summary.strip():
        body_lines.extend(["## Summary", "", summary.strip(), ""])
    if entity_items or concept_items:
        body_lines.extend(["## Linked Pages", ""])
        if entity_items:
            body_lines.append("### Entities")
            body_lines.extend(f"- {_wikilink(path, _item_name(item))}" for item, path in zip(entity_items, entity_paths))
            body_lines.append("")
        if concept_items:
            body_lines.append("### Concepts")
            body_lines.extend(f"- {_wikilink(path, _item_name(item))}" for item, path in zip(concept_items, concept_paths))
            body_lines.append("")
    body_lines.extend(["## Source Content", "", content.strip(), ""])
    source_content = _join_frontmatter(source_props, "\n".join(body_lines))

    writes: list[tuple[Path, str]] = [(source_full, source_content)]
    touched_paths = [source_rel]

    for kind, items, paths, folder_tag in [
        ("entity", entity_items, entity_paths, "entity"),
        ("concept", concept_items, concept_paths, "concept"),
    ]:
        for item, rel_path in zip(items, paths):
            full = _safe_path(vault, rel_path)
            existing = _read_text(full) if full.exists() else ""
            props, body = _split_frontmatter(existing)
            name = _item_name(item)
            props["title"] = props.get("title") or name
            props["type"] = props.get("type") or kind
            props["tags"] = _merge_unique(props.get("tags"), [folder_tag])
            props["sources"] = _merge_unique(props.get("sources"), [source_rel])
            summary_text = _item_summary(item)
            block_lines = [
                f"_Updated from {_wikilink(source_rel, source_title)} at {_utc_now()}._",
                "",
                "## Source Links",
                "",
                f"- {_wikilink(source_rel, source_title)}",
            ]
            if summary_text:
                block_lines.extend(["", "## Summary", "", summary_text])
            block = _generated_block(block_lines)
            if not body.strip():
                body = f"# {name}\n\n"
            new_body = _replace_block(body, GENERATED_START, GENERATED_END, block, name)
            writes.append((full, _join_frontmatter(props, new_body)))
            touched_paths.append(rel_path)

    result = _write_many(vault, writes, dry_run)
    result["sourcePath"] = source_rel
    result["entityPaths"] = entity_paths
    result["conceptPaths"] = concept_paths

    follow_up: list[dict[str, Any]] = []
    if update_index:
        follow_up.append(obsidian_update_wiki_index(vault_path=str(vault), index_path=index_path, dry_run=dry_run))
    if append_log:
        follow_up.append(
            obsidian_append_wiki_log(
                message=f"Ingested source note: {source_title}",
                vault_path=str(vault),
                log_path=log_path,
                event_type="ingest",
                touched_paths_json=json.dumps(touched_paths, ensure_ascii=False),
                metadata_json=json.dumps({"source": source_rel, "entities": len(entity_paths), "concepts": len(concept_paths)}, ensure_ascii=False),
                dry_run=dry_run,
            )
        )
    result["followUp"] = follow_up
    result["ok"] = result["ok"] and all(item.get("ok", False) for item in follow_up)
    return result


@mcp.tool()
def obsidian_parse_bibtex(
    bibtex: str,
) -> dict[str, Any]:
    """Parse BibTeX into normalized reference metadata."""
    entries = _parse_bibtex_entries(bibtex)
    return {"ok": True, "entryCount": len(entries), "entries": entries}


@mcp.tool()
def obsidian_ingest_reference(
    metadata_json: str,
    vault_path: str = "",
    source_folder: str = "literature",
    abstract: str = "",
    notes: str = "",
    content: str = "",
    attachment_path: str = "",
    entities_json: str = "[]",
    concepts_json: str = "[]",
    index_path: str = "index.md",
    log_path: str = "log.md",
    overwrite: bool = False,
    update_index: bool = True,
    append_log: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Ingest one literature/reference metadata object as a linked source note."""
    metadata_raw = _json(metadata_json, {})
    if not isinstance(metadata_raw, dict):
        raise ValueError("metadata_json must decode to an object.")
    metadata = _metadata_from_reference(metadata_raw)
    title = str(metadata.get("title") or "Untitled Reference")
    rel_path = f"{source_folder.strip('/')}/{_reference_filename(metadata)}.md"
    tags = _merge_unique(metadata.get("tags"), ["source", "literature"])
    source_props = dict(metadata)
    source_props["type"] = "literature"
    source_props["tags"] = tags
    if attachment_path:
        source_props["attachment"] = attachment_path
    body = _reference_source_body(metadata, abstract=abstract or str(metadata.get("abstract") or ""), notes=notes, content=content, attachment_path=attachment_path)
    result = obsidian_ingest_source_note(
        source_path=rel_path,
        content=body,
        vault_path=vault_path,
        title=title,
        summary=str(metadata.get("abstract") or abstract or "")[:800],
        metadata_json=json.dumps(source_props, ensure_ascii=False),
        entities_json=entities_json,
        concepts_json=concepts_json,
        source_type="literature",
        index_path=index_path,
        log_path=log_path,
        overwrite=overwrite,
        update_index=update_index,
        append_log=append_log,
        dry_run=dry_run,
    )
    result["referencePath"] = rel_path
    result["metadata"] = metadata
    return result


@mcp.tool()
def obsidian_ingest_bibtex(
    bibtex: str,
    vault_path: str = "",
    source_folder: str = "literature",
    index_path: str = "index.md",
    log_path: str = "log.md",
    overwrite: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Ingest one or more BibTeX entries as literature source notes."""
    entries = _parse_bibtex_entries(bibtex)
    results: list[dict[str, Any]] = []
    for entry in entries:
        results.append(
            obsidian_ingest_reference(
                metadata_json=json.dumps(entry, ensure_ascii=False),
                vault_path=vault_path,
                source_folder=source_folder,
                index_path=index_path,
                log_path=log_path,
                overwrite=overwrite,
                update_index=True,
                append_log=True,
                dry_run=dry_run,
            )
        )
    return {"ok": all(item.get("ok", False) for item in results), "entryCount": len(entries), "results": results, "dryRun": dry_run}


@mcp.tool()
def obsidian_ingest_mineru_markdown(
    markdown_content: str = "",
    markdown_path: str = "",
    pdf_attachment_path: str = "",
    vault_path: str = "",
    source_path: str = "",
    title: str = "",
    metadata_json: str = "{}",
    entities_json: str = "[]",
    concepts_json: str = "[]",
    index_path: str = "index.md",
    log_path: str = "log.md",
    overwrite: bool = False,
    update_index: bool = True,
    append_log: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Ingest MinerU Markdown output and optional PDF attachment as a linked source note."""
    vault = _vault(vault_path)
    metadata = _json(metadata_json, {})
    if not isinstance(metadata, dict):
        raise ValueError("metadata_json must decode to an object.")
    content = markdown_content
    if markdown_path:
        content = _read_text(_safe_path(vault, markdown_path))
    if not content.strip():
        raise ValueError("markdown_content or markdown_path is required.")
    source_title = title or str(metadata.get("title") or _note_title_from_path(markdown_path or "MinerU Extraction.md"))
    rel_path = source_path.strip() or f"sources/mineru/{_slug_filename(source_title)}.md"
    props = dict(metadata)
    props["type"] = "mineru"
    props["tags"] = _merge_unique(props.get("tags"), ["source", "mineru"])
    if markdown_path:
        props["mineru_markdown"] = markdown_path
    if pdf_attachment_path:
        props["attachment"] = pdf_attachment_path
    body_parts = [f"# {source_title}", ""]
    if pdf_attachment_path:
        body_parts.extend(["## PDF Attachment", "", f"- ![[{pdf_attachment_path}]]", ""])
    body_parts.extend(["## MinerU Markdown", "", content.strip(), ""])
    result = obsidian_ingest_source_note(
        source_path=rel_path,
        content="\n".join(body_parts),
        vault_path=str(vault),
        title=source_title,
        summary=str(metadata.get("summary") or _markdown_excerpt(content)),
        metadata_json=json.dumps(props, ensure_ascii=False),
        entities_json=entities_json,
        concepts_json=concepts_json,
        source_type="mineru",
        index_path=index_path,
        log_path=log_path,
        overwrite=overwrite,
        update_index=update_index,
        append_log=append_log,
        dry_run=dry_run,
    )
    result["sourcePath"] = rel_path
    result["markdownPath"] = markdown_path
    result["pdfAttachmentPath"] = pdf_attachment_path
    return result


@mcp.tool()
def obsidian_ingest_pdf_attachment(
    pdf_attachment_path: str,
    vault_path: str = "",
    source_path: str = "",
    title: str = "",
    metadata_json: str = "{}",
    notes: str = "",
    entities_json: str = "[]",
    concepts_json: str = "[]",
    index_path: str = "index.md",
    log_path: str = "log.md",
    overwrite: bool = False,
    update_index: bool = True,
    append_log: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Create a source note for a PDF attachment that is already in the vault."""
    vault = _vault(vault_path)
    pdf_full = _safe_path(vault, pdf_attachment_path)
    if not pdf_full.exists() and not dry_run:
        raise FileNotFoundError(f"PDF attachment not found: {pdf_attachment_path}")
    metadata = _json(metadata_json, {})
    if not isinstance(metadata, dict):
        raise ValueError("metadata_json must decode to an object.")
    source_title = title or str(metadata.get("title") or _note_title_from_path(pdf_attachment_path))
    rel_path = source_path.strip() or f"sources/pdf/{_slug_filename(source_title)}.md"
    props = dict(metadata)
    props["type"] = "pdf"
    props["tags"] = _merge_unique(props.get("tags"), ["source", "pdf"])
    props["attachment"] = pdf_attachment_path
    body = _reference_source_body(props, abstract=str(metadata.get("abstract") or ""), notes=notes, attachment_path=pdf_attachment_path)
    result = obsidian_ingest_source_note(
        source_path=rel_path,
        content=body,
        vault_path=str(vault),
        title=source_title,
        summary=str(metadata.get("abstract") or notes or ""),
        metadata_json=json.dumps(props, ensure_ascii=False),
        entities_json=entities_json,
        concepts_json=concepts_json,
        source_type="pdf",
        index_path=index_path,
        log_path=log_path,
        overwrite=overwrite,
        update_index=update_index,
        append_log=append_log,
        dry_run=dry_run,
    )
    result["sourcePath"] = rel_path
    result["pdfAttachmentPath"] = pdf_attachment_path
    return result


@mcp.tool()
def obsidian_zotero_ping(
    api_base: str = "",
) -> dict[str, Any]:
    """Check whether Zotero Desktop local API is reachable."""
    base = (api_base or ZOTERO_API_BASE).rstrip("/")
    try:
        items = _zotero_api("users/0/items", {"limit": 1, "format": "json"}, base)
        return {"ok": True, "api": base, "sampleCount": len(items or [])}
    except Exception as exc:
        return {"ok": False, "api": base, "error": str(exc)}


@mcp.tool()
def obsidian_zotero_search_items(
    query: str = "",
    item_type: str = "",
    tag: str = "",
    limit: int = 25,
    api_base: str = "",
) -> list[dict[str, Any]]:
    """Search local Zotero items by query, type, or tag."""
    params: dict[str, Any] = {"limit": max(1, min(limit, 100)), "format": "json"}
    if query:
        params["q"] = query
    if item_type:
        params["itemType"] = item_type
    if tag:
        params["tag"] = tag
    return [_zotero_item_summary(item) for item in _zotero_api("users/0/items", params, api_base) or []]


@mcp.tool()
def obsidian_zotero_get_item(
    key: str,
    api_base: str = "",
) -> dict[str, Any]:
    """Get one Zotero item by key."""
    item = _zotero_api(f"users/0/items/{key}", {"format": "json"}, api_base)
    return _zotero_item_summary(item)


@mcp.tool()
def obsidian_zotero_get_children(
    parent_key: str,
    api_base: str = "",
) -> dict[str, list[dict[str, Any]]]:
    """Get notes, annotations, attachments, and other child items for one Zotero item."""
    children = [_zotero_item_summary(item) for item in _zotero_api(f"users/0/items/{parent_key}/children", {"format": "json", "limit": 100}, api_base) or []]
    grouped = {"notes": [], "annotations": [], "attachments": [], "other": []}
    for child in children:
        item_type = child.get("itemType")
        if item_type == "note":
            grouped["notes"].append(child)
        elif item_type == "annotation":
            grouped["annotations"].append(child)
        elif item_type == "attachment":
            grouped["attachments"].append(child)
        else:
            grouped["other"].append(child)
    return grouped


@mcp.tool()
def obsidian_zotero_list_pdf_attachments(
    parent_key: str = "",
    query: str = "",
    limit: int = 50,
    api_base: str = "",
) -> list[dict[str, Any]]:
    """List Zotero PDF attachments, optionally under a parent item."""
    if parent_key:
        items = _zotero_api(f"users/0/items/{parent_key}/children", {"format": "json", "limit": 100}, api_base) or []
    else:
        params: dict[str, Any] = {"itemType": "attachment", "limit": max(1, min(limit, 100)), "format": "json"}
        if query:
            params["q"] = query
        items = _zotero_api("users/0/items", params, api_base) or []
    summaries = [_zotero_item_summary(item) for item in items]
    return [item for item in summaries if item.get("contentType") == "application/pdf" or str(item.get("attachmentPath") or "").lower().endswith(".pdf")]


@mcp.tool()
def obsidian_zotero_extract_pdf_text(
    attachment_key: str,
    max_pages: int = 5,
    api_base: str = "",
) -> dict[str, Any]:
    """Extract text from a Zotero PDF attachment key if a PDF reader library is installed."""
    attachment = obsidian_zotero_get_item(attachment_key, api_base)
    return _extract_pdf_text_from_path(_resolve_zotero_attachment_path(attachment), max_pages)


@mcp.tool()
def obsidian_ingest_zotero_item(
    key: str,
    vault_path: str = "",
    source_folder: str = "literature",
    attachments_folder: str = "attachments/zotero",
    copy_pdf_attachments: bool = False,
    include_child_notes: bool = True,
    include_annotations: bool = True,
    include_pdf_text: bool = False,
    max_pdf_pages: int = 5,
    entities_json: str = "[]",
    concepts_json: str = "[]",
    index_path: str = "index.md",
    log_path: str = "log.md",
    overwrite: bool = False,
    dry_run: bool = False,
    api_base: str = "",
) -> dict[str, Any]:
    """Fetch a Zotero item and ingest it as a literature note in the vault."""
    vault = _vault(vault_path)
    item = obsidian_zotero_get_item(key, api_base)
    children = obsidian_zotero_get_children(key, api_base)
    metadata = _metadata_from_reference(item)
    metadata["zoteroKey"] = key
    metadata["tags"] = _merge_unique(metadata.get("tags"), ["source", "literature", "zotero"])
    notes_content = _zotero_notes_and_annotations(
        {
            "notes": children.get("notes", []) if include_child_notes else [],
            "annotations": children.get("annotations", []) if include_annotations else [],
        }
    )
    attachment_path = ""
    copied_attachments: list[str] = []
    linked_attachments: list[str] = []
    zotero_attachment_paths: list[str] = []
    attachment_errors: list[dict[str, str]] = []
    pdf_text_parts: list[str] = []
    for attachment in children.get("attachments", []):
        if attachment.get("contentType") != "application/pdf" and not str(attachment.get("attachmentPath") or "").lower().endswith(".pdf"):
            continue
        try:
            source_pdf = _resolve_zotero_attachment_path(attachment)
        except Exception as exc:
            attachment_errors.append({"key": str(attachment.get("key") or ""), "title": str(attachment.get("title") or ""), "error": str(exc)})
            continue
        if copy_pdf_attachments:
            dest_rel = f"{attachments_folder.strip('/')}/{key}/{_slug_filename(source_pdf.name)}"
            dest = _safe_path(vault, dest_rel)
            if not dry_run:
                dest.parent.mkdir(parents=True, exist_ok=True)
                if source_pdf.exists():
                    shutil.copy2(source_pdf, dest)
                else:
                    attachment_errors.append({"key": str(attachment.get("key") or ""), "title": str(attachment.get("title") or source_pdf.name), "error": f"PDF file was not found on disk: {source_pdf}"})
                    continue
            copied_attachments.append(dest_rel)
            linked_attachments.append(dest_rel)
            if not attachment_path:
                attachment_path = dest_rel
        else:
            source_path = str(source_pdf)
            zotero_attachment_paths.append(source_path)
        if include_pdf_text:
            extracted = _extract_pdf_text_from_path(source_pdf, max_pdf_pages)
            if extracted.get("ok") and extracted.get("text"):
                pdf_text_parts.append(f"## PDF Text: {attachment.get('title') or source_pdf.name}\n\n{extracted['text']}")
            elif not extracted.get("ok"):
                attachment_errors.append({"key": str(attachment.get("key") or ""), "title": str(attachment.get("title") or source_pdf.name), "error": str(extracted.get("error") or "PDF text extraction failed.")})
    if linked_attachments:
        metadata["attachments"] = linked_attachments
    if zotero_attachment_paths:
        metadata["zoteroAttachmentPaths"] = zotero_attachment_paths
    attachment_content = ""
    if attachment_errors:
        lines = ["## Attachment Import Warnings", ""]
        for item in attachment_errors:
            title = item.get("title") or item.get("key") or "attachment"
            lines.append(f"- {title}: {item.get('error')}")
        attachment_content = "\n".join(lines)
    content = "\n\n".join(part for part in [notes_content, attachment_content, *pdf_text_parts] if part)
    result = obsidian_ingest_reference(
        metadata_json=json.dumps(metadata, ensure_ascii=False),
        vault_path=str(vault),
        source_folder=source_folder,
        abstract=str(item.get("abstract") or ""),
        notes=notes_content,
        content="\n\n".join(part for part in [attachment_content, *pdf_text_parts] if part),
        attachment_path=attachment_path,
        entities_json=entities_json,
        concepts_json=concepts_json,
        index_path=index_path,
        log_path=log_path,
        overwrite=overwrite,
        update_index=True,
        append_log=True,
        dry_run=dry_run,
    )
    result["zoteroKey"] = key
    result["children"] = {"notes": len(children.get("notes", [])), "annotations": len(children.get("annotations", [])), "attachments": len(children.get("attachments", []))}
    result["copiedAttachments"] = copied_attachments
    result["linkedAttachments"] = linked_attachments
    result["zoteroAttachmentPaths"] = zotero_attachment_paths
    result["attachmentErrors"] = attachment_errors
    result["includedContentChars"] = len(content)
    return result


@mcp.tool()
def obsidian_list_schema_presets() -> dict[str, Any]:
    """List built-in frontmatter schema presets."""
    return dict(SCHEMA_PRESETS)


@mcp.tool()
def obsidian_validate_vault_schema(
    vault_path: str = "",
    folder: str = "",
    schemas_json: str = "{}",
    validate_canvas: bool = True,
    validate_bases: bool = True,
    write_json_path: str = "",
) -> dict[str, Any]:
    """Validate Markdown frontmatter schemas plus Canvas and Base file structure."""
    vault = _vault(vault_path)
    custom_schemas = _json(schemas_json, {})
    if not isinstance(custom_schemas, dict):
        raise ValueError("schemas_json must decode to an object.")
    schemas = dict(SCHEMA_PRESETS)
    schemas.update(custom_schemas)
    issues: list[dict[str, Any]] = []
    checked = {"markdown": 0, "canvas": 0, "bases": 0}

    for path in _iter_files(vault, folder):
        rel_path = _rel(vault, path)
        suffix = path.suffix.lower()
        if suffix == ".md":
            checked["markdown"] += 1
            text = _read_text(path)
            props, _ = _split_frontmatter(text)
            schema_key = str(props.get("type") or "").strip().lower()
            if not props:
                issues.append({"path": rel_path, "severity": "warning", "message": "Markdown note has no frontmatter."})
                continue
            if schema_key and schema_key in schemas:
                issues.extend(_validate_schema_for_props(rel_path, props, schemas[schema_key]))
            elif schema_key:
                issues.append({"path": rel_path, "severity": "info", "field": "type", "value": schema_key, "message": "No schema preset exists for this note type."})
            else:
                issues.extend(_validate_schema_for_props(rel_path, props, {"required": {"title": "str", "tags": "list_or_str"}}, severity="warning"))
        elif suffix == ".canvas" and validate_canvas:
            checked["canvas"] += 1
            try:
                issues.extend(_validate_canvas_payload(rel_path, json.loads(_read_text(path))))
            except Exception as exc:
                issues.append({"path": rel_path, "severity": "error", "message": f"Invalid Canvas JSON: {exc}"})
        elif suffix == ".base" and validate_bases:
            checked["bases"] += 1
            try:
                issues.extend(_validate_base_payload(rel_path, _load_yaml(_read_text(path))))
            except Exception as exc:
                issues.append({"path": rel_path, "severity": "error", "message": f"Invalid Base YAML: {exc}"})

    summary = {
        "errorCount": sum(1 for issue in issues if issue.get("severity") == "error"),
        "warningCount": sum(1 for issue in issues if issue.get("severity") == "warning"),
        "infoCount": sum(1 for issue in issues if issue.get("severity") == "info"),
    }
    result: dict[str, Any] = {"ok": summary["errorCount"] == 0, "vaultPath": str(vault), "folder": folder, "checked": checked, "summary": summary, "issues": issues}
    if write_json_path:
        output = _safe_path(vault, write_json_path)
        _write_text(output, json.dumps(result, ensure_ascii=False, indent=2))
        result["writtenTo"] = _rel(vault, output)
    return result


@mcp.tool()
def obsidian_apply_schema_defaults(
    vault_path: str = "",
    folder: str = "",
    schemas_json: str = "{}",
    defaults_json: str = "{}",
    include_recommended: bool = False,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Fill missing frontmatter fields from built-in/custom schemas, using dry-run by default."""
    vault = _vault(vault_path)
    custom_schemas = _json(schemas_json, {})
    defaults = _json(defaults_json, {})
    if not isinstance(custom_schemas, dict):
        raise ValueError("schemas_json must decode to an object.")
    if not isinstance(defaults, dict):
        raise ValueError("defaults_json must decode to an object.")
    schemas = dict(SCHEMA_PRESETS)
    schemas.update(custom_schemas)

    writes: list[tuple[Path, str]] = []
    updates: list[dict[str, Any]] = []
    checked = 0
    for path in _iter_files(vault, folder):
        if path.suffix.lower() != ".md":
            continue
        checked += 1
        rel_path = _rel(vault, path)
        text = _read_text(path)
        props, body = _split_frontmatter(text)
        schema_key = _infer_schema_key(rel_path, props)
        schema = schemas.get(schema_key) if schema_key else {"required": {"title": "str", "tags": "list_or_str"}}
        if not isinstance(schema, dict):
            continue
        fields: dict[str, Any] = dict(schema.get("required", {}))
        if include_recommended and isinstance(schema.get("recommended"), dict):
            fields.update(schema["recommended"])
        additions: dict[str, Any] = {}
        for field, expected_type in fields.items():
            if field in props and props.get(field) not in (None, ""):
                continue
            value = _schema_default_value(rel_path, schema_key, field, str(expected_type), defaults)
            if value == "" and field != "title":
                continue
            additions[field] = value
        if not additions:
            continue
        updated = dict(props)
        updated.update(additions)
        writes.append((path, _join_frontmatter(updated, body)))
        updates.append({"path": rel_path, "schema": schema_key or "generic", "added": additions})

    result = _write_many(vault, writes, dry_run)
    result["checked"] = checked
    result["updateCount"] = len(updates)
    result["updates"] = updates
    return result


@mcp.tool()
def obsidian_suggest_graph_improvements(
    vault_path: str = "",
    folder: str = "",
    max_suggestions: int = 50,
) -> dict[str, Any]:
    """Suggest graph improvements such as creating unresolved notes, reciprocal links, and merging similar pages."""
    vault = _vault(vault_path)
    graph = obsidian_build_graph(vault_path=str(vault), folder=folder, include_tags=True)
    limit = max(1, max_suggestions)
    suggestions: list[dict[str, Any]] = []

    for target, sources in sorted(graph["unresolved"].items(), key=lambda item: (-len(item[1]), item[0].lower())):
        suggestions.append(
            {
                "kind": "create_note",
                "priority": "high" if len(sources) > 1 else "medium",
                "target": target,
                "sources": sources,
                "message": "Create a note for this unresolved wikilink or retarget the sources.",
            }
        )

    existing_edges = {(edge["source"], edge["target"]) for edge in graph["edges"]}
    for edge in graph["edges"]:
        reverse = (edge["target"], edge["source"])
        if reverse not in existing_edges:
            suggestions.append(
                {
                    "kind": "consider_reciprocal_link",
                    "priority": "low",
                    "source": edge["target"],
                    "target": edge["source"],
                    "message": "Consider adding a contextual backlink when the relationship should be navigable both ways.",
                }
            )
            if len(suggestions) >= limit:
                break

    normalized_titles: dict[str, list[str]] = {}
    for node in graph["nodes"]:
        title_key = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", str(node.get("title") or node["id"]).lower())
        if title_key:
            normalized_titles.setdefault(title_key, []).append(str(node["id"]))
    for title_key, paths in sorted(normalized_titles.items()):
        if len(paths) > 1:
            suggestions.append({"kind": "possible_duplicate", "priority": "medium", "key": title_key, "paths": paths, "message": "These notes have very similar normalized titles."})

    markdown_links: list[dict[str, str]] = []
    attachments: list[dict[str, str]] = []
    attachment_exts = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".xlsx", ".docx", ".pptx"}
    for path in _collect_markdown(vault):
        rel_path = _rel(vault, path)
        if folder and not rel_path.startswith(folder.strip("/")):
            continue
        body = _split_frontmatter(_read_text(path))[1]
        for match in MARKDOWN_LINK_RE.finditer(body):
            target = match.group(1).strip()
            if target.startswith(("http://", "https://", "obsidian://", "mailto:")):
                continue
            markdown_links.append({"source": rel_path, "target": target})
        for match in EMBED_RE.finditer(body):
            target = _target_from_link(match.group(1))
            if Path(target).suffix.lower() in attachment_exts:
                attachments.append({"source": rel_path, "target": target})

    if markdown_links:
        suggestions.append({"kind": "markdown_links", "priority": "info", "count": len(markdown_links), "examples": markdown_links[:10], "message": "Markdown links are not first-class wikilinks; consider converting internal targets."})
    if attachments:
        suggestions.append({"kind": "attachment_links", "priority": "info", "count": len(attachments), "examples": attachments[:10], "message": "Attachment embeds were found and can be modeled in a richer graph later."})

    result = {
        "vaultPath": str(vault),
        "folder": folder,
        "suggestionCount": min(len(suggestions), limit),
        "suggestions": suggestions[:limit],
        "graph": {
            "nodeCount": graph["nodeCount"],
            "edgeCount": graph["edgeCount"],
            "unresolvedCount": sum(len(sources) for sources in graph["unresolved"].values()),
            "orphanCount": len(graph["orphans"]),
            "deadEndCount": len(graph["deadEnds"]),
        },
    }
    return result


@mcp.tool()
def obsidian_create_canvas(
    path: str,
    nodes_json: str,
    edges_json: str = "[]",
    vault_path: str = "",
    overwrite: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Create a JSON Canvas file from node and edge JSON arrays."""
    vault = _vault(vault_path)
    rel_path = path if path.lower().endswith(".canvas") else f"{path}.canvas"
    full = _safe_path(vault, rel_path)
    if full.exists() and not overwrite:
        return {"ok": False, "path": _rel(vault, full), "error": "Canvas exists. Pass overwrite=true to replace it."}
    nodes = _json(nodes_json, [])
    edges = _json(edges_json, [])
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise ValueError("nodes_json and edges_json must decode to arrays.")
    node_ids = {node.get("id") for node in nodes if isinstance(node, dict)}
    if len(node_ids) != len(nodes):
        raise ValueError("Every Canvas node needs a unique id.")
    for edge in edges:
        if not isinstance(edge, dict):
            raise ValueError("Each edge must be an object.")
        if edge.get("fromNode") not in node_ids or edge.get("toNode") not in node_ids:
            raise ValueError(f"Canvas edge references missing node: {edge}")
    payload = {"nodes": nodes, "edges": edges}
    result = _write_result(vault, full, json.dumps(payload, ensure_ascii=False, indent=2), dry_run)
    result["nodeCount"] = len(nodes)
    result["edgeCount"] = len(edges)
    return result


@mcp.tool()
def obsidian_create_canvas_from_graph(
    path: str,
    vault_path: str = "",
    folder: str = "",
    tag: str = "",
    layout: str = "grid",
    max_nodes: int = 80,
    include_orphans: bool = True,
    include_summary: bool = True,
    group_nodes: bool = False,
    group_by: str = "tag",
    overwrite: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Create a JSON Canvas knowledge map from the vault wikilink graph."""
    vault = _vault(vault_path)
    rel_path = path if path.lower().endswith(".canvas") else f"{path}.canvas"
    full = _safe_path(vault, rel_path)
    if full.exists() and not overwrite:
        return {"ok": False, "path": _rel(vault, full), "error": "Canvas exists. Pass overwrite=true to replace it."}
    layout_key = layout.strip().lower()
    if layout_key not in {"grid", "radial", "grouped", "layered"}:
        raise ValueError("layout must be grid, radial, grouped, or layered.")
    group_mode = group_by.strip().lower()
    if group_mode not in {"tag", "folder"}:
        raise ValueError("group_by must be tag or folder.")

    graph = obsidian_build_graph(vault_path=str(vault), folder=folder, include_tags=True)
    selected_tag = tag.strip().lstrip("#")
    node_by_id = {str(node["id"]): node for node in graph["nodes"]}
    selected_ids: list[str] = []
    for node in sorted(graph["nodes"], key=lambda item: str(item["id"]).lower()):
        tags = [str(value) for value in node.get("tags", [])]
        if selected_tag and selected_tag not in tags:
            continue
        selected_ids.append(str(node["id"]))

    if not include_orphans:
        linked_ids = {edge["source"] for edge in graph["edges"]} | {edge["target"] for edge in graph["edges"]}
        selected_ids = [node_id for node_id in selected_ids if node_id in linked_ids]
    selected_ids = selected_ids[: max(1, max_nodes)]
    selected_set = set(selected_ids)

    width = 360
    height = 220
    spacing_x = 120
    spacing_y = 120
    nodes: list[dict[str, Any]] = []
    if include_summary:
        summary_text = "\n".join(
            [
                "# Vault Map",
                "",
                f"- Generated: {_utc_now()}",
                f"- Notes: {len(selected_ids)}",
                f"- Source folder: {folder or '(vault root)'}",
                f"- Tag filter: {selected_tag or '(none)'}",
            ]
        )
        nodes.append({"id": "summary", "type": "text", "x": -520, "y": -260, "width": 420, "height": 220, "text": summary_text, "color": "3"})

    group_bounds: dict[str, list[int]] = {}
    for index, node_id in enumerate(selected_ids):
        node = node_by_id[node_id]
        if layout_key == "layered":
            tags = [str(value) for value in node.get("tags", [])]
            layer_order = ["source", "entity", "concept", "task", "equipment", "economics", "literature", "utility"]
            layer = next((layer_order.index(tag) for tag in layer_order if tag in tags), len(layer_order))
            same_layer_before = sum(
                1
                for previous_id in selected_ids[:index]
                if next((layer_order.index(tag) for tag in layer_order if tag in [str(value) for value in node_by_id[previous_id].get("tags", [])]), len(layer_order)) == layer
            )
            x, y = layer * (width + spacing_x), same_layer_before * (height + spacing_y)
        elif layout_key == "grouped":
            group_key = _canvas_group_key(node, group_mode)
            group_names = sorted({_canvas_group_key(node_by_id[item], group_mode) for item in selected_ids})
            group_index = group_names.index(group_key)
            same_group_before = sum(1 for previous_id in selected_ids[:index] if _canvas_group_key(node_by_id[previous_id], group_mode) == group_key)
            x = group_index * (width + spacing_x + 240)
            y = same_group_before * (height + spacing_y)
        else:
            x, y = _canvas_position(index, len(selected_ids), layout_key, width, height, spacing_x, spacing_y)
        tags = [str(value) for value in node.get("tags", [])]
        if group_nodes or layout_key == "grouped":
            group_key = _canvas_group_key(node, group_mode)
            bounds = group_bounds.setdefault(group_key, [x, y, x + width, y + height])
            bounds[0] = min(bounds[0], x)
            bounds[1] = min(bounds[1], y)
            bounds[2] = max(bounds[2], x + width)
            bounds[3] = max(bounds[3], y + height)
        nodes.append(
            {
                "id": _canvas_node_id(node_id),
                "type": "file",
                "x": x,
                "y": y,
                "width": width,
                "height": height,
                "file": node_id,
                "color": _canvas_color_for_tags(tags),
            }
        )

    if group_bounds:
        group_canvas_nodes: list[dict[str, Any]] = []
        for group_index, (group_name, bounds) in enumerate(sorted(group_bounds.items())):
            x1, y1, x2, y2 = bounds
            group_canvas_nodes.append(
                {
                    "id": _canvas_group_id(group_name),
                    "type": "group",
                    "x": x1 - 40,
                    "y": y1 - 70,
                    "width": max(440, x2 - x1 + 80),
                    "height": max(320, y2 - y1 + 120),
                    "label": group_name,
                    "color": str((group_index % 6) + 1),
                }
            )
        insert_at = 1 if include_summary else 0
        nodes[insert_at:insert_at] = group_canvas_nodes

    edges: list[dict[str, Any]] = []
    for index, edge in enumerate(graph["edges"]):
        source = str(edge["source"])
        target = str(edge["target"])
        if source not in selected_set or target not in selected_set:
            continue
        edges.append(
            {
                "id": _canvas_edge_id(source, target, index),
                "fromNode": _canvas_node_id(source),
                "fromSide": "right",
                "toNode": _canvas_node_id(target),
                "toSide": "left",
                "toEnd": "arrow",
                "label": str(edge.get("kind") or "link"),
            }
        )

    payload = {"nodes": nodes, "edges": edges}
    result = _write_result(vault, full, json.dumps(payload, ensure_ascii=False, indent=2), dry_run)
    result["nodeCount"] = len(nodes)
    result["noteNodeCount"] = len(selected_ids)
    result["edgeCount"] = len(edges)
    result["layout"] = layout_key
    result["tag"] = selected_tag
    result["groupCount"] = len(group_bounds)
    return result


@mcp.tool()
def obsidian_create_base(
    path: str,
    base_json: str,
    vault_path: str = "",
    overwrite: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Create an Obsidian Bases .base file from a JSON object."""
    vault = _vault(vault_path)
    rel_path = path if path.lower().endswith(".base") else f"{path}.base"
    full = _safe_path(vault, rel_path)
    if full.exists() and not overwrite:
        return {"ok": False, "path": _rel(vault, full), "error": "Base exists. Pass overwrite=true to replace it."}
    base = _json(base_json, {})
    if not isinstance(base, dict):
        raise ValueError("base_json must decode to an object.")
    result = _write_result(vault, full, _dump_yaml(base) + "\n", dry_run)
    result["topLevelKeys"] = list(base.keys())
    return result


@mcp.tool()
def obsidian_list_base_templates() -> dict[str, str]:
    """List built-in Obsidian Bases templates."""
    return dict(BASE_TEMPLATE_DESCRIPTIONS)


@mcp.tool()
def obsidian_create_base_template(
    template: str,
    path: str = "",
    vault_path: str = "",
    options_json: str = "{}",
    overwrite: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Create an Obsidian Bases file from a built-in template."""
    vault = _vault(vault_path)
    options = _json(options_json, {})
    if not isinstance(options, dict):
        raise ValueError("options_json must decode to an object.")
    template_key = template.strip().lower().replace("-", "_")
    base = _base_template(template_key, options)
    rel_path = path.strip() if path.strip() else f"bases/{template_key}.base"
    rel_path = rel_path if rel_path.lower().endswith(".base") else f"{rel_path}.base"
    full = _safe_path(vault, rel_path)
    if full.exists() and not overwrite:
        return {"ok": False, "path": _rel(vault, full), "error": "Base exists. Pass overwrite=true to replace it."}
    result = _write_result(vault, full, _dump_yaml(base) + "\n", dry_run)
    result["template"] = template_key
    result["description"] = BASE_TEMPLATE_DESCRIPTIONS[template_key]
    result["topLevelKeys"] = list(base.keys())
    return result


@mcp.tool()
def obsidian_list_dataview_templates() -> dict[str, str]:
    """List built-in Dataview note templates."""
    return dict(DATAVIEW_TEMPLATE_DESCRIPTIONS)


@mcp.tool()
def obsidian_create_dataview_note(
    template: str,
    path: str = "",
    vault_path: str = "",
    options_json: str = "{}",
    overwrite: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Create a Markdown note containing a Dataview query block."""
    vault = _vault(vault_path)
    options = _json(options_json, {})
    if not isinstance(options, dict):
        raise ValueError("options_json must decode to an object.")
    template_key = template.strip().lower().replace("-", "_")
    content = _dataview_template(template_key, options)
    rel_path = path.strip() if path.strip() else f"views/{template_key}-dataview.md"
    rel_path = _ensure_md_path(rel_path)
    full = _safe_path(vault, rel_path)
    if full.exists() and not overwrite:
        return {"ok": False, "path": _rel(vault, full), "error": "Dataview note exists. Pass overwrite=true to replace it."}
    result = _write_result(vault, full, content, dry_run)
    result["template"] = template_key
    result["description"] = DATAVIEW_TEMPLATE_DESCRIPTIONS[template_key]
    return result


@mcp.tool()
def obsidian_preview_edit_plan(
    plan_json: str,
    vault_path: str = "",
) -> dict[str, Any]:
    """Preview a multi-file edit plan and return per-file diffs without writing."""
    vault = _vault(vault_path)
    operations = _plan_operations(plan_json)
    previews = _preview_edit_plan(vault, operations)
    return {
        "ok": True,
        "vaultPath": str(vault),
        "operationCount": len(operations),
        "changeCount": sum(1 for item in previews if item["changed"]),
        "changes": previews,
    }


@mcp.tool()
def obsidian_apply_edit_plan(
    plan_json: str,
    vault_path: str = "",
    transaction_id: str = "",
) -> dict[str, Any]:
    """Apply a multi-file edit plan after creating vault-local backups."""
    vault = _vault(vault_path)
    operations = _plan_operations(plan_json)
    previews = _preview_edit_plan(vault, operations)
    txid = transaction_id.strip() or f"{_utc_now().replace(':', '').replace('-', '')}-{uuid.uuid4().hex[:8]}"
    manifest_entries: list[dict[str, Any]] = []
    applied: list[dict[str, Any]] = []

    for preview, operation in zip(previews, operations):
        full, before, after, exists = _apply_operation_to_text(vault, operation)
        rel_path = _rel(vault, full)
        backup = _backup_path(vault, txid, rel_path)
        backup.parent.mkdir(parents=True, exist_ok=True)
        if exists:
            _write_text(backup, before)
        manifest_entries.append({"path": rel_path, "existed": exists, "backup": _rel(vault, backup) if exists else ""})
        if operation["op"] == "delete":
            if exists:
                full.unlink()
        else:
            _write_text(full, after)
        applied.append({**preview, "backup": _rel(vault, backup) if exists else ""})

    manifest = {
        "transactionId": txid,
        "createdAt": _utc_now(),
        "operations": manifest_entries,
    }
    manifest_path = _transaction_manifest_path(vault, txid)
    _write_text(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2))
    return {
        "ok": True,
        "vaultPath": str(vault),
        "transactionId": txid,
        "manifestPath": _rel(vault, manifest_path),
        "operationCount": len(operations),
        "changeCount": sum(1 for item in applied if item["changed"]),
        "changes": applied,
    }


@mcp.tool()
def obsidian_rollback_edit_plan(
    transaction_id: str,
    vault_path: str = "",
    dry_run: bool = False,
) -> dict[str, Any]:
    """Rollback a previously applied edit plan from its vault-local backups."""
    vault = _vault(vault_path)
    txid = transaction_id.strip()
    if not txid:
        raise ValueError("transaction_id is required.")
    manifest_path = _transaction_manifest_path(vault, txid)
    if not manifest_path.exists():
        raise FileNotFoundError(f"Transaction manifest not found: {txid}")
    manifest = json.loads(_read_text(manifest_path))
    restored: list[dict[str, Any]] = []
    for entry in manifest.get("operations", []):
        rel_path = str(entry["path"])
        full = _safe_path(vault, rel_path)
        existed = bool(entry.get("existed"))
        before = _read_text(full) if full.exists() else ""
        if existed:
            backup_rel = str(entry.get("backup") or "")
            backup = _safe_path(vault, backup_rel)
            if not backup.exists():
                raise FileNotFoundError(f"Backup missing for {rel_path}: {backup_rel}")
            after = _read_text(backup)
            action = "restore"
        else:
            after = ""
            action = "delete_created"
        restored.append({"path": rel_path, "action": action, "changed": before != after or (not existed and full.exists()), "diff": _diff_text(rel_path, before, after)})
        if dry_run:
            continue
        if existed:
            _write_text(full, after)
        elif full.exists():
            full.unlink()
    return {
        "ok": True,
        "dryRun": dry_run,
        "vaultPath": str(vault),
        "transactionId": txid,
        "restoredCount": sum(1 for item in restored if item["changed"]),
        "changes": restored,
    }


@mcp.tool()
def obsidian_cli(
    command: str,
    params_json: str = "{}",
    flags_json: str = "[]",
    vault: str = "",
    cwd: str = "",
    timeout_seconds: int = 30,
) -> dict[str, Any]:
    """Call the local Obsidian CLI with parameter and flag JSON."""
    cli = os.environ.get("OBSIDIAN_CLI_COMMAND", "obsidian")
    if shutil.which(cli) is None:
        return {"ok": False, "error": f"Obsidian CLI command not found on PATH: {cli}"}
    params = _json(params_json, {})
    flags = _json(flags_json, [])
    if not isinstance(params, dict):
        raise ValueError("params_json must decode to an object.")
    if not isinstance(flags, list):
        raise ValueError("flags_json must decode to an array.")
    args = [cli]
    if vault:
        args.append(f"vault={vault}")
    if command:
        args.append(command)
    for key, value in params.items():
        args.append(f"{key}={value}")
    for flag in flags:
        args.append(str(flag))
    run_cwd = str(_vault(cwd)) if cwd else None
    completed = subprocess.run(
        args,
        cwd=run_cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=max(1, timeout_seconds),
    )
    fallback_command = ""
    if command == "base:query" and os.name == "nt" and completed.returncode != 0 and not completed.stdout and not completed.stderr:
        fallback_command = subprocess.list2cmdline(args)
        completed = subprocess.run(
            fallback_command,
            cwd=run_cwd,
            shell=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(1, timeout_seconds),
        )
    return {
        "ok": completed.returncode == 0,
        "command": args,
        "fallbackCommand": fallback_command,
        "returnCode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def _clean_cli_params(params: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in params.items() if value not in ("", None)}


def _parse_cli_stdout(result: dict[str, Any], output_format: str = "") -> dict[str, Any]:
    parsed = None
    stdout = result.get("stdout", "").strip()
    if output_format == "json" and stdout:
        try:
            parsed = json.loads(result["stdout"])
        except json.JSONDecodeError as exc:
            no_rows_messages = {"No tasks found.", "No backlinks found.", "No results found."}
            if stdout in no_rows_messages:
                parsed = []
            else:
                result = dict(result)
                result["parseError"] = str(exc)
    if parsed is not None:
        result = dict(result)
        result["data"] = parsed
    return result


def _call_obsidian_cli(command: str, params: dict[str, Any] | None = None, flags: list[str] | None = None, vault: str = "", timeout_seconds: int = 30) -> dict[str, Any]:
    return obsidian_cli(
        command,
        params_json=json.dumps(_clean_cli_params(params or {}), ensure_ascii=False),
        flags_json=json.dumps(flags or [], ensure_ascii=False),
        vault=vault,
        timeout_seconds=timeout_seconds,
    )


@mcp.tool()
def obsidian_cli_read(
    path: str = "",
    file: str = "",
    vault: str = "",
    max_chars: int = 20000,
) -> dict[str, Any]:
    """Read a file through the Obsidian CLI."""
    result = _call_obsidian_cli("read", {"path": path, "file": file}, vault=vault)
    if result.get("stdout") and max_chars > 0:
        result = dict(result)
        result["truncated"] = len(result["stdout"]) > max_chars
        result["content"] = result["stdout"][:max_chars]
    return result


@mcp.tool()
def obsidian_cli_open(
    path: str = "",
    file: str = "",
    vault: str = "",
    newtab: bool = False,
) -> dict[str, Any]:
    """Open a file through the Obsidian CLI."""
    flags = ["newtab"] if newtab else []
    return _call_obsidian_cli("open", {"path": path, "file": file}, flags, vault=vault)


@mcp.tool()
def obsidian_cli_backlinks(
    path: str = "",
    file: str = "",
    vault: str = "",
    counts: bool = False,
    total: bool = False,
    output_format: str = "json",
) -> dict[str, Any]:
    """List backlinks through the Obsidian CLI."""
    flags = []
    if counts:
        flags.append("counts")
    if total:
        flags.append("total")
    fmt = output_format or "json"
    result = _call_obsidian_cli("backlinks", {"path": path, "file": file, "format": fmt}, flags, vault=vault)
    return _parse_cli_stdout(result, fmt)


@mcp.tool()
def obsidian_cli_base_query(
    path: str = "",
    file: str = "",
    view: str = "",
    vault: str = "",
    output_format: str = "json",
    timeout_seconds: int = 30,
) -> dict[str, Any]:
    """Query an Obsidian Base through the Obsidian CLI."""
    fmt = output_format or "json"
    result = _call_obsidian_cli("base:query", {"path": path, "file": file, "view": view, "format": fmt}, vault=vault, timeout_seconds=timeout_seconds)
    return _parse_cli_stdout(result, fmt)


@mcp.tool()
def obsidian_cli_properties(
    path: str = "",
    file: str = "",
    name: str = "",
    vault: str = "",
    counts: bool = False,
    total: bool = False,
    sort: str = "",
    output_format: str = "json",
) -> dict[str, Any]:
    """List vault or file properties through the Obsidian CLI."""
    flags = []
    if counts:
        flags.append("counts")
    if total:
        flags.append("total")
    fmt = output_format or "json"
    result = _call_obsidian_cli("properties", {"path": path, "file": file, "name": name, "sort": sort, "format": fmt}, flags, vault=vault)
    return _parse_cli_stdout(result, fmt)


@mcp.tool()
def obsidian_cli_property_read(
    name: str,
    path: str = "",
    file: str = "",
    vault: str = "",
) -> dict[str, Any]:
    """Read one property value through the Obsidian CLI."""
    return _call_obsidian_cli("property:read", {"name": name, "path": path, "file": file}, vault=vault)


@mcp.tool()
def obsidian_cli_property_set(
    name: str,
    value: str,
    path: str = "",
    file: str = "",
    property_type: str = "text",
    vault: str = "",
) -> dict[str, Any]:
    """Set one property value through the Obsidian CLI."""
    return _call_obsidian_cli("property:set", {"name": name, "value": value, "type": property_type, "path": path, "file": file}, vault=vault)


@mcp.tool()
def obsidian_cli_property_remove(
    name: str,
    path: str = "",
    file: str = "",
    vault: str = "",
) -> dict[str, Any]:
    """Remove one property through the Obsidian CLI."""
    return _call_obsidian_cli("property:remove", {"name": name, "path": path, "file": file}, vault=vault)


@mcp.tool()
def obsidian_cli_tasks(
    path: str = "",
    file: str = "",
    vault: str = "",
    done: bool = False,
    todo: bool = False,
    status: str = "",
    total: bool = False,
    output_format: str = "json",
) -> dict[str, Any]:
    """List tasks through the Obsidian CLI."""
    flags = []
    if done:
        flags.append("done")
    if todo:
        flags.append("todo")
    if total:
        flags.append("total")
    fmt = output_format or "json"
    result = _call_obsidian_cli("tasks", {"path": path, "file": file, "status": status, "format": fmt}, flags, vault=vault)
    return _parse_cli_stdout(result, fmt)


@mcp.tool()
def obsidian_cli_screenshot(
    output_path: str,
    vault: str = "",
    timeout_seconds: int = 30,
) -> dict[str, Any]:
    """Take an Obsidian developer screenshot through the CLI."""
    return _call_obsidian_cli("dev:screenshot", {"path": output_path}, vault=vault, timeout_seconds=timeout_seconds)


@mcp.tool()
def obsidian_cli_plugin_reload(
    plugin_id: str,
    vault: str = "",
) -> dict[str, Any]:
    """Reload an Obsidian plugin through the CLI."""
    return _call_obsidian_cli("plugin:reload", {"id": plugin_id}, vault=vault)


@mcp.tool()
def obsidian_cli_move_or_rename(
    operation: str,
    path: str = "",
    file: str = "",
    to: str = "",
    name: str = "",
    vault: str = "",
    dry_run: bool = True,
) -> dict[str, Any]:
    """Move or rename a file through the Obsidian CLI. Defaults to dry_run=true."""
    op = operation.strip().lower()
    if op not in {"move", "rename"}:
        raise ValueError("operation must be move or rename.")
    params = _clean_cli_params({"path": path, "file": file, "to": to if op == "move" else "", "name": name if op == "rename" else ""})
    missing_destination = (op == "move" and "to" not in params) or (op == "rename" and "name" not in params)
    if missing_destination:
        raise ValueError("move requires to; rename requires name.")
    if "path" not in params and "file" not in params:
        raise ValueError("path or file is required.")
    command_preview = ["obsidian"]
    if vault:
        command_preview.append(f"vault={vault}")
    command_preview.append(op)
    command_preview.extend(f"{key}={value}" for key, value in params.items())
    if dry_run:
        return {"ok": True, "dryRun": True, "command": command_preview, "message": "Dry run only. Pass dry_run=false to execute."}
    result = _call_obsidian_cli(op, params, vault=vault)
    result["dryRun"] = False
    return result


if __name__ == "__main__":
    mcp.run()
