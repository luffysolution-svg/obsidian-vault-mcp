"""BibTeX result types and the metadata-only fallback renderer."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any

from ...domain.errors import ObsidianVaultMcpError

_YEAR_RE = re.compile(r"(?<!\d)(\d{4})(?!\d)")
_BIBTEX_RE = re.compile(r"^\s*@\w+\s*[({]", re.MULTILINE)
_BIBTEX_ENTRY_RE = re.compile(r"@([A-Za-z]+)\s*([({])")
_BIBTEX_FIELD_RE = re.compile(
    r"^\s*([A-Za-z][A-Za-z0-9_.:-]*)\s*=\s*(.*?)\s*$",
    re.DOTALL,
)
_CITEKEY_RE = re.compile(r"[^A-Za-z0-9_:.+-]+")
_LOCAL_FILE_REFERENCE_RE = re.compile(
    r"(?:\bfile\s*:|(?<![A-Za-z0-9])[A-Za-z](?:\\)?:[\\/]|(?<![\\/])\\\\[^\\/\s])",
    re.IGNORECASE,
)
_LOCAL_FILE_FIELDS = frozenset(
    {
        "attachment",
        "attachments",
        "file",
        "file-path",
        "filepath",
        "files",
        "full-text",
        "fulltext",
        "local-file",
        "local-path",
        "local-url",
        "path",
        "pdf",
    }
)
_NON_RECORD_ENTRY_TYPES = frozenset({"comment", "preamble", "string"})


class BibTeXError(ObsidianVaultMcpError, ValueError):
    """A BibTeX provider or renderer returned unusable data."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "bibtex_error",
        provider: str = "builtin",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.provider = provider
        self.details = details or {}

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable error payload."""

        return {
            "ok": False,
            "code": self.code,
            "provider": self.provider,
            "message": str(self),
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class BibTeXResult(Mapping[str, Any]):
    """Successful BibTeX output plus non-silent fallback diagnostics.

    The object behaves like a read-only mapping for MCP/JSON-oriented callers
    while retaining a typed Python API.
    """

    provider: str
    bibtex: str
    errors: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return True

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "ok": True,
            "provider": self.provider,
            "bibtex": self.bibtex,
            "errors": [dict(error) for error in self.errors],
        }

    def __getitem__(self, key: str) -> Any:
        return self.to_dict()[key]

    def __iter__(self) -> Iterator[str]:
        return iter(("ok", "provider", "bibtex", "errors"))

    def __len__(self) -> int:
        return 4


def is_bibtex(value: str) -> bool:
    """Return whether ``value`` contains at least one BibTeX entry."""

    return bool(value and _BIBTEX_RE.search(value))


def sanitize_bibtex(value: str) -> str:
    """Remove local attachment fields and filesystem references from BibTeX."""

    output: list[str] = []
    cursor = 0
    while match := _BIBTEX_ENTRY_RE.search(value, cursor):
        open_index = match.end() - 1
        end_index = _find_entry_end(value, open_index, match.group(2))
        if end_index is None:
            break

        output.append(value[cursor : match.start()])
        entry = value[match.start() : end_index + 1]
        if match.group(1).lower() in _NON_RECORD_ENTRY_TYPES:
            output.append(entry)
        else:
            relative_open_index = open_index - match.start()
            output.append(_sanitize_entry(entry, relative_open_index))
        cursor = end_index + 1

    output.append(value[cursor:])
    return "".join(output)


def generate_builtin_bibtex(item: Mapping[str, Any]) -> str:
    """Generate a deterministic basic BibTeX entry from Zotero metadata.

    Explicit mappings are provided for every V2-required Zotero type:
    ``journalArticle``, ``conferencePaper``, ``book``, ``bookSection``,
    ``thesis``, ``report``, ``preprint`` and ``patent``. Unknown types use a
    conservative ``@misc`` entry rather than dropping the citation.
    """

    data = _flatten_item(item)
    item_type = _text(data.get("itemType")) or "document"
    entry_type = _entry_type(item_type, data)
    citekey = _citekey(data)

    fields: list[tuple[str, str]] = []
    _add(fields, "title", data.get("title"))
    _add_creators(fields, data, item_type)

    if item_type == "journalArticle":
        _add(fields, "journal", data.get("publicationTitle") or data.get("journal"))
        _add(fields, "year", _year(data.get("date") or data.get("year")))
        _add(fields, "volume", data.get("volume"))
        _add(fields, "number", data.get("issue"))
        _add(fields, "pages", data.get("pages"))
        _add(fields, "publisher", data.get("publisher"))
    elif item_type == "conferencePaper":
        _add(
            fields,
            "booktitle",
            data.get("proceedingsTitle") or data.get("conferenceName") or data.get("publicationTitle"),
        )
        _add(fields, "year", _year(data.get("date") or data.get("year")))
        _add(fields, "pages", data.get("pages"))
        _add(fields, "publisher", data.get("publisher"))
        _add(fields, "address", data.get("place"))
    elif item_type == "book":
        _add(fields, "publisher", data.get("publisher"))
        _add(fields, "year", _year(data.get("date") or data.get("year")))
        _add(fields, "address", data.get("place"))
        _add(fields, "edition", data.get("edition"))
        _add(fields, "series", data.get("series"))
        _add(fields, "isbn", data.get("ISBN") or data.get("isbn"))
    elif item_type == "bookSection":
        _add(fields, "booktitle", data.get("bookTitle") or data.get("publicationTitle"))
        _add(fields, "publisher", data.get("publisher"))
        _add(fields, "year", _year(data.get("date") or data.get("year")))
        _add(fields, "pages", data.get("pages"))
        _add(fields, "address", data.get("place"))
        _add(fields, "edition", data.get("edition"))
        _add(fields, "isbn", data.get("ISBN") or data.get("isbn"))
    elif item_type == "thesis":
        _add(fields, "school", data.get("university") or data.get("institution"))
        _add(fields, "year", _year(data.get("date") or data.get("year")))
        _add(fields, "type", data.get("thesisType"))
        _add(fields, "address", data.get("place"))
    elif item_type == "report":
        _add(fields, "institution", data.get("institution") or data.get("publisher"))
        _add(fields, "year", _year(data.get("date") or data.get("year")))
        _add(fields, "number", data.get("reportNumber"))
        _add(fields, "type", data.get("reportType"))
        _add(fields, "address", data.get("place"))
    elif item_type == "preprint":
        _add(fields, "year", _year(data.get("date") or data.get("year")))
        _add(fields, "howpublished", data.get("repository") or data.get("archive"))
        _add(fields, "eprint", data.get("archiveID") or data.get("eprint"))
        _add(fields, "archiveprefix", data.get("archive") or data.get("archivePrefix"))
        _add(fields, "primaryclass", data.get("archiveLocation") or data.get("primaryClass"))
    elif item_type == "patent":
        _add(fields, "year", _year(data.get("date") or data.get("year")))
        _add(fields, "number", data.get("patentNumber") or data.get("applicationNumber"))
        _add(fields, "holder", data.get("assignee"))
        _add(fields, "address", data.get("country") or data.get("place"))
        _add(fields, "howpublished", data.get("patentType") or "Patent")
    else:
        _add(fields, "year", _year(data.get("date") or data.get("year")))
        _add(fields, "publisher", data.get("publisher") or data.get("institution"))
        _add(fields, "howpublished", data.get("repository"))

    _add(fields, "doi", data.get("DOI") or data.get("doi"))
    _add(fields, "url", data.get("url"))
    _add(fields, "language", data.get("language"))

    if not fields:
        raise BibTeXError(
            "Zotero item does not contain metadata usable for BibTeX",
            code="missing_bibtex_metadata",
            details={"itemType": item_type},
        )

    body = ",\n".join(f"  {name} = {{{_escape(value)}}}" for name, value in fields)
    return f"@{entry_type}{{{citekey},\n{body}\n}}"


# Readable alias used by callers that prefer a builder-style name.
build_builtin_bibtex = generate_builtin_bibtex


def _find_entry_end(value: str, open_index: int, opener: str) -> int | None:
    depth = 1
    brace_depth = 0
    in_quotes = False
    escaped = False

    for index in range(open_index + 1, len(value)):
        character = value[index]
        if escaped:
            escaped = False
            continue
        if character == "\\":
            escaped = True
            continue
        if character == '"':
            in_quotes = not in_quotes
            continue
        if in_quotes:
            continue

        if opener == "{":
            if character == "{":
                depth += 1
            elif character == "}":
                depth -= 1
                if depth == 0:
                    return index
            continue

        if character == "{":
            brace_depth += 1
        elif character == "}" and brace_depth:
            brace_depth -= 1
        elif brace_depth == 0 and character == "(":
            depth += 1
        elif brace_depth == 0 and character == ")":
            depth -= 1
            if depth == 0:
                return index
    return None


def _sanitize_entry(entry: str, open_index: int) -> str:
    chunks = _split_top_level(entry[open_index + 1 : -1])
    if len(chunks) < 2:
        return entry

    fields: list[str] = []
    removed = False
    for chunk in chunks[1:]:
        stripped = chunk.strip()
        if not stripped:
            continue
        match = _BIBTEX_FIELD_RE.match(stripped)
        if match and _is_local_field(match.group(1), match.group(2)):
            removed = True
            continue
        fields.append(stripped)

    if not removed:
        return entry

    newline = "\r\n" if "\r\n" in entry else "\n"
    citation_key = chunks[0].strip()
    rendered_fields = f",{newline}".join(f"  {field}" for field in fields)
    body = f"{citation_key},{newline}"
    if rendered_fields:
        body += f"{rendered_fields}{newline}"
    return f"{entry[: open_index + 1]}{body}{entry[-1]}"


def _split_top_level(value: str) -> list[str]:
    chunks: list[str] = []
    start = 0
    brace_depth = 0
    parenthesis_depth = 0
    in_quotes = False
    escaped = False

    for index, character in enumerate(value):
        if escaped:
            escaped = False
            continue
        if character == "\\":
            escaped = True
            continue
        if character == '"':
            in_quotes = not in_quotes
            continue
        if in_quotes:
            continue
        if character == "{":
            brace_depth += 1
        elif character == "}" and brace_depth:
            brace_depth -= 1
        elif character == "(" and brace_depth == 0:
            parenthesis_depth += 1
        elif character == ")" and brace_depth == 0 and parenthesis_depth:
            parenthesis_depth -= 1
        elif character == "," and brace_depth == 0 and parenthesis_depth == 0:
            chunks.append(value[start:index])
            start = index + 1

    chunks.append(value[start:])
    return chunks


def _is_local_field(name: str, value: str) -> bool:
    normalized_name = name.lower().replace("_", "-")
    return (
        normalized_name in _LOCAL_FILE_FIELDS
        or normalized_name.startswith("bdsk-file-")
        or bool(_LOCAL_FILE_REFERENCE_RE.search(value))
    )


def _flatten_item(item: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(item, Mapping):
        raise BibTeXError(
            "BibTeX metadata must be a mapping",
            code="invalid_bibtex_metadata",
            details={"metadataType": type(item).__name__},
        )
    raw_data = item.get("data")
    data = dict(raw_data) if isinstance(raw_data, Mapping) else dict(item)
    for key in ("key", "version", "citationKey", "citekey"):
        if key not in data and item.get(key) is not None:
            data[key] = item[key]
    return data


def _entry_type(item_type: str, data: Mapping[str, Any]) -> str:
    if item_type == "thesis":
        thesis_type = _text(data.get("thesisType")).lower()
        return "mastersthesis" if "master" in thesis_type else "phdthesis"
    return {
        "journalArticle": "article",
        "conferencePaper": "inproceedings",
        "book": "book",
        "bookSection": "incollection",
        "report": "techreport",
        "preprint": "misc",
        "patent": "misc",
    }.get(item_type, "misc")


def _add_creators(
    fields: list[tuple[str, str]],
    data: Mapping[str, Any],
    item_type: str,
) -> None:
    creators = data.get("creators")
    if not isinstance(creators, list):
        return

    author_types = {"author"}
    if item_type == "patent":
        author_types.add("inventor")
    authors = [_creator_name(creator) for creator in creators if _creator_type(creator) in author_types]
    editors = [_creator_name(creator) for creator in creators if _creator_type(creator) == "editor"]
    _add(fields, "author", " and ".join(name for name in authors if name))
    _add(fields, "editor", " and ".join(name for name in editors if name))


def _creator_type(creator: Any) -> str:
    return _text(creator.get("creatorType")) if isinstance(creator, Mapping) else ""


def _creator_name(creator: Any) -> str:
    if not isinstance(creator, Mapping):
        return ""
    corporate = _text(creator.get("name"))
    if corporate:
        return corporate
    first = _text(creator.get("firstName"))
    last = _text(creator.get("lastName"))
    if first and last:
        return f"{last}, {first}"
    return last or first


def _add(fields: list[tuple[str, str]], name: str, value: Any) -> None:
    text = _text(value)
    if text:
        fields.append((name, text))


def _text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split()).strip()


def _year(value: Any) -> str:
    match = _YEAR_RE.search(_text(value))
    return match.group(1) if match else ""


def _citekey(data: Mapping[str, Any]) -> str:
    preferred = _text(data.get("citationKey") or data.get("citekey") or data.get("key"))
    if not preferred:
        creators = data.get("creators")
        first_creator = creators[0] if isinstance(creators, list) and creators else {}
        author = _creator_name(first_creator).split(",", 1)[0]
        year = _year(data.get("date") or data.get("year"))
        first_title_word = next(iter(re.findall(r"[\w]+", _text(data.get("title")))), "item")
        preferred = f"{author}{year}{first_title_word}" or "item"

    ascii_key = unicodedata.normalize("NFKD", preferred).encode("ascii", "ignore").decode("ascii")
    key = _CITEKEY_RE.sub("_", ascii_key).strip("_")
    return key or "item"


def _escape(value: str) -> str:
    escaped: list[str] = []
    replacements = {
        "\\": r"\textbackslash{}",
        "{": r"\{",
        "}": r"\}",
        "%": r"\%",
        "&": r"\&",
        "#": r"\#",
        "_": r"\_",
        "$": r"\$",
    }
    for character in value:
        escaped.append(replacements.get(character, character))
    return "".join(escaped)
