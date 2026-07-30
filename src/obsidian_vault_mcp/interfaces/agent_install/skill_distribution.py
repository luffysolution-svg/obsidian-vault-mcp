"""Safely distribute canonical Agent Skills into project-local client folders."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from ...application.skill_service import (
    SKILL_NAMES,
    SkillResourceService,
    extract_managed_block,
    upgrade_managed_skill,
)
from .common import (
    AgentInstallError,
    ConfigurationValidationError,
    SkillInstallResult,
    atomic_write_bytes,
    atomic_write_text,
    backup_config,
)

SKILL_MANIFEST_NAME = ".obsidian-vault-mcp-skills.json"
SKILL_MANIFEST_SCHEMA_VERSION = 2
_SUPPORTED_MANIFEST_SCHEMAS = {1, SKILL_MANIFEST_SCHEMA_VERSION}
_SKILL_NAME_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_LEGACY_SKILL_NAMES = frozenset(
    {
        "analyze-figures",
        "compare-papers",
        "evidence-based-qa",
        "literature-review",
        "structured-paper-note",
        "theory-note-synthesis",
        "topic-note-synthesis",
        "uncertainty-audit",
        "verify-paper-claims",
    }
)


@dataclass(frozen=True)
class _PlannedFile:
    path: Path
    content: str
    existed: bool
    changed: bool


@dataclass(frozen=True)
class _PlannedSkill:
    name: str
    path: Path
    files: tuple[_PlannedFile, ...]
    action: str
    version: str
    managed_hash: str

    @property
    def changed(self) -> bool:
        return any(file.changed for file in self.files)


@dataclass(frozen=True)
class _PlannedRemoval:
    name: str
    path: Path
    version: str
    managed_hash: str


@dataclass(frozen=True)
class SkillDistributionPlan:
    client: str
    project_root: Path
    skill_directory: Path
    manifest_path: Path
    skills: tuple[_PlannedSkill, ...]
    removals: tuple[_PlannedRemoval, ...]
    removed_skills: tuple[_PlannedRemoval, ...]
    manifest_content: str
    manifest_existed: bool
    manifest_changed: bool

    @property
    def changed(self) -> bool:
        return self.manifest_changed or bool(self.removals) or any(skill.changed for skill in self.skills)

    def results(self, backups: Mapping[str, Path] | None = None) -> tuple[SkillInstallResult, ...]:
        backup_paths = backups or {}
        current = tuple(
            SkillInstallResult(
                name=skill.name,
                path=skill.path,
                changed=skill.changed,
                action=skill.action,
                version=skill.version,
                managed_hash=skill.managed_hash,
                backup_path=backup_paths.get(skill.name),
            )
            for skill in self.skills
        )
        removed = tuple(
            SkillInstallResult(
                name=skill.name,
                path=skill.path,
                changed=True,
                action="remove",
                version=skill.version,
                managed_hash=skill.managed_hash,
                backup_path=backup_paths.get(skill.name),
            )
            for skill in self.removed_skills
        )
        return (*current, *removed)


@dataclass(frozen=True)
class _AppliedFile:
    path: Path
    existed: bool
    backup_path: Path | None


@dataclass(frozen=True)
class SkillDistributionReceipt:
    plan: SkillDistributionPlan
    applied: tuple[_AppliedFile, ...]
    results: tuple[SkillInstallResult, ...]
    manifest_backup_path: Path | None


def plan_skill_distribution(
    *,
    client: str,
    project_root: str | os.PathLike[str],
    skill_directory: str | os.PathLike[str],
) -> SkillDistributionPlan:
    """Validate and prepare a deterministic all-or-nothing Skill update."""

    root = Path(project_root).expanduser().resolve()
    directory = _safe_project_child(root, skill_directory)
    manifest_path = directory / SKILL_MANIFEST_NAME
    _validate_destination(root, directory, expect_directory=True)
    _validate_destination(root, manifest_path, expect_directory=False)
    manifest, manifest_text = _load_manifest(manifest_path, client)
    tracked = manifest.get("skills", {})
    if not isinstance(tracked, Mapping):
        raise ConfigurationValidationError(f"Skill manifest skills must be an object: {manifest_path}")

    service = SkillResourceService()
    official_metadata = {item["name"]: item for item in service.list()}
    planned: list[_PlannedSkill] = []
    removals: list[_PlannedRemoval] = []
    next_tracked: dict[str, dict[str, Any]] = {}

    for name in SKILL_NAMES:
        metadata = official_metadata[name]
        official_files = service.files(name)
        official_hash = str(metadata["managedHash"])
        version = str(metadata["version"])
        tracked_entry = tracked.get(name)
        tracked_references = _tracked_reference_hashes(tracked_entry, name, manifest_path) if tracked_entry is not None else {}
        skill_files: list[_PlannedFile] = []

        skill_target = directory / name / "SKILL.md"
        _validate_destination(root, skill_target, expect_directory=False)
        official_skill = official_files["SKILL.md"]
        skill_existed = skill_target.exists()
        if skill_existed:
            existing_skill = _read_text(skill_target, "Skill")
            expected_hash = _tracked_hash(tracked_entry, name, manifest_path) if tracked_entry is not None else ""
            if not expected_hash:
                try:
                    current_hash = extract_managed_block(existing_skill).sha256
                except ValueError as exc:
                    raise ConfigurationValidationError(f"Existing Skill is not safely upgradeable: {skill_target}: {exc}") from exc
                if current_hash != official_hash:
                    raise ConfigurationValidationError(
                        f"Existing Skill is not tracked by {manifest_path}; refusing to overwrite its managed block: {skill_target}"
                    )
                expected_hash = official_hash
            upgraded = upgrade_managed_skill(existing_skill, official_skill, expected_existing_hash=expected_hash)
            if not upgraded["ok"]:
                warning = upgraded["warnings"][0]
                raise ConfigurationValidationError(f"Cannot upgrade {skill_target}: {warning['code']}: {warning['message']}")
            skill_content = str(upgraded["content"])
            skill_changed = skill_content != existing_skill
        else:
            skill_content = official_skill
            skill_changed = True
        skill_files.append(_PlannedFile(skill_target, skill_content, skill_existed, skill_changed))

        for relative_path, content in official_files.items():
            if relative_path == "SKILL.md":
                continue
            target = _resource_target(root, directory / name, relative_path)
            existed = target.exists()
            if existed:
                existing = _read_text(target, "Skill reference")
                expected_hash = tracked_references.get(relative_path)
                current_hash = _sha256(existing)
                official_reference_hash = _sha256(content)
                if expected_hash is not None and current_hash != expected_hash:
                    raise ConfigurationValidationError(f"Cannot replace modified tracked reference {target}")
                if expected_hash is None and current_hash != official_reference_hash:
                    raise ConfigurationValidationError(
                        f"Existing Skill reference is not tracked by {manifest_path}; refusing to overwrite it: {target}"
                    )
                changed = existing != content
            else:
                changed = True
            skill_files.append(_PlannedFile(target, content, existed, changed))

        for relative_path, digest in tracked_references.items():
            if relative_path in official_files:
                continue
            target = _resource_target(root, directory / name, relative_path)
            if not target.exists():
                continue
            existing = _read_text(target, "Skill reference")
            if _sha256(existing) != digest:
                raise ConfigurationValidationError(f"Cannot remove modified tracked reference {target}")
            removals.append(_PlannedRemoval(name, target, version, official_hash))

        changed = any(file.changed for file in skill_files) or any(removal.name == name for removal in removals)
        action = "install" if not skill_existed else ("upgrade" if changed else "unchanged")
        planned.append(
            _PlannedSkill(
                name=name,
                path=skill_target,
                files=tuple(skill_files),
                action=action,
                version=version,
                managed_hash=official_hash,
            )
        )
        next_tracked[name] = {
            "version": version,
            "managedHash": official_hash,
            "files": {
                relative_path: _sha256(content)
                for relative_path, content in official_files.items()
                if relative_path != "SKILL.md"
            },
        }

    removed_skills: list[_PlannedRemoval] = []
    for name in sorted((set(tracked) & _LEGACY_SKILL_NAMES) - set(SKILL_NAMES)):
        _validate_skill_name(name, manifest_path)
        tracked_entry = tracked[name]
        version = _tracked_version(tracked_entry)
        managed_hash = _tracked_hash(tracked_entry, name, manifest_path)
        skill_target = directory / name / "SKILL.md"
        _validate_destination(root, skill_target, expect_directory=False)
        if skill_target.exists():
            existing = _read_text(skill_target, "legacy Skill")
            try:
                current_hash = extract_managed_block(existing).sha256
            except ValueError as exc:
                raise ConfigurationValidationError(f"Tracked legacy Skill is not safely removable: {skill_target}: {exc}") from exc
            if current_hash != managed_hash:
                raise ConfigurationValidationError(f"Tracked legacy Skill has a modified managed block: {skill_target}")
            removal = _PlannedRemoval(name, skill_target, version, managed_hash)
            removals.append(removal)
            removed_skills.append(removal)
        else:
            removed_skills.append(_PlannedRemoval(name, skill_target, version, managed_hash))

        for relative_path, digest in _tracked_reference_hashes(tracked_entry, name, manifest_path).items():
            target = _resource_target(root, directory / name, relative_path)
            if not target.exists():
                continue
            existing = _read_text(target, "legacy Skill reference")
            if _sha256(existing) != digest:
                raise ConfigurationValidationError(f"Tracked legacy Skill reference was modified: {target}")
            removals.append(_PlannedRemoval(name, target, version, managed_hash))

    next_manifest = dict(manifest)
    next_manifest.update(
        {
            "schemaVersion": SKILL_MANIFEST_SCHEMA_VERSION,
            "client": client,
            "skills": {name: next_tracked[name] for name in sorted(next_tracked)},
        }
    )
    next_manifest_text = json.dumps(next_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    return SkillDistributionPlan(
        client=client,
        project_root=root,
        skill_directory=directory,
        manifest_path=manifest_path,
        skills=tuple(planned),
        removals=tuple(removals),
        removed_skills=tuple(removed_skills),
        manifest_content=next_manifest_text,
        manifest_existed=manifest_path.exists(),
        manifest_changed=not manifest_path.exists() or manifest_text != next_manifest_text,
    )


def apply_skill_distribution(plan: SkillDistributionPlan) -> SkillDistributionReceipt:
    """Atomically replace planned files and restore every applied file on failure."""

    applied: list[_AppliedFile] = []
    backups: dict[str, Path] = {}
    manifest_backup: Path | None = None
    try:
        for skill in plan.skills:
            for file in skill.files:
                if not file.changed:
                    continue
                backup = backup_config(file.path) if file.existed else None
                if backup is not None and file.path == skill.path:
                    backups[skill.name] = backup
                applied.append(_AppliedFile(file.path, file.existed, backup))
                atomic_write_text(file.path, file.content)

        for removal in plan.removals:
            backup = backup_config(removal.path)
            if removal.path.name == "SKILL.md":
                backups[removal.name] = backup
            applied.append(_AppliedFile(removal.path, True, backup))
            removal.path.unlink()

        if plan.manifest_changed:
            manifest_backup = backup_config(plan.manifest_path) if plan.manifest_existed else None
            applied.append(_AppliedFile(plan.manifest_path, plan.manifest_existed, manifest_backup))
            atomic_write_text(plan.manifest_path, plan.manifest_content)
    except Exception as exc:
        try:
            _rollback_applied(applied, plan)
        except Exception as rollback_exc:
            raise AgentInstallError(f"Skill write failed and rollback also failed: {rollback_exc}") from exc
        raise AgentInstallError(f"Skill write failed; installed files were restored: {exc}") from exc
    return SkillDistributionReceipt(
        plan=plan,
        applied=tuple(applied),
        results=plan.results(backups),
        manifest_backup_path=manifest_backup,
    )


def rollback_skill_distribution(receipt: SkillDistributionReceipt) -> None:
    """Restore a successfully applied Skill set after a later installer failure."""

    _rollback_applied(list(receipt.applied), receipt.plan)


def _load_manifest(path: Path, client: str) -> tuple[dict[str, Any], str]:
    if not path.exists():
        return {}, ""
    try:
        text = path.read_text(encoding="utf-8")
        value = json.loads(text)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ConfigurationValidationError(f"Invalid Skill manifest at {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ConfigurationValidationError(f"Skill manifest root must be an object: {path}")
    if value.get("schemaVersion") not in _SUPPORTED_MANIFEST_SCHEMAS:
        raise ConfigurationValidationError(f"Unsupported Skill manifest schema at {path}")
    if value.get("client") != client:
        raise ConfigurationValidationError(f"Skill manifest client mismatch at {path}")
    return value, text


def _tracked_hash(value: Any, name: str, manifest_path: Path) -> str:
    if not isinstance(value, Mapping):
        raise ConfigurationValidationError(f"Invalid tracked Skill entry for {name}: {manifest_path}")
    digest = value.get("managedHash")
    if not _is_sha256(digest):
        raise ConfigurationValidationError(f"Invalid managed hash for {name}: {manifest_path}")
    return str(digest)


def _tracked_reference_hashes(value: Any, name: str, manifest_path: Path) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise ConfigurationValidationError(f"Invalid tracked Skill entry for {name}: {manifest_path}")
    files = value.get("files", {})
    if not isinstance(files, Mapping):
        raise ConfigurationValidationError(f"Invalid tracked Skill files for {name}: {manifest_path}")
    result: dict[str, str] = {}
    for relative_path, digest in files.items():
        if not isinstance(relative_path, str):
            raise ConfigurationValidationError(f"Invalid tracked Skill file path for {name}: {manifest_path}")
        _validate_reference_path(relative_path)
        if not _is_sha256(digest):
            raise ConfigurationValidationError(f"Invalid tracked Skill file hash for {name}/{relative_path}: {manifest_path}")
        result[relative_path] = str(digest)
    return result


def _tracked_version(value: Any) -> str:
    if isinstance(value, Mapping) and isinstance(value.get("version"), str):
        return str(value["version"])
    return ""


def _resource_target(project_root: Path, skill_root: Path, relative_path: str) -> Path:
    _validate_reference_path(relative_path)
    target = skill_root.joinpath(*PurePosixPath(relative_path).parts)
    _validate_destination(project_root, target, expect_directory=False)
    return target


def _validate_reference_path(relative_path: str) -> None:
    path = PurePosixPath(relative_path)
    if path.is_absolute() or ".." in path.parts or len(path.parts) < 2 or path.parts[0] != "references" or path.suffix != ".md":
        raise ConfigurationValidationError(f"Invalid managed Skill reference path: {relative_path}")


def _validate_skill_name(name: Any, manifest_path: Path) -> None:
    if not isinstance(name, str) or _SKILL_NAME_PATTERN.fullmatch(name) is None:
        raise ConfigurationValidationError(f"Invalid tracked Skill name in {manifest_path}: {name!r}")


def _read_text(path: Path, label: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ConfigurationValidationError(f"Cannot read {label} {path}: {exc}") from exc


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _safe_project_child(project_root: Path, value: str | os.PathLike[str]) -> Path:
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = project_root / candidate
    candidate = Path(os.path.abspath(candidate))
    try:
        candidate.relative_to(project_root)
    except ValueError as exc:
        raise ConfigurationValidationError(f"Skill directory must stay inside the project: {candidate}") from exc
    return candidate


def _validate_destination(project_root: Path, path: Path, *, expect_directory: bool) -> None:
    try:
        relative = path.relative_to(project_root)
    except ValueError as exc:
        raise ConfigurationValidationError(f"Skill path must stay inside the project: {path}") from exc
    current = project_root
    for index, part in enumerate(relative.parts):
        current /= part
        if not current.exists() and not current.is_symlink():
            continue
        if _is_link_or_reparse(current):
            raise ConfigurationValidationError(f"Skill installation refuses linked or reparse paths: {current}")
        is_last = index == len(relative.parts) - 1
        if not is_last and not current.is_dir():
            raise ConfigurationValidationError(f"Skill parent path is not a directory: {current}")
        if is_last and expect_directory and not current.is_dir():
            raise ConfigurationValidationError(f"Skill directory path is not a directory: {current}")
        if is_last and not expect_directory and not current.is_file():
            raise ConfigurationValidationError(f"Skill destination is not a file: {current}")


def _is_link_or_reparse(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _rollback_applied(applied: list[_AppliedFile], plan: SkillDistributionPlan) -> None:
    errors: list[str] = []
    for item in reversed(applied):
        try:
            if item.existed:
                if item.backup_path is None or not item.backup_path.is_file():
                    raise RuntimeError(f"missing backup for {item.path}")
                atomic_write_bytes(item.path, item.backup_path.read_bytes())
            else:
                item.path.unlink(missing_ok=True)
                _remove_empty_parents(item.path.parent, stop=plan.project_root)
        except Exception as exc:
            errors.append(f"{item.path}: {exc}")
    if errors:
        raise AgentInstallError("; ".join(errors))


def _remove_empty_parents(path: Path, *, stop: Path) -> None:
    current = path
    while current != stop:
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent
