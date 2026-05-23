from . import helpers as _helpers

globals().update({name: value for name, value in vars(_helpers).items() if not name.startswith("__")})


@tool()
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


@tool()
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


@tool()
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


@tool()
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


@tool()
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


@tool()
def obsidian_delete_file(
    path: str,
    vault_path: str = "",
    backup: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Delete a vault-relative file, optionally backing it up to .obsidian-vault-backups/ first."""
    vault = _vault(vault_path)
    full = _safe_path(vault, path)
    rel = _rel(vault, full)
    if not full.exists():
        return {"ok": False, "path": rel, "error": "File does not exist."}
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_rel = f"{BACKUP_DIR}/manual/{timestamp}/{rel}" if backup else ""
    if dry_run:
        return {"ok": True, "path": rel, "backup": backup_rel, "dryRun": True}
    if backup:
        backup_full = vault / backup_rel
        backup_full.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(full, backup_full)
    full.unlink()
    return {"ok": True, "path": rel, "backup": backup_rel, "dryRun": False}


@tool()
def obsidian_move_file(
    path: str,
    to: str,
    vault_path: str = "",
    update_wikilinks: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Move a vault-relative file to a different directory. Pass update_wikilinks=true to rewrite [[links]] across the vault."""
    vault = _vault(vault_path)
    src_full = _safe_path(vault, path)
    src_rel = _rel(vault, src_full)
    if not src_full.exists():
        return {"ok": False, "path": src_rel, "error": "File does not exist."}
    to_dir = _safe_path(vault, to)
    dest_full = to_dir / src_full.name
    dest_rel = (Path(to.strip("/")) / src_full.name).as_posix()
    if not dry_run and dest_full.exists():
        return {"ok": False, "path": src_rel, "error": f"Destination already exists: {dest_rel}"}
    if dry_run:
        return {"ok": True, "from": src_rel, "to": dest_rel, "dryRun": True}
    dest_full.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src_full), str(dest_full))
    result: dict[str, Any] = {"ok": True, "from": src_rel, "to": dest_rel, "dryRun": False}
    if update_wikilinks:
        rewrites = _rewrite_wikilinks(vault, src_rel, dest_rel)
        result["updatedFiles"] = rewrites["files"]
        result["replacementCount"] = rewrites["count"]
    return result


@tool()
def obsidian_rename_file(
    path: str,
    name: str,
    vault_path: str = "",
    update_wikilinks: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Rename a vault-relative file in place. Pass update_wikilinks=true to rewrite [[links]] across the vault."""
    vault = _vault(vault_path)
    src_full = _safe_path(vault, path)
    src_rel = _rel(vault, src_full)
    if not src_full.exists():
        return {"ok": False, "path": src_rel, "error": "File does not exist."}
    if "/" in name or "\\" in name:
        return {"ok": False, "path": src_rel, "error": "name must be a filename only, not a path. Use obsidian_move_file to change directories."}
    dest_full = src_full.parent / name
    dest_rel = _rel(vault, dest_full)
    if not dry_run and dest_full.exists():
        return {"ok": False, "path": src_rel, "error": f"Destination already exists: {dest_rel}"}
    if dry_run:
        return {"ok": True, "from": src_rel, "to": dest_rel, "dryRun": True}
    src_full.rename(dest_full)
    result: dict[str, Any] = {"ok": True, "from": src_rel, "to": dest_rel, "dryRun": False}
    if update_wikilinks:
        rewrites = _rewrite_wikilinks(vault, src_rel, dest_rel)
        result["updatedFiles"] = rewrites["files"]
        result["replacementCount"] = rewrites["count"]
    return result


@tool()
def obsidian_create_note(
    path: str,
    title: str = "",
    body: str = "",
    properties_json: str = "{}",
    vault_path: str = "",
    template_path: str = "",
    template_name: str = "",
    use_template: bool = False,
    overwrite: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Create a Markdown note with YAML properties, optionally applying a user template."""
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
    content_body = _s(body).strip()
    template_used = ""
    content_body, template_used, properties = _apply_note_template(vault, note_title, content_body, properties, template_path, template_name, use_template)
    content_body = content_body.strip()
    if content_body and not content_body.startswith("#"):
        content_body = f"# {note_title}\n\n{content_body}"
    elif not content_body:
        content_body = f"# {note_title}\n"
    content = _join_frontmatter(properties, content_body)
    result = _write_result(vault, full, content, dry_run)
    result["properties"] = properties
    result["template"] = template_used
    return result


@tool()
def obsidian_list_user_templates(vault_path: str = "") -> dict[str, Any]:
    """List Markdown templates discovered from Obsidian Templates/Templater settings and plugin config."""
    vault = _vault(vault_path)
    config = _template_config(vault)
    return {"ok": True, "vaultPath": str(vault), "config": config, "templates": _list_user_templates(vault)}


@tool()
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


@tool()
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


@tool()
def obsidian_build_graph(
    vault_path: str = "",
    folder: str = "",
    include_tags: bool = True,
    write_json_path: str = "",
) -> dict[str, Any]:
    """Build graph data from Markdown wikilinks, embeds, frontmatter tags, and backlinks."""
    vault = _vault(vault_path)
    if not write_json_path:
        cached = _graph_cache_get(vault, folder, include_tags)
        if cached is not None:
            return cached
    md_files = [path for path in _iter_files(vault, folder) if path.suffix.lower() == ".md"]
    known_by_key: dict[str, set[str]] = {}
    file_cache: dict[str, tuple[Path, dict[str, Any], str]] = {}
    for path in md_files:
        rel_path = _rel(vault, path)
        props, body = _split_frontmatter(_read_text(path))
        file_cache[rel_path] = (path, props, body)
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

    def _add_edge(source: str, raw_target: str, kind: str) -> None:
        target_rel, ambiguous_targets = _resolve_note_key(known_by_key, raw_target)
        if target_rel and target_rel != source:
            edges.append({"source": source, "target": target_rel, "kind": kind})
            outgoing[source].add(target_rel)
            incoming.setdefault(target_rel, set()).add(source)
        elif ambiguous_targets:
            ambiguous.setdefault(raw_target, []).append({"source": source, "matches": ambiguous_targets})
        else:
            unresolved.setdefault(raw_target, []).append(source)

    for rel_path, (path, props, body) in file_cache.items():
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
            for match in regex.finditer(body):
                _add_edge(rel_path, _target_from_link(match.group(1)), kind)
        for field in CITATION_LINK_FIELDS:
            for value in _listify(props.get(field)):
                raw_target = _frontmatter_link_target(str(value))
                if raw_target:
                    _add_edge(rel_path, raw_target, field)

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
    if not write_json_path:
        _graph_cache_set(vault, folder, include_tags, result)
    if write_json_path:
        output = _safe_path(vault, write_json_path)
        _write_text(output, json.dumps(result, ensure_ascii=False, indent=2))
        result["writtenTo"] = _rel(vault, output)
    return result


@tool()
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


@tool()
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


@tool()
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


@tool()
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
    entities_folder = _configured_path(vault, "entitiesFolder", entities_folder, "entities")
    concepts_folder = _configured_path(vault, "conceptsFolder", concepts_folder, "concepts")
    index_path = _configured_path(vault, "indexPath", index_path, "index.md")
    log_path = _configured_path(vault, "logPath", log_path, "log.md")
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
    if _s(summary).strip():
        body_lines.extend(["## Summary", "", _s(summary).strip(), ""])
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


@tool()
def obsidian_parse_bibtex(
    bibtex: str,
) -> dict[str, Any]:
    """Parse BibTeX into normalized reference metadata."""
    entries = _parse_bibtex_entries(bibtex)
    return {"ok": True, "entryCount": len(entries), "entries": entries}


@tool()
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
    vault = _vault(vault_path)
    source_folder = _configured_path(vault, "literatureFolder", source_folder, "literature")
    index_path = _configured_path(vault, "indexPath", index_path, "index.md")
    log_path = _configured_path(vault, "logPath", log_path, "log.md")
    metadata_raw = _json(metadata_json, {})
    if not isinstance(metadata_raw, dict):
        raise ValueError("metadata_json must decode to an object.")
    metadata = _metadata_from_reference(metadata_raw)
    title = str(metadata.get("title") or "Untitled Reference")
    rel_path = f"{source_folder.strip('/')}/{_reference_filename(metadata)}.md"
    duplicate = _find_existing_reference(vault, metadata, source_folder)
    if duplicate and not overwrite:
        return {"ok": True, "duplicate": True, "existingPath": duplicate["path"], "matchedOn": duplicate["field"], "referencePath": rel_path, "metadata": metadata}
    tags = _merge_unique(metadata.get("tags"), ["source", "literature"])
    _exclude_keys = {
        "parentItem", "note", "annotationText", "annotationComment",
        "annotationType", "annotationColor", "annotationPageLabel", "annotationPosition",
        "attachmentPath", "contentType", "links", "rawData",
        "creators", "zoteroLinks",
        "key", "version", "date",
        "relations",
    }
    # Fields that should only appear when they have a non-null value
    _omit_if_empty = {
        "publicationTitle", "volume", "issue", "pages", "publisher", "ISBN", "journalAbbreviation",
        "conferenceName", "proceedingsTitle", "bookTitle",
        "university", "thesisType", "patentNumber", "assignee", "country",
        "reportNumber", "institution", "place", "edition", "numPages", "series", "repository",
        "doi",
    }
    source_props = {}
    for k, v in metadata.items():
        if k in _exclude_keys:
            continue
        if k in _omit_if_empty and not v:
            continue
        source_props[k] = v
    source_props["type"] = "literature"
    source_props["tags"] = tags
    if attachment_path:
        source_props["attachment"] = attachment_path
    body = _reference_source_body(metadata, abstract=abstract or str(metadata.get("abstract") or ""), notes=notes, content=content, attachment_path=attachment_path)
    result = obsidian_ingest_source_note(
        source_path=rel_path,
        content=body,
        vault_path=str(vault),
        title=title,
        summary="",
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


@tool()
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
    vault = _vault(vault_path)
    source_folder = _configured_path(vault, "literatureFolder", source_folder, "literature")
    index_path = _configured_path(vault, "indexPath", index_path, "index.md")
    log_path = _configured_path(vault, "logPath", log_path, "log.md")
    entries = _parse_bibtex_entries(bibtex)
    results: list[dict[str, Any]] = []
    for entry in entries:
        results.append(
            obsidian_ingest_reference(
                metadata_json=json.dumps(entry, ensure_ascii=False),
                vault_path=str(vault),
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


@tool()
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
    source_root = _configured_path(vault, "mineruSourceFolder", "sources/mineru", "sources/mineru")
    index_path = _configured_path(vault, "indexPath", index_path, "index.md")
    log_path = _configured_path(vault, "logPath", log_path, "log.md")
    metadata = _json(metadata_json, {})
    if not isinstance(metadata, dict):
        raise ValueError("metadata_json must decode to an object.")
    content = _s(markdown_content)
    if markdown_path:
        content = _read_text(_safe_path(vault, markdown_path))
    if not content.strip():
        raise ValueError("markdown_content or markdown_path is required.")
    source_title = title or str(metadata.get("title") or _note_title_from_path(_s(markdown_path) or "MinerU Extraction.md"))
    rel_path = _s(source_path).strip() or f"{source_root}/{_slug_filename(source_title)}.md"

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


@tool()
def obsidian_mineru_status(
    cli_command: str = "",
) -> dict[str, Any]:
    """Check optional MinerU CLI availability and token environment variables."""
    return _mineru_cli_status(cli_command)


@tool()
def obsidian_mineru_extract(
    input_path: str,
    vault_path: str = "",
    output_path: str = "",
    mode: str = "",
    output_format: str = "md",
    language: str = "ch",
    pages: str = "",
    model: str = "",
    ocr: bool = False,
    table: bool = False,
    formula: bool = False,
    token: str = "",
    base_url: str = "",
    cli_command: str = "",
    timeout_seconds: int = MINERU_TIMEOUT,
    verbose: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run MinerU CLI extraction and save output under the vault.

    Mode selection (auto when mode is empty):
    - If a token is available (param or MINERU_TOKEN / MINERU_API_TOKEN env var),
      defaults to 'extract' (precise, up to 600 pages).
    - Otherwise defaults to 'flash-extract' (free, up to 20 pages).
    Pass mode='flash-extract' explicitly to force flash even when a token is set.
    """
    vault = _vault(vault_path)
    # Resolve token: explicit param wins, then env vars
    resolved_token = token or os.environ.get("MINERU_TOKEN") or os.environ.get("MINERU_API_TOKEN") or ""
    # Resolve mode: explicit param wins, then auto-select based on token availability
    resolved_mode = _s(mode).strip() or ("extract" if resolved_token else "flash-extract")
    token_source = "param" if token else ("env" if resolved_token else "none")
    status = _mineru_cli_status(cli_command)
    cli = str(status.get("path") or cli_command or MINERU_CLI_COMMAND)
    input_arg, input_name = _mineru_input_argument(vault, input_path)
    output_full, output_rel = _mineru_output_path(vault, output_path, input_name)
    args = _mineru_command_args(
        cli=cli,
        mode=resolved_mode,
        input_arg=input_arg,
        output_full=output_full,
        output_format=output_format,
        language=language,
        pages=pages,
        model=model,
        ocr=ocr,
        table=table,
        formula=formula,
        token=resolved_token,
        base_url=base_url,
        verbose=verbose,
        timeout_seconds=timeout_seconds,
    )
    redacted_args = list(args)
    if resolved_token and "--token" in redacted_args:
        token_index = redacted_args.index("--token") + 1
        if token_index < len(redacted_args):
            redacted_args[token_index] = "***"
    result: dict[str, Any] = {
        "ok": False,
        "dryRun": dry_run,
        "vaultPath": str(vault),
        "input": input_path,
        "outputPath": output_rel,
        "mode": resolved_mode,
        "tokenSource": token_source,
        "command": redacted_args,
        "mineru": status,
    }
    if not status.get("available"):
        result["error"] = status.get("installHint") or "MinerU CLI is not available."
        return result
    if not status.get("ok"):
        result["error"] = status.get("error") or "MinerU CLI is available but its version check failed."
        return result
    if dry_run:
        result["ok"] = True
        return result

    if output_full.suffix:
        output_full.parent.mkdir(parents=True, exist_ok=True)
    else:
        output_full.mkdir(parents=True, exist_ok=True)
    try:
        completed = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=max(1, timeout_seconds + 30), check=False)  # noqa: S603
    except Exception as exc:
        result["error"] = f"MinerU CLI failed to start: {exc}"
        return result
    markdown_rel = _find_mineru_markdown(vault, output_full)
    result.update(
        {
            "ok": completed.returncode == 0 and bool(markdown_rel),
            "returnCode": completed.returncode,
            "stdout": _s(completed.stdout).strip(),
            "stderr": _s(completed.stderr).strip(),
            "markdownPath": markdown_rel,
        }
    )
    if completed.returncode != 0:
        result["error"] = "MinerU CLI failed."
    elif not markdown_rel:
        result["error"] = "MinerU CLI completed but no Markdown output was found."
    return result


@tool()
def obsidian_mineru_extract_and_ingest(
    input_path: str,
    vault_path: str = "",
    output_path: str = "",
    source_path: str = "",
    title: str = "",
    mode: str = "",
    output_format: str = "md",
    language: str = "ch",
    pages: str = "",
    model: str = "",
    ocr: bool = False,
    table: bool = False,
    formula: bool = False,
    token: str = "",
    base_url: str = "",
    cli_command: str = "",
    timeout_seconds: int = MINERU_TIMEOUT,
    metadata_json: str = "{}",
    entities_json: str = "[]",
    concepts_json: str = "[]",
    index_path: str = "index.md",
    log_path: str = "log.md",
    overwrite: bool = False,
    zotero_key: str = "",
    update_index: bool = True,
    append_log: bool = True,
    verbose: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Extract a document with MinerU CLI, then ingest the Markdown output.

    Mode and token follow the same auto-resolution as obsidian_mineru_extract:
    precise 'extract' mode is used automatically when a token is available.
    When zotero_key is provided and extraction succeeds, the corresponding
    literature note in the vault will have mineru_markdown added to its YAML
    frontmatter (all other fields and body content are left unchanged).
    """
    vault = _vault(vault_path)
    extraction = obsidian_mineru_extract(
        input_path=input_path,
        vault_path=str(vault),
        output_path=output_path,
        mode=mode,
        output_format=output_format,
        language=language,
        pages=pages,
        model=model,
        ocr=ocr,
        table=table,
        formula=formula,
        token=token,
        base_url=base_url,
        cli_command=cli_command,
        timeout_seconds=timeout_seconds,
        verbose=verbose,
        dry_run=dry_run,
    )
    result: dict[str, Any] = {"ok": False, "dryRun": dry_run, "extraction": extraction}
    if dry_run:
        result["ok"] = extraction.get("ok", False)
        return result
    if not extraction.get("ok"):
        result["error"] = extraction.get("error") or "MinerU extraction failed."
        return result

    pdf_attachment_path = ""
    if not _is_url(input_path):
        try:
            input_full = Path(input_path).expanduser()
            if not input_full.is_absolute():
                input_full = _safe_path(vault, input_path)
            input_full = input_full.resolve()
            try:
                pdf_attachment_path = _rel(vault, input_full)
            except ValueError:
                pdf_attachment_path = ""
        except Exception:
            pdf_attachment_path = ""

    ingest = obsidian_ingest_mineru_markdown(
        markdown_path=str(extraction.get("markdownPath") or ""),
        pdf_attachment_path=pdf_attachment_path,
        vault_path=str(vault),
        source_path=source_path,
        title=title,
        metadata_json=metadata_json,
        entities_json=entities_json,
        concepts_json=concepts_json,
        index_path=index_path,
        log_path=log_path,
        overwrite=overwrite,
        update_index=update_index,
        append_log=append_log,
        dry_run=False,
    )
    result["ingest"] = ingest
    result["ok"] = bool(ingest.get("ok"))

    # If a zotero_key is given and extraction succeeded, add mineru_markdown to the literature note
    if zotero_key and result["ok"]:
        markdown_rel = str(extraction.get("markdownPath") or "")
        if markdown_rel:
            lit_note = _find_existing_reference(vault, {"zoteroKey": zotero_key}, "")
            if lit_note:
                lit_path = _safe_path(vault, lit_note["path"])
                existing_props, existing_body = _split_frontmatter(_read_text(lit_path))
                wikilink = "[[" + re.sub(r"\.md$", "", markdown_rel) + "]]"
                existing_props["mineru_markdown"] = wikilink
                if not dry_run:
                    lit_path.write_text(_join_frontmatter(existing_props, existing_body), encoding="utf-8")
                result["zoteroKey"] = zotero_key
                result["literatureNotePath"] = lit_note["path"]

    return result


@tool()
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
    source_root = _configured_path(vault, "pdfSourceFolder", "sources/pdf", "sources/pdf")
    index_path = _configured_path(vault, "indexPath", index_path, "index.md")
    log_path = _configured_path(vault, "logPath", log_path, "log.md")
    pdf_full = _safe_path(vault, pdf_attachment_path)
    if not pdf_full.exists() and not dry_run:
        raise FileNotFoundError(f"PDF attachment not found: {pdf_attachment_path}")
    metadata = _json(metadata_json, {})
    if not isinstance(metadata, dict):
        raise ValueError("metadata_json must decode to an object.")
    source_title = title or str(metadata.get("title") or _note_title_from_path(pdf_attachment_path))
    rel_path = _s(source_path).strip() or f"{source_root}/{_slug_filename(source_title)}.md"
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


@tool()
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


@tool()
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


@tool()
def obsidian_zotero_list_collections(
    api_base: str = "",
) -> list[dict[str, Any]]:
    """List all Zotero collections with their key, name, parent, and item count.

    Returns a flat list sorted by name. Use the key field with
    obsidian_ingest_zotero_collection to batch-import by collection name.
    """
    raw = _zotero_api("users/0/collections", {"limit": 100, "format": "json"}, api_base) or []
    result = []
    for col in raw:
        data = col.get("data", {})
        meta = col.get("meta", {})
        parent = data.get("parentCollection") or ""
        result.append({
            "key": col.get("key", ""),
            "name": data.get("name", ""),
            "parentKey": parent if parent else None,
            "numItems": meta.get("numItems", 0),
        })
    result.sort(key=lambda c: c["name"].lower())
    return result


@tool()
def obsidian_zotero_get_item(
    key: str,
    api_base: str = "",
) -> dict[str, Any]:
    """Get one Zotero item by key."""
    item = _zotero_api(f"users/0/items/{key}", {"format": "json"}, api_base)
    return _zotero_item_summary(item)


@tool()
def obsidian_zotero_get_children(
    parent_key: str,
    api_base: str = "",
) -> dict[str, list[dict[str, Any]]]:
    """Get notes, annotations, attachments, and other child items for one Zotero item."""
    direct = [_zotero_item_summary(item) for item in _zotero_api(f"users/0/items/{parent_key}/children", {"format": "json", "limit": 100}, api_base) or []]
    grouped: dict[str, list[dict[str, Any]]] = {"notes": [], "annotations": [], "attachments": [], "other": []}
    pdf_keys: list[str] = []
    for child in direct:
        item_type = child.get("itemType")
        if item_type == "note":
            grouped["notes"].append(child)
        elif item_type == "annotation":
            grouped["annotations"].append(child)
        elif item_type == "attachment":
            grouped["attachments"].append(child)
            if child.get("key"):
                pdf_keys.append(str(child["key"]))
        else:
            grouped["other"].append(child)

    # Zotero stores annotations as children of the PDF attachment, but the
    # Better BibTeX local API does not expose them via /items/{pdf_key}/children.
    # Fall back to a global annotation search filtered by parentItem.
    if not grouped["annotations"] and pdf_keys:
        all_annots = _zotero_api("users/0/items", {"format": "json", "itemType": "annotation", "limit": 100}, api_base) or []
        for item in all_annots:
            if item.get("data", {}).get("parentItem") in pdf_keys:
                grouped["annotations"].append(_zotero_item_summary(item))

    return grouped


@tool()
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


@tool()
def obsidian_zotero_extract_pdf_text(
    attachment_key: str,
    max_pages: int = 5,
    api_base: str = "",
) -> dict[str, Any]:
    """Extract text from a Zotero PDF attachment key if a PDF reader library is installed."""
    attachment = obsidian_zotero_get_item(attachment_key, api_base)
    return _extract_pdf_text_from_path(_resolve_zotero_attachment_path(attachment), max_pages)


@tool()
def obsidian_ingest_zotero_item(
    key: str,
    vault_path: str = "",
    source_folder: str = "literature",
    attachments_folder: str = "attachments/zotero",
    attachment_name_strategy: str = "original",
    copy_pdf_attachments: bool = False,
    include_child_notes: bool = True,
    include_annotations: bool = True,
    annotations_mode: str = "flat",
    color_labels_json: str = "{}",
    include_pdf_text: bool = False,
    max_pdf_pages: int = 5,
    folder_by_collection: bool = False,
    folder_by_type: bool = False,
    tag_by_collection: bool = False,
    entities_json: str = "[]",
    concepts_json: str = "[]",
    index_path: str = "index.md",
    log_path: str = "log.md",
    overwrite: bool = False,
    dry_run: bool = False,
    api_base: str = "",
) -> dict[str, Any]:
    """Fetch a Zotero item and ingest it as a literature note in the vault.

    folder_by_type: place items in sub-folders by itemType (e.g. literature/journalArticle/).
    folder_by_collection: place items in sub-folders named after their first Zotero collection.
    tag_by_collection: add all Zotero collection names as tags (collection/<slug>).
    When both folder_by_collection and folder_by_type are set, collection takes precedence.
    """
    vault = _vault(vault_path)
    source_folder = _configured_path(vault, "literatureFolder", source_folder, "literature")
    attachments_folder = _configured_path(vault, "zoteroAttachmentsFolder", attachments_folder, "attachments/zotero")
    attachment_name_strategy = str(_config_value(vault, "zoteroAttachmentNameStrategy", attachment_name_strategy, "original") or "original")
    index_path = _configured_path(vault, "indexPath", index_path, "index.md")
    log_path = _configured_path(vault, "logPath", log_path, "log.md")
    item = obsidian_zotero_get_item(key, api_base)
    children = obsidian_zotero_get_children(key, api_base)
    metadata = _metadata_from_reference(item)
    metadata["zoteroKey"] = key
    metadata["zoteroVersion"] = item.get("version")
    metadata["zoteroSelect"] = _zotero_select_uri(key)
    metadata["tags"] = _merge_unique(metadata.get("tags"), ["source", "literature", "zotero"])

    # Resolve collection names from Zotero keys (always, for human-readable collections field)
    collection_names: list[str] = []
    collection_keys = item.get("collections") or []
    for col_key in collection_keys:
        try:
            col_data = _zotero_api(f"users/0/collections/{col_key}", {"format": "json"}, api_base) or {}
            col_name = col_data.get("data", {}).get("name") or ""
            if col_name:
                collection_names.append(col_name)
        except Exception:
            pass
    if collection_names:
        metadata["collections"] = collection_names

    # Resolve sub-folder: collection name takes precedence over item type
    if folder_by_collection or folder_by_type or tag_by_collection:
        subfolder = ""
        if folder_by_collection and collection_names:
            subfolder = _slug_filename(collection_names[0])
        if not subfolder and folder_by_type:
            item_type = str(item.get("itemType") or "")
            if item_type:
                subfolder = item_type
        if subfolder:
            source_folder = f"{source_folder.rstrip('/')}/{subfolder}"

    if tag_by_collection and collection_names:
        col_tags = [re.sub(r"\s+", "-", re.sub(r'[<>:"/\\|?*\x00-\x1f#\[\]]', "", n).strip()).lower() for n in collection_names]
        col_tags = [f"collection/{t}" for t in col_tags if t]
        metadata["tags"] = _merge_unique(metadata.get("tags"), col_tags)

    # Version-based update detection
    _preserved_user_fields: dict[str, Any] = {}
    if not overwrite:
        existing = _find_existing_reference(vault, metadata, source_folder)
        if existing:
            existing_path = _safe_path(vault, existing["path"])
            existing_props, _ = _split_frontmatter(_read_text(existing_path))
            stored_version = existing_props.get("zoteroVersion")
            current_version = item.get("version")
            if stored_version is not None and current_version is not None:
                if stored_version == current_version:
                    return {"ok": True, "upToDate": True, "existingPath": existing["path"], "zoteroVersion": current_version, "zoteroKey": key}
                # version changed: preserve user-added fields not owned by Zotero
                _preserved_user_fields = {
                    k: v for k, v in existing_props.items()
                    if k not in _ZOTERO_OWNED_FIELDS and not k.startswith("zotero")
                }
                overwrite = True

    _ann_children = {
        "notes": children.get("notes", []) if include_child_notes else [],
        "annotations": children.get("annotations", []) if include_annotations else [],
    }
    if annotations_mode == "structured":
        _color_labels = _resolve_annotation_color_labels(vault, color_labels_json)
        notes_content = _zotero_annotations_structured(_ann_children, _color_labels)
    else:
        notes_content = _zotero_notes_and_annotations(_ann_children)
    attachment_path = ""
    copied_attachments: list[str] = []
    linked_attachments: list[str] = []
    zotero_attachment_paths: list[str] = []
    other_attachments: list[dict[str, str]] = []
    attachment_errors: list[dict[str, str]] = []
    pdf_text_parts: list[str] = []
    pdf_keys: list[str] = []
    for attachment_index, attachment in enumerate(children.get("attachments", []), start=1):
        content_type = str(attachment.get("contentType") or "")
        att_path_str = str(attachment.get("attachmentPath") or "")
        is_pdf = content_type == "application/pdf" or att_path_str.lower().endswith(".pdf")
        if not is_pdf:
            # Collect non-PDF attachments (web snapshots, images, Word, etc.)
            att_key = str(attachment.get("key") or "")
            att_title = str(attachment.get("title") or att_key or "attachment")
            if att_path_str or att_key:
                other_attachments.append({
                    "key": att_key,
                    "title": att_title,
                    "contentType": content_type,
                    "path": att_path_str,
                    "zoteroSelect": _zotero_select_uri(att_key) if att_key else "",
                })
            continue
        if attachment.get("key"):
            pdf_keys.append(str(attachment["key"]))
        try:
            source_pdf = _resolve_zotero_attachment_path(attachment)
        except Exception as exc:
            attachment_errors.append({"key": str(attachment.get("key") or ""), "title": str(attachment.get("title") or ""), "error": str(exc)})
            continue
        if copy_pdf_attachments:
            filename = _attachment_filename(attachment_name_strategy, source_pdf, key, attachment, metadata, attachment_index)
            dest_rel = f"{attachments_folder.strip('/')}/{key}/{filename}"
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
    zotero_links = _zotero_links_for_item(key, pdf_keys)
    if zotero_links:
        metadata["zoteroLinks"] = zotero_links
    if pdf_keys:
        metadata["zoteroPdfKeys"] = pdf_keys
        metadata["zoteroPdfLinks"] = [_zotero_pdf_uri(pdf_key) for pdf_key in pdf_keys]
    if linked_attachments:
        metadata["attachments"] = linked_attachments
    if zotero_attachment_paths:
        metadata["zoteroAttachmentPaths"] = zotero_attachment_paths
    if other_attachments:
        metadata["otherAttachments"] = other_attachments

    # Build relations section: resolve related Zotero item keys to vault note wikilinks
    relations_content = ""
    related_uris = item.get("relations") or []
    if related_uris:
        # Extract item keys from zotero://select/library/items/{KEY} URIs
        related_keys = []
        for uri in related_uris:
            m = re.search(r"/items/([A-Z0-9]+)$", str(uri))
            if m:
                related_keys.append(m.group(1))
        if related_keys:
            rel_lines = ["## Related", ""]
            for rel_key in related_keys:
                # Try to find an existing vault note for this key
                existing_rel = _find_existing_reference(vault, {"zoteroKey": rel_key}, source_folder)
                if existing_rel:
                    note_stem = Path(existing_rel["path"]).stem
                    rel_lines.append(f"- [[{note_stem}]]")
                else:
                    rel_lines.append(f"- zotero://select/library/items/{rel_key}")
            relations_content = "\n".join(rel_lines)

    attachment_content = ""
    if attachment_errors:
        lines = ["## Attachment Import Warnings", ""]
        for err_item in attachment_errors:
            title = err_item.get("title") or err_item.get("key") or "attachment"
            lines.append(f"- {title}: {err_item.get('error')}")
        attachment_content = "\n".join(lines)
    content = "\n\n".join(part for part in [notes_content, relations_content, attachment_content, *pdf_text_parts] if part)

    result = obsidian_ingest_reference(
        metadata_json=json.dumps(metadata, ensure_ascii=False),
        vault_path=str(vault),
        source_folder=source_folder,
        abstract=str(item.get("abstract") or ""),
        notes=notes_content,
        content="\n\n".join(part for part in [relations_content, attachment_content, *pdf_text_parts] if part),
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
    # Restore user-added YAML fields (e.g. mineru_markdown) that were in the old note
    if _preserved_user_fields and result.get("ok") and not dry_run:
        written_rel = result.get("referencePath") or ""
        if written_rel:
            written_path = _safe_path(vault, written_rel)
            if written_path.exists():
                props, body = _split_frontmatter(_read_text(written_path))
                for k, v in _preserved_user_fields.items():
                    props[k] = v
                written_path.write_text(_join_frontmatter(props, body), encoding="utf-8")
    result["zoteroKey"] = key
    result["children"] = {"notes": len(children.get("notes", [])), "annotations": len(children.get("annotations", [])), "attachments": len(children.get("attachments", []))}
    result["copiedAttachments"] = copied_attachments
    result["linkedAttachments"] = linked_attachments
    result["zoteroAttachmentPaths"] = zotero_attachment_paths
    result["attachmentErrors"] = attachment_errors
    result["includedContentChars"] = len(content)
    return result


@tool()
def obsidian_ingest_zotero_collection(
    collection_key: str = "",
    tag: str = "",
    item_type: str = "",
    query: str = "",
    vault_path: str = "",
    source_folder: str = "literature",
    attachments_folder: str = "attachments/zotero",
    attachment_name_strategy: str = "original",
    copy_pdf_attachments: bool = False,
    include_child_notes: bool = True,
    include_annotations: bool = True,
    annotations_mode: str = "flat",
    color_labels_json: str = "{}",
    include_pdf_text: bool = False,
    max_pdf_pages: int = 5,
    folder_by_collection: bool = False,
    folder_by_type: bool = False,
    tag_by_collection: bool = False,
    index_path: str = "index.md",
    log_path: str = "log.md",
    overwrite: bool = False,
    skip_up_to_date: bool = True,
    limit: int = 100,
    dry_run: bool = False,
    api_base: str = "",
) -> dict[str, Any]:
    """Batch-ingest Zotero items into the vault.

    Fetch items from a collection, tag, item type filter, or free-text query
    (at least one of collection_key / tag / item_type / query is required).
    Items whose zoteroVersion matches the stored value are skipped unless
    skip_up_to_date=False or overwrite=True.
    folder_by_collection / folder_by_type are forwarded to obsidian_ingest_zotero_item.
    """
    if not any([collection_key, tag, item_type, query]):
        raise ValueError("Provide at least one of: collection_key, tag, item_type, query.")

    params: dict[str, Any] = {"format": "json", "limit": max(1, min(limit, 100))}
    if tag:
        params["tag"] = tag
    if item_type:
        params["itemType"] = item_type
    if query:
        params["q"] = query

    if collection_key:
        raw_items = _zotero_api(f"users/0/collections/{collection_key}/items/top", params, api_base) or []
    else:
        raw_items = _zotero_api("users/0/items/top", params, api_base) or []

    # Filter to real parent items (exclude attachments/notes/annotations)
    skip_types = {"attachment", "note", "annotation"}
    keys = [
        item.get("key")
        for item in raw_items
        if item.get("key") and item.get("data", {}).get("itemType") not in skip_types
    ]

    results: list[dict[str, Any]] = []
    skipped = 0
    updated = 0
    created = 0
    errors = 0

    for item_key in keys:
        try:
            res = obsidian_ingest_zotero_item(
                key=item_key,
                vault_path=vault_path,
                source_folder=source_folder,
                attachments_folder=attachments_folder,
                attachment_name_strategy=attachment_name_strategy,
                copy_pdf_attachments=copy_pdf_attachments,
                include_child_notes=include_child_notes,
                include_annotations=include_annotations,
                annotations_mode=annotations_mode,
                color_labels_json=color_labels_json,
                include_pdf_text=include_pdf_text,
                max_pdf_pages=max_pdf_pages,
                folder_by_collection=folder_by_collection,
                folder_by_type=folder_by_type,
                tag_by_collection=tag_by_collection,
                index_path=index_path,
                log_path=log_path,
                overwrite=overwrite,
                dry_run=dry_run,
                api_base=api_base,
            )
            if res.get("upToDate") and skip_up_to_date:
                skipped += 1
            elif res.get("duplicate"):
                skipped += 1
            elif res.get("changed"):
                updated += 1
            else:
                created += 1
            results.append({"key": item_key, **{k: v for k, v in res.items() if k in {"ok", "upToDate", "duplicate", "changed", "referencePath", "path", "attachmentErrors"}}})
        except Exception as exc:
            errors += 1
            results.append({"key": item_key, "ok": False, "error": str(exc)})

    return {
        "ok": errors == 0,
        "total": len(keys),
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
        "dryRun": dry_run,
        "results": results,
    }


@tool()
def obsidian_list_schema_presets() -> dict[str, Any]:
    """List built-in frontmatter schema presets."""
    return dict(SCHEMA_PRESETS)


@tool()
def obsidian_doctor(vault_path: str = "") -> dict[str, Any]:
    """Run a local readiness check for vault resolution, templates, dependencies, and optional integrations."""
    return _doctor(vault_path)


@tool()
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


@tool()
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


@tool()
def obsidian_suggest_graph_improvements(
    vault_path: str = "",
    folder: str = "",
    max_suggestions: int = 50,
    max_reciprocal: int = 10,
) -> dict[str, Any]:
    """Suggest graph improvements such as creating unresolved notes, reciprocal links, and merging similar pages."""
    vault = _vault(vault_path)
    graph = obsidian_build_graph(vault_path=str(vault), folder=folder, include_tags=True)
    limit = max(1, max_suggestions)
    reciprocal_limit = max(0, max_reciprocal)
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
    reciprocal_count = 0
    for edge in graph["edges"]:
        if reciprocal_count >= reciprocal_limit:
            break
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
            reciprocal_count += 1
            if len(suggestions) >= limit:
                break

    normalized_titles: dict[str, list[str]] = {}
    for node in graph["nodes"]:
        raw = str(node.get("title") or node["id"]).lower().strip()
        title_key = re.sub(r"[-_\s]+", " ", raw)
        title_key = re.sub(r"[^a-z0-9\u4e00-\u9fff\s]+", "", title_key).strip()
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
        if folder and not rel_path.startswith(_s(folder).strip("/")):
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


@tool()
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
    payload = {"nodes": nodes, "edges": edges}
    issues = _validate_canvas_payload(rel_path, payload)
    errors = [issue for issue in issues if issue.get("severity") == "error"]
    if errors:
        raise ValueError(f"Invalid Canvas payload: {errors[0]['message']}")
    result = _write_result(vault, full, json.dumps(payload, ensure_ascii=False, indent=2), dry_run)
    result["nodeCount"] = len(nodes)
    result["edgeCount"] = len(edges)
    result["validation"] = {"issueCount": len(issues), "issues": issues}
    return result


@tool()
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
    layer_order_json: str = "",
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
    _default_layer_order = ["source", "entity", "concept", "task", "equipment", "economics", "literature", "utility"]
    if _s(layer_order_json).strip():
        parsed_order = _json(layer_order_json, _default_layer_order)
        if not isinstance(parsed_order, list) or not all(isinstance(item, str) for item in parsed_order):
            raise ValueError("layer_order_json must be a JSON array of tag name strings.")
        layer_order = [str(item).strip() for item in parsed_order if str(item).strip()]
    else:
        layer_order = _default_layer_order

    graph = obsidian_build_graph(vault_path=str(vault), folder=folder, include_tags=True)
    selected_tag = _s(tag).strip().lstrip("#")
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


@tool()
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
    issues = _validate_base_payload(rel_path, base)
    errors = [issue for issue in issues if issue.get("severity") == "error"]
    if errors:
        raise ValueError(f"Invalid Base payload: {errors[0]['message']}")
    result = _write_result(vault, full, _dump_yaml(base) + "\n", dry_run)
    result["topLevelKeys"] = list(base.keys())
    result["validation"] = {"issueCount": len(issues), "issues": issues}
    return result


@tool()
def obsidian_list_base_templates() -> dict[str, str]:
    """List built-in Obsidian Bases templates."""
    return dict(BASE_TEMPLATE_DESCRIPTIONS)


@tool()
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
    template_key = _s(template).strip().lower().replace("-", "_")
    base = _base_template(template_key, options)
    rel_path = _s(path).strip() if _s(path).strip() else f"bases/{template_key}.base"
    rel_path = rel_path if rel_path.lower().endswith(".base") else f"{rel_path}.base"
    full = _safe_path(vault, rel_path)
    if full.exists() and not overwrite:
        return {"ok": False, "path": _rel(vault, full), "error": "Base exists. Pass overwrite=true to replace it."}
    result = _write_result(vault, full, _dump_yaml(base) + "\n", dry_run)
    result["template"] = template_key
    result["description"] = BASE_TEMPLATE_DESCRIPTIONS[template_key]
    result["topLevelKeys"] = list(base.keys())
    return result


@tool()
def obsidian_list_dataview_templates() -> dict[str, str]:
    """List built-in Dataview note templates."""
    return dict(DATAVIEW_TEMPLATE_DESCRIPTIONS)


@tool()
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
    template_key = _s(template).strip().lower().replace("-", "_")
    content = _dataview_template(template_key, options)
    rel_path = _s(path).strip() if _s(path).strip() else f"views/{template_key}-dataview.md"
    rel_path = _ensure_md_path(rel_path)
    full = _safe_path(vault, rel_path)
    if full.exists() and not overwrite:
        return {"ok": False, "path": _rel(vault, full), "error": "Dataview note exists. Pass overwrite=true to replace it."}
    result = _write_result(vault, full, content, dry_run)
    result["template"] = template_key
    result["description"] = DATAVIEW_TEMPLATE_DESCRIPTIONS[template_key]
    return result


@tool()
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


@tool()
def obsidian_apply_edit_plan(
    plan_json: str,
    vault_path: str = "",
    transaction_id: str = "",
) -> dict[str, Any]:
    """Apply a multi-file edit plan after creating vault-local backups."""
    vault = _vault(vault_path)
    operations = _plan_operations(plan_json)
    previews = _preview_edit_plan(vault, operations)
    txid = _transaction_id(transaction_id)
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


@tool()
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


@tool()
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
    executable = shutil.which(cli)
    if executable is None:
        return {"ok": False, "error": f"Obsidian CLI command not found on PATH: {cli}"}
    params = _json(params_json, {})
    flags = _json(flags_json, [])
    if not isinstance(params, dict):
        raise ValueError("params_json must decode to an object.")
    if not isinstance(flags, list):
        raise ValueError("flags_json must decode to an array.")
    args = [executable]
    if vault:
        args.append(f"vault={vault}")
    if command:
        args.append(command)
    for key, value in params.items():
        args.append(f"{key}={value}")
    for flag in flags:
        args.append(str(flag))
    run_cwd = str(_vault(cwd)) if cwd else None
    try:
        completed = subprocess.run(
            args,
            cwd=run_cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(1, timeout_seconds),
        )
    except Exception as exc:
        return {"ok": False, "command": args, "returnCode": -1, "stdout": "", "stderr": "", "error": f"Obsidian CLI failed to run: {exc}"}
    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    fatal_output = stdout in {"Vault not found.", "File not found.", "Command not found."} or stderr in {"Vault not found.", "File not found.", "Command not found."}
    ok = completed.returncode == 0 and not fatal_output
    result = {
        "ok": ok,
        "command": args,
        "returnCode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }
    if fatal_output:
        result["error"] = stdout or stderr
    return result


def _clean_cli_params(params: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in params.items() if value not in ("", None)}


def _parse_cli_stdout(result: dict[str, Any], output_format: str = "") -> dict[str, Any]:
    if not result.get("ok", False):
        return result
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


@tool()
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


@tool()
def obsidian_cli_open(
    path: str = "",
    file: str = "",
    vault: str = "",
    newtab: bool = False,
) -> dict[str, Any]:
    """Open a file through the Obsidian CLI."""
    flags = ["newtab"] if newtab else []
    return _call_obsidian_cli("open", {"path": path, "file": file}, flags, vault=vault)


@tool()
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


@tool()
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


@tool()
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


@tool()
def obsidian_cli_property_read(
    name: str,
    path: str = "",
    file: str = "",
    vault: str = "",
) -> dict[str, Any]:
    """Read one property value through the Obsidian CLI."""
    return _call_obsidian_cli("property:read", {"name": name, "path": path, "file": file}, vault=vault)


@tool()
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


@tool()
def obsidian_cli_property_remove(
    name: str,
    path: str = "",
    file: str = "",
    vault: str = "",
) -> dict[str, Any]:
    """Remove one property through the Obsidian CLI."""
    return _call_obsidian_cli("property:remove", {"name": name, "path": path, "file": file}, vault=vault)


@tool()
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


@tool()
def obsidian_cli_screenshot(
    output_path: str,
    vault: str = "",
    timeout_seconds: int = 30,
) -> dict[str, Any]:
    """Take an Obsidian developer screenshot through the CLI."""
    return _call_obsidian_cli("dev:screenshot", {"path": output_path}, vault=vault, timeout_seconds=timeout_seconds)


@tool()
def obsidian_cli_plugin_reload(
    plugin_id: str,
    vault: str = "",
) -> dict[str, Any]:
    """Reload an Obsidian plugin through the CLI."""
    return _call_obsidian_cli("plugin:reload", {"id": plugin_id}, vault=vault)


@tool()
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


