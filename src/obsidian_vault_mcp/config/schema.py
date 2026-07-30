"""Strict validation and normalization for the V2 JSON configuration."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from ..domain.errors import ConfigurationError, IdentityError, PathValidationError
from ..domain.frontmatter import MANAGED_FIELD_ORDER
from ..domain.identity import render_filename, validate_naming_pattern
from ..domain.paths import normalize_vault_relative
from .defaults import DEFAULT_CONFIG, SCHEMA_URL, SCHEMA_VERSION

_ALLOWED_KEYS: dict[str, set[str]] = {
    "root": {
        "$schema",
        "schemaVersion",
        "literature",
        "identity",
        "naming",
        "attachments",
        "frontmatter",
        "note",
        "zotero",
        "bibtex",
        "mineru",
        "analysis",
        "index",
        "base",
        "safety",
    },
    "literature": {"root", "index", "base", "wikiFolder"},
    "identity": {"strategy"},
    "naming": {"note", "pdf", "mineruMarkdown", "mineruImage"},
    "attachments": {"pdfFolder", "copyPdf", "overwritePolicy"},
    "frontmatter": {"omitEmpty", "preserveUnknownFields", "fieldOrder"},
    "note": {
        "omitEmptySections",
        "preserveUserSections",
        "readingNotesHeading",
        "embedPdf",
        "embedMineruMarkdown",
    },
    "zotero": {
        "apiBase",
        "linkedAttachmentBaseDir",
        "syncNotes",
        "syncAnnotations",
        "syncTags",
        "paginationSize",
    },
    "bibtex": {"enabled", "provider", "fallback"},
    "mineru": {
        "enabled",
        "mode",
        "markdownFolder",
        "imageFolder",
        "imageLinkStyle",
        "replacePreviousOutput",
        "maxConcurrentJobs",
    },
    "analysis": {
        "folder",
        "base",
        "fullReadsFolder",
        "reviewsFolder",
        "passageQaFolder",
        "figureQaFolder",
        "conceptsFolder",
    },
    "index": {"autoRebuild", "recentLimit", "groupBy"},
    "base": {"autoRebuild", "name"},
    "safety": {
        "atomicWrites",
        "backupBeforeReplace",
        "retainBackups",
        "defaultDryRunForMigration",
        "lockPerItem",
    },
}

# A public JSON Schema description for editors and integrations. Runtime
# validation below also performs cross-field, path, and filename checks that
# JSON Schema cannot express concisely.
CONFIG_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": SCHEMA_URL,
    "title": "Obsidian Vault MCP V2 configuration",
    "description": "Configuration for the local Zotero, MinerU, and Obsidian literature pipeline.",
    "type": "object",
    "required": ["schemaVersion"],
    "additionalProperties": False,
    "properties": {
        "$schema": {
            "type": "string",
            "minLength": 1,
            "default": SCHEMA_URL,
        },
        "schemaVersion": {"const": SCHEMA_VERSION, "default": SCHEMA_VERSION},
        "literature": {
            "type": "object",
            "additionalProperties": False,
            "default": DEFAULT_CONFIG["literature"],
            "properties": {
                "root": {"type": "string", "minLength": 1, "default": "Literature"},
                "index": {"type": "string", "minLength": 1, "default": "Literature/index.md"},
                "base": {"type": "string", "minLength": 1, "default": "Literature/Literature.base"},
                "wikiFolder": {"type": "string", "minLength": 1, "default": "Literature/Wiki"},
            },
        },
        "identity": {
            "type": "object",
            "additionalProperties": False,
            "default": DEFAULT_CONFIG["identity"],
            "properties": {
                "strategy": {"const": "zoteroKey", "default": "zoteroKey"},
            },
        },
        "naming": {
            "type": "object",
            "additionalProperties": False,
            "default": DEFAULT_CONFIG["naming"],
            "properties": {
                "note": {"type": "string", "minLength": 1, "default": "{zoteroKey}.md"},
                "pdf": {"type": "string", "minLength": 1, "default": "{zoteroKey}.pdf"},
                "mineruMarkdown": {"type": "string", "minLength": 1, "default": "{zoteroKey}.md"},
                "mineruImage": {
                    "type": "string",
                    "minLength": 1,
                    "default": "{zoteroKey}-fig{index:02d}.{ext}",
                },
            },
        },
        "attachments": {
            "type": "object",
            "additionalProperties": False,
            "default": DEFAULT_CONFIG["attachments"],
            "properties": {
                "pdfFolder": {"type": "string", "minLength": 1, "default": "Literature/attachment"},
                "copyPdf": {"type": "boolean", "default": True},
                "overwritePolicy": {
                    "type": "string",
                    "enum": ["always", "never", "if-source-changed"],
                    "default": "if-source-changed",
                },
            },
        },
        "frontmatter": {
            "type": "object",
            "additionalProperties": False,
            "default": DEFAULT_CONFIG["frontmatter"],
            "properties": {
                "omitEmpty": {"type": "boolean", "default": True},
                "preserveUnknownFields": {"type": "boolean", "default": True},
                "fieldOrder": {
                    "type": "array",
                    "const": list(MANAGED_FIELD_ORDER),
                    "default": list(MANAGED_FIELD_ORDER),
                },
            },
        },
        "note": {
            "type": "object",
            "additionalProperties": False,
            "default": DEFAULT_CONFIG["note"],
            "properties": {
                "omitEmptySections": {"type": "boolean", "default": True},
                "preserveUserSections": {"type": "boolean", "default": True},
                "readingNotesHeading": {"type": "string", "minLength": 1, "default": "Reading Notes"},
                "embedPdf": {"type": "boolean", "default": True},
                "embedMineruMarkdown": {"type": "boolean", "default": True},
            },
        },
        "zotero": {
            "type": "object",
            "additionalProperties": False,
            "default": DEFAULT_CONFIG["zotero"],
            "properties": {
                "apiBase": {
                    "type": "string",
                    "minLength": 1,
                    "default": "http://127.0.0.1:23119/api",
                },
                "linkedAttachmentBaseDir": {"type": "string", "default": ""},
                "syncNotes": {"type": "boolean", "default": True},
                "syncAnnotations": {"type": "boolean", "default": True},
                "syncTags": {"type": "boolean", "default": True},
                "paginationSize": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 100},
            },
        },
        "bibtex": {
            "type": "object",
            "additionalProperties": False,
            "default": DEFAULT_CONFIG["bibtex"],
            "properties": {
                "enabled": {"type": "boolean", "default": True},
                "provider": {
                    "type": "string",
                    "enum": ["auto", "better-bibtex", "zotero", "builtin"],
                    "default": "auto",
                },
                "fallback": {"type": "string", "enum": ["builtin", "none"], "default": "builtin"},
            },
        },
        "mineru": {
            "type": "object",
            "additionalProperties": False,
            "default": DEFAULT_CONFIG["mineru"],
            "properties": {
                "enabled": {"type": "boolean", "default": True},
                "mode": {"type": "string", "enum": ["auto", "local", "api"], "default": "auto"},
                "markdownFolder": {
                    "type": "string",
                    "minLength": 1,
                    "default": "Literature/attachment/MinerU",
                },
                "imageFolder": {
                    "type": "string",
                    "minLength": 1,
                    "default": "Literature/attachment/MinerU/image",
                },
                "imageLinkStyle": {
                    "type": "string",
                    "enum": ["markdown-relative"],
                    "default": "markdown-relative",
                },
                "replacePreviousOutput": {"type": "boolean", "default": True},
                "maxConcurrentJobs": {"type": "integer", "minimum": 1, "maximum": 64, "default": 2},
            },
        },
        "analysis": {
            "type": "object",
            "additionalProperties": False,
            "default": DEFAULT_CONFIG["analysis"],
            "properties": {
                "folder": {
                    "type": "string",
                    "minLength": 1,
                    "default": "Literature/Analysis",
                },
                "base": {
                    "type": "string",
                    "minLength": 1,
                    "default": "Literature/Analysis/Analysis.base",
                },
                "fullReadsFolder": {
                    "type": "string",
                    "minLength": 1,
                    "default": "Literature/Analysis/full-reads",
                },
                "reviewsFolder": {
                    "type": "string",
                    "minLength": 1,
                    "default": "Literature/Analysis/reviews",
                },
                "passageQaFolder": {
                    "type": "string",
                    "minLength": 1,
                    "default": "Literature/Analysis/qa/passages",
                },
                "figureQaFolder": {
                    "type": "string",
                    "minLength": 1,
                    "default": "Literature/Analysis/qa/figures",
                },
                "conceptsFolder": {
                    "type": "string",
                    "minLength": 1,
                    "default": "Literature/Analysis/concepts",
                },
            },
        },
        "index": {
            "type": "object",
            "additionalProperties": False,
            "default": DEFAULT_CONFIG["index"],
            "properties": {
                "autoRebuild": {"type": "boolean", "default": True},
                "recentLimit": {"type": "integer", "minimum": 0, "maximum": 10000, "default": 20},
                "groupBy": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["year", "journal", "tags"]},
                    "uniqueItems": True,
                    "default": ["year", "journal", "tags"],
                },
            },
        },
        "base": {
            "type": "object",
            "additionalProperties": False,
            "default": DEFAULT_CONFIG["base"],
            "properties": {
                "autoRebuild": {"type": "boolean", "default": True},
                "name": {"type": "string", "minLength": 1, "default": "Literature Matrix"},
            },
        },
        "safety": {
            "type": "object",
            "additionalProperties": False,
            "default": DEFAULT_CONFIG["safety"],
            "properties": {
                "atomicWrites": {"type": "boolean", "default": True},
                "backupBeforeReplace": {"type": "boolean", "default": True},
                "retainBackups": {"type": "integer", "minimum": 0, "maximum": 10000, "default": 10},
                "defaultDryRunForMigration": {"type": "boolean", "default": True},
                "lockPerItem": {"type": "boolean", "default": True},
            },
        },
    },
}


def validate_config(config: Mapping[str, Any]) -> dict[str, Any]:
    """Strictly validate user config and return a normalized full config.

    Sections may omit values to inherit V2 defaults. Unknown fields, wrong
    types, unsafe paths, unsupported enum values, and unstable naming patterns
    are rejected rather than silently ignored.
    """

    if not isinstance(config, Mapping):
        raise ConfigurationError("configuration root must be a JSON object")
    raw = deepcopy(dict(config))
    _reject_unknown(raw, "root")
    if "schemaVersion" not in raw:
        raise ConfigurationError("missing required configuration field: schemaVersion")
    if type(raw["schemaVersion"]) is not int or raw["schemaVersion"] != SCHEMA_VERSION:
        raise ConfigurationError(f"schemaVersion must be exactly {SCHEMA_VERSION}")
    if "$schema" in raw:
        _expect_string(raw["$schema"], "$schema", non_empty=True)

    for section in _ALLOWED_KEYS:
        if section == "root" or section not in raw:
            continue
        if not isinstance(raw[section], Mapping):
            raise ConfigurationError(f"{section} must be a JSON object")
        raw[section] = dict(raw[section])
        _reject_unknown(raw[section], section)

    result = _deep_merge(DEFAULT_CONFIG, raw)
    _validate_paths(result)
    _validate_identity_and_naming(result)
    _validate_frontmatter(result)
    _validate_scalar_sections(result)
    return result


def _validate_paths(config: dict[str, Any]) -> None:
    path_fields = (
        ("literature", "root"),
        ("literature", "index"),
        ("literature", "base"),
        ("literature", "wikiFolder"),
        ("attachments", "pdfFolder"),
        ("mineru", "markdownFolder"),
        ("mineru", "imageFolder"),
        ("analysis", "folder"),
        ("analysis", "base"),
        ("analysis", "fullReadsFolder"),
        ("analysis", "reviewsFolder"),
        ("analysis", "passageQaFolder"),
        ("analysis", "figureQaFolder"),
        ("analysis", "conceptsFolder"),
    )
    for section, name in path_fields:
        value = _expect_string(config[section][name], f"{section}.{name}", non_empty=True)
        try:
            config[section][name] = normalize_vault_relative(value)
        except PathValidationError as exc:
            raise ConfigurationError(f"invalid {section}.{name}: {exc}") from exc
    if config["literature"]["index"] == config["literature"]["base"]:
        raise ConfigurationError("literature.index and literature.base must be different files")
    analysis = config["analysis"]
    if not analysis["base"].lower().endswith(".base"):
        raise ConfigurationError("analysis.base must be a .base file")
    for name in (
        "base",
        "fullReadsFolder",
        "reviewsFolder",
        "passageQaFolder",
        "figureQaFolder",
        "conceptsFolder",
    ):
        if not _is_inside(analysis[name], analysis["folder"]):
            raise ConfigurationError(f"analysis.{name} must stay inside analysis.folder")
    folders = [
        analysis["fullReadsFolder"],
        analysis["reviewsFolder"],
        analysis["passageQaFolder"],
        analysis["figureQaFolder"],
        analysis["conceptsFolder"],
    ]
    if len({value.casefold() for value in folders}) != len(folders):
        raise ConfigurationError("analysis subfolders must be distinct")


def _validate_identity_and_naming(config: dict[str, Any]) -> None:
    strategy = _expect_string(config["identity"]["strategy"], "identity.strategy", non_empty=True)
    if strategy != "zoteroKey":
        raise ConfigurationError("identity.strategy must be 'zoteroKey' in V2")

    requirements = {
        "note": ("zoteroKey",),
        "pdf": ("zoteroKey",),
        "mineruMarkdown": ("zoteroKey",),
        "mineruImage": ("zoteroKey", "index", "ext"),
    }
    rendered: dict[str, str] = {}
    for name, required in requirements.items():
        pattern = _expect_string(config["naming"][name], f"naming.{name}", non_empty=True)
        try:
            validate_naming_pattern(pattern, required_fields=required)
            rendered[name] = render_filename(
                pattern,
                zotero_key="ABCD1234",
                first_author="Smith",
                year=2024,
                short_title="Example",
                index=1,
                ext="png",
            )
        except IdentityError as exc:
            raise ConfigurationError(f"invalid naming.{name}: {exc}") from exc
    expected_suffixes = {"note": ".md", "pdf": ".pdf", "mineruMarkdown": ".md"}
    for name, suffix in expected_suffixes.items():
        if not rendered[name].lower().endswith(suffix):
            raise ConfigurationError(f"naming.{name} must render a {suffix} filename")
    if not rendered["mineruImage"].lower().endswith(".png"):
        raise ConfigurationError("naming.mineruImage must retain the {ext} extension")


def _validate_frontmatter(config: dict[str, Any]) -> None:
    frontmatter = config["frontmatter"]
    _expect_bool(frontmatter["omitEmpty"], "frontmatter.omitEmpty")
    _expect_bool(frontmatter["preserveUnknownFields"], "frontmatter.preserveUnknownFields")
    order = frontmatter["fieldOrder"]
    if not isinstance(order, list) or any(not isinstance(name, str) for name in order):
        raise ConfigurationError("frontmatter.fieldOrder must be an array of strings")
    if order != list(MANAGED_FIELD_ORDER):
        raise ConfigurationError("frontmatter.fieldOrder must match the fixed V2 managed field order")


def _validate_scalar_sections(config: dict[str, Any]) -> None:
    attachments = config["attachments"]
    _expect_bool(attachments["copyPdf"], "attachments.copyPdf")
    _expect_enum(
        attachments["overwritePolicy"],
        "attachments.overwritePolicy",
        {"always", "never", "if-source-changed"},
    )

    note = config["note"]
    for name in ("omitEmptySections", "preserveUserSections", "embedPdf", "embedMineruMarkdown"):
        _expect_bool(note[name], f"note.{name}")
    _expect_string(note["readingNotesHeading"], "note.readingNotesHeading", non_empty=True)

    zotero = config["zotero"]
    _expect_string(zotero["apiBase"], "zotero.apiBase", non_empty=True)
    _expect_string(zotero["linkedAttachmentBaseDir"], "zotero.linkedAttachmentBaseDir")
    for name in ("syncNotes", "syncAnnotations", "syncTags"):
        _expect_bool(zotero[name], f"zotero.{name}")
    _expect_int(zotero["paginationSize"], "zotero.paginationSize", minimum=1, maximum=1000)

    bibtex = config["bibtex"]
    _expect_bool(bibtex["enabled"], "bibtex.enabled")
    _expect_enum(bibtex["provider"], "bibtex.provider", {"auto", "better-bibtex", "zotero", "builtin"})
    _expect_enum(bibtex["fallback"], "bibtex.fallback", {"builtin", "none"})

    mineru = config["mineru"]
    _expect_bool(mineru["enabled"], "mineru.enabled")
    _expect_bool(mineru["replacePreviousOutput"], "mineru.replacePreviousOutput")
    _expect_enum(mineru["mode"], "mineru.mode", {"auto", "local", "api"})
    _expect_enum(mineru["imageLinkStyle"], "mineru.imageLinkStyle", {"markdown-relative"})
    _expect_int(mineru["maxConcurrentJobs"], "mineru.maxConcurrentJobs", minimum=1, maximum=64)

    index = config["index"]
    _expect_bool(index["autoRebuild"], "index.autoRebuild")
    _expect_int(index["recentLimit"], "index.recentLimit", minimum=0, maximum=10_000)
    groups = index["groupBy"]
    if not isinstance(groups, list) or any(group not in {"year", "journal", "tags"} for group in groups):
        raise ConfigurationError("index.groupBy may contain only 'year', 'journal', and 'tags'")
    if len(groups) != len(set(groups)):
        raise ConfigurationError("index.groupBy cannot contain duplicates")

    base = config["base"]
    _expect_bool(base["autoRebuild"], "base.autoRebuild")
    _expect_string(base["name"], "base.name", non_empty=True)

    safety = config["safety"]
    for name in (
        "atomicWrites",
        "backupBeforeReplace",
        "defaultDryRunForMigration",
        "lockPerItem",
    ):
        _expect_bool(safety[name], f"safety.{name}")
    _expect_int(safety["retainBackups"], "safety.retainBackups", minimum=0, maximum=10_000)


def _is_inside(path: str, folder: str) -> bool:
    return path == folder or path.startswith(f"{folder}/")


def _reject_unknown(mapping: Mapping[str, Any], section: str) -> None:
    unknown = set(mapping) - _ALLOWED_KEYS[section]
    if unknown:
        prefix = "" if section == "root" else f"{section}."
        names = ", ".join(f"{prefix}{name}" for name in sorted(unknown))
        raise ConfigurationError(f"unknown configuration field(s): {names}")


def _deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(base))
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(result.get(key), Mapping):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def _expect_string(value: Any, name: str, *, non_empty: bool = False) -> str:
    if not isinstance(value, str) or (non_empty and not value.strip()):
        qualifier = "non-empty " if non_empty else ""
        raise ConfigurationError(f"{name} must be a {qualifier}string")
    return value


def _expect_bool(value: Any, name: str) -> bool:
    if type(value) is not bool:
        raise ConfigurationError(f"{name} must be a boolean")
    return value


def _expect_int(value: Any, name: str, *, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ConfigurationError(f"{name} must be an integer from {minimum} to {maximum}")
    return value


def _expect_enum(value: Any, name: str, allowed: set[str]) -> str:
    if not isinstance(value, str) or value not in allowed:
        choices = ", ".join(sorted(allowed))
        raise ConfigurationError(f"{name} must be one of: {choices}")
    return value
