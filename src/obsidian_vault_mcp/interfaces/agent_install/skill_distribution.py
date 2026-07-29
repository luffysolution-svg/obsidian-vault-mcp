"""Safely distribute canonical Agent Skills into project-local client folders."""

from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
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
SKILL_MANIFEST_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class _PlannedSkill:
    name: str
    path: Path
    content: str
    existed: bool
    changed: bool
    action: str
    version: str
    managed_hash: str


@dataclass(frozen=True)
class SkillDistributionPlan:
    client: str
    project_root: Path
    skill_directory: Path
    manifest_path: Path
    skills: tuple[_PlannedSkill, ...]
    manifest_content: str
    manifest_existed: bool
    manifest_changed: bool

    @property
    def changed(self) -> bool:
        return self.manifest_changed or any(skill.changed for skill in self.skills)

    def results(self, backups: Mapping[str, Path] | None = None) -> tuple[SkillInstallResult, ...]:
        backup_paths = backups or {}
        return tuple(
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
    next_tracked = dict(tracked)
    for name in SKILL_NAMES:
        official = service.read(name)
        metadata = official_metadata[name]
        official_hash = str(metadata["managedHash"])
        version = str(metadata["version"])
        target = directory / name / "SKILL.md"
        _validate_destination(root, target, expect_directory=False)
        existed = target.exists()
        if existed:
            try:
                existing = target.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                raise ConfigurationValidationError(f"Cannot read existing Skill {target}: {exc}") from exc
            tracked_entry = tracked.get(name)
            expected_hash = _tracked_hash(tracked_entry, name, manifest_path) if tracked_entry is not None else ""
            if not expected_hash:
                try:
                    current_hash = extract_managed_block(existing).sha256
                except ValueError as exc:
                    raise ConfigurationValidationError(f"Existing Skill is not safely upgradeable: {target}: {exc}") from exc
                if current_hash != official_hash:
                    raise ConfigurationValidationError(
                        f"Existing Skill is not tracked by {manifest_path}; refusing to overwrite its managed block: {target}"
                    )
                expected_hash = official_hash
            upgraded = upgrade_managed_skill(existing, official, expected_existing_hash=expected_hash)
            if not upgraded["ok"]:
                warning = upgraded["warnings"][0]
                raise ConfigurationValidationError(f"Cannot upgrade {target}: {warning['code']}: {warning['message']}")
            content = str(upgraded["content"])
            changed = content != existing
            action = "upgrade" if changed else "unchanged"
        else:
            content = official
            changed = True
            action = "install"
        planned.append(
            _PlannedSkill(
                name=name,
                path=target,
                content=content,
                existed=existed,
                changed=changed,
                action=action,
                version=version,
                managed_hash=official_hash,
            )
        )
        next_tracked[name] = {"version": version, "managedHash": official_hash}

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
            if not skill.changed:
                continue
            backup = backup_config(skill.path) if skill.existed else None
            if backup is not None:
                backups[skill.name] = backup
            applied.append(_AppliedFile(skill.path, skill.existed, backup))
            atomic_write_text(skill.path, skill.content)
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
    if value.get("schemaVersion") != SKILL_MANIFEST_SCHEMA_VERSION:
        raise ConfigurationValidationError(f"Unsupported Skill manifest schema at {path}")
    if value.get("client") != client:
        raise ConfigurationValidationError(f"Skill manifest client mismatch at {path}")
    return value, text


def _tracked_hash(value: Any, name: str, manifest_path: Path) -> str:
    if not isinstance(value, Mapping):
        raise ConfigurationValidationError(f"Invalid tracked Skill entry for {name}: {manifest_path}")
    digest = value.get("managedHash")
    if not isinstance(digest, str) or len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise ConfigurationValidationError(f"Invalid managed hash for {name}: {manifest_path}")
    return digest


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
