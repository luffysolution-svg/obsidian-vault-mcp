from __future__ import annotations

import re
from collections.abc import Mapping

MANAGED_SECTIONS = (
    ("abstract", "Abstract"),
    ("pdf", "PDF"),
    ("mineru", "MinerU"),
    ("zotero-notes", "Zotero Notes"),
    ("bibtex", "BibTeX"),
)


def _managed_section(name: str, heading: str, content: str) -> str:
    return "\n".join(
        [
            f"## {heading}",
            "",
            f"<!-- ovm:{name}:start -->",
            content.strip(),
            f"<!-- ovm:{name}:end -->",
        ]
    )


def _remove_managed_sections(body: str) -> str:
    result = body.replace("\r\n", "\n").replace("\r", "\n")
    result = re.sub(r"\A\s*# [^\n]*\n*", "", result, count=1)
    for name, heading in MANAGED_SECTIONS:
        section = re.compile(
            rf"(?ms)^##[ \t]+{re.escape(heading)}[ \t]*\n+"
            rf"<!--[ \t]*ovm:{re.escape(name)}:start[ \t]*-->.*?"
            rf"<!--[ \t]*ovm:{re.escape(name)}:end[ \t]*-->[ \t]*\n*"
        )
        result = section.sub("", result)
        orphan = re.compile(
            rf"(?ms)<!--[ \t]*ovm:{re.escape(name)}:start[ \t]*-->.*?"
            rf"<!--[ \t]*ovm:{re.escape(name)}:end[ \t]*-->[ \t]*\n*"
        )
        result = orphan.sub("", result)
    return result.strip()


def _wikilink_target(path: str) -> str:
    normalized = path.replace("\\", "/").strip("/")
    return normalized[:-3] if normalized.lower().endswith(".md") else normalized


def render_note_body(
    title: str,
    *,
    abstract: str = "",
    pdf_path: str = "",
    mineru_path: str = "",
    zotero_notes: str = "",
    bibtex: str = "",
    existing_body: str = "",
    reading_notes_heading: str = "Reading Notes",
    embed_pdf: bool = True,
    embed_mineru: bool = True,
    omit_empty: bool = True,
) -> str:
    """Render managed note blocks while preserving every user-owned section."""
    clean_title = " ".join(str(title).split()) or "Untitled"
    content: dict[str, str] = {
        "abstract": abstract.strip(),
        "pdf": f"![[{pdf_path.replace(chr(92), '/').strip('/') }]]" if pdf_path and embed_pdf else "",
        "mineru": "",
        "zotero-notes": zotero_notes.strip(),
        "bibtex": f"```bibtex\n{bibtex.strip()}\n```" if bibtex.strip() else "",
    }
    if mineru_path:
        target = _wikilink_target(mineru_path)
        mineru_lines = [f"- Full text: [[{target}]]"]
        if embed_mineru:
            mineru_lines.extend(["", f"![[{target}]]"])
        content["mineru"] = "\n".join(mineru_lines)

    parts = [f"# {clean_title}"]
    for name, heading in MANAGED_SECTIONS:
        value = content[name]
        if value or not omit_empty:
            parts.append(_managed_section(name, heading, value))

    user_content = _remove_managed_sections(existing_body)
    reading_pattern = re.compile(rf"(?m)^##[ \t]+{re.escape(reading_notes_heading)}[ \t]*$")
    if not user_content:
        user_content = f"## {reading_notes_heading}"
    elif not reading_pattern.search(user_content):
        user_content = f"{user_content.rstrip()}\n\n## {reading_notes_heading}"
    parts.append(user_content)
    return "\n\n".join(part.rstrip() for part in parts if part is not None).rstrip() + "\n"


def managed_section_values(body: str) -> Mapping[str, str]:
    """Read managed block values for verification and migration diagnostics."""
    values: dict[str, str] = {}
    for name, _heading in MANAGED_SECTIONS:
        match = re.search(
            rf"(?ms)<!--[ \t]*ovm:{re.escape(name)}:start[ \t]*-->\s*(.*?)\s*"
            rf"<!--[ \t]*ovm:{re.escape(name)}:end[ \t]*-->",
            body,
        )
        if match:
            values[name] = match.group(1)
    return values


def replace_managed_section(body: str, name: str, heading: str, content: str) -> str:
    """Replace, insert, or remove one managed section without touching others."""
    if name not in {section_name for section_name, _ in MANAGED_SECTIONS}:
        raise ValueError(f"unknown managed section: {name}")
    normalized = body.replace("\r\n", "\n").replace("\r", "\n")
    pattern = re.compile(
        rf"(?ms)^##[ \t]+{re.escape(heading)}[ \t]*\n+"
        rf"<!--[ \t]*ovm:{re.escape(name)}:start[ \t]*-->.*?"
        rf"<!--[ \t]*ovm:{re.escape(name)}:end[ \t]*-->[ \t]*\n*"
    )
    replacement = _managed_section(name, heading, content).rstrip() + "\n\n" if content.strip() else ""
    if pattern.search(normalized):
        return pattern.sub(replacement, normalized, count=1).rstrip() + "\n"
    if not content.strip():
        return normalized.rstrip() + "\n"

    section_index = next(index for index, section in enumerate(MANAGED_SECTIONS) if section[0] == name)
    for later_name, later_heading in MANAGED_SECTIONS[section_index + 1 :]:
        later_pattern = re.compile(
            rf"(?m)^##[ \t]+{re.escape(later_heading)}[ \t]*\n+"
            rf"<!--[ \t]*ovm:{re.escape(later_name)}:start[ \t]*-->"
        )
        later = later_pattern.search(normalized)
        if later:
            return (
                normalized[: later.start()].rstrip()
                + "\n\n"
                + replacement
                + normalized[later.start() :].lstrip()
            ).rstrip() + "\n"
    reading = re.search(r"(?m)^##[ \t]+Reading Notes[ \t]*$", normalized)
    if reading:
        return (normalized[: reading.start()].rstrip() + "\n\n" + replacement + normalized[reading.start() :].lstrip()).rstrip() + "\n"
    return (normalized.rstrip() + "\n\n" + replacement).rstrip() + "\n"
