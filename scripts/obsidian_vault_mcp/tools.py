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
def obsidian_vault_stats(
    vault_path: str = "",
    top_tags: int = 20,
    top_linked: int = 10,
) -> dict[str, Any]:
    """Return per-folder note counts, top tags by frequency, and most-linked notes."""
    vault = _vault(vault_path)
    graph = obsidian_build_graph(vault_path=str(vault), include_tags=True)

    by_folder: dict[str, int] = {}
    for path in _iter_files(vault):
        if path.suffix.lower() != ".md":
            continue
        parts = path.relative_to(vault).parts
        folder_key = parts[0] if len(parts) > 1 else "/"
        by_folder[folder_key] = by_folder.get(folder_key, 0) + 1

    sorted_tags = sorted(graph.get("tags", []), key=lambda x: x["count"], reverse=True)
    top_tag_list = sorted_tags[:max(1, top_tags)]

    nodes_by_id = {n["id"]: n for n in graph["nodes"]}
    backlinks = graph.get("backlinks", {})
    hub_candidates = [
        {
            "path": node_id,
            "title": nodes_by_id.get(node_id, {}).get("title") or Path(node_id).stem,
            "incomingLinks": len(sources),
        }
        for node_id, sources in backlinks.items()
        if sources
    ]
    top_linked_list = sorted(hub_candidates, key=lambda x: x["incomingLinks"], reverse=True)[:max(1, top_linked)]

    return {
        "vaultPath": str(vault),
        "markdownCount": graph["nodeCount"],
        "edgeCount": graph["edgeCount"],
        "orphanCount": len(graph["orphans"]),
        "byFolder": by_folder,
        "topTags": top_tag_list,
        "topLinked": top_linked_list,
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
    use_regex: bool = False,
    limit: int = 50,
    context_chars: int = 140,
    context_lines: int = 0,
) -> list[dict[str, Any]]:
    """Search text files in a vault and return matching line snippets. Set use_regex=true for regular expression matching."""
    vault = _vault(vault_path)
    wanted = _extension_set(extensions)
    compiled: re.Pattern[str] | None = None
    needle: str = ""
    if use_regex:
        try:
            flags = 0 if case_sensitive else re.IGNORECASE
            compiled = re.compile(query, flags)
        except re.error as exc:
            return [{"error": f"Invalid regex: {exc}"}]
    else:
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
            match_dicts: list[dict[str, Any]] = []
            if compiled is not None:
                for m in compiled.finditer(line):
                    index = m.start()
                    matched_len = m.end() - m.start()
                    start = max(0, index - context_chars // 2)
                    end = min(len(line), index + matched_len + context_chars // 2)
                    match_dicts.append({"path": _rel(vault, path), "line": number, "snippet": line[start:end].strip()})
            else:
                haystack = line if case_sensitive else line.lower()
                index = haystack.find(needle)
                if index != -1:
                    start = max(0, index - context_chars // 2)
                    end = min(len(line), index + len(query) + context_chars // 2)
                    match_dicts.append({"path": _rel(vault, path), "line": number, "snippet": line[start:end].strip()})
            for match_dict in match_dicts:
                if context_lines > 0:
                    line_idx = number - 1
                    before_start = max(0, line_idx - context_lines)
                    after_end = min(len(lines), line_idx + context_lines + 1)
                    match_dict["contextBefore"] = lines[before_start:line_idx]
                    match_dict["contextAfter"] = lines[line_idx + 1:after_end]
                matches.append(match_dict)
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
    """Move a vault-relative file to a different directory or full target path.
    Pass update_wikilinks=true to rewrite [[links]] across the vault.

    to: target directory (e.g. "archive") or full target path including filename
    (e.g. "archive/renamed.md"). If 'to' has a file extension it is treated as a
    complete target path; otherwise the source filename is preserved.
    """
    vault = _vault(vault_path)
    src_full = _safe_path(vault, path)
    src_rel = _rel(vault, src_full)
    if not src_full.exists():
        return {"ok": False, "path": src_rel, "error": "File does not exist."}
    to_stripped = to.strip("/")
    to_path = Path(to_stripped)
    # If 'to' carries a file extension, treat it as a complete target path.
    # Otherwise treat it as a target directory and preserve the source filename.
    if to_path.suffix:
        dest_full = _safe_path(vault, to_stripped)
        dest_rel = to_path.as_posix()
    else:
        dest_full = _safe_path(vault, to_stripped) / src_full.name
        dest_rel = (to_path / src_full.name).as_posix()
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
def obsidian_batch_move_files(
    to: str,
    vault_path: str = "",
    paths_json: str = "[]",
    glob_pattern: str = "",
    tag: str = "",
    folder: str = "",
    update_wikilinks: bool = False,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Move multiple vault files to a target directory.

    Specify which files to move via at least one of:
      paths_json: JSON array of vault-relative paths, e.g. '["papers/A.md","papers/B.md"]'
      glob_pattern: shell glob matched against each file's name, e.g. "*.md"
      tag: move all .md files that carry this frontmatter or inline tag
      folder: move all files found in this vault-relative folder

    update_wikilinks=true rewrites [[links]] after each move (slow for large vaults).
    dry_run=true (default): report planned moves without executing them.
    """
    vault = _vault(vault_path)
    files_to_move: list[str] = []

    if paths_json and paths_json != "[]":
        try:
            parsed = json.loads(paths_json)
        except json.JSONDecodeError as exc:
            return {
                "ok": False,
                "error": f"Invalid paths_json: {exc}",
                "total": 0,
                "movedCount": 0,
                "errorCount": 0,
                "moved": [],
                "errors": [],
                "dryRun": dry_run,
            }
        files_to_move.extend(str(p) for p in parsed)

    if glob_pattern:
        import fnmatch
        for path in _iter_files(vault, folder):
            if fnmatch.fnmatch(path.name, glob_pattern) or fnmatch.fnmatch(_rel(vault, path), glob_pattern):
                rel = _rel(vault, path)
                if rel not in files_to_move:
                    files_to_move.append(rel)

    if tag:
        for path in _iter_files(vault, folder):
            if path.suffix.lower() != ".md":
                continue
            props, body = _split_frontmatter(_read_text(path))
            all_tags = _frontmatter_tags(props) + _inline_tags(body)
            if tag in all_tags:
                rel = _rel(vault, path)
                if rel not in files_to_move:
                    files_to_move.append(rel)

    if folder and not glob_pattern and not tag and not (paths_json and paths_json != "[]"):
        for path in _iter_files(vault, folder):
            rel = _rel(vault, path)
            if rel not in files_to_move:
                files_to_move.append(rel)

    moved: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for file_path in files_to_move:
        res = obsidian_move_file(
            path=file_path,
            to=to,
            vault_path=str(vault),
            update_wikilinks=update_wikilinks,
            dry_run=dry_run,
        )
        if res.get("ok"):
            moved.append({"from": res["from"], "to": res["to"]})
        else:
            errors.append({"path": file_path, "error": res.get("error", "unknown error")})

    return {
        "ok": len(errors) == 0,
        "total": len(files_to_move),
        "movedCount": len(moved),
        "errorCount": len(errors),
        "moved": moved,
        "errors": errors,
        "dryRun": dry_run,
    }


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
def obsidian_find_orphans(
    vault_path: str = "",
    folder: str = "",
    exclude_index: bool = True,
) -> dict[str, Any]:
    """Return all Markdown notes that have no incoming wikilinks, with file metadata."""
    vault = _vault(vault_path)
    graph = obsidian_build_graph(vault_path=str(vault), folder=folder, include_tags=True)

    excluded: set[str] = set()
    if exclude_index:
        index_path = _configured_path(vault, "indexPath", "index.md", "index.md")
        log_path = _configured_path(vault, "logPath", "log.md", "log.md")
        excluded = {index_path.lower(), log_path.lower()}

    nodes_by_id = {n["id"]: n for n in graph["nodes"]}
    orphan_details: list[dict[str, Any]] = []
    for orphan_id in graph["orphans"]:
        if orphan_id.lower() in excluded:
            continue
        node = nodes_by_id.get(orphan_id, {})
        full = _safe_path(vault, orphan_id)
        stat = full.stat() if full.exists() else None
        orphan_details.append(
            {
                "path": orphan_id,
                "title": node.get("title") or Path(orphan_id).stem,
                "tags": node.get("tags", []),
                "size": stat.st_size if stat else 0,
                "modified": int(stat.st_mtime) if stat else 0,
            }
        )

    return {
        "vaultPath": str(vault),
        "orphanCount": len(orphan_details),
        "totalNotes": graph["nodeCount"],
        "orphans": orphan_details,
    }


@tool()
def obsidian_find_broken_links(
    vault_path: str = "",
    folder: str = "",
    fix: bool = False,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Scan for broken [[wikilinks]] and [markdown](links), with optional fix to strip dead links.

    fix=True: replace [[DeadTarget]] with DeadTarget and [[DeadTarget|Label]] with Label.
    dry_run=True (default): report only, do not write files.
    """
    vault = _vault(vault_path)
    graph = obsidian_build_graph(vault_path=str(vault), folder=folder)

    # Broken wikilinks from graph
    broken_wikilinks: list[dict[str, Any]] = [
        {"file": source, "target": target, "type": "wikilink"}
        for target, sources in graph["unresolved"].items()
        for source in sources
    ]

    # Broken local markdown links: scan files for [label](path) that don't exist
    broken_md_links: list[dict[str, Any]] = []
    _url_schemes = ("http://", "https://", "ftp://", "mailto:", "zotero:", "#", "obsidian://")
    for path in _iter_files(vault, folder):
        if path.suffix.lower() != ".md":
            continue
        rel = _rel(vault, path)
        text = _read_text(path)
        for m in MARKDOWN_LINK_RE.finditer(text):
            raw_target = m.group(1)
            if any(raw_target.startswith(scheme) for scheme in _url_schemes):
                continue
            target_clean = unquote(raw_target.split("#")[0].split("?")[0])
            if not target_clean:
                continue
            candidate_rel = path.parent / target_clean
            candidate_abs = vault / target_clean
            if not candidate_rel.exists() and not candidate_abs.exists():
                broken_md_links.append({"file": rel, "target": raw_target, "type": "markdown"})

    all_broken = broken_wikilinks + broken_md_links
    fixed_count = 0

    if fix:
        # Build set of broken wikilink targets (normalized)
        broken_targets: set[str] = {_normalize_note_key(e["target"]) for e in broken_wikilinks}

        files_with_dead_wikilinks: set[str] = {e["file"] for e in broken_wikilinks}
        for rel_path in files_with_dead_wikilinks:
            full = _safe_path(vault, rel_path)
            if not full.exists():
                continue
            original = _read_text(full)

            def _replacer(m: re.Match, _broken: set[str] = broken_targets) -> str:
                inner = m.group(1)
                raw = _target_from_link(inner)
                if _normalize_note_key(raw) in _broken:
                    parts = inner.split("|", 1)
                    return parts[1].strip() if len(parts) > 1 else raw
                return m.group(0)

            new_text = WIKILINK_RE.sub(_replacer, original)
            if new_text != original:
                if not dry_run:
                    _write_text(full, new_text)
                fixed_count += 1

    return {
        "vaultPath": str(vault),
        "totalBroken": len(all_broken),
        "brokenWikilinks": broken_wikilinks,
        "brokenMarkdownLinks": broken_md_links,
        "fixed": fixed_count,
        "dryRun": dry_run,
    }


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
    rename_images: bool = False,
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

    if rename_images and result["ok"]:
        markdown_rel = str(extraction.get("markdownPath") or "")
        if markdown_rel:
            rename_result = obsidian_mineru_rename_images(
                markdown_rel,
                vault_path=str(vault),
                dry_run=False,
            )
            result["imageRename"] = rename_result

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
def obsidian_mineru_extract_folder(
    input_folder: str,
    vault_path: str = "",
    output_folder: str = "mineru",
    mode: str = "",
    language: str = "ch",
    skip_extracted: bool = True,
    ingest: bool = False,
    token: str = "",
    rename_images: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Batch-extract all PDF files in a folder using MinerU.

    skip_extracted=true (default): skip any PDF whose output directory already contains a .md file.
    ingest=true: automatically call obsidian_ingest_mineru_markdown after each successful extraction.
    rename_images=true: call obsidian_mineru_rename_images on each successfully extracted Markdown.
    dry_run=true: enumerate PDFs and show skip/extract decisions without running MinerU.
    """
    vault = _vault(vault_path)
    if Path(input_folder).is_absolute():
        input_full = Path(input_folder)
    else:
        input_full = _safe_path(vault, input_folder)

    if not input_full.is_dir():
        return {
            "ok": False,
            "error": f"Not a directory: {input_folder}",
            "total": 0,
            "extracted": 0,
            "skipped": 0,
            "errors": 0,
            "dryRun": dry_run,
            "results": [],
        }

    pdf_files = sorted(
        set(list(input_full.rglob("*.pdf")) + list(input_full.rglob("*.PDF"))),
        key=lambda p: str(p).lower(),
    )

    output_base = vault / output_folder if output_folder else vault / "mineru"
    results: list[dict[str, Any]] = []
    extracted = 0
    skipped = 0
    errors = 0

    for pdf_path in pdf_files:
        pdf_rel = _rel(vault, pdf_path) if pdf_path.is_relative_to(vault) else str(pdf_path)
        stem = pdf_path.stem

        if skip_extracted:
            expected_md = output_base / stem / f"{stem}.md"
            if expected_md.exists():
                skipped += 1
                results.append({
                    "input": pdf_rel,
                    "status": "skipped",
                    "reason": "already_extracted",
                    "outputPath": _rel(vault, expected_md),
                })
                continue

        if dry_run:
            results.append({"input": pdf_rel, "status": "would_extract"})
            continue

        try:
            res = obsidian_mineru_extract(
                input_path=str(pdf_path),
                vault_path=str(vault),
                output_path=output_folder,
                mode=mode,
                language=language,
                token=token,
                dry_run=False,
            )
            if res.get("ok"):
                extracted += 1
                entry: dict[str, Any] = {
                    "input": pdf_rel,
                    "status": "extracted",
                    "outputPath": res.get("markdownPath", ""),
                }
                if ingest and res.get("markdownPath"):
                    ingest_res = obsidian_ingest_mineru_markdown(
                        markdown_path=res["markdownPath"],
                        vault_path=str(vault),
                    )
                    entry["ingested"] = ingest_res.get("ok", False)
                if rename_images and res.get("markdownPath"):
                    rename_res = obsidian_mineru_rename_images(
                        res["markdownPath"],
                        vault_path=str(vault),
                        dry_run=False,
                    )
                    entry["imageRename"] = rename_res
                results.append(entry)
            else:
                errors += 1
                results.append({
                    "input": pdf_rel,
                    "status": "error",
                    "error": res.get("error", "MinerU extraction failed"),
                })
        except Exception as exc:
            errors += 1
            results.append({"input": pdf_rel, "status": "error", "error": str(exc)})

    return {
        "ok": errors == 0,
        "total": len(pdf_files),
        "extracted": extracted,
        "skipped": skipped,
        "errors": errors,
        "dryRun": dry_run,
        "results": results,
    }




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




PIPELINE_CONFIG_FILE = ".obsidian-vault-pipeline.json"
PIPELINE_DEFAULT_CONFIG: dict[str, str] = {
    "literatureFolder": "literature",
    "zoteroAttachmentsFolder": "attachments/zotero",
    "mineruAttachmentsFolder": "attachments/mineru",
    "noteFilenamePattern": "{firstAuthor} {year} - {shortTitle}",
    "pdfFilenamePattern": "{shortTitle}",
    "mineruMarkdownName": "paper.md",
    "mineruImagesIndexName": "images-index.md",
}
PIPELINE_PLUGIN_OWNED_FIELDS = {
    "title",
    "authors",
    "year",
    "doi",
    "publicationTitle",
    "abstract",
    "zoteroKey",
    "zoteroVersion",
    "zoteroSelect",
    "zoteroPdfKeys",
    "zoteroPdfLinks",
    "zoteroAttachmentPaths",
    "attachments",
    "attachmentLinks",
    "pdfStatus",
    "attachmentErrors",
    "mineruStatus",
    "mineruError",
    "mineruExtractedAt",
    "mineruMarkdown",
    "mineruMarkdownLink",
    "mineruImagesFolder",
    "mineruImagesIndex",
    "mineruImagesIndexLink",
    "mineruImageRenameStatus",
}


def _pipeline_config(vault: Path) -> dict[str, str]:
    loaded = _load_json_file(vault / PIPELINE_CONFIG_FILE, {})
    config = dict(PIPELINE_DEFAULT_CONFIG)
    if isinstance(loaded, dict):
        for key, value in loaded.items():
            if key in config and value is not None:
                text = str(value).replace("\\", "/").strip()
                config[key] = text.strip("/") if key.endswith("Folder") else text
    return config


def _pipeline_ascii_slug(value: str, fallback: str = "untitled") -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "-", _s(value).lower()).strip("-")
    return text or fallback


def _pipeline_title_words(title: str, max_words: int = 10) -> str:
    words = re.findall(r"[A-Za-z0-9]+", title)
    ascii_text = " ".join(words)
    if len(ascii_text) < 4:
        return _slug_filename(title)[:80].strip() or "Untitled"
    selected = words[:max_words]
    return " ".join(word[:1].upper() + word[1:] for word in selected)


def _pipeline_first_author(metadata: dict[str, Any]) -> str:
    authors = _listify(metadata.get("authors"))
    if not authors:
        return "Unknown"
    first = str(authors[0]).strip()
    if "," in first:
        return first.split(",", 1)[0].strip() or "Unknown"
    parts = first.split()
    return parts[-1].strip() if parts else "Unknown"


def _pipeline_year(metadata: dict[str, Any]) -> str:
    year = str(metadata.get("year") or "").strip()
    if year:
        return year
    match = re.search(r"\d{4}", str(metadata.get("date") or ""))
    return match.group(0) if match else "n.d."


def _pipeline_note_filename(metadata: dict[str, Any], config: dict[str, str]) -> str:
    title = str(metadata.get("title") or "Untitled Reference")
    values = {
        "firstAuthor": _pipeline_first_author(metadata),
        "year": _pipeline_year(metadata),
        "shortTitle": _pipeline_title_words(title),
    }
    pattern = config.get("noteFilenamePattern") or PIPELINE_DEFAULT_CONFIG["noteFilenamePattern"]
    return _slug_filename(pattern.format(**values)).strip() + ".md"


def _pipeline_pdf_filename(metadata: dict[str, Any], source_pdf: Path, config: dict[str, str]) -> str:
    title = str(metadata.get("title") or source_pdf.stem)
    values = {
        "firstAuthor": _pipeline_first_author(metadata),
        "year": _pipeline_year(metadata),
        "shortTitle": _pipeline_ascii_slug(title, source_pdf.stem.lower()),
    }
    pattern = config.get("pdfFilenamePattern") or PIPELINE_DEFAULT_CONFIG["pdfFilenamePattern"]
    stem = _pipeline_ascii_slug(pattern.format(**values), _pipeline_ascii_slug(source_pdf.stem, "paper"))
    return f"{stem}{source_pdf.suffix.lower() or '.pdf'}"


def _pipeline_literature_rel(metadata: dict[str, Any], config: dict[str, str]) -> str:
    return f"{config['literatureFolder'].strip('/')}/{_pipeline_note_filename(metadata, config)}"


def _pipeline_mineru_dir(config: dict[str, str], zotero_key: str) -> str:
    return f"{config['mineruAttachmentsFolder'].strip('/')}/{zotero_key}"


def _pipeline_section(body: str, heading: str) -> str:
    pattern = re.compile(rf"(^## {re.escape(heading)}\s*\n.*?)(?=^##\s+|\Z)", re.DOTALL | re.MULTILINE)
    match = pattern.search(body)
    return match.group(1).rstrip() if match else f"## {heading}\n\n"


def _pipeline_child_notes(children: dict[str, Any]) -> str:
    selected = {"notes": children.get("notes", []), "annotations": children.get("annotations", [])}
    content = _zotero_notes_and_annotations(selected).strip()
    return content or "- No Zotero child notes or annotations found."


def _pipeline_literature_content(
    title: str,
    props: dict[str, Any],
    notes_content: str,
    existing_body: str = "",
) -> str:
    abstract = _s(props.get("abstract")).strip()
    pdf_lines = []
    for rel in _listify(props.get("attachments")):
        pdf_lines.append(f"- Local: ![[{rel}]]")
    for uri in _listify(props.get("zoteroPdfLinks")):
        pdf_lines.append(f"- Zotero: [Open in Zotero]({uri})")
    if not pdf_lines:
        pdf_lines.append("- PDF missing or not copied.")

    mineru_lines = []
    if props.get("mineruMarkdownLink"):
        mineru_lines.append(f"- Markdown: {props['mineruMarkdownLink']}")
    if props.get("mineruImagesIndexLink"):
        mineru_lines.append(f"- Images: {props['mineruImagesIndexLink']}")
    if not mineru_lines:
        mineru_lines.append("- Not parsed with MinerU yet.")

    sections = [
        f"# {title}",
        "",
        "## Abstract",
        "",
        abstract or "No abstract available from Zotero.",
        "",
        "## PDF",
        "",
        *pdf_lines,
        "",
        "## Zotero Notes & Annotations",
        "",
        notes_content.strip(),
        "",
        "## MinerU Extraction",
        "",
        *mineru_lines,
        "",
        _pipeline_section(existing_body, "Reading Notes"),
        "",
        _pipeline_section(existing_body, "AI Summary"),
        "",
    ]
    return "\n".join(sections).rstrip() + "\n"


def _pipeline_write_literature_note(
    vault: Path,
    rel_path: str,
    plugin_props: dict[str, Any],
    notes_content: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    full = _safe_path(vault, rel_path)
    existing_text = _read_text(full) if full.exists() else ""
    existing_props, existing_body = _split_frontmatter(existing_text)
    merged = dict(existing_props)
    for key in PIPELINE_PLUGIN_OWNED_FIELDS:
        if key in plugin_props:
            merged[key] = plugin_props[key]
    existing_tags = _listify(existing_props.get("tags"))
    merged["tags"] = _merge_unique(existing_tags, plugin_props.get("tags") or [])
    if "type" in plugin_props:
        merged["type"] = plugin_props["type"]
    title = str(plugin_props.get("title") or existing_props.get("title") or _note_title_from_path(rel_path))
    body = _pipeline_literature_content(title, merged, notes_content, existing_body)
    result = _write_result(vault, full, _join_frontmatter(merged, body), dry_run)
    result["created"] = not bool(existing_text)
    return result


def _pipeline_replace_section(body: str, heading: str, replacement: str) -> str:
    pattern = re.compile(rf"^## {re.escape(heading)}\s*\n.*?(?=^##\s+|\Z)", re.DOTALL | re.MULTILINE)
    clean = replacement.rstrip() + "\n\n"
    if pattern.search(body):
        return pattern.sub(clean.rstrip() + "\n", body, count=1)
    return body.rstrip() + "\n\n" + clean


def _pipeline_update_literature_mineru_fields(
    vault: Path,
    rel_path: str,
    mineru_props: dict[str, Any],
    dry_run: bool = False,
) -> dict[str, Any]:
    full = _safe_path(vault, rel_path)
    props, body = _split_frontmatter(_read_text(full))
    props.update(mineru_props)
    lines = ["## MinerU Extraction", ""]
    if props.get("mineruMarkdownLink"):
        lines.append(f"- Markdown: {props['mineruMarkdownLink']}")
    if props.get("mineruImagesIndexLink"):
        lines.append(f"- Images: {props['mineruImagesIndexLink']}")
    if props.get("mineruStatus") == "failed" and props.get("mineruError"):
        lines.append(f"- Status: failed - {props['mineruError']}")
    if len(lines) == 2:
        lines.append("- Not parsed with MinerU yet.")
    updated_body = _pipeline_replace_section(body, "MinerU Extraction", "\n".join(lines))
    return _write_result(vault, full, _join_frontmatter(props, updated_body), dry_run)


def _pipeline_find_literature(vault: Path, zotero_key: str = "", literature_path: str = "") -> tuple[str, dict[str, Any], str]:
    if literature_path:
        rel = _ensure_md_path(literature_path)
        full = _safe_path(vault, rel)
        props, body = _split_frontmatter(_read_text(full))
        return rel, props, body
    config = _pipeline_config(vault)
    found = _find_existing_reference(vault, {"zoteroKey": zotero_key}, config["literatureFolder"])
    if not found:
        raise FileNotFoundError(f"No literature note found for Zotero key: {zotero_key}")
    full = _safe_path(vault, found["path"])
    props, body = _split_frontmatter(_read_text(full))
    return found["path"], props, body


def _pipeline_strip_caption(caption: str) -> str:
    text = re.sub(r"^[#>*_\s-]*(figure|fig\.?|table|scheme|chart|equation|eq\.?)\s*\d+[\s:.-]*", "", caption, flags=re.IGNORECASE)
    text = re.sub(r"^[#>*_\s-]*[A-Za-z]*\s*\d+[\s:.-]*", "", text).strip(" .:-_*")
    return text or caption.strip()


def _pipeline_image_type(caption: str, alt: str = "") -> str:
    text = f"{caption} {alt}".lower()
    if any(word in text for word in ["table", "summary table"]):
        return "table"
    if any(word in text for word in ["scheme", "pathway", "mechanism"]):
        return "scheme"
    if any(word in text for word in ["equation", "formula", "rate equation"]):
        return "eq"
    if any(word in text for word in ["figure", "fig", "chart", "diagram", "flow", "comparison"]):
        return "fig"
    return "img"


def _pipeline_image_slug(caption: str, alt: str, fallback: str) -> str:
    text = _pipeline_strip_caption(caption) if caption else alt
    words = re.findall(r"[A-Za-z0-9]+", text.lower())
    if not words:
        return fallback
    stop = {"figure", "fig", "table", "scheme", "chart", "image", "the", "and", "of", "for", "a", "an"}
    words = [word for word in words if word not in stop]
    return "-".join(words[:8]) or fallback


def _pipeline_markdown_image_entries(vault: Path, markdown_rel: str) -> tuple[Path, list[tuple[int, str, str, str]], list[str]]:
    md_full = _safe_path(vault, markdown_rel)
    lines = _read_text(md_full).splitlines()
    return md_full, _mineru_find_images(lines), lines


def _pipeline_write_image_index(
    vault: Path,
    zotero_key: str,
    mineru_markdown_rel: str,
    mappings: list[dict[str, Any]],
    cleanup_candidates: list[str],
    config: dict[str, str],
    parent_rel: str = "",
) -> str:
    mineru_dir = _pipeline_mineru_dir(config, zotero_key)
    index_rel = f"{mineru_dir}/{config['mineruImagesIndexName']}"
    props = {
        "type": "mineru-image-index",
        "parent": parent_rel,
        "parentLink": _wikilink(parent_rel) if parent_rel else "",
        "zoteroKey": zotero_key,
        "sourceExtraction": mineru_markdown_rel,
        "sourceExtractionLink": _wikilink(mineru_markdown_rel),
    }
    title = f"Images - {zotero_key}"
    lines = [
        f"# {title}",
        "",
        f"- Literature note: {_wikilink(parent_rel) if parent_rel else 'Not linked'}",
        f"- MinerU Markdown: {_wikilink(mineru_markdown_rel)}",
        "",
        "| ID | Image | File | Caption | Used For | Original |",
        "|---|---|---|---|---|---|",
    ]
    for mapping in mappings:
        lines.append(
            f"| {mapping['id']} | ![[{mapping['new']}]] | `{Path(mapping['new']).name}` | {mapping.get('caption') or ''} | {mapping.get('usedFor') or ''} | `{mapping['old']}` |"
        )
    if cleanup_candidates:
        lines.extend(["", "## Cleanup Candidates", ""])
        lines.extend(f"- `{candidate}`" for candidate in cleanup_candidates)
    _write_text(_safe_path(vault, index_rel), _join_frontmatter(props, "\n".join(lines).rstrip() + "\n"))
    return index_rel


@tool()
def obsidian_pipeline_config(vault_path: str = "") -> dict[str, Any]:
    """Return the vault-local literature pipeline configuration and effective defaults."""
    vault = _vault(vault_path)
    config_path = vault / PIPELINE_CONFIG_FILE
    config = _pipeline_config(vault)
    return {
        "ok": True,
        "vaultPath": str(vault),
        "path": PIPELINE_CONFIG_FILE,
        "exists": config_path.exists(),
        "config": config,
        "folders": {
            "literature": config["literatureFolder"],
            "zoteroAttachments": config["zoteroAttachmentsFolder"],
            "mineruAttachments": config["mineruAttachmentsFolder"],
        },
    }


@tool()
def obsidian_pipeline_doctor(vault_path: str = "") -> dict[str, Any]:
    """Run a focused readiness check for the Zotero-MinerU-Obsidian literature pipeline."""
    vault = _vault(vault_path)
    try:
        zotero = obsidian_zotero_ping()
    except Exception as exc:
        zotero = {"ok": False, "error": str(exc)}
    return {
        "ok": True,
        "vaultPath": str(vault),
        "profile": {
            "tools": get_registered_tool_names(),
        },
        "pipelineConfig": obsidian_pipeline_config(str(vault)),
        "zotero": zotero,
        "mineru": obsidian_mineru_status(),
        "legacyDoctor": _doctor(str(vault)),
    }


@tool()
def obsidian_pipeline_ingest_item(
    zotero_key: str,
    vault_path: str = "",
    parse_with_mineru: bool = False,
    dry_run: bool = False,
    api_base: str = "",
) -> dict[str, Any]:
    """Import one Zotero parent item into the stable literature pipeline layout."""
    vault = _vault(vault_path)
    config = _pipeline_config(vault)
    item = obsidian_zotero_get_item(zotero_key, api_base)
    children = obsidian_zotero_get_children(zotero_key, api_base)
    metadata = _metadata_from_reference(item)
    title = str(metadata.get("title") or "Untitled Reference")
    authors = _listify(metadata.get("authors"))
    literature_rel = _pipeline_literature_rel(metadata, config)

    copied: list[str] = []
    source_paths: list[str] = []
    pdf_keys: list[str] = []
    attachment_errors: list[dict[str, str]] = []
    for index, attachment in enumerate(children.get("attachments", []), start=1):
        content_type = str(attachment.get("contentType") or "")
        attachment_path = str(attachment.get("attachmentPath") or "")
        if content_type != "application/pdf" and not attachment_path.lower().endswith(".pdf"):
            continue
        if attachment.get("key"):
            pdf_keys.append(str(attachment["key"]))
        try:
            source_pdf = _resolve_zotero_attachment_path(attachment)
            source_paths.append(str(source_pdf))
            pdf_name = _pipeline_pdf_filename(metadata, source_pdf, config)
            if len(children.get("attachments", [])) > 1 and index > 1:
                pdf_name = f"{Path(pdf_name).stem}-{index}{Path(pdf_name).suffix}"
            dest_rel = f"{config['zoteroAttachmentsFolder'].strip('/')}/{zotero_key}/{pdf_name}"
            dest = _safe_path(vault, dest_rel)
            if not source_pdf.exists():
                attachment_errors.append({"key": str(attachment.get("key") or ""), "error": f"PDF file was not found on disk: {source_pdf}"})
                continue
            if not dry_run:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_pdf, dest)
            copied.append(dest_rel)
        except Exception as exc:
            attachment_errors.append({"key": str(attachment.get("key") or ""), "error": str(exc)})

    plugin_props: dict[str, Any] = {
        "type": "literature",
        "title": title,
        "authors": authors,
        "year": int(_pipeline_year(metadata)) if _pipeline_year(metadata).isdigit() else _pipeline_year(metadata),
        "doi": metadata.get("doi") or metadata.get("DOI"),
        "publicationTitle": metadata.get("publicationTitle"),
        "abstract": metadata.get("abstract") or metadata.get("abstractNote") or "",
        "zoteroKey": zotero_key,
        "zoteroVersion": item.get("version"),
        "zoteroSelect": _zotero_select_uri(zotero_key),
        "zoteroPdfKeys": pdf_keys,
        "zoteroPdfLinks": [_zotero_pdf_uri(key) for key in pdf_keys],
        "zoteroAttachmentPaths": source_paths,
        "attachments": copied,
        "attachmentLinks": [_wikilink(path) for path in copied],
        "pdfStatus": "copied" if copied else "missing",
        "attachmentErrors": attachment_errors,
        "tags": ["literature", "zotero"],
    }
    if not copied and attachment_errors:
        plugin_props["pdfStatus"] = "missing"
    notes_content = _pipeline_child_notes(children)
    write = _pipeline_write_literature_note(vault, literature_rel, plugin_props, notes_content, dry_run)
    result: dict[str, Any] = {
        "ok": write.get("ok", False),
        "zoteroKey": zotero_key,
        "title": title,
        "literaturePath": literature_rel,
        "pdfPath": copied[0] if copied else "",
        "copiedAttachments": copied,
        "zoteroAttachmentPaths": source_paths,
        "attachmentErrors": attachment_errors,
        "status": "created" if write.get("created") else "updated",
        "changed": write.get("changed", False),
        "dryRun": dry_run,
    }
    if parse_with_mineru and not dry_run:
        parse = obsidian_pipeline_parse_with_mineru(zotero_key=zotero_key, vault_path=str(vault))
        result["mineru"] = parse
        result["mineruMarkdown"] = parse.get("mineruMarkdown", "")
        result["mineruImagesIndex"] = parse.get("mineruImagesIndex", "")
        result["ok"] = result["ok"] and bool(parse.get("ok"))
    return result


@tool()
def obsidian_pipeline_rename_mineru_images(
    zotero_key: str = "",
    mineru_markdown_path: str = "",
    vault_path: str = "",
    dry_run: bool = False,
) -> dict[str, Any]:
    """Rename MinerU images to portable English semantic slugs and regenerate images-index.md."""
    vault = _vault(vault_path)
    config = _pipeline_config(vault)
    if not mineru_markdown_path:
        if not zotero_key:
            raise ValueError("zotero_key or mineru_markdown_path is required.")
        mineru_markdown_path = f"{_pipeline_mineru_dir(config, zotero_key)}/{config['mineruMarkdownName']}"
    md_full, refs, lines = _pipeline_markdown_image_entries(vault, mineru_markdown_path)
    props, body = _split_frontmatter(_read_text(md_full))
    effective_key = zotero_key or str(props.get("zoteroKey") or md_full.parent.name)
    parent_rel = str(props.get("parent") or "")
    md_dir = md_full.parent
    content = _read_text(md_full)
    mappings: list[dict[str, Any]] = []
    used_names: set[str] = set()
    type_counts: dict[str, int] = {}
    errors: list[dict[str, str]] = []

    seen: set[str] = set()
    ordered_refs = []
    for entry in refs:
        if entry[2] not in seen:
            seen.add(entry[2])
            ordered_refs.append(entry)

    for line_idx, _raw, image_path, alt in ordered_refs:
        caption, strategy = _mineru_extract_caption(lines, line_idx, 4)
        if not caption and alt.strip():
            caption = alt.strip()
            strategy = "alt"
        image_type = _pipeline_image_type(caption, alt)
        type_counts[image_type] = type_counts.get(image_type, 0) + 1
        fallback_slug = "unclassified-figure" if image_type == "img" else image_type
        slug = _pipeline_image_slug(caption, alt, fallback_slug)
        ext = Path(image_path).suffix.lower() or ".png"
        new_name = f"{image_type}-{type_counts[image_type]:02d}-{slug}{ext}"
        while new_name in used_names:
            type_counts[image_type] += 1
            new_name = f"{image_type}-{type_counts[image_type]:02d}-{slug}{ext}"
        used_names.add(new_name)
        old_full = md_dir / image_path
        new_rel = str(Path(image_path).parent / new_name).replace("\\", "/")
        new_full = md_dir / new_rel
        if not dry_run:
            if old_full.exists() and old_full.resolve() != new_full.resolve():
                new_full.parent.mkdir(parents=True, exist_ok=True)
                old_full.rename(new_full)
            elif not old_full.exists() and not new_full.exists():
                errors.append({"path": image_path, "error": "Image file not found on disk"})
                continue
        content = content.replace(image_path, new_rel)
        mappings.append({
            "id": f"{image_type}-{type_counts[image_type]:02d}",
            "old": image_path,
            "new": new_rel if new_rel.startswith(_pipeline_mineru_dir(config, effective_key)) else f"{_rel(vault, md_dir / new_rel)}",
            "caption": caption,
            "usedFor": _pipeline_strip_caption(caption) if caption else "Unclassified figure.",
            "strategy": strategy or "fallback",
        })

    if not dry_run:
        _write_text(md_full, content)

    referenced_names = {Path(mapping["new"]).name for mapping in mappings}
    images_dir = md_dir / "images"
    cleanup_candidates = []
    if images_dir.exists():
        cleanup_candidates = sorted(
            path.name for path in images_dir.iterdir()
            if path.is_file() and path.name not in referenced_names
        )
    index_rel = ""
    if not dry_run:
        index_rel = _pipeline_write_image_index(vault, effective_key, mineru_markdown_path, mappings, cleanup_candidates, config, parent_rel)
    return {
        "ok": not errors,
        "zoteroKey": effective_key,
        "markdownPath": mineru_markdown_path,
        "imagesIndex": index_rel,
        "totalImages": len(ordered_refs),
        "renamed": len(mappings),
        "errors": errors,
        "cleanupCandidates": cleanup_candidates,
        "mappings": mappings,
        "dryRun": dry_run,
    }


@tool()
def obsidian_pipeline_parse_with_mineru(
    zotero_key: str = "",
    literature_path: str = "",
    vault_path: str = "",
    dry_run: bool = False,
) -> dict[str, Any]:
    """Parse a pipeline literature PDF with MinerU and refresh machine-generated assets."""
    vault = _vault(vault_path)
    config = _pipeline_config(vault)
    lit_rel, lit_props, _lit_body = _pipeline_find_literature(vault, zotero_key, literature_path)
    effective_key = zotero_key or str(lit_props.get("zoteroKey") or "")
    if not effective_key:
        raise ValueError("Could not resolve zoteroKey from the literature note.")
    pdf_rel = str((_listify(lit_props.get("attachments")) or [""])[0])
    if not pdf_rel:
        raise FileNotFoundError(f"No copied PDF is recorded for {effective_key}.")
    mineru_dir = _pipeline_mineru_dir(config, effective_key)
    markdown_rel = f"{mineru_dir}/{config['mineruMarkdownName']}"
    images_index_rel = f"{mineru_dir}/{config['mineruImagesIndexName']}"
    if dry_run:
        return {"ok": True, "dryRun": True, "zoteroKey": effective_key, "mineruMarkdown": markdown_rel, "mineruImagesIndex": images_index_rel}

    extraction = obsidian_mineru_extract(
        input_path=pdf_rel,
        vault_path=str(vault),
        output_path=mineru_dir,
        dry_run=False,
    )
    if not extraction.get("ok"):
        mineru_error = extraction.get("error") or "MinerU extraction failed."
        _pipeline_update_literature_mineru_fields(vault, lit_rel, {"mineruStatus": "failed", "mineruError": mineru_error}, False)
        return {"ok": False, "zoteroKey": effective_key, "stage": "mineru_extract", "error": mineru_error, "extraction": extraction}

    source_md_rel = str(extraction.get("markdownPath") or markdown_rel)
    source_md_full = _safe_path(vault, source_md_rel)
    source_props, source_body = _split_frontmatter(_read_text(source_md_full))
    paper_props = {
        "type": "mineru-extraction",
        "parent": lit_rel,
        "parentLink": _wikilink(lit_rel),
        "zoteroKey": effective_key,
        "sourcePdf": pdf_rel,
        "sourcePdfLink": _wikilink(pdf_rel),
        "zoteroPdfLink": str((_listify(lit_props.get("zoteroPdfLinks")) or [""])[0]),
        "imagesFolder": f"{mineru_dir}/images",
        "imagesIndex": images_index_rel,
        "imagesIndexLink": _wikilink(images_index_rel),
    }
    paper_body = "\n".join([
        f"# {lit_props.get('title') or Path(lit_rel).stem} - MinerU Extraction",
        "",
        "## Original PDF",
        "",
        f"![[{pdf_rel}]]",
        "",
        "## Images",
        "",
        _wikilink(images_index_rel),
        "",
        "## Extracted Content",
        "",
        source_body.strip() or _read_text(source_md_full).strip(),
        "",
    ])
    _write_text(_safe_path(vault, markdown_rel), _join_frontmatter({**source_props, **paper_props}, paper_body))
    rename = obsidian_pipeline_rename_mineru_images(effective_key, markdown_rel, str(vault), dry_run=False)

    mineru_lit_props = {
        "mineruStatus": "parsed" if rename.get("ok") else "image_rename_failed",
        "mineruExtractedAt": _utc_now(),
        "mineruMarkdown": markdown_rel,
        "mineruMarkdownLink": _wikilink(markdown_rel),
        "mineruImagesFolder": f"{mineru_dir}/images",
        "mineruImagesIndex": images_index_rel,
        "mineruImagesIndexLink": _wikilink(images_index_rel),
        "tags": _merge_unique(lit_props.get("tags"), ["literature", "zotero", "mineru"]),
    }
    _pipeline_update_literature_mineru_fields(vault, lit_rel, mineru_lit_props, False)
    return {
        "ok": bool(rename.get("ok")),
        "zoteroKey": effective_key,
        "literaturePath": lit_rel,
        "pdfPath": pdf_rel,
        "mineruMarkdown": markdown_rel,
        "mineruImagesIndex": images_index_rel,
        "imageRename": rename,
        "extraction": extraction,
        "status": mineru_lit_props["mineruStatus"],
    }


@tool()
def obsidian_pipeline_ingest_collection(
    collection_key: str,
    vault_path: str = "",
    parse_with_mineru: bool = False,
    limit: int = 100,
    dry_run: bool = False,
    api_base: str = "",
) -> dict[str, Any]:
    """Import every parent item in a Zotero collection, continuing after per-item failures."""
    vault = _vault(vault_path)
    params = {"format": "json", "limit": max(1, min(limit, 100))}
    raw_items = _zotero_api(f"users/0/collections/{collection_key}/items/top", params, api_base) or []
    skip_types = {"attachment", "note", "annotation"}
    keys = [
        str(item.get("key") or item.get("data", {}).get("key"))
        for item in raw_items
        if (item.get("key") or item.get("data", {}).get("key")) and item.get("data", {}).get("itemType") not in skip_types
    ]
    results: list[dict[str, Any]] = []
    counts = {"succeeded": 0, "failed": 0, "created": 0, "updated": 0, "mineruParsed": 0, "mineruFailed": 0, "imageRenamed": 0, "imageRenameFailed": 0}
    for key in keys:
        try:
            item_result = obsidian_pipeline_ingest_item(key, str(vault), parse_with_mineru=parse_with_mineru, dry_run=dry_run, api_base=api_base)
            status = item_result.get("status") or "updated"
            counts["succeeded"] += 1
            if status == "created":
                counts["created"] += 1
            else:
                counts["updated"] += 1
            parse = item_result.get("mineru") or {}
            if parse:
                if parse.get("ok"):
                    counts["mineruParsed"] += 1
                    if parse.get("imageRename", {}).get("ok"):
                        counts["imageRenamed"] += 1
                    else:
                        counts["imageRenameFailed"] += 1
                else:
                    counts["mineruFailed"] += 1
            results.append({
                "zoteroKey": key,
                "title": item_result.get("title", ""),
                "literaturePath": item_result.get("literaturePath", ""),
                "pdfPath": item_result.get("pdfPath", ""),
                "mineruMarkdown": item_result.get("mineruMarkdown", ""),
                "status": status,
            })
        except Exception as exc:
            counts["failed"] += 1
            results.append({"zoteroKey": key, "status": "failed", "stage": "ingest_item", "error": str(exc)})
    return {"ok": True, "collectionKey": collection_key, "total": len(keys), **counts, "dryRun": dry_run, "results": results}


@tool()
def obsidian_pipeline_migrate_layout(vault_path: str = "", dry_run: bool = True) -> dict[str, Any]:
    """Plan or apply migration of recognized literature pipeline assets into the focused layout."""
    vault = _vault(vault_path)
    config = _pipeline_config(vault)
    planned_moves: list[dict[str, str]] = []
    planned_yaml_updates: list[dict[str, Any]] = []
    planned_link_updates: list[dict[str, Any]] = []
    warnings: list[str] = []

    for path in _collect_markdown(vault):
        rel = _rel(vault, path)
        props, body = _split_frontmatter(_read_text(path))
        note_type = str(props.get("type") or "")
        key = str(props.get("zoteroKey") or "")
        if note_type not in {"literature", "mineru-extraction", "mineru-image-index"} or not key:
            continue
        if note_type == "literature":
            updates: dict[str, Any] = {}
            for old_pdf in _listify(props.get("attachments")):
                old_pdf_rel = str(old_pdf)
                if not old_pdf_rel or old_pdf_rel.startswith(config["zoteroAttachmentsFolder"]):
                    continue
                old_full = _safe_path(vault, old_pdf_rel)
                new_pdf_rel = f"{config['zoteroAttachmentsFolder']}/{key}/{_pipeline_ascii_slug(old_full.stem, 'paper')}{old_full.suffix.lower() or '.pdf'}"
                planned_moves.append({"from": old_pdf_rel, "to": new_pdf_rel, "kind": "zotero-pdf"})
                updates.setdefault("attachments", []).append(new_pdf_rel)
                updates.setdefault("attachmentLinks", []).append(_wikilink(new_pdf_rel))
                planned_link_updates.append({"path": rel, "from": old_pdf_rel, "to": new_pdf_rel})
            old_mineru = str(props.get("mineruMarkdown") or "").strip()
            if old_mineru and old_mineru != f"{_pipeline_mineru_dir(config, key)}/{config['mineruMarkdownName']}":
                new_mineru = f"{_pipeline_mineru_dir(config, key)}/{config['mineruMarkdownName']}"
                planned_moves.append({"from": old_mineru, "to": new_mineru, "kind": "mineru-markdown"})
                updates["mineruMarkdown"] = new_mineru
                updates["mineruMarkdownLink"] = _wikilink(new_mineru)
                updates["mineruImagesIndex"] = f"{_pipeline_mineru_dir(config, key)}/{config['mineruImagesIndexName']}"
                updates["mineruImagesIndexLink"] = _wikilink(updates["mineruImagesIndex"])
                planned_link_updates.append({"path": rel, "from": old_mineru, "to": new_mineru})
            if updates:
                planned_yaml_updates.append({"path": rel, "updates": updates})
        elif note_type == "mineru-extraction" and rel != f"{_pipeline_mineru_dir(config, key)}/{config['mineruMarkdownName']}":
            planned_moves.append({"from": rel, "to": f"{_pipeline_mineru_dir(config, key)}/{config['mineruMarkdownName']}", "kind": "mineru-markdown"})
        elif note_type == "mineru-image-index" and rel != f"{_pipeline_mineru_dir(config, key)}/{config['mineruImagesIndexName']}":
            planned_moves.append({"from": rel, "to": f"{_pipeline_mineru_dir(config, key)}/{config['mineruImagesIndexName']}", "kind": "mineru-image-index"})

    if not dry_run:
        for move in planned_moves:
            src = _safe_path(vault, move["from"])
            dest = _safe_path(vault, move["to"])
            if not src.exists():
                warnings.append(f"Missing source: {move['from']}")
                continue
            if dest.exists():
                warnings.append(f"Destination exists, skipped: {move['to']}")
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dest))
        for update in planned_yaml_updates:
            full = _safe_path(vault, update["path"])
            props, body = _split_frontmatter(_read_text(full))
            props.update(update["updates"])
            text = _join_frontmatter(props, body)
            for link in planned_link_updates:
                if link["path"] == update["path"]:
                    text = text.replace(link["from"], link["to"]).replace(_wikilink(link["from"]), _wikilink(link["to"]))
            _write_text(full, text)

    return {
        "ok": True,
        "dryRun": dry_run,
        "plannedMoves": planned_moves,
        "plannedYamlUpdates": planned_yaml_updates,
        "plannedMarkdownLinkUpdates": planned_link_updates,
        "warnings": warnings,
    }


@tool()
def obsidian_build_citation_network(
    vault_path: str = "",
    source_folder: str = "literature",
    dry_run: bool = True,
) -> dict[str, Any]:
    """Scan literature notes for Zotero relations and write [[wikilinks]] into the cites frontmatter field.

    Reads the 'relations' frontmatter list (values may be zotero://select/library/items/KEY URIs).
    Resolves each relation key to a vault note via the zoteroKey index.
    Adds unresolved targets as [[path]] entries to the note's 'cites' list.
    dry_run=true (default): report planned updates without writing.
    """
    vault = _vault(vault_path)
    root = _safe_path(vault, source_folder) if source_folder else vault

    # Build zoteroKey → vault-relative-path index from all notes in source_folder
    key_to_path: dict[str, str] = {}
    if root.exists():
        for path in root.rglob("*.md"):
            if any(part in DEFAULT_EXCLUDES or part.startswith(".") for part in path.relative_to(vault).parts):
                continue
            props, _ = _split_frontmatter(_read_text(path))
            zk = str(props.get("zoteroKey") or "").strip()
            if zk:
                key_to_path[zk.upper()] = _rel(vault, path)

    _ZOTERO_KEY_RE = re.compile(r"items/([A-Z0-9]+)", re.IGNORECASE)

    updated_notes: list[dict[str, Any]] = []

    if root.exists():
        for path in root.rglob("*.md"):
            if any(part in DEFAULT_EXCLUDES or part.startswith(".") for part in path.relative_to(vault).parts):
                continue
            rel = _rel(vault, path)
            props, body = _split_frontmatter(_read_text(path))

            # Collect referenced keys from 'relations' field
            relation_keys: set[str] = set()
            for val in _listify(props.get("relations")):
                val_str = str(val).strip()
                m = _ZOTERO_KEY_RE.search(val_str)
                if m:
                    relation_keys.add(m.group(1).upper())
                elif val_str:
                    relation_keys.add(val_str.upper())

            if not relation_keys:
                continue

            # Resolve keys to vault paths (skip self)
            new_wikilinks: list[str] = []
            for key in relation_keys:
                resolved = key_to_path.get(key)
                if resolved and resolved != rel:
                    new_wikilinks.append(f"[[{resolved}]]")

            if not new_wikilinks:
                continue

            # Merge with existing 'cites' list, avoiding duplicates
            existing_cites: list[str] = [str(v) for v in _listify(props.get("cites")) if v]
            existing_set = set(existing_cites)
            added = [link for link in new_wikilinks if link not in existing_set]
            if not added:
                continue

            props["cites"] = existing_cites + added
            new_text = _join_frontmatter(props, body)
            if not dry_run:
                _write_text(path, new_text)
            updated_notes.append({"path": rel, "addedLinks": added})

    return {
        "ok": True,
        "updatedCount": len(updated_notes),
        "dryRun": dry_run,
        "updatedNotes": updated_notes,
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
    use_scoring: bool = False,
    max_scoring_pairs: int = 500,
) -> dict[str, Any]:
    """Suggest graph improvements such as creating unresolved notes, reciprocal links, and merging similar pages.

    use_scoring=True adds 4-signal scored link suggestions (requires networkx>=3.0).
    Scored entries have kind='scored_link' and include score, signals, and reason fields.
    max_scoring_pairs: maximum node pairs to evaluate for Adamic-Adar (default 500).
    """
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

    if use_scoring:
        try:
            G = _build_nx_graph(graph)
            source_index = _build_source_index(graph)
            scored = _compute_scored_suggestions(G, graph, source_index, max_pairs=max_scoring_pairs)
            suggestions = scored + suggestions
        except Exception as exc:
            suggestions.insert(0, {"kind": "scoring_error", "message": str(exc)})

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


@tool()
def obsidian_build_reading_digest(
    vault_path: str = "",
    folder: str = "literature",
    output_path: str = "reading-digest.md",
    since_days: int = 7,
    group_by: str = "tag",
    dry_run: bool = False,
) -> dict[str, Any]:
    """Aggregate [!quote], [!highlight], [!important], and [!note] callout blocks from recently
    modified notes into a digest file grouped by tag or callout type.

    since_days: only scan notes modified within the last N days.
    group_by: "tag" groups by frontmatter/inline tags; "type" groups by callout type.
    dry_run=True: return a preview without writing the output file.
    """
    import time as _time

    vault = _vault(vault_path)
    cutoff = _time.time() - since_days * 86400

    _CALLOUT_BLOCK_RE = re.compile(
        r"(^> \[!(?:quote|highlight|important|note)[^\]]*\][ \t]*.*?(?:\n(?:> .*|>))*)",
        re.IGNORECASE | re.MULTILINE,
    )
    _CALLOUT_TYPE_RE = re.compile(r"\[!([^\]]+)\]", re.IGNORECASE)

    excerpts: list[dict[str, Any]] = []

    for path in _iter_files(vault, folder):
        if path.suffix.lower() != ".md":
            continue
        if path.stat().st_mtime < cutoff:
            continue
        rel = _rel(vault, path)
        props, body = _split_frontmatter(_read_text(path))
        title = str(props.get("title") or path.stem)
        tags = _frontmatter_tags(props) + _inline_tags(body)

        for m in _CALLOUT_BLOCK_RE.finditer(body):
            block = m.group(0)
            type_match = _CALLOUT_TYPE_RE.search(block)
            callout_type = type_match.group(1).lower() if type_match else "note"
            content_lines = []
            for raw_line in block.split("\n"):
                stripped = raw_line.lstrip(">").strip()
                if stripped and not _CALLOUT_TYPE_RE.search(stripped):
                    content_lines.append(stripped)
            content = "\n".join(content_lines).strip()
            if content:
                excerpts.append(
                    {
                        "source": rel,
                        "title": title,
                        "tags": tags,
                        "type": callout_type,
                        "content": content,
                    }
                )

    result: dict[str, Any] = {
        "ok": True,
        "excerptCount": len(excerpts),
        "outputPath": output_path,
        "dryRun": dry_run,
    }

    if not excerpts:
        result["message"] = "No callout excerpts found in the specified date range."
        return result

    # Group excerpts
    groups: dict[str, list[dict[str, Any]]] = {}
    if group_by == "tag":
        for exc in excerpts:
            for tag in (exc["tags"] or ["untagged"]):
                groups.setdefault(tag, []).append(exc)
    else:
        for exc in excerpts:
            groups.setdefault(exc["type"], []).append(exc)

    # Build digest Markdown
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines: list[str] = [
        "---",
        "title: Reading Digest",
        f"generated: {now_iso}",
        "tags: [digest]",
        "---",
        "",
        f"# Reading Digest — Last {since_days} day{'s' if since_days != 1 else ''}",
        "",
    ]
    for group_name in sorted(groups):
        lines.append(f"## {group_name}")
        lines.append("")
        for exc in groups[group_name]:
            lines.append(f"**From** [[{exc['source']}|{exc['title']}]]")
            lines.append("")
            lines.append(f"> [!{exc['type']}]")
            for content_line in exc["content"].split("\n"):
                lines.append(f"> {content_line}")
            lines.append("")

    content = "\n".join(lines)

    if dry_run:
        result["preview"] = content[:600]
        return result

    output_full = _safe_path(vault, output_path)
    output_full.parent.mkdir(parents=True, exist_ok=True)
    _write_text(output_full, content)
    result["writtenTo"] = output_path
    return result


@tool()
def obsidian_build_graph_communities(
    vault_path: str = "",
    folder: str = "",
    min_community_size: int = 3,
    write_frontmatter: bool = False,
    dry_run: bool = True,
    resolution: float = 1.0,
) -> dict[str, Any]:
    """Detect Louvain community structure in the vault knowledge graph.

    Returns community labels, sizes, modularity score, and top nodes per community.
    write_frontmatter=True adds a 'community' YAML field to each note (label = highest-inDegree node's title).
    dry_run=True (default): analysis only, no file writes.
    resolution: higher values produce smaller, more granular communities (default 1.0).
    min_community_size: communities smaller than this are excluded from results.
    """
    try:
        import networkx as nx  # noqa: F401
        from networkx.algorithms.community import louvain_communities
        from networkx.algorithms.community.quality import modularity as nx_modularity
    except ImportError:
        return {"ok": False, "error": "networkx>=3.0 is required. Install with: pip install 'networkx>=3.0'"}

    vault = _vault(vault_path)
    graph = obsidian_build_graph(vault_path=str(vault), folder=folder, include_tags=True)
    G = _build_nx_graph(graph)

    if G.number_of_nodes() < 2:
        return {"ok": True, "communityCount": 0, "modularity": 0.0, "communities": [], "written": 0, "dryRun": dry_run}

    raw_communities = louvain_communities(G, resolution=resolution, seed=42)
    try:
        mod_score = round(nx_modularity(G, raw_communities), 4)
    except Exception:
        mod_score = 0.0

    nodes_by_id = {n["id"]: n for n in graph["nodes"]}
    backlinks = graph.get("backlinks", {})

    communities_out: list[dict[str, Any]] = []
    for comm_id, comm_set in enumerate(raw_communities):
        if len(comm_set) < min_community_size:
            continue
        sorted_by_indegree = sorted(comm_set, key=lambda nid: -len(backlinks.get(nid, [])))
        top_node = sorted_by_indegree[0]
        label = str(nodes_by_id.get(top_node, {}).get("title") or Path(top_node).stem)
        tag_freq: dict[str, int] = {}
        for nid in comm_set:
            for tag in nodes_by_id.get(nid, {}).get("tags", []):
                tag_freq[tag] = tag_freq.get(tag, 0) + 1
        dominant_tags = [t for t, _ in sorted(tag_freq.items(), key=lambda x: -x[1])[:3]]
        communities_out.append({
            "id": comm_id,
            "size": len(comm_set),
            "label": label,
            "topNodes": sorted_by_indegree[:3],
            "dominantTags": dominant_tags,
            "_members": sorted(comm_set),
        })

    written = 0
    if write_frontmatter:
        for comm in communities_out:
            for node_path in comm["_members"]:
                full = _safe_path(vault, node_path)
                if not full.exists() or full.suffix.lower() != ".md":
                    continue
                props, body = _split_frontmatter(_read_text(full))
                props["community"] = comm["label"]
                if not dry_run:
                    _write_text(full, _join_frontmatter(props, body))
                written += 1

    for comm in communities_out:
        del comm["_members"]

    return {
        "ok": True,
        "communityCount": len(communities_out),
        "modularity": mod_score,
        "communities": communities_out,
        "written": written,
        "dryRun": dry_run,
    }


@tool()
def obsidian_graph_insights(
    vault_path: str = "",
    folder: str = "",
    top_n: int = 20,
) -> dict[str, Any]:
    """Detect structural patterns in the vault knowledge graph.

    Returns four insight categories:
    - bridgeNodes: low-degree but high-betweenness nodes (cross-community connectors)
    - surprisingLinks: unconnected node pairs from different communities with high source overlap
    - sparseClusters: Louvain communities with low internal edge density (< 0.2)
    - isolatedHubs: notes with high outDegree (>= 5) but very low inDegree (<= 1)

    top_n: max results per category (default 20).
    Requires networkx>=3.0.
    """
    try:
        import networkx as nx
        from networkx.algorithms.community import louvain_communities
    except ImportError:
        return {"ok": False, "error": "networkx>=3.0 is required. Install with: pip install 'networkx>=3.0'"}

    vault = _vault(vault_path)
    graph = obsidian_build_graph(vault_path=str(vault), folder=folder, include_tags=True)
    G = _build_nx_graph(graph)
    nodes_by_id = {n["id"]: n for n in graph["nodes"]}

    if G.number_of_nodes() < 3:
        return {"ok": True, "bridgeNodes": [], "surprisingLinks": [], "sparseClusters": [], "isolatedHubs": []}

    source_index = _build_source_index(graph)
    backlinks = graph.get("backlinks", {})

    # Directed outgoing counts (from edges list)
    outgoing_counts: dict[str, int] = {}
    for edge in graph["edges"]:
        outgoing_counts[edge["source"]] = outgoing_counts.get(edge["source"], 0) + 1

    # ------------------------------------------------------------------ #
    # 1. Bridge Nodes: high betweenness, low-to-median degree             #
    # ------------------------------------------------------------------ #
    betweenness = nx.betweenness_centrality(G, normalized=True)
    degrees = dict(G.degree())
    sorted_degrees = sorted(degrees.values())
    median_degree = sorted_degrees[len(sorted_degrees) // 2] if sorted_degrees else 0

    bridge_nodes: list[dict[str, Any]] = []
    for nid, bt in sorted(betweenness.items(), key=lambda x: -x[1]):
        if bt > 0.05 and degrees.get(nid, 0) <= max(median_degree, 1):
            node = nodes_by_id.get(nid, {})
            bridge_nodes.append({
                "path": nid,
                "title": str(node.get("title") or Path(nid).stem),
                "betweenness": round(bt, 4),
                "degree": degrees.get(nid, 0),
            })
            if len(bridge_nodes) >= top_n:
                break

    # ------------------------------------------------------------------ #
    # 2. Isolated Hubs: high outDegree, very low inDegree                 #
    # ------------------------------------------------------------------ #
    isolated_hubs: list[dict[str, Any]] = []
    for node in graph["nodes"]:
        nid = node["id"]
        out_deg = outgoing_counts.get(nid, 0)
        in_deg = len(backlinks.get(nid, []))
        if out_deg >= 5 and in_deg <= 1:
            isolated_hubs.append({
                "path": nid,
                "title": str(node.get("title") or Path(nid).stem),
                "outDegree": out_deg,
                "inDegree": in_deg,
            })
    isolated_hubs.sort(key=lambda x: -x["outDegree"])
    isolated_hubs = isolated_hubs[:top_n]

    # ------------------------------------------------------------------ #
    # 3. Louvain communities for cross-community analysis                 #
    # ------------------------------------------------------------------ #
    raw_communities: list[Any] = []
    node_to_community: dict[str, int] = {}
    try:
        raw_communities = list(louvain_communities(G, seed=42))
        for comm_id, comm_set in enumerate(raw_communities):
            for nid in comm_set:
                node_to_community[nid] = comm_id
    except Exception:
        pass

    # ------------------------------------------------------------------ #
    # 4. Surprising Cross-Community Links                                 #
    # ------------------------------------------------------------------ #
    surprising_links: list[dict[str, Any]] = []
    if node_to_community:
        existing_pairs: set[tuple[str, str]] = set()
        for edge in graph["edges"]:
            existing_pairs.add((edge["source"], edge["target"]))
            existing_pairs.add((edge["target"], edge["source"]))

        node_ids = [n["id"] for n in graph["nodes"]]
        for i, u in enumerate(node_ids):
            if len(surprising_links) >= top_n * 3:
                break
            for v in node_ids[i + 1:]:
                if (u, v) in existing_pairs:
                    continue
                comm_u = node_to_community.get(u)
                comm_v = node_to_community.get(v)
                if comm_u is None or comm_v is None or comm_u == comm_v:
                    continue
                overlap = _compute_source_overlap(source_index.get(u, set()), source_index.get(v, set()))
                if overlap * 4.0 >= 2.0:
                    shared = source_index.get(u, set()) & source_index.get(v, set())
                    surprising_links.append({
                        "from": u,
                        "to": v,
                        "sourceOverlapScore": round(overlap * 4.0, 2),
                        "fromCommunity": comm_u,
                        "toCommunity": comm_v,
                        "reason": f"共享来源 {len(shared)} 项",
                    })
        surprising_links.sort(key=lambda x: -x["sourceOverlapScore"])
        surprising_links = surprising_links[:top_n]

    # ------------------------------------------------------------------ #
    # 5. Sparse Clusters: low intra-community edge density                #
    # ------------------------------------------------------------------ #
    sparse_clusters: list[dict[str, Any]] = []
    for comm_id, comm_set in enumerate(raw_communities):
        comm_list = list(comm_set)
        if len(comm_list) < 3:
            continue
        subgraph = G.subgraph(comm_list)
        n = len(comm_list)
        max_possible = n * (n - 1) / 2
        density = subgraph.number_of_edges() / max_possible if max_possible > 0 else 0.0
        if density < 0.2:
            top_node = max(comm_list, key=lambda nid: len(backlinks.get(nid, [])))
            label = str(nodes_by_id.get(top_node, {}).get("title") or Path(top_node).stem)
            sparse_clusters.append({
                "communityId": comm_id,
                "community": label,
                "density": round(density, 3),
                "nodeCount": n,
                "suggestion": "考虑拆分为子社区或在内部添加更多关联链接",
            })

    sparse_clusters.sort(key=lambda x: x["density"])
    sparse_clusters = sparse_clusters[:top_n]

    return {
        "ok": True,
        "bridgeNodes": bridge_nodes,
        "surprisingLinks": surprising_links,
        "sparseClusters": sparse_clusters,
        "isolatedHubs": isolated_hubs,
    }


@tool()
def obsidian_wiki_context(
    topic: str = "",
    note_path: str = "",
    vault_path: str = "",
    max_neighbors: int = 10,
    max_search_results: int = 10,
    max_zotero_items: int = 5,
    max_entity_nodes: int = 10,
    neighbor_snippet_chars: int = 300,
    zotero_api_base: str = "",
    folder: str = "",
) -> dict[str, Any]:
    """Collect vault context for LLM-driven wiki page generation.

    Given a topic string and/or an existing note path, gathers context from
    four sources and returns a structured JSON bundle:
    - neighbors: 1-hop wikilink neighbours with body snippets
    - searchResults: full-text matches across the vault
    - zoteroItems: matching Zotero literature items (title + abstract)
    - entityNodes / conceptNodes: matching notes in entities/ and concepts/

    Also returns suggestedFrontmatter and suggestedSections to guide the LLM.
    Zotero is optional: if unavailable, zoteroItems is [] and zoteroAvailable is false.

    The calling LLM uses the returned bundle to generate wiki page content,
    which is then written to the vault via obsidian_write_wiki_page.
    """
    vault = _vault(vault_path)

    if not _s(topic).strip() and not _s(note_path).strip():
        raise ValueError("topic or note_path is required.")

    # Resolve existing note
    existing_note: dict[str, Any] | None = None
    note_rel = ""
    if _s(note_path).strip():
        note_rel = _ensure_md_path(_s(note_path).strip())
        try:
            full = _safe_path(vault, note_rel)
            if full.exists():
                text = _read_text(full)
                props, body = _split_frontmatter(text)
                existing_note = {
                    "path": _rel(vault, full),
                    "properties": props,
                    "body": body[:2000],
                }
        except Exception:
            pass

    # Determine effective topic
    effective_topic = _s(topic).strip() or _note_title_from_path(note_rel)

    # 1. Wikilink neighbours (requires a graph anchor)
    neighbors: list[dict[str, Any]] = []
    if note_rel:
        try:
            graph = obsidian_build_graph(vault_path=str(vault), folder=folder, include_tags=True)
            neighbors = _wiki_neighbors(vault, note_rel, graph, max_neighbors, neighbor_snippet_chars)
        except Exception:
            pass

    # 2. Full-text search
    search_results = _wiki_search_results(vault, effective_topic, max_search_results)

    # 3. Zotero items (graceful degradation)
    zotero_items: list[dict[str, Any]] = []
    zotero_available = False
    try:
        zotero_items = _wiki_zotero_items(effective_topic, max_zotero_items, zotero_api_base)
        zotero_available = True
    except Exception:
        pass

    # 4. Entity/concept nodes
    entities_folder = _configured_path(vault, "entitiesFolder", "entities", "entities")
    concepts_folder = _configured_path(vault, "conceptsFolder", "concepts", "concepts")
    entity_nodes, concept_nodes = _wiki_entity_concept_nodes(
        vault, effective_topic, entities_folder, concepts_folder,
        max_entity_nodes, neighbor_snippet_chars,
    )

    # Assemble suggestedFrontmatter
    seen_related: set[str] = set()
    related: list[str] = []
    for item in neighbors + entity_nodes + concept_nodes:
        p = item["path"]
        if p not in seen_related:
            seen_related.add(p)
            related.append(p)

    zotero_keys = [item["key"] for item in zotero_items if item.get("key")]

    suggested_fm: dict[str, Any] = {
        "title": effective_topic,
        "type": "wiki",
        "tags": ["wiki"],
    }
    if related:
        suggested_fm["related"] = related
    if zotero_keys:
        suggested_fm["zoteroKeys"] = zotero_keys

    return {
        "topic": effective_topic,
        "notePath": note_rel or None,
        "existingNote": existing_note,
        "neighbors": neighbors,
        "searchResults": search_results,
        "zoteroItems": zotero_items,
        "entityNodes": entity_nodes,
        "conceptNodes": concept_nodes,
        "zoteroAvailable": zotero_available,
        "suggestedFrontmatter": suggested_fm,
        "suggestedSections": [
            "## Overview",
            "## Key Concepts",
            "## Related Notes",
            "## References",
        ],
    }


@tool()
def obsidian_write_wiki_page(
    path: str,
    content: str,
    vault_path: str = "",
    title: str = "",
    properties_json: str = "{}",
    overwrite: bool = False,
    update_index: bool = True,
    append_log: bool = True,
    index_path: str = "index.md",
    log_path: str = "log.md",
    dry_run: bool = False,
) -> dict[str, Any]:
    """Write an LLM-generated wiki page to the vault.

    Accepts Markdown content produced by a calling LLM and writes it to the
    specified path (typically wiki/<slug>.md) with standard wiki frontmatter:
    type=wiki, tags=[wiki], title, and created timestamp.

    Extra frontmatter fields (e.g. related, zoteroKeys) can be injected via
    properties_json. After writing, optionally updates the vault index and
    appends a wiki_generated event to the log.

    Set dry_run=true to preview the final file content without writing.
    Set overwrite=true to replace an existing page.
    """
    if not _s(path).strip():
        raise ValueError("path is required.")
    if not _s(content).strip():
        raise ValueError("content is required.")

    extra_props = _json(properties_json, {})
    if not isinstance(extra_props, dict):
        raise ValueError("properties_json must decode to an object.")

    vault = _vault(vault_path)
    rel = _ensure_md_path(_s(path).strip())
    full = _safe_path(vault, rel)

    existed = full.exists()
    if existed and not overwrite:
        return {
            "ok": False,
            "path": rel,
            "error": "Wiki page already exists. Pass overwrite=true to replace it.",
        }

    # Assemble frontmatter
    page_title = _s(title).strip() or _note_title_from_path(rel)
    props: dict[str, Any] = {
        "title": page_title,
        "type": "wiki",
        "tags": ["wiki"],
        "created": _utc_now(),
    }
    props.update(extra_props)
    props["type"] = "wiki"  # ensure type is never overridden

    final_content = _join_frontmatter(props, content)

    if dry_run:
        return {
            "ok": True,
            "path": rel,
            "created": not existed,
            "dryRun": True,
            "indexUpdated": False,
            "logAppended": False,
            "content": final_content,
        }

    _write_text(full, final_content)

    index_updated = False
    index_error: str | None = None
    if update_index:
        try:
            obsidian_update_wiki_index(vault_path=str(vault), index_path=index_path)
            index_updated = True
        except Exception as exc:
            index_error = str(exc)

    log_appended = False
    log_error: str | None = None
    if append_log:
        try:
            obsidian_append_wiki_log(
                f"Wiki page generated: {page_title}",
                vault_path=str(vault),
                log_path=log_path,
                event_type="wiki_generated",
                touched_paths_json=json.dumps([rel]),
            )
            log_appended = True
        except Exception as exc:
            log_error = str(exc)

    result: dict[str, Any] = {
        "ok": True,
        "path": rel,
        "created": not existed,
        "dryRun": False,
        "indexUpdated": index_updated,
        "logAppended": log_appended,
        "content": None,
    }
    if index_error:
        result["indexError"] = index_error
    if log_error:
        result["logError"] = log_error
    return result


@tool()
def obsidian_wiki_stale_pages(
    vault_path: str = "",
    wiki_folder: str = "wiki",
    min_age_days: int = 7,
    since_days: int = 7,
    max_new_notes: int = 5,
    top_n: int = 50,
) -> dict[str, Any]:
    """Scan the wiki folder for pages that may need regeneration.

    Returns pages where at least one of these signals fires within the
    last since_days days AND after the page was originally created:

    - ``related_modified``: a note listed in the page's ``related``
      frontmatter field has been modified.
    - ``new_notes``: a vault note (outside wiki_folder) whose content
      contains the page's title keywords has been modified.

    Only pages whose ``created`` timestamp is at least min_age_days old
    are examined.  Results are sorted by newNeighborCount descending
    (most stale first) and capped at top_n.

    Use the returned stalePages list to decide which wiki pages to
    regenerate via obsidian_wiki_context + obsidian_write_wiki_page.
    """
    if min_age_days < 0:
        raise ValueError("min_age_days must be >= 0")
    if since_days < 0:
        raise ValueError("since_days must be >= 0")
    if top_n < 1:
        raise ValueError("top_n must be >= 1")
    if max_new_notes < 1:
        raise ValueError("max_new_notes must be >= 1")
    vault = _vault(vault_path)
    stale_pages, checked_count = _stale_wiki_pages_scan(
        vault, wiki_folder, min_age_days, since_days, max_new_notes, top_n
    )
    return {
        "stalePages": stale_pages,
        "checkedCount": checked_count,
        "staleCount": len(stale_pages),
        "wikiFolder": wiki_folder,
        "minAgeDays": min_age_days,
        "sinceDays": since_days,
        "topN": top_n,
    }
