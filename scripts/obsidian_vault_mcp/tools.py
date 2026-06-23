from . import helpers as _helpers

globals().update({name: value for name, value in vars(_helpers).items() if not name.startswith("__")})



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

PIPELINE_CONFIG_FILE = ".obsidian-vault-pipeline.json"
PIPELINE_DEFAULT_CONFIG: dict[str, str] = {
    "literatureFolder": "literature",
    "zoteroAttachmentsFolder": "attachments/zotero",
    "zoteroLinkedAttachmentBaseDirectory": "",
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


# ── MinerU internal helpers (not registered as MCP tools) ───────────────────


def obsidian_mineru_status(cli_command: str = "") -> dict[str, Any]:
    """Check optional MinerU CLI availability and token environment variables."""
    return _mineru_cli_status(cli_command)


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
    """Run MinerU CLI extraction and save output under the vault (internal helper)."""
    vault = _vault(vault_path)
    resolved_token = token or os.environ.get("MINERU_TOKEN") or os.environ.get("MINERU_API_TOKEN") or ""
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


def _pipeline_first_sentence(text: str, fallback: str) -> str:
    clean = " ".join(_s(text).split())
    if not clean:
        return fallback
    match = re.match(r"(.{20,280}?[.!?。！？])(?:\s|$)", clean)
    if match:
        return match.group(1).strip()
    return clean[:280].rstrip() or fallback


def _pipeline_ai_summary_template(props: dict[str, Any], source_text: str = "") -> str:
    abstract = _s(props.get("abstract")).strip()
    title = _s(props.get("title")).strip() or "this paper"
    core = _pipeline_first_sentence(abstract or source_text, "No core finding is available in the current Zotero or MinerU text.")
    scope_parts = []
    if props.get("year"):
        scope_parts.append(str(props["year"]))
    if props.get("publicationTitle"):
        scope_parts.append(str(props["publicationTitle"]))
    scope = "; ".join(scope_parts) or f"Literature note for {title}."
    return "\n".join([
        "## AI Summary",
        "",
        f"**Core Finding:** {core}",
        "",
        "**Method:** Not specified in available Zotero or MinerU text.",
        "",
        f"**Dataset / Scope:** {scope}",
        "",
        "**Limitations:** Not specified in available Zotero or MinerU text.",
        "",
        "**My Assessment:** Generated as a starter summary from local metadata/extracted text; refine after reading.",
        "",
    ])


def _pipeline_write_ai_summary(
    vault: Path,
    rel_path: str,
    source_text: str = "",
    dry_run: bool = False,
) -> dict[str, Any]:
    full = _safe_path(vault, rel_path)
    props, body = _split_frontmatter(_read_text(full))
    section_re = re.compile(r"^## AI Summary\s*\n(.*?)(?=^##\s+|\Z)", re.DOTALL | re.MULTILINE)
    match = section_re.search(body)
    if match and match.group(1).strip():
        return {"ok": True, "path": rel_path, "written": False, "reason": "AI Summary already has content."}

    summary = _pipeline_ai_summary_template(props, source_text).rstrip() + "\n\n"
    if match:
        updated_body = section_re.sub(summary.rstrip() + "\n", body, count=1)
    else:
        reading_re = re.compile(r"^## Reading Notes\s*\n", re.MULTILINE)
        reading_match = reading_re.search(body)
        if reading_match:
            updated_body = body[:reading_match.start()] + summary + body[reading_match.start():]
        else:
            updated_body = body.rstrip() + "\n\n" + summary
    result = _write_result(vault, full, _join_frontmatter(props, updated_body.rstrip() + "\n"), dry_run)
    result["written"] = bool(result.get("ok"))
    return result


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
    write_ai_summary: bool = False,
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
            source_pdf = _resolve_zotero_attachment_path(attachment, config.get("zoteroLinkedAttachmentBaseDirectory", ""))
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
        parse = obsidian_pipeline_parse_with_mineru(zotero_key=zotero_key, vault_path=str(vault), write_ai_summary=write_ai_summary)
        result["mineru"] = parse
        result["mineruMarkdown"] = parse.get("mineruMarkdown", "")
        result["mineruImagesIndex"] = parse.get("mineruImagesIndex", "")
        result["ok"] = result["ok"] and bool(parse.get("ok"))
    elif write_ai_summary and not dry_run:
        summary = _pipeline_write_ai_summary(vault, literature_rel, str(metadata.get("abstract") or metadata.get("abstractNote") or ""))
        result["aiSummary"] = summary
        result["ok"] = result["ok"] and bool(summary.get("ok"))
    elif write_ai_summary:
        result["aiSummary"] = {"ok": True, "written": False, "dryRun": True}
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
                old_full.replace(new_full)
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
    write_ai_summary: bool = False,
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
    try:
        rename = obsidian_pipeline_rename_mineru_images(effective_key, markdown_rel, str(vault), dry_run=False)
    except Exception as exc:
        rename = {"ok": False, "error": str(exc), "renamed": 0, "errors": [{"error": str(exc)}]}

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
    ai_summary = None
    if write_ai_summary:
        ai_summary = _pipeline_write_ai_summary(vault, lit_rel, source_body.strip() or _read_text(source_md_full).strip())
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
        "aiSummary": ai_summary,
    }


@tool()
def obsidian_pipeline_ingest_collection(
    collection_key: str,
    vault_path: str = "",
    parse_with_mineru: bool = False,
    write_ai_summary: bool = False,
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
            item_result = obsidian_pipeline_ingest_item(
                key,
                str(vault),
                parse_with_mineru=parse_with_mineru,
                write_ai_summary=write_ai_summary,
                dry_run=dry_run,
                api_base=api_base,
            )
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




def obsidian_doctor(vault_path: str = "") -> dict[str, Any]:
    """Run a local readiness check for vault resolution, templates, dependencies, and optional integrations."""
    return _doctor(vault_path)

























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




















