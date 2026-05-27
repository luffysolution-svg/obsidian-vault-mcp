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


def _s(value: Any, default: str = "") -> str:
    """Return value as str, replacing None with default."""
    return default if value is None else str(value)


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
    if _s(template_path).strip():
        rel_path = _ensure_md_path(_s(template_path).strip())
        return rel_path, _read_text(_safe_path(vault, rel_path))
    wanted = _s(template_name).strip()
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


def _moment_to_strftime(fmt: str) -> str:
    replacements = [
        ("YYYY", "%Y"),
        ("YY", "%y"),
        ("MMMM", "%B"),
        ("MMM", "%b"),
        ("MM", "%m"),
        ("DD", "%d"),
        ("HH", "%H"),
        ("mm", "%M"),
        ("ss", "%S"),
    ]
    result = fmt
    for old, new in replacements:
        result = result.replace(old, new)
    return result


def _render_template(template: str, title: str, body: str, properties: dict[str, Any]) -> str:
    now = datetime.now()

    def property_value(key: str) -> str:
        value = properties.get(key, "")
        if isinstance(value, (list, dict)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    def replace_date(match: re.Match[str]) -> str:
        fmt = match.group(1) or "YYYY-MM-DD"
        return now.strftime(_moment_to_strftime(fmt))

    def replace_time(match: re.Match[str]) -> str:
        fmt = match.group(1) or "HH:mm"
        return now.strftime(_moment_to_strftime(fmt))

    def replace_property(match: re.Match[str]) -> str:
        return property_value(match.group(1).strip())

    rendered = template
    replacements = {
        "{{title}}": title,
        "{{name}}": title,
        "{{date}}": now.strftime("%Y-%m-%d"),
        "{{time}}": now.strftime("%H:%M"),
        "{{body}}": body,
        "{{content}}": body,
        "<% tp.file.title %>": title,
        "<% tp.file.content %>": body,
    }
    for key, value in replacements.items():
        rendered = rendered.replace(key, value)
    for key, value in properties.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", property_value(str(key)))
    rendered = re.sub(r"\{\{\s*date(?::([^}]+))?\s*\}\}", replace_date, rendered)
    rendered = re.sub(r"\{\{\s*time(?::([^}]+))?\s*\}\}", replace_time, rendered)
    rendered = re.sub(r"\{\{\s*(?:property|prop)\s*:\s*([^}]+)\s*\}\}", replace_property, rendered)
    rendered = re.sub(r"<%\s*tp\.date\.now\(\s*['\"]([^'\"]+)['\"]\s*\)\s*%>", replace_date, rendered)
    rendered = re.sub(r"<%\s*tp\.frontmatter\.([A-Za-z0-9_-]+)\s*%>", replace_property, rendered)
    return rendered


def _apply_note_template(vault: Path, title: str, body: str, properties: dict[str, Any], template_path: str = "", template_name: str = "", use_template: bool = False) -> tuple[str, str, dict[str, Any]]:
    config = _template_config(vault)
    should_use = use_template or bool(_s(template_path).strip() or _s(template_name).strip() or config.get("defaultTemplate"))
    if not should_use:
        return body, "", properties
    rel_path, template = _find_user_template(vault, template_path, template_name)
    template_props, template_body = _split_frontmatter(template)
    merged_props = dict(template_props)
    merged_props.update(properties)
    rendered_body = _render_template(template_body, title, body, merged_props)
    rendered_props = {
        key: _render_template(str(value), title, body, merged_props) if isinstance(value, str) else value
        for key, value in merged_props.items()
    }
    return rendered_body, rel_path, rendered_props


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


def _transaction_id(value: str = "") -> str:
    raw = _s(value).strip()
    if not raw:
        return f"{_utc_now().replace(':', '').replace('-', '')}-{uuid.uuid4().hex[:8]}"
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", raw):
        raise ValueError("transaction_id may only contain letters, numbers, dots, underscores, and hyphens.")
    return raw


def _backup_path(vault: Path, transaction_id: str, rel_path: str) -> Path:
    root = (vault / BACKUP_DIR / transaction_id).resolve()
    candidate = (root / rel_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Backup path escapes transaction directory: {rel_path}") from exc
    return candidate


def _transaction_manifest_path(vault: Path, transaction_id: str) -> Path:
    root = (vault / BACKUP_DIR / transaction_id).resolve()
    try:
        root.relative_to((vault / BACKUP_DIR).resolve())
    except ValueError as exc:
        raise ValueError(f"Transaction path escapes backup directory: {transaction_id}") from exc
    return root / "manifest.json"


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
    tag = str(value).strip().lstrip("#")
    if "/" in tag:
        # Hierarchical tag: normalize each segment (replace spaces with hyphens)
        segments = [re.sub(r"\s+", "-", seg.strip()) for seg in tag.split("/")]
        return "/".join(s for s in segments if s)
    return tag


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


def _rewrite_wikilinks(vault: Path, old_rel: str, new_rel: str) -> dict[str, Any]:
    """Rewrite [[wikilinks]] across all .md files after a file move or rename."""
    old_stem = Path(old_rel).stem
    new_stem = Path(new_rel).stem
    old_no_ext = re.sub(r"\.md$", "", old_rel)
    new_no_ext = re.sub(r"\.md$", "", new_rel)

    patterns: list[tuple[re.Pattern[str], str]] = [
        (re.compile(rf"\[\[{re.escape(old_no_ext)}\]\]"), f"[[{new_no_ext}]]"),
        (re.compile(rf"\[\[{re.escape(old_no_ext)}\|([^\]]+)\]\]"), rf"[[{new_no_ext}|\1]]"),
    ]
    if old_stem != old_no_ext:
        patterns.extend([
            (re.compile(rf"\[\[{re.escape(old_stem)}\]\]"), f"[[{new_stem}]]"),
            (re.compile(rf"\[\[{re.escape(old_stem)}\|([^\]]+)\]\]"), rf"[[{new_stem}|\1]]"),
        ])

    updated_files: list[str] = []
    total_count = 0
    for md_path in _collect_markdown(vault):
        rel = _rel(vault, md_path)
        if rel == old_rel:
            continue
        text = _read_text(md_path)
        new_text = text
        count = 0
        for pattern, replacement in patterns:
            new_text, n = pattern.subn(replacement, new_text)
            count += n
        if count > 0:
            _write_text(md_path, new_text)
            updated_files.append(rel)
            total_count += count
    return {"files": updated_files, "count": total_count}


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
    clean_label = _s(label).strip()
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
    clean_folder = folder.strip("/").replace("\\", "/")
    return f"{clean_folder}/{_slug_filename(_item_name(item))}.md"


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
        parts.append(f'"{_s(folder).strip("/")}"')
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


BIBTEX_MONTHS = {
    "jan": "January",
    "feb": "February",
    "mar": "March",
    "apr": "April",
    "may": "May",
    "jun": "June",
    "jul": "July",
    "aug": "August",
    "sep": "September",
    "oct": "October",
    "nov": "November",
    "dec": "December",
}


class _BibTeXParser:
    def __init__(self, raw: str):
        self.raw = raw
        self.length = len(raw)
        self.pos = 0
        self.strings: dict[str, str] = dict(BIBTEX_MONTHS)

    def parse(self) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        while True:
            self._skip_ws_and_comments()
            at = self.raw.find("@", self.pos)
            if at == -1:
                break
            self.pos = at + 1
            entry_type = self._read_identifier().lower()
            self._skip_ws_and_comments()
            if not entry_type or self.pos >= self.length or self.raw[self.pos] not in "{(":
                continue
            close = "}" if self.raw[self.pos] == "{" else ")"
            self.pos += 1
            if entry_type == "string":
                self._parse_string(close)
            elif entry_type in {"comment", "preamble"}:
                self._skip_balanced(close)
            else:
                entry = self._parse_entry(entry_type, close)
                if entry:
                    entries.append(entry)
        return entries

    def _skip_ws_and_comments(self) -> None:
        while self.pos < self.length:
            if self.raw[self.pos].isspace():
                self.pos += 1
                continue
            if self.raw[self.pos] == "%":
                newline = self.raw.find("\n", self.pos)
                self.pos = self.length if newline == -1 else newline + 1
                continue
            break

    def _read_identifier(self) -> str:
        start = self.pos
        while self.pos < self.length and re.match(r"[A-Za-z0-9_.:+/-]", self.raw[self.pos]):
            self.pos += 1
        return self.raw[start:self.pos].strip()

    def _read_until_entry_delimiter(self, close: str) -> str:
        start = self.pos
        while self.pos < self.length and self.raw[self.pos] not in {",", close}:
            self.pos += 1
        return self.raw[start:self.pos].strip()

    def _consume(self, value: str) -> bool:
        self._skip_ws_and_comments()
        if self.pos < self.length and self.raw[self.pos] == value:
            self.pos += 1
            return True
        return False

    def _skip_balanced(self, close: str) -> None:
        depth = 1
        quote = False
        escape = False
        while self.pos < self.length and depth > 0:
            ch = self.raw[self.pos]
            self.pos += 1
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"' and close == "}" and depth == 1:
                quote = not quote
                continue
            if quote:
                continue
            if ch in "{(":
                depth += 1
            elif ch == close:
                depth -= 1

    def _parse_string(self, close: str) -> None:
        while self.pos < self.length:
            self._skip_ws_and_comments()
            if self._consume(close):
                return
            key = self._read_identifier().lower()
            if not key or not self._consume("="):
                self._skip_balanced(close)
                return
            self.strings[key] = self._parse_value(close)
            self._consume(",")

    def _parse_entry(self, entry_type: str, close: str) -> dict[str, Any]:
        citekey = self._read_until_entry_delimiter(close)
        if not citekey:
            self._skip_balanced(close)
            return {}
        if self._consume(close):
            return {"entryType": entry_type, "citekey": citekey}
        self._consume(",")
        fields: dict[str, Any] = {}
        while self.pos < self.length:
            self._skip_ws_and_comments()
            if self._consume(close):
                break
            name = self._read_identifier().lower()
            if not name:
                self.pos += 1
                continue
            if not self._consume("="):
                fields[name] = ""
                self._consume(",")
                continue
            fields[name] = _clean_bibtex_value(self._parse_value(close))
            self._consume(",")
        if "author" in fields:
            fields["authors"] = _split_authors(str(fields["author"]))
        if "editor" in fields:
            fields["editors"] = _split_authors(str(fields["editor"]))
        if "keywords" in fields:
            fields["keywords"] = [part.strip() for part in re.split(r"[,;]", str(fields["keywords"])) if part.strip()]
        if "year" in fields:
            try:
                fields["year"] = int(str(fields["year"])[:4])
            except ValueError:
                pass
        return {"entryType": entry_type, "citekey": citekey.strip(), **fields}

    def _parse_value(self, close: str) -> str:
        parts = [self._parse_value_part(close)]
        while True:
            self._skip_ws_and_comments()
            if self.pos >= self.length or self.raw[self.pos] != "#":
                break
            self.pos += 1
            parts.append(self._parse_value_part(close))
        return "".join(parts)

    def _parse_value_part(self, close: str) -> str:
        self._skip_ws_and_comments()
        if self.pos >= self.length:
            return ""
        ch = self.raw[self.pos]
        if ch == "{":
            return self._read_braced()
        if ch == '"':
            return self._read_quoted()
        token = self._read_until_value_delimiter(close)
        if re.fullmatch(r"[+-]?\d+", token):
            return token
        return self.strings.get(token.lower(), token)

    def _read_until_value_delimiter(self, close: str) -> str:
        start = self.pos
        while self.pos < self.length and self.raw[self.pos] not in {"#", ",", close} and not self.raw[self.pos].isspace():
            self.pos += 1
        return self.raw[start:self.pos].strip()

    def _read_braced(self) -> str:
        self.pos += 1
        depth = 1
        start = self.pos
        escape = False
        while self.pos < self.length and depth > 0:
            ch = self.raw[self.pos]
            if escape:
                escape = False
                self.pos += 1
                continue
            if ch == "\\":
                escape = True
                self.pos += 1
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    value = self.raw[start:self.pos]
                    self.pos += 1
                    return value
            self.pos += 1
        return self.raw[start:self.pos]

    def _read_quoted(self) -> str:
        self.pos += 1
        start = self.pos
        brace_depth = 0
        escape = False
        while self.pos < self.length:
            ch = self.raw[self.pos]
            if escape:
                escape = False
                self.pos += 1
                continue
            if ch == "\\":
                escape = True
                self.pos += 1
                continue
            if ch == "{":
                brace_depth += 1
            elif ch == "}" and brace_depth > 0:
                brace_depth -= 1
            elif ch == '"' and brace_depth == 0:
                value = self.raw[start:self.pos]
                self.pos += 1
                return value
            self.pos += 1
        return self.raw[start:self.pos]


def _clean_bibtex_value(value: str) -> str:
    cleaned = value.strip().rstrip(",").strip()
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    replacements = {
        r"\\&": "&",
        r"\\%": "%",
        r"\\_": "_",
        r"\\#": "#",
        r"\\$": "$",
        "{": "",
        "}": "",
    }
    for old, new in replacements.items():
        cleaned = cleaned.replace(old, new)
    return cleaned


def _split_authors(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"\s+and\s+", value) if part.strip()]


def _parse_bibtex_entries(raw: str) -> list[dict[str, Any]]:
    return _BibTeXParser(raw).parse()


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
    # Promote extra bibliographic fields from rawData if not already set at top level
    raw = metadata.get("rawData") or {}
    for field in (
        "volume", "issue", "pages", "publisher", "ISBN", "journalAbbreviation",
        "conferenceName", "proceedingsTitle", "bookTitle",
        "university", "thesisType", "patentNumber", "assignee", "country",
        "reportNumber", "institution", "place", "edition", "numPages", "series", "repository",
    ):
        if not metadata.get(field):
            value = raw.get(field)
            if value:
                metadata[field] = value
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
    title = str(metadata.get("title") or "Untitled Reference")
    year = str(metadata.get("year") or "").strip()
    first_author = ""
    authors = _listify(metadata.get("authors"))
    if authors:
        first_author = str(authors[0]).split(",")[0].split()[-1]
    author_year = f"{first_author} ({year})" if first_author and year else first_author or year
    pieces = [piece for piece in [author_year, title[:80]] if piece]
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
    lines: list[str] = []
    authors = _listify(metadata.get("authors"))
    item_type = str(metadata.get("itemType") or "")
    if authors:
        lines.extend(["## Citation", "", f"- Authors: {', '.join(str(author) for author in authors)}"])
        if metadata.get("year"):
            lines.append(f"- Year: {metadata['year']}")
        if metadata.get("doi"):
            lines.append(f"- DOI: {metadata['doi']}")
        if metadata.get("url"):
            lines.append(f"- URL: {metadata['url']}")
        # Type-specific citation fields
        if item_type == "journalArticle":
            if metadata.get("publicationTitle"):
                lines.append(f"- Journal: {metadata['publicationTitle']}")
            vol_issue = "/".join(str(metadata[f]) for f in ("volume", "issue") if metadata.get(f))
            if vol_issue:
                lines.append(f"- Vol/Issue: {vol_issue}")
            if metadata.get("pages"):
                lines.append(f"- Pages: {metadata['pages']}")
        elif item_type == "conferencePaper":
            if metadata.get("conferenceName"):
                lines.append(f"- Conference: {metadata['conferenceName']}")
            if metadata.get("proceedingsTitle"):
                lines.append(f"- Proceedings: {metadata['proceedingsTitle']}")
            if metadata.get("place"):
                lines.append(f"- Place: {metadata['place']}")
            if metadata.get("pages"):
                lines.append(f"- Pages: {metadata['pages']}")
        elif item_type in ("book", "bookSection"):
            if item_type == "bookSection" and metadata.get("bookTitle"):
                lines.append(f"- Book: {metadata['bookTitle']}")
            if metadata.get("publisher"):
                lines.append(f"- Publisher: {metadata['publisher']}")
            if metadata.get("place"):
                lines.append(f"- Place: {metadata['place']}")
            if metadata.get("edition"):
                lines.append(f"- Edition: {metadata['edition']}")
            if metadata.get("ISBN"):
                lines.append(f"- ISBN: {metadata['ISBN']}")
            if metadata.get("pages"):
                lines.append(f"- Pages: {metadata['pages']}")
        elif item_type == "thesis":
            if metadata.get("university"):
                lines.append(f"- University: {metadata['university']}")
            if metadata.get("thesisType"):
                lines.append(f"- Type: {metadata['thesisType']}")
            if metadata.get("place"):
                lines.append(f"- Place: {metadata['place']}")
        elif item_type == "patent":
            if metadata.get("patentNumber"):
                lines.append(f"- Patent No.: {metadata['patentNumber']}")
            if metadata.get("country"):
                lines.append(f"- Country: {metadata['country']}")
            if metadata.get("assignee"):
                lines.append(f"- Assignee: {metadata['assignee']}")
        elif item_type == "report":
            if metadata.get("reportNumber"):
                lines.append(f"- Report No.: {metadata['reportNumber']}")
            if metadata.get("institution"):
                lines.append(f"- Institution: {metadata['institution']}")
        elif item_type == "preprint":
            if metadata.get("repository"):
                lines.append(f"- Repository: {metadata['repository']}")
        lines.append("")
    attachment_paths = [str(item) for item in _listify(metadata.get("attachments")) if str(item).strip()]
    if attachment_path and attachment_path not in attachment_paths:
        attachment_paths.insert(0, attachment_path)
    if attachment_paths:
        lines.extend(["## Attachments", ""])
        lines.extend(f"- ![[{path}]]" for path in attachment_paths)
        lines.append("")
    other_attachments = _listify(metadata.get("otherAttachments"))
    if other_attachments:
        lines.extend(["## Other Attachments", ""])
        for att in other_attachments:
            if isinstance(att, dict):
                title = att.get("title") or att.get("key") or "attachment"
                path = att.get("path") or ""
                ctype = att.get("contentType") or ""
                label = f"{title} ({ctype})" if ctype else title
                lines.append(f"- [{label}]({path})" if path else f"- {label}")
            else:
                lines.append(f"- {att}")
        lines.append("")
    if abstract:
        lines.extend(["## Abstract", "", _s(abstract).strip(), ""])
    if notes:
        lines.extend([_s(notes).strip(), ""])
    if content:
        lines.extend(["## Extracted Content", "", _s(content).strip(), ""])
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
    # Extract related item keys from relations.dc:relation (list of zotero://... URIs)
    relations_raw = data.get("relations", {})
    related_uris: list[str] = []
    if isinstance(relations_raw, dict):
        dc_rel = relations_raw.get("dc:relation", [])
        if isinstance(dc_rel, str):
            dc_rel = [dc_rel]
        related_uris = [str(u) for u in dc_rel if u]
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
        "collections": data.get("collections", []),
        "relations": related_uris,
        "volume": data.get("volume"),
        "issue": data.get("issue"),
        "pages": data.get("pages"),
        "publisher": data.get("publisher"),
        "ISBN": data.get("ISBN"),
        "journalAbbreviation": data.get("journalAbbreviation"),
        # Type-specific fields
        "conferenceName": data.get("conferenceName"),
        "proceedingsTitle": data.get("proceedingsTitle"),
        "bookTitle": data.get("bookTitle"),
        "university": data.get("university"),
        "thesisType": data.get("thesisType"),
        "patentNumber": data.get("patentNumber"),
        "assignee": data.get("assignee"),
        "country": data.get("country"),
        "reportNumber": data.get("reportNumber"),
        "institution": data.get("institution"),
        "place": data.get("place"),
        "edition": data.get("edition"),
        "numPages": data.get("numPages"),
        "series": data.get("series"),
        "repository": data.get("repository"),
        "parentItem": data.get("parentItem"),
        "note": _plain_note(data.get("note")) if data.get("itemType") == "note" else "",
        "annotationText": data.get("annotationText"),
        "annotationComment": data.get("annotationComment"),
        "annotationType": data.get("annotationType"),
        "annotationColor": data.get("annotationColor"),
        "annotationPageLabel": data.get("annotationPageLabel"),
        "annotationPosition": data.get("annotationPosition"),
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


_ANNOTATION_COLOR_NAMES: dict[str, str] = {
    "#ffd400": "yellow",
    "#ff6666": "red",
    "#5fb236": "green",
    "#2ea8e5": "blue",
    "#a28ae5": "purple",
    "#e56eee": "magenta",
    "#f19837": "orange",
    "#aaaaaa": "gray",
}

_ANNOTATION_COLOR_EMOJIS: dict[str, str] = {
    "#ffd400": "🟡",
    "#ff6666": "🔴",
    "#5fb236": "🟢",
    "#2ea8e5": "🔵",
    "#a28ae5": "🟣",
    "#e56eee": "🩷",
    "#f19837": "🟠",
    "#aaaaaa": "⬜",
}


def _annotation_emoji(color: str | None) -> str:
    if not color:
        return "📝"
    key = color.lower()
    if key in _ANNOTATION_COLOR_EMOJIS:
        return _ANNOTATION_COLOR_EMOJIS[key]
    nearest_emoji, nearest_dist = min(
        ((emoji, _color_distance(key, hex_c)) for hex_c, emoji in _ANNOTATION_COLOR_EMOJIS.items()),
        key=lambda x: x[1],
    )
    return nearest_emoji if nearest_dist <= 20 else "📝"  # spec: ±20 tolerance for color matching


def _resolve_annotation_color_labels(vault: Path, color_labels_json: str) -> dict[str, str]:
    labels: dict[str, str] = dict(_ANNOTATION_COLOR_NAMES)
    labels.update(_load_ethereal_color_labels())
    vault_cfg = _vault_config(vault).get("annotationColorLabels", {})
    if isinstance(vault_cfg, dict):
        labels.update({k.lower(): str(v) for k, v in vault_cfg.items()})
    if color_labels_json and color_labels_json.strip() not in ("{}", ""):
        try:
            param_labels = json.loads(color_labels_json)
            if isinstance(param_labels, dict):
                labels.update({k.lower(): str(v) for k, v in param_labels.items()})
        except json.JSONDecodeError:
            pass
    return labels


# Cache for Ethereal Style color labels loaded from prefs.js
_ethereal_color_labels: dict[str, str] = {}
_ethereal_color_labels_mtime: float = 0.0


def _load_ethereal_color_labels() -> dict[str, str]:
    """Load annotation color name mappings from Ethereal Style (ZoteroStyle) plugin prefs.js."""
    global _ethereal_color_labels, _ethereal_color_labels_mtime
    import glob as _glob
    import sys as _sys
    if _sys.platform == "win32":
        candidates = ["~/AppData/Roaming/Zotero/Zotero/Profiles/*/prefs.js"]
    elif _sys.platform == "darwin":
        candidates = ["~/Library/Application Support/Zotero/Profiles/*/prefs.js"]
    else:
        xdg = os.environ.get("XDG_DATA_HOME", "")
        candidates = [os.path.join(xdg, "zotero/Profiles/*/prefs.js")] if xdg else ["~/.zotero/zotero/Profiles/*/prefs.js"]
    prefs_files: list[str] = []
    for pattern in candidates:
        prefs_files = _glob.glob(os.path.expanduser(pattern))
        if prefs_files:
            break
    if not prefs_files:
        return _ethereal_color_labels
    prefs_path = prefs_files[0]
    try:
        mtime = os.path.getmtime(prefs_path)
    except OSError:
        return _ethereal_color_labels
    # Return cached result if file hasn't changed
    if mtime == _ethereal_color_labels_mtime and _ethereal_color_labels:
        return _ethereal_color_labels
    result: dict[str, str] = {}
    try:
        with open(prefs_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        import re as _re
        m = _re.search(
            r'user_pref\("extensions\.zotero\.zoterostyle\.annotationColors",\s*"(.+?)"\)',
            content,
        )
        if m:
            raw = m.group(1).replace('\\"', '"')
            pairs = json.loads(raw)
            for name, hex_color in pairs:
                result[hex_color.lower()] = name
    except Exception:
        pass
    if result:
        _ethereal_color_labels = result
        _ethereal_color_labels_mtime = mtime
    return _ethereal_color_labels


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int] | None:
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return None
    try:
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        return None


def _color_distance(a: str, b: str) -> float:
    ra = _hex_to_rgb(a)
    rb = _hex_to_rgb(b)
    if ra is None or rb is None:
        return float("inf")
    return ((ra[0]-rb[0])**2 + (ra[1]-rb[1])**2 + (ra[2]-rb[2])**2) ** 0.5


def _annotation_color_label(color: str | None) -> str:
    if not color:
        return ""
    key = color.lower()
    labels = _load_ethereal_color_labels()
    # 1. Exact match against zoterostyle config
    if key in labels:
        return labels[key]
    # 2. Nearest-color match within zoterostyle config (threshold: RGB distance ≤ 15)
    if labels:
        nearest_label, nearest_dist = min(
            ((lbl, _color_distance(key, cfg_hex)) for cfg_hex, lbl in labels.items()),
            key=lambda x: x[1],
        )
        if nearest_dist <= 15:
            return nearest_label
    # 3. Fallback to built-in Zotero standard English names
    return _ANNOTATION_COLOR_NAMES.get(key, color)


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
            ann_type = str(annotation.get("annotationType") or "highlight")
            page = str(annotation.get("annotationPageLabel") or "").strip()
            color = _annotation_color_label(annotation.get("annotationColor"))

            meta_parts = []
            if page:
                meta_parts.append(f"p. {page}")
            if color:
                meta_parts.append(color)
            if ann_type and ann_type != "highlight":
                meta_parts.append(ann_type)
            meta = f" `[{', '.join(meta_parts)}]`" if meta_parts else ""

            # Parse position for machine-readable HTML comment
            position_comment = ""
            raw_pos = annotation.get("annotationPosition")
            if raw_pos:
                try:
                    pos_data = json.loads(raw_pos) if isinstance(raw_pos, str) else raw_pos
                    if isinstance(pos_data, dict):
                        position_comment = f"<!-- zotero-position: {json.dumps(pos_data, separators=(',', ':'))} -->"
                except Exception:
                    pass

            if ann_type == "note" and not text:
                if comment:
                    lines.append(f"> [!note]{meta}")
                    lines.append(f"> {comment}")
                    if position_comment:
                        lines.append(position_comment)
                    lines.append("")
            else:
                if text:
                    lines.append(f"> [!quote]{meta}")
                    lines.append(f"> {text}")
                    if comment:
                        lines.append("> ")
                        lines.append(f"> **Note:** {comment}")
                    if position_comment:
                        lines.append(position_comment)
                    lines.append("")
                elif comment:
                    lines.append(f"> [!note]{meta}")
                    lines.append(f"> {comment}")
                    if position_comment:
                        lines.append(position_comment)
                    lines.append("")
    return "\n".join(lines).strip()


def _zotero_annotations_structured(
    children: dict[str, list[dict[str, Any]]],
    color_labels: dict[str, str],
) -> str:
    """Render annotations as foldable callouts sorted by page, with color emoji and semantic labels."""
    lines: list[str] = []
    notes = children.get("notes", [])
    annotations = children.get("annotations", [])

    if notes:
        lines.extend(["## Zotero Notes", ""])
        for note in notes:
            lines.extend([f"### Note {note.get('key')}", "", str(note.get("note") or "").strip(), ""])

    if annotations:
        lines.extend(["## Annotations", ""])

        def _page_sort_key(ann: dict[str, Any]) -> tuple[int, Any]:
            page = str(ann.get("annotationPageLabel") or "")
            try:
                return (0, int(page))
            except ValueError:
                return (1, page)

        for annotation in sorted(annotations, key=_page_sort_key):
            text = str(annotation.get("annotationText") or "").strip()
            comment = str(annotation.get("annotationComment") or "").strip()
            ann_type = str(annotation.get("annotationType") or "highlight")
            page = str(annotation.get("annotationPageLabel") or "").strip()
            color = annotation.get("annotationColor")

            emoji = _annotation_emoji(color)
            label = ""
            if color:
                key = color.lower()
                if key in color_labels:
                    label = color_labels[key]
                elif color_labels:
                    nearest = min(
                        ((lbl, _color_distance(key, cfg)) for cfg, lbl in color_labels.items()),
                        key=lambda x: x[1],
                    )
                    if nearest[1] <= 20:
                        label = nearest[0]

            header_parts = [emoji]
            if label:
                header_parts.append(label)
            if page:
                header_parts.append(f"— p.{page}")
            header = " ".join(header_parts)

            if ann_type == "note" and not text:
                if comment:
                    lines.append(f"> [!note]+ {header}")
                    lines.append(f"> {comment}")
                    lines.append("")
            else:
                if text:
                    lines.append(f"> [!quote]+ {header}")
                    lines.append(f"> {text}")
                    if comment:
                        lines.append("> ")
                        lines.append(f"> *{comment}*")
                    lines.append("")
                elif comment:
                    lines.append(f"> [!note]+ {header}")
                    lines.append(f"> {comment}")
                    lines.append("")

    return "\n".join(lines).strip()


_ZOTERO_OWNED_FIELDS = frozenset({
    "title", "authors", "year", "abstract", "doi", "DOI",
    "zoteroKey", "zoteroVersion", "zoteroSelect", "zoteroLinks",
    "zoteroPdfKeys", "zoteroPdfLinks", "zoteroAttachmentPaths",
    "attachments", "attachment", "otherAttachments",
    "volume", "issue", "pages", "publisher", "ISBN", "journalAbbreviation",
    "conferenceName", "proceedingsTitle", "bookTitle",
    "university", "thesisType", "patentNumber", "assignee", "country",
    "reportNumber", "institution", "place", "edition", "numPages", "series", "repository",
    "itemType", "journal", "publicationTitle", "booktitle", "type",
    "citekey", "citationKey", "url", "language", "collections",
})


def _replace_zotero_sections(body: str, new_notes_content: str) -> str:
    """Replace ## Zotero Notes / ## Zotero Annotations block with new_notes_content."""
    first_pos = -1
    for heading in ("## Zotero Notes\n", "## Zotero Annotations\n"):
        pos = body.find(heading)
        if pos != -1 and (first_pos == -1 or pos < first_pos):
            first_pos = pos

    if first_pos == -1:
        if not new_notes_content:
            return body
        marker = "\n## Extracted Content"
        if marker in body:
            return body.replace(marker, "\n\n" + new_notes_content.strip() + marker, 1)
        return body.rstrip() + "\n\n" + new_notes_content.strip() + "\n"

    # Find end of Zotero block: next ## heading that is not a Zotero section
    search_pos = first_pos
    end_pos = len(body)
    while True:
        next_h2 = body.find("\n## ", search_pos + 1)
        if next_h2 == -1:
            end_pos = len(body)
            break
        if body[next_h2 + 1:].startswith("## Zotero "):
            search_pos = next_h2 + 1
            continue
        end_pos = next_h2
        break

    before = body[:first_pos].rstrip("\n")
    after = body[end_pos:]
    if new_notes_content:
        return before + "\n\n" + new_notes_content.strip() + "\n" + after
    return before + "\n" + after


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
        completed = subprocess.run([executable, "version"], capture_output=True, text=True, timeout=20, check=False)  # noqa: S603
        status["versionCommand"] = [executable, "version"]
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


# ── MinerU image rename helpers ─────────────────────────────────────────────

# Matches  ![alt](path)  anywhere on a line
_MINERU_MD_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
# Matches  ![[path]]  (Obsidian wikilink image)
_MINERU_WIKI_IMAGE_RE = re.compile(r"!\[\[([^\]]+)\]\]")

# Strong caption: starts with 图/表/Figure/Table/Scheme/Chart/式/公式 + optional space + digit
_MINERU_CAPTION_STRONG_RE = re.compile(
    r"^[>\s*_]*(?:图|表|Figure|Table|Scheme|Chart|式|公式)\s*\d+",
    re.IGNORECASE,
)
# Weak caption: entire line is bold or italic markdown (common inline caption)
_MINERU_CAPTION_WEAK_RE = re.compile(r"^\*{1,2}.+\*{1,2}$")

# Characters illegal in filenames on Windows/macOS/Linux
_MINERU_ILLEGAL_CHARS_RE = re.compile(r'[<>:"/\\|?*\n\r\t]')


def _mineru_find_images(lines: list[str]) -> list[tuple[int, str, str, str]]:
    """Scan markdown lines for image references.

    Returns a list of (line_idx, raw_ref, img_path, alt) tuples.
      raw_ref  — the full original text matched, e.g. ![alt](images/uuid.png)
      img_path — just the path/filename portion, e.g. images/uuid.png
      alt      — alt text (empty string for wikilink format)
    One entry per occurrence; the same img_path may appear multiple times.
    """
    results: list[tuple[int, str, str, str]] = []
    for idx, line in enumerate(lines):
        for m in _MINERU_MD_IMAGE_RE.finditer(line):
            alt = m.group(1)
            path = m.group(2)
            results.append((idx, m.group(0), path, alt))
        for m in _MINERU_WIKI_IMAGE_RE.finditer(line):
            path = m.group(1)
            # Only treat as image if it looks like an image file
            if Path(path).suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp"}:
                results.append((idx, m.group(0), path, ""))
    return results


def _mineru_extract_caption(
    lines: list[str], img_line_idx: int, window: int
) -> tuple[str, str]:
    """Sliding-window caption search around an image line.

    Returns (caption_text, strategy) where strategy is one of:
      "caption_after"   — caption found on a line after the image
      "caption_before"  — caption found on a line before the image
      "radius"          — caption found anywhere in the window (strong only)
      ""                — nothing found (caller applies fallback)
    """
    total = len(lines)

    def _is_strong(line: str) -> bool:
        return bool(_MINERU_CAPTION_STRONG_RE.match(line.strip()))

    def _is_weak(line: str) -> bool:
        stripped = line.strip()
        return bool(_MINERU_CAPTION_WEAK_RE.match(stripped)) and len(stripped) > 3

    # Priority 2: scan lines AFTER the image
    for i in range(img_line_idx + 1, min(total, img_line_idx + window + 1)):
        text = lines[i].strip()
        if not text:
            continue
        if _is_strong(text) or _is_weak(text):
            return text, "caption_after"
        break  # stop at first non-empty line that doesn't match

    # Priority 3: scan lines BEFORE the image (reversed)
    for i in range(img_line_idx - 1, max(-1, img_line_idx - window - 1), -1):
        text = lines[i].strip()
        if not text:
            continue
        if _is_strong(text) or _is_weak(text):
            return text, "caption_before"
        break  # stop at first non-empty line that doesn't match

    # Priority 4: anywhere in the full window — strong pattern only
    start = max(0, img_line_idx - window)
    end = min(total, img_line_idx + window + 1)
    for i in range(start, end):
        if i == img_line_idx:
            continue
        text = lines[i].strip()
        if _is_strong(text):
            return text, "radius"

    return "", ""


def _mineru_caption_to_slug(
    caption: str, doc_slug: str, ext: str, used: set[str]
) -> str:
    """Convert a caption string into a deduplicated image filename.

    Rules:
    - Illegal filename characters removed
    - ASCII whitespace runs replaced with '-'
    - Chinese characters kept verbatim
    - Truncated to 60 characters
    - Format: {doc_slug}_{cleaned_caption}{ext}
    - Appends _2, _3, … if the name is already in `used`
    """
    cleaned = _MINERU_ILLEGAL_CHARS_RE.sub("", caption).strip()
    cleaned = re.sub(r"[ \t]+", "-", cleaned)
    cleaned = cleaned[:60].rstrip("-")
    if not cleaned:
        cleaned = "img"

    stem = f"{doc_slug}_{cleaned}" if doc_slug else cleaned
    candidate = f"{stem}{ext}"
    if candidate not in used:
        used.add(candidate)
        return candidate
    counter = 2
    while True:
        candidate = f"{stem}_{counter}{ext}"
        if candidate not in used:
            used.add(candidate)
            return candidate
        counter += 1


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
    edge_ids: set[str] = set()
    valid_node_types = {"text", "file", "link", "group"}
    valid_sides = {"top", "right", "bottom", "left"}
    valid_ends = {"none", "arrow"}
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            issues.append({"path": rel_path, "severity": "error", "message": f"Node {index} must be an object."})
            continue
        for key in ["id", "type", "x", "y", "width", "height"]:
            if key not in node:
                issues.append({"path": rel_path, "severity": "error", "node": node.get("id", index), "field": key, "message": "Canvas node is missing a required field."})
        node_id = node.get("id")
        node_type = node.get("type")
        if not isinstance(node_id, str) or not node_id:
            issues.append({"path": rel_path, "severity": "error", "node": index, "field": "id", "message": "Canvas node id must be a non-empty string."})
        if node_type not in valid_node_types:
            issues.append({"path": rel_path, "severity": "error", "node": node.get("id", index), "field": "type", "message": "Canvas node type must be text, file, link, or group."})
        for key in ["x", "y", "width", "height"]:
            if key in node and not isinstance(node.get(key), (int, float)):
                issues.append({"path": rel_path, "severity": "error", "node": node.get("id", index), "field": key, "message": "Canvas node geometry fields must be numbers."})
        for key in ["width", "height"]:
            if isinstance(node.get(key), (int, float)) and node.get(key) <= 0:
                issues.append({"path": rel_path, "severity": "error", "node": node.get("id", index), "field": key, "message": "Canvas node size must be positive."})
        if node_type == "text" and not isinstance(node.get("text"), str):
            issues.append({"path": rel_path, "severity": "error", "node": node.get("id", index), "field": "text", "message": "Text nodes require a text string."})
        if node_type == "file" and not isinstance(node.get("file"), str):
            issues.append({"path": rel_path, "severity": "error", "node": node.get("id", index), "field": "file", "message": "File nodes require a file path string."})
        if node_type == "link" and not isinstance(node.get("url"), str):
            issues.append({"path": rel_path, "severity": "error", "node": node.get("id", index), "field": "url", "message": "Link nodes require a URL string."})
        if "color" in node and not isinstance(node.get("color"), str):
            issues.append({"path": rel_path, "severity": "warning", "node": node.get("id", index), "field": "color", "message": "Canvas node color should be a string."})
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
        edge_id = edge.get("id")
        if not isinstance(edge_id, str) or not edge_id:
            issues.append({"path": rel_path, "severity": "error", "edge": index, "field": "id", "message": "Canvas edge id must be a non-empty string."})
        if edge.get("id") in edge_ids:
            issues.append({"path": rel_path, "severity": "error", "edge": edge.get("id"), "message": "Duplicate Canvas edge id."})
        if edge.get("id"):
            edge_ids.add(str(edge["id"]))
        if edge.get("fromNode") not in node_ids or edge.get("toNode") not in node_ids:
            issues.append({"path": rel_path, "severity": "error", "edge": edge.get("id", index), "message": "Canvas edge references a missing node."})
        for key in ["fromSide", "toSide"]:
            if key in edge and edge.get(key) not in valid_sides:
                issues.append({"path": rel_path, "severity": "error", "edge": edge.get("id", index), "field": key, "message": "Canvas edge side must be top, right, bottom, or left."})
        for key in ["fromEnd", "toEnd"]:
            if key in edge and edge.get(key) not in valid_ends:
                issues.append({"path": rel_path, "severity": "error", "edge": edge.get("id", index), "field": key, "message": "Canvas edge end must be none or arrow."})
    return issues


def _validate_base_filter(rel_path: str, value: Any, field: str = "filters") -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if value in ("", None):
        return issues
    if isinstance(value, str):
        return issues
    if isinstance(value, list):
        for index, item in enumerate(value):
            issues.extend(_validate_base_filter(rel_path, item, f"{field}[{index}]"))
        return issues
    if isinstance(value, dict):
        if len(value) != 1:
            issues.append({"path": rel_path, "severity": "error", "field": field, "message": "Base filter objects should contain exactly one operator."})
        for operator, nested in value.items():
            if operator not in {"and", "or", "not"}:
                issues.append({"path": rel_path, "severity": "error", "field": field, "operator": operator, "message": "Base filter operator must be and, or, or not."})
                continue
            if operator in {"and", "or"} and not isinstance(nested, list):
                issues.append({"path": rel_path, "severity": "error", "field": field, "operator": operator, "message": "Base and/or filters must contain a list."})
            issues.extend(_validate_base_filter(rel_path, nested, f"{field}.{operator}"))
        return issues
    issues.append({"path": rel_path, "severity": "error", "field": field, "message": "Base filter must be a string, list, or operator object."})
    return issues


CITATION_LINK_FIELDS = ("related", "cites", "references", "entities", "concepts", "sources")

_WIKILINK_VALUE_RE = re.compile(r"^\[\[([^\]\n]+)\]\]$")


def _frontmatter_link_target(value: str) -> str:
    """Return the note key from a frontmatter value that is a path or a [[wikilink]]."""
    stripped = str(value).strip()
    m = _WIKILINK_VALUE_RE.match(stripped)
    if m:
        return _target_from_link(m.group(1))
    return _target_from_link(stripped)


_graph_cache: dict[tuple[str, str, bool], tuple[float, dict[str, Any]]] = {}


def _graph_cache_get(vault: Path, folder: str, include_tags: bool) -> dict[str, Any] | None:
    key = (str(vault), folder, include_tags)
    if key not in _graph_cache:
        return None
    cached_mtime, cached_result = _graph_cache[key]
    for path in _iter_files(vault, folder):
        if path.suffix.lower() == ".md":
            try:
                if path.stat().st_mtime > cached_mtime:
                    _graph_cache.pop(key, None)
                    return None
            except OSError:
                _graph_cache.pop(key, None)
                return None
    return cached_result


def _graph_cache_set(vault: Path, folder: str, include_tags: bool, result: dict[str, Any]) -> None:
    key = (str(vault), folder, include_tags)
    max_mtime = 0.0
    for path in _iter_files(vault, folder):
        if path.suffix.lower() == ".md":
            try:
                mtime = path.stat().st_mtime
                if mtime > max_mtime:
                    max_mtime = mtime
            except OSError:
                pass
    _graph_cache[key] = (max_mtime, result)


def _graph_cache_invalidate(vault: Path, folder: str = "") -> None:
    keys_to_remove = [k for k in _graph_cache if k[0] == str(vault) and (not folder or k[1] == folder)]
    for k in keys_to_remove:
        _graph_cache.pop(k, None)


def _validate_base_payload(rel_path: str, payload: Any) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if not isinstance(payload, dict):
        return [{"path": rel_path, "severity": "error", "message": "Base root must be a YAML object."}]
    allowed_top_level = {"filters", "formulas", "properties", "summaries", "views"}
    for key in payload:
        if key not in allowed_top_level:
            issues.append({"path": rel_path, "severity": "warning", "field": key, "message": "Unknown top-level Base key."})
    issues.extend(_validate_base_filter(rel_path, payload.get("filters"), "filters"))
    for key in ["formulas", "properties", "summaries"]:
        if key in payload and not isinstance(payload.get(key), dict):
            issues.append({"path": rel_path, "severity": "error", "field": key, "message": f"Base {key} section must be an object."})
    views = payload.get("views")
    if not isinstance(views, list) or not views:
        issues.append({"path": rel_path, "severity": "error", "field": "views", "message": "Base must define at least one view."})
        return issues
    for index, view in enumerate(views):
        if not isinstance(view, dict):
            issues.append({"path": rel_path, "severity": "error", "view": index, "message": "Base view must be an object."})
            continue
        if not isinstance(view.get("type"), str) or not view.get("type"):
            issues.append({"path": rel_path, "severity": "error", "view": index, "field": "type", "message": "Base view type is required."})
        if not view.get("name"):
            issues.append({"path": rel_path, "severity": "warning", "view": index, "field": "name", "message": "Base view should have a name."})
        if "filters" in view:
            issues.extend(_validate_base_filter(rel_path, view.get("filters"), f"views[{index}].filters"))
        if "limit" in view and not isinstance(view.get("limit"), int):
            issues.append({"path": rel_path, "severity": "error", "view": index, "field": "limit", "message": "Base view limit must be an integer."})
        if "order" in view and not (isinstance(view.get("order"), list) and all(isinstance(item, str) for item in view.get("order", []))):
            issues.append({"path": rel_path, "severity": "error", "view": index, "field": "order", "message": "Base view order must be a list of property strings."})
        if "summaries" in view and not isinstance(view.get("summaries"), dict):
            issues.append({"path": rel_path, "severity": "error", "view": index, "field": "summaries", "message": "Base view summaries must be an object."})
        if "groupBy" in view:
            group_by = view.get("groupBy")
            if not isinstance(group_by, dict) or not isinstance(group_by.get("property"), str):
                issues.append({"path": rel_path, "severity": "error", "view": index, "field": "groupBy", "message": "Base groupBy must define a property string."})
            direction = str(group_by.get("direction", "")).upper() if isinstance(group_by, dict) else ""
            if direction and direction not in {"ASC", "DESC"}:
                issues.append({"path": rel_path, "severity": "error", "view": index, "field": "groupBy.direction", "message": "Base groupBy direction must be ASC or DESC."})
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
        op = str(operation.get("op") or operation.get("operation") or operation.get("type") or "").strip().lower()
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


# ---------------------------------------------------------------------------
# Graph intelligence helpers (networkx-based)
# ---------------------------------------------------------------------------

_SOURCE_EDGE_KINDS = {"related", "cites", "references", "entities", "concepts", "sources"}

_FOLDER_TYPE_MAP = {
    "literature": "literature",
    "lit": "literature",
    "papers": "literature",
    "concepts": "concept",
    "concept": "concept",
    "entities": "entity",
    "entity": "entity",
    "sources": "source",
    "projects": "project",
    "project": "project",
}


def _build_nx_graph(graph_data: dict[str, Any]) -> Any:
    """Convert obsidian_build_graph output into a networkx undirected Graph.

    Raises ImportError if networkx is not installed.
    """
    try:
        import networkx as nx
    except ImportError:
        raise ImportError("networkx>=3.0 is required for graph analytics. Install with: pip install 'networkx>=3.0'")
    G = nx.Graph()
    for node in graph_data["nodes"]:
        G.add_node(node["id"])
    for edge in graph_data["edges"]:
        src, tgt = edge["source"], edge["target"]
        if not G.has_edge(src, tgt):
            G.add_edge(src, tgt)
    return G


def _build_source_index(graph_data: dict[str, Any]) -> dict[str, set[str]]:
    """Map each node to its set of source identifiers.

    Identifiers come from:
    - targets of outgoing citation-kind edges (cites, references, related, etc.)
    - first 5 frontmatter tags, prefixed with '#' to avoid path collisions
    """
    index: dict[str, set[str]] = {n["id"]: set() for n in graph_data["nodes"]}
    for edge in graph_data["edges"]:
        if edge.get("kind") in _SOURCE_EDGE_KINDS:
            src = edge["source"]
            if src in index:
                index[src].add(edge["target"])
    for node in graph_data["nodes"]:
        for tag in node.get("tags", [])[:5]:
            if tag:
                index[node["id"]].add(f"#{tag}")
    return index


def _compute_source_overlap(sources_a: set[str], sources_b: set[str]) -> float:
    """Overlap coefficient between two source sets: |A∩B| / max(|A|, |B|). Returns 0.0 if either is empty."""
    if not sources_a or not sources_b:
        return 0.0
    intersection = len(sources_a & sources_b)
    if intersection == 0:
        return 0.0
    return intersection / max(len(sources_a), len(sources_b))


def _get_node_type(node_id: str) -> str:
    """Infer node type from the first folder segment of its vault-relative path."""
    first_folder = node_id.split("/")[0].lower() if "/" in node_id else ""
    return _FOLDER_TYPE_MAP.get(first_folder, "note")


def _compute_scored_suggestions(
    G: Any,
    graph_data: dict[str, Any],
    source_index: dict[str, set[str]],
    max_pairs: int = 500,
) -> list[dict[str, Any]]:
    """Compute scored link suggestions using the 4-signal model.

    Signals:
      source_overlap × 4.0   — shared citation targets and tags (Jaccard)
      adamic_adar    × 1.5   — common neighbours via networkx
      type_affinity  × 1.0   — same inferred folder type
      direct_link    × 3.0   — (used as filter only; unconnected pairs always 0)

    Only node pairs with source_overlap > 0 are scored.
    The top max_pairs candidates (by overlap) are passed to adamic_adar_index.
    """
    import networkx as nx

    existing_pairs: set[tuple[str, str]] = set()
    for edge in graph_data["edges"]:
        existing_pairs.add((edge["source"], edge["target"]))
        existing_pairs.add((edge["target"], edge["source"]))

    node_ids = [n["id"] for n in graph_data["nodes"]]

    # Find candidate pairs with source_overlap > 0
    candidates: list[tuple[str, str, float]] = []
    for i, u in enumerate(node_ids):
        for v in node_ids[i + 1:]:
            if (u, v) in existing_pairs:
                continue
            overlap = _compute_source_overlap(source_index.get(u, set()), source_index.get(v, set()))
            if overlap > 0:
                candidates.append((u, v, overlap))

    # Limit to top max_pairs by overlap before computing Adamic-Adar
    candidates.sort(key=lambda x: -x[2])
    candidates = candidates[:max_pairs]

    if not candidates:
        return []

    # Compute Adamic-Adar for all candidates at once
    aa_map: dict[tuple[str, str], float] = {}
    try:
        for u, v, aa_score in nx.adamic_adar_index(G, [(u, v) for u, v, _ in candidates]):
            aa_map[(u, v)] = aa_score
    except Exception:
        pass  # Defensive guard against unexpected networkx version changes or malformed edge data

    results: list[dict[str, Any]] = []
    for u, v, overlap in candidates:
        aa = aa_map.get((u, v), 0.0)
        type_aff = 1.0 if _get_node_type(u) == _get_node_type(v) else 0.0
        score = 4.0 * overlap + 1.5 * aa + 1.0 * type_aff

        shared = source_index.get(u, set()) & source_index.get(v, set())
        reason_parts: list[str] = []
        if shared:
            reason_parts.append(f"共享来源 {len(shared)} 项")
        if aa > 0.01:
            reason_parts.append(f"{round(aa, 1)} 个共同邻居")
        reason = "；".join(reason_parts) if reason_parts else "存在间接关联"

        results.append({
            "kind": "scored_link",
            "from": u,
            "to": v,
            "score": round(score, 2),
            "signals": {
                "sourceOverlap": round(4.0 * overlap, 2),
                "adamicAdar": round(1.5 * aa, 2),
                "typeAffinity": type_aff,
                "directLink": 0.0,
            },
            "reason": reason,
        })

    results.sort(key=lambda x: -x["score"])
    return results


# ──────────────────────────────────────────────────────────────────────────── #
# Wiki context helpers                                                         #
# ──────────────────────────────────────────────────────────────────────────── #


def _wiki_neighbors(
    vault: Path,
    topic_id: str,
    graph: dict[str, Any],
    max_n: int,
    snippet_chars: int,
) -> list[dict[str, Any]]:
    """Return 1-hop wikilink neighbours of *topic_id* in *graph*, each with a body snippet."""
    nodes_by_id = {n["id"]: n for n in graph.get("nodes", [])}
    neighbor_ids: set[str] = set()
    for edge in graph.get("edges", []):
        if edge.get("source") == topic_id:
            neighbor_ids.add(edge["target"])
        elif edge.get("target") == topic_id:
            neighbor_ids.add(edge["source"])

    results: list[dict[str, Any]] = []
    for nid in sorted(neighbor_ids):
        if len(results) >= max_n:
            break
        node = nodes_by_id.get(nid, {})
        title = str(node.get("title") or Path(nid).stem)
        snippet = ""
        try:
            full = _safe_path(vault, nid)
            if full.exists():
                _, body = _split_frontmatter(_read_text(full))
                snippet = body.strip()[:snippet_chars]
        except Exception:
            pass
        results.append({"path": nid, "title": title, "snippet": snippet})
    return results


def _wiki_search_results(
    vault: Path,
    topic: str,
    max_n: int,
    context_chars: int = 140,
) -> list[dict[str, Any]]:
    """Full-text search across all .md files for *topic* (case-insensitive)."""
    needle = topic.lower()
    if not needle:
        return []
    results: list[dict[str, Any]] = []
    for path in _iter_files(vault):
        if path.suffix.lower() != ".md":
            continue
        try:
            lines = _read_text(path).splitlines()
        except UnicodeDecodeError:
            continue
        for number, line in enumerate(lines, start=1):
            idx = line.lower().find(needle)
            if idx != -1:
                start = max(0, idx - context_chars // 2)
                end = min(len(line), idx + len(needle) + context_chars // 2)
                results.append({
                    "path": _rel(vault, path),
                    "line": number,
                    "snippet": line[start:end].strip(),
                })
                if len(results) >= max_n:
                    return results
    return results


def _wiki_zotero_items(
    topic: str,
    max_n: int,
    api_base: str = "",
) -> list[dict[str, Any]]:
    """Search Zotero for *topic* and return title + abstract for each hit.

    Raises on any network/timeout error — caller is responsible for catching.
    """
    params: dict[str, Any] = {"q": topic, "limit": max(1, min(max_n, 100)), "format": "json"}
    raw_items = _zotero_api("users/0/items", params, api_base) or []
    result: list[dict[str, Any]] = []
    for item in raw_items:
        data = item.get("data", {})
        authors = [
            c.get("lastName", "")
            for c in data.get("creators", [])
            if c.get("creatorType") == "author"
        ]
        raw_date = str(data.get("date", "") or "")
        year = raw_date[:4] if raw_date else ""
        result.append({
            "key": item.get("key") or data.get("key"),
            "title": data.get("title", ""),
            "abstract": data.get("abstractNote", ""),
            "authors": authors,
            "year": year,
        })
    return result


def _wiki_entity_concept_nodes(
    vault: Path,
    topic: str,
    entities_folder: str,
    concepts_folder: str,
    max_n: int,
    snippet_chars: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Search *entities_folder* and *concepts_folder* for notes matching *topic*."""
    needle = topic.lower()

    def _search(folder_name: str) -> list[dict[str, Any]]:
        folder = vault / folder_name
        if not folder.exists() or not folder.is_dir():
            return []
        hits: list[dict[str, Any]] = []
        for path in sorted(folder.rglob("*.md")):
            if len(hits) >= max_n:
                break
            rel = _rel(vault, path)
            try:
                text = _read_text(path)
            except Exception:
                continue
            props, body = _split_frontmatter(text)
            title = str(props.get("title") or path.stem)
            if needle in (title + " " + body).lower():
                hits.append({
                    "path": rel,
                    "title": title,
                    "snippet": body.strip()[:snippet_chars],
                })
        return hits

    return _search(entities_folder), _search(concepts_folder)
