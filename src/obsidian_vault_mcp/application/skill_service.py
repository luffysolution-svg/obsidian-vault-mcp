"""Read and safely upgrade the canonical model-independent Agent Skills."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

from ..domain.frontmatter import parse_frontmatter

MANAGED_START = "<!-- ovm:skill-managed:start -->"
MANAGED_END = "<!-- ovm:skill-managed:end -->"
SKILL_RESOURCE_VERSION = "1.0.0"
SKILL_NAMES = (
    "paper-qa",
    "full-read",
    "passage-qa",
    "figure-qa",
    "compare-papers",
    "literature-review",
    "concept-learning",
)


@dataclass(frozen=True)
class ManagedSkillBlock:
    before: str
    content: str
    after: str

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()


def extract_managed_block(text: str) -> ManagedSkillBlock:
    """Extract exactly one ordered managed block from a Skill document."""

    if not isinstance(text, str):
        raise TypeError("Skill content must be text")
    start_count = text.count(MANAGED_START)
    end_count = text.count(MANAGED_END)
    if start_count != 1 or end_count != 1:
        raise ValueError("Skill must contain exactly one managed start marker and one managed end marker")
    start = text.index(MANAGED_START)
    end = text.index(MANAGED_END)
    if end < start:
        raise ValueError("Skill managed markers are out of order")
    content_start = start + len(MANAGED_START)
    return ManagedSkillBlock(text[:start], text[content_start:end], text[end + len(MANAGED_END) :])


def upgrade_managed_skill(
    existing: str,
    official: str,
    *,
    expected_existing_hash: str = "",
) -> dict[str, Any]:
    """Replace only the official block while preserving all user text around it."""

    try:
        current = extract_managed_block(existing)
    except ValueError as exc:
        return {"ok": False, "changed": False, "content": existing, "warnings": [{"code": "legacy-skill-format", "message": str(exc)}]}
    replacement = extract_managed_block(official)
    if expected_existing_hash and current.sha256 != expected_existing_hash:
        return {
            "ok": False,
            "changed": False,
            "content": existing,
            "managedHash": current.sha256,
            "warnings": [{"code": "managed-block-modified", "message": "The installed managed block differs from the expected version."}],
        }
    content = f"{current.before}{MANAGED_START}{replacement.content}{MANAGED_END}{current.after}"
    return {
        "ok": True,
        "changed": content != existing,
        "content": content,
        "managedHash": replacement.sha256,
        "version": SKILL_RESOURCE_VERSION,
        "warnings": [],
    }


class SkillResourceService:
    """Expose the one canonical Skill set without client-specific mirrors."""

    package = "obsidian_vault_mcp.resources.agent_marketplace"
    skill_root = "plugins/obsidian-literature/skills"

    def list(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for name in SKILL_NAMES:
            text = self.read(name)
            document = parse_frontmatter(text)
            block = extract_managed_block(text)
            result.append(
                {
                    "name": name,
                    "description": str(document.fields.get("description") or ""),
                    "version": SKILL_RESOURCE_VERSION,
                    "managedHash": block.sha256,
                    "files": {
                        relative_path: hashlib.sha256(content.encode("utf-8")).hexdigest()
                        for relative_path, content in self.files(name).items()
                    },
                }
            )
        return result

    def read(self, name: str) -> str:
        return self.files(name)["SKILL.md"]

    def files(self, name: str) -> dict[str, str]:
        """Return every canonical Skill file with deterministic POSIX-relative paths."""

        if name not in SKILL_NAMES:
            raise ValueError(f"unknown Agent Skill: {name}")
        root = resources.files(self.package).joinpath(self.skill_root, name)
        if isinstance(root, Path):
            root = _extended_length_path(root)
        discovered: dict[str, str] = {}

        def visit(directory: Any, prefix: tuple[str, ...] = ()) -> None:
            for child in sorted(directory.iterdir(), key=lambda item: item.name):
                if child.name == "__pycache__":
                    continue
                relative_parts = (*prefix, child.name)
                if child.is_dir():
                    visit(child, relative_parts)
                elif child.is_file():
                    relative_path = "/".join(relative_parts)
                    if relative_path != "SKILL.md" and not (
                        relative_path.startswith("references/") and relative_path.endswith(".md")
                    ):
                        raise ValueError(f"unsupported Agent Skill resource: {name}/{relative_path}")
                    discovered[relative_path] = child.read_text(encoding="utf-8")

        visit(root)
        if "SKILL.md" not in discovered:
            raise ValueError(f"Agent Skill is missing SKILL.md: {name}")
        return discovered


def _extended_length_path(path: Path) -> Path:
    """Use the Windows extended path namespace for deeply installed resources."""

    if os.name != "nt":
        return path
    absolute = os.path.abspath(path)
    if absolute.startswith("\\\\?\\"):
        return Path(absolute)
    if absolute.startswith("\\\\"):
        return Path(f"\\\\?\\UNC\\{absolute[2:]}")
    return Path(f"\\\\?\\{absolute}")
