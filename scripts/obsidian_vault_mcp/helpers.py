from . import common as _common

globals().update({name: value for name, value in vars(_common).items() if not name.startswith("__")})


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


def _load_json_file(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(_read_text(path))
    except Exception:
        return default


def _vault_config(vault: Path) -> dict[str, Any]:
    config: dict[str, Any] = {}
    for rel_path in [".obsidian-vault-mcp.json", ".obsidian/obsidian-vault-mcp.json"]:
        loaded = _load_json_file(vault / rel_path, {})
        if isinstance(loaded, dict):
            config.update(loaded)
    return config


def _config_value(vault: Path, key: str, current: Any, default: Any) -> Any:
    if current != default:
        return current
    return _vault_config(vault).get(key, current)


def _configured_path(vault: Path, key: str, current: str, default: str) -> str:
    return str(_config_value(vault, key, current, default) or default).strip("/")


def _template_config(vault: Path) -> dict[str, Any]:
    config = _vault_config(vault)
    folders: list[str] = []
    default_template = str(config.get("defaultTemplate") or "").strip()

    templates_json = _load_json_file(vault / ".obsidian" / "templates.json", {})
    if isinstance(templates_json, dict):
        for key in ["folder", "templateFolder", "templateFolderPath", "folderPath"]:
            value = str(templates_json.get(key) or "").strip()
            if value:
                folders.append(value)
        default_template = default_template or str(templates_json.get("defaultTemplate") or "").strip()

    templater_json = _load_json_file(vault / ".obsidian" / "plugins" / "templater-obsidian" / "data.json", {})
    if isinstance(templater_json, dict):
        for key in ["template_folder", "templateFolder", "templates_folder", "folder"]:
            value = str(templater_json.get(key) or "").strip()
            if value:
                folders.append(value)
        default_template = default_template or str(templater_json.get("default_template") or templater_json.get("defaultTemplate") or "").strip()

    configured_folder = str(config.get("templateFolder") or "").strip()
    if configured_folder:
        folders.insert(0, configured_folder)

    seen: set[str] = set()
    unique_folders = []
    for folder in folders:
        normalized = folder.replace("\\", "/").strip("/")
        if normalized and normalized not in seen:
            seen.add(normalized)
            unique_folders.append(normalized)
    return {"folders": unique_folders, "defaultTemplate": default_template}


def _list_user_templates(vault: Path) -> list[dict[str, Any]]:
    templates: list[dict[str, Any]] = []
    for folder in _template_config(vault)["folders"]:
        root = _safe_path(vault, folder)
        if not root.exists():
            continue
        for path in root.rglob("*.md"):
            rel_path = _rel(vault, path)
            templates.append({"path": rel_path, "name": path.stem, "folder": folder})
    return sorted(templates, key=lambda item: item["path"].lower())


def _find_user_template(vault: Path, template_path: str = "", template_name: str = "") -> tuple[str, str]:
    if template_path.strip():
        rel_path = _ensure_md_path(template_path.strip())
        return rel_path, _read_text(_safe_path(vault, rel_path))
    wanted = template_name.strip()
    config = _template_config(vault)
    if not wanted:
        wanted = str(config.get("defaultTemplate") or "").strip()
    if not wanted:
        return "", ""
    wanted_key = wanted.lower().removesuffix(".md")
    for item in _list_user_templates(vault):
        path_key = str(item["path"]).lower().removesuffix(".md")
        name_key = str(item["name"]).lower()
        if wanted_key in {path_key, name_key}:
            rel_path = str(item["path"])
            return rel_path, _read_text(_safe_path(vault, rel_path))
    raise FileNotFoundError(f"Template not found: {wanted}")


def _render_template(template: str, title: str, body: str, properties: dict[str, Any]) -> str:
    rendered = template
    replacements = {
        "{{title}}": title,
        "{{name}}": title,
        "{{date}}": datetime.now().strftime("%Y-%m-%d"),
        "{{time}}": datetime.now().strftime("%H:%M"),
        "{{body}}": body,
        "{{content}}": body,
    }
    for key, value in replacements.items():
        rendered = rendered.replace(key, value)
    for key, value in properties.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", str(value))
    return rendered


def _apply_note_template(vault: Path, title: str, body: str, properties: dict[str, Any], template_path: str = "", template_name: str = "", use_template: bool = False) -> tuple[str, str]:
    config = _template_config(vault)
    should_use = use_template or bool(template_path.strip() or template_name.strip() or config.get("defaultTemplate"))
    if not should_use:
        return body, ""
    rel_path, template = _find_user_template(vault, template_path, template_name)
    return _render_template(template, title, body, properties), rel_path


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


def _zotero_select_uri(key: str) -> str:
    return f"zotero://select/library/items/{key}" if key else ""


def _zotero_pdf_uri(key: str) -> str:
    return f"zotero://open-pdf/library/items/{key}" if key else ""


def _zotero_links_for_item(key: str, pdf_keys: list[str] | None = None) -> dict[str, Any]:
    links: dict[str, Any] = {}
    select_uri = _zotero_select_uri(key)
    if select_uri:
        links["select"] = select_uri
    pdf_uris = [_zotero_pdf_uri(pdf_key) for pdf_key in pdf_keys or [] if pdf_key]
    if pdf_uris:
        links["pdf"] = pdf_uris
    return links


def _find_existing_reference(vault: Path, metadata: dict[str, Any], folder: str = "") -> dict[str, Any]:
    candidates = {
        "zoteroKey": str(metadata.get("zoteroKey") or "").strip().lower(),
        "doi": str(metadata.get("doi") or metadata.get("DOI") or "").strip().lower(),
        "citekey": str(metadata.get("citekey") or metadata.get("citationKey") or "").strip().lower(),
        "title": str(metadata.get("title") or "").strip().lower(),
    }
    root = _safe_path(vault, folder) if folder else vault
    if not root.exists():
        return {}
    for path in root.rglob("*.md"):
        if any(part in DEFAULT_EXCLUDES or part.startswith(".") for part in path.relative_to(vault).parts):
            continue
        props, _body = _split_frontmatter(_read_text(path))
        checks = {
            "zoteroKey": str(props.get("zoteroKey") or "").strip().lower(),
            "doi": str(props.get("doi") or props.get("DOI") or "").strip().lower(),
            "citekey": str(props.get("citekey") or props.get("citationKey") or "").strip().lower(),
            "title": str(props.get("title") or "").strip().lower(),
        }
        for field, value in candidates.items():
            if value and checks.get(field) == value:
                return {"path": _rel(vault, path), "field": field, "value": value}
    return {}


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


def _attachment_filename(strategy: str, source_pdf: Path, parent_key: str, attachment: dict[str, Any], metadata: dict[str, Any], index: int = 1) -> str:
    ext = source_pdf.suffix or ".pdf"
    strategy_key = (strategy or "original").strip().lower().replace("-", "_")
    if strategy_key == "zotero_key":
        base = str(attachment.get("key") or parent_key or source_pdf.stem)
    elif strategy_key in {"citekey", "citation_key"}:
        base = str(metadata.get("citekey") or metadata.get("citationKey") or metadata.get("zoteroKey") or parent_key or source_pdf.stem)
    elif strategy_key == "title_year":
        pieces = [str(metadata.get("year") or "").strip(), str(metadata.get("title") or source_pdf.stem).strip()]
        base = " - ".join(piece for piece in pieces if piece)
    elif strategy_key == "parent_key":
        base = f"{parent_key}-{index}"
    else:
        base = source_pdf.name
    filename = _slug_filename(base)
    if not filename.lower().endswith(ext.lower()):
        filename = f"{filename}{ext}"
    return filename


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


def _is_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _mineru_token_available() -> bool:
    return bool(os.environ.get("MINERU_TOKEN") or os.environ.get("MINERU_API_TOKEN"))


def _mineru_cli_status(cli_command: str = "") -> dict[str, Any]:
    cli = cli_command or MINERU_CLI_COMMAND
    executable = shutil.which(cli)
    status: dict[str, Any] = {
        "cli": cli,
        "available": executable is not None,
        "path": executable or "",
        "tokenAvailable": _mineru_token_available(),
        "tokenEnvVars": [name for name in ["MINERU_TOKEN", "MINERU_API_TOKEN"] if os.environ.get(name)],
    }
    if not executable:
        status["installHint"] = "Install MinerU CLI with: npm install -g mineru-open-api"
        return status
    try:
        completed = subprocess.run([cli, "version"], capture_output=True, text=True, timeout=20, check=False)  # noqa: S603
        status["versionCommand"] = [cli, "version"]
        status["returnCode"] = completed.returncode
        status["stdout"] = completed.stdout.strip()
        status["stderr"] = completed.stderr.strip()
        status["ok"] = completed.returncode == 0
    except Exception as exc:
        status["ok"] = False
        status["error"] = str(exc)
    return status


def _mineru_input_argument(vault: Path, input_path: str) -> tuple[str, str]:
    value = input_path.strip()
    if not value:
        raise ValueError("input_path is required.")
    if _is_url(value):
        parsed = urlparse(value)
        name = Path(parsed.path).name or "remote-document.pdf"
        return value, name
    candidate = Path(value).expanduser()
    full = candidate.resolve() if candidate.is_absolute() else _safe_path(vault, value)
    if not full.exists():
        raise FileNotFoundError(f"MinerU input file was not found: {value}")
    return str(full), full.name


def _mineru_output_path(vault: Path, output_path: str, input_name: str) -> tuple[Path, str]:
    rel_path = output_path.strip() or f"mineru-output/{_slug_filename(Path(input_name).stem or 'document')}"
    full = _safe_path(vault, rel_path)
    return full, _rel(vault, full)


def _find_mineru_markdown(vault: Path, output_full: Path) -> str:
    if output_full.is_file() and output_full.suffix.lower() in {".md", ".markdown"}:
        return _rel(vault, output_full)
    search_root = output_full if output_full.is_dir() else output_full.parent
    if not search_root.exists():
        return ""
    markdown_files = [
        path
        for path in search_root.rglob("*")
        if path.is_file() and path.suffix.lower() in {".md", ".markdown"}
    ]
    if not markdown_files:
        return ""
    markdown_files.sort(key=lambda path: (path.stat().st_mtime, len(path.parts)), reverse=True)
    return _rel(vault, markdown_files[0])


def _mineru_command_args(
    cli: str,
    mode: str,
    input_arg: str,
    output_full: Path,
    output_format: str,
    language: str,
    pages: str,
    model: str,
    ocr: bool,
    table: bool,
    formula: bool,
    token: str,
    base_url: str,
    verbose: bool,
    timeout_seconds: int,
) -> list[str]:
    normalized_mode = mode.strip().lower()
    if normalized_mode not in {"flash-extract", "extract"}:
        raise ValueError("mode must be 'flash-extract' or 'extract'.")
    args = [cli, normalized_mode, input_arg, "-o", str(output_full)]
    if normalized_mode == "extract":
        args.extend(["-f", output_format or "md"])
        if model:
            args.extend(["--model", model])
    if language:
        args.extend(["--language" if normalized_mode == "flash-extract" else "-l", language])
    if pages:
        args.extend(["--pages", pages])
    if ocr:
        args.append("--ocr")
    if table:
        args.append("--table")
    if formula:
        args.append("--formula")
    if token:
        args.extend(["--token", token])
    if base_url:
        args.extend(["--base-url", base_url])
    if verbose:
        args.append("--verbose")
    args.extend(["--timeout", str(max(1, timeout_seconds))])
    return args


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


def _clean_cli_params(params: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in params.items() if value not in ("", None, False)}


def _doctor(vault_path: str = "") -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    try:
        vault = _vault(vault_path)
        checks.append({"name": "vault", "ok": True, "path": str(vault)})
    except Exception as exc:
        return {"ok": False, "checks": [{"name": "vault", "ok": False, "error": str(exc)}]}

    checks.append({"name": "vault_config", "ok": True, "config": _vault_config(vault)})
    checks.append({"name": "templates", "ok": True, "config": _template_config(vault), "count": len(_list_user_templates(vault))})
    checks.append({"name": "obsidian_cli", "ok": shutil.which(os.environ.get("OBSIDIAN_CLI_COMMAND", "obsidian")) is not None})
    try:
        import yaml  # type: ignore  # noqa: F401

        checks.append({"name": "pyyaml", "ok": True})
    except Exception as exc:
        checks.append({"name": "pyyaml", "ok": False, "error": str(exc)})
    try:
        import pypdf  # type: ignore  # noqa: F401

        checks.append({"name": "pypdf", "ok": True})
    except Exception:
        try:
            import PyPDF2  # type: ignore  # noqa: F401

            checks.append({"name": "pypdf", "ok": True, "fallback": "PyPDF2"})
        except Exception as exc:
            checks.append({"name": "pypdf", "ok": False, "error": str(exc)})
    mineru_status = _mineru_cli_status()
    mineru_status["name"] = "mineru_cli"
    checks.append(mineru_status)
    try:
        sample = _zotero_api("users/0/items", {"limit": 1, "format": "json"})
        checks.append({"name": "zotero_api", "ok": True, "sampleCount": len(sample or [])})
    except Exception as exc:
        checks.append({"name": "zotero_api", "ok": False, "error": str(exc)})
    optional = {"obsidian_cli", "zotero_api", "mineru_cli", "pypdf"}
    return {"ok": all(item.get("ok", False) for item in checks if item.get("name") not in optional), "checks": checks}


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


