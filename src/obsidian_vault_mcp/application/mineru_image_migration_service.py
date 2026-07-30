"""Safe migration of legacy flat MinerU images into per-paper folders."""

from __future__ import annotations

import hashlib
import os
import posixpath
import re
import stat
from collections.abc import Mapping
from contextlib import ExitStack
from dataclasses import dataclass, field
from html import unescape
from pathlib import Path, PurePosixPath
from typing import Any

from ..adapters.mineru.normalizer import parse_image_references, resolve_image_reference
from ..adapters.vault.filesystem import VaultFilesystem
from ..adapters.vault.lock import ItemLock
from ..config.loader import load_config
from ..domain.frontmatter import parse_frontmatter
from ..domain.identity import validate_zotero_key
from ..domain.paths import normalize_vault_relative
from .transaction_service import TransactionService

_IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp"})
_LEGACY_IMAGE_RE = re.compile(
    r"^(?P<key>[A-Za-z0-9][A-Za-z0-9_-]{0,63})-fig(?P<index>[0-9]{2,})"
    r"(?P<extension>\.(?:png|jpe?g|gif|webp))$",
    re.IGNORECASE,
)
_HTML_IMAGE_SOURCE_RE = re.compile(
    r"""<img\b[^>]*\bsrc\s*=\s*(?:"(?P<double>[^"]*)"|'(?P<single>[^']*)'|(?P<bare>[^\s"'=<>`]+))""",
    re.IGNORECASE | re.DOTALL,
)


@dataclass(frozen=True)
class _MarkdownRecord:
    key: str
    relative: str
    path: Path
    text: str
    sha256: str


@dataclass(frozen=True)
class _LegacyImage:
    key: str
    filename: str
    relative: str
    path: Path
    sha256: str


@dataclass
class _PaperPlan:
    key: str
    markdown: _MarkdownRecord | None = None
    images: list[_LegacyImage] = field(default_factory=list)
    replacements: list[tuple[int, int, str]] = field(default_factory=list)
    existing_copies: set[str] = field(default_factory=set)
    blockers: set[str] = field(default_factory=set)


class MinerUImageMigrationService:
    """Copy owned flat images and atomically rewrite their Markdown references."""

    def __init__(
        self,
        vault_path: str | os.PathLike[str],
        config: Mapping[str, Any] | None = None,
        *,
        transaction_service: TransactionService | None = None,
    ) -> None:
        self.vault_path = Path(vault_path).expanduser().resolve()
        if not self.vault_path.is_dir():
            raise NotADirectoryError(f"Vault root is not a directory: {self.vault_path}")
        self.config = (
            dict(config)
            if config is not None
            else load_config(self.vault_path, require_exists=False)
        )
        mineru = self.config.get("mineru")
        section = mineru if isinstance(mineru, Mapping) else {}
        self.markdown_root_relative = normalize_vault_relative(
            str(section.get("markdownFolder", "Literature/attachment/MinerU"))
        )
        self.image_root_relative = normalize_vault_relative(
            str(
                section.get(
                    "imageFolder",
                    "Literature/attachment/MinerU/image",
                )
            )
        )
        self.markdown_root = self._lexical(self.markdown_root_relative)
        self.image_root = self._lexical(self.image_root_relative)
        self.fs = VaultFilesystem(self.vault_path)
        self.transactions = transaction_service or TransactionService(self.vault_path)

    def migrate(
        self,
        *,
        dry_run: bool = True,
        apply: bool = False,
        transaction_id: str | None = None,
        conflict_policy: str = "preserve-user",
        cleanup_legacy: bool = False,
        confirm_vault_offline: bool = False,
    ) -> dict[str, Any]:
        """Preview by default and apply all safe image changes in one transaction.

        Legacy flat images are preserved by default so an uncoordinated writer cannot
        create a broken reference in the final instant before commit. Destructive
        cleanup is available only after the caller explicitly confirms that every
        process capable of writing the Vault is offline.
        """

        if conflict_policy != "preserve-user":
            raise ValueError(
                "MinerU image migration supports only conflict_policy preserve-user"
            )
        execute = bool(apply and not dry_run)
        if execute and cleanup_legacy and not confirm_vault_offline:
            raise ValueError(
                "cleanup_legacy requires confirm_vault_offline=True after all Vault "
                "writers have been stopped"
            )
        skipped: list[dict[str, str]] = []
        missing: list[dict[str, str]] = []
        plans: dict[str, _PaperPlan] = {}

        markdown_by_key = self._scan_markdown(skipped)
        for key, record in markdown_by_key.items():
            plans[key.casefold()] = _PaperPlan(key=key, markdown=record)

        flat_by_path = self._scan_flat_images(plans, skipped)
        self._scan_legacy_references(plans, flat_by_path, missing, skipped)
        if cleanup_legacy:
            self._protect_external_references(plans, flat_by_path, skipped)
        self._validate_targets(plans, skipped)

        copied: list[dict[str, str]] = []
        moved: list[dict[str, str]] = []
        preserved: list[dict[str, str]] = []
        rewritten: list[dict[str, Any]] = []
        transaction = self.transactions.begin(
            transaction_id=transaction_id,
            dry_run=not execute,
        )
        transaction.guard(
            lambda: self._recheck_safe_plans(
                plans,
                flat_by_path,
                cleanup_legacy=cleanup_legacy,
            )
        )
        for plan in sorted(plans.values(), key=lambda item: (item.key.casefold(), item.key)):
            if plan.blockers or plan.markdown is None:
                continue
            for image in sorted(
                plan.images,
                key=lambda item: (item.filename.casefold(), item.filename),
            ):
                target = self._target_relative(plan.key, image.filename)
                entry = {
                    "zoteroKey": plan.key,
                    "from": image.relative,
                    "to": target,
                }
                if target.casefold() not in plan.existing_copies:
                    transaction.copy(image.path, target)
                    copied.append(entry)
                if cleanup_legacy:
                    transaction.delete(image.relative)
                    moved.append(entry)
                else:
                    preserved.append(
                        {
                            "zoteroKey": plan.key,
                            "path": image.relative,
                            "canonicalPath": target,
                        }
                    )
            if plan.replacements:
                next_text = plan.markdown.text
                for start, end, replacement in sorted(
                    plan.replacements,
                    key=lambda item: item[0],
                    reverse=True,
                ):
                    next_text = f"{next_text[:start]}{replacement}{next_text[end:]}"
                if next_text != plan.markdown.text:
                    transaction.write_text(plan.markdown.relative, next_text)
                    rewritten.append(
                        {
                            "zoteroKey": plan.key,
                            "path": plan.markdown.relative,
                            "referenceCount": len(plan.replacements),
                        }
                    )

        if execute and (copied or moved or rewritten):
            changed_keys = sorted(
                {
                    *(entry["zoteroKey"] for entry in copied),
                    *(entry["zoteroKey"] for entry in moved),
                    *(entry["zoteroKey"] for entry in rewritten),
                },
                key=lambda value: (value.casefold(), value),
            )
            with ExitStack() as locks:
                for key in changed_keys:
                    locks.enter_context(ItemLock(self.vault_path, key))
                committed = transaction.commit()
        else:
            committed = transaction.commit()
        reparse_keys = sorted(
            {
                plan.key
                for plan in plans.values()
                if plan.blockers.intersection(
                    {
                        "ambiguous-flat-reference",
                        "missing-flat-image",
                        "reference-key-mismatch",
                        "unsafe-flat-image",
                        "html-flat-image-reference",
                        "unrewritable-flat-reference",
                        "external-flat-image-reference",
                        "vault-reference-scan-incomplete",
                    }
                )
            },
            key=lambda value: (value.casefold(), value),
        )
        affected_keys = sorted(
            {
                *(entry["zoteroKey"] for entry in copied),
                *(entry["zoteroKey"] for entry in moved),
                *(entry["zoteroKey"] for entry in rewritten),
                *reparse_keys,
            },
            key=lambda value: (value.casefold(), value),
        )
        return {
            **committed,
            "ok": True,
            "dryRun": not execute,
            "applied": execute,
            "cleanupLegacy": cleanup_legacy,
            "vaultOfflineConfirmed": bool(cleanup_legacy and confirm_vault_offline),
            "copiedImages": copied,
            "movedImages": moved,
            "preservedLegacyImages": preserved,
            "rewrittenMarkdown": rewritten,
            "skipped": sorted(
                skipped,
                key=lambda item: (
                    item.get("zoteroKey", "").casefold(),
                    item.get("path", "").casefold(),
                    item["reason"],
                ),
            ),
            "missingReferencedImages": sorted(
                missing,
                key=lambda item: (
                    item["zoteroKey"].casefold(),
                    item["imagePath"].casefold(),
                ),
            ),
            "reparseZoteroKeys": reparse_keys,
            "affectedZoteroKeys": affected_keys,
        }

    def rollback(
        self,
        transaction_id: str,
        *,
        dry_run: bool = False,
        conflict_policy: str = "preserve-user",
    ) -> dict[str, Any]:
        """Roll back one applied image migration transaction."""

        return self.transactions.rollback(
            transaction_id,
            dry_run=dry_run,
            conflict_policy=conflict_policy,
        )

    def _scan_markdown(
        self,
        skipped: list[dict[str, str]],
    ) -> dict[str, _MarkdownRecord]:
        if _uses_link_or_reparse_point(self.markdown_root, stop=self.vault_path):
            skipped.append(
                {
                    "path": self.markdown_root_relative,
                    "reason": "markdown-root-reparse-point",
                }
            )
            return {}
        if not self.markdown_root.exists():
            return {}
        if not self.markdown_root.is_dir():
            skipped.append(
                {
                    "path": self.markdown_root_relative,
                    "reason": "markdown-root-not-directory",
                }
            )
            return {}

        candidates: dict[str, list[_MarkdownRecord]] = {}
        for path in sorted(
            (
                item
                for item in self.markdown_root.iterdir()
                if item.suffix.casefold() == ".md"
            ),
            key=lambda item: (item.name.casefold(), item.name),
        ):
            relative = self._relative(path)
            if _uses_link_or_reparse_point(path, stop=self.markdown_root):
                skipped.append({"path": relative, "reason": "markdown-reparse-point"})
                continue
            if not path.is_file():
                skipped.append({"path": relative, "reason": "markdown-not-regular-file"})
                continue
            try:
                content = self.fs.read_bytes_owned(relative)
                text = content.decode("utf-8")
                document = parse_frontmatter(text)
                key = validate_zotero_key(str(document.fields.get("zoteroKey") or ""))
            except (OSError, UnicodeError, TypeError, ValueError):
                skipped.append({"path": relative, "reason": "markdown-ownership-uncertain"})
                continue
            if key not in path.name:
                skipped.append(
                    {
                        "path": relative,
                        "zoteroKey": key,
                        "reason": "markdown-key-mismatch",
                    }
                )
                continue
            candidates.setdefault(key.casefold(), []).append(
                _MarkdownRecord(
                    key=key,
                    relative=relative,
                    path=path,
                    text=text,
                    sha256=_sha256(content),
                )
            )

        result: dict[str, _MarkdownRecord] = {}
        for folded_key, records in candidates.items():
            if len(records) == 1:
                result[records[0].key] = records[0]
                continue
            for record in records:
                skipped.append(
                    {
                        "path": record.relative,
                        "zoteroKey": record.key,
                        "reason": "duplicate-markdown-key",
                    }
                )
            result.pop(folded_key, None)
        return result

    def _scan_flat_images(
        self,
        plans: dict[str, _PaperPlan],
        skipped: list[dict[str, str]],
    ) -> dict[str, _LegacyImage]:
        if _uses_link_or_reparse_point(self.image_root, stop=self.vault_path):
            skipped.append(
                {
                    "path": self.image_root_relative,
                    "reason": "image-root-reparse-point",
                }
            )
            return {}
        if not self.image_root.exists():
            return {}
        if not self.image_root.is_dir():
            skipped.append(
                {
                    "path": self.image_root_relative,
                    "reason": "image-root-not-directory",
                }
            )
            return {}

        result: dict[str, _LegacyImage] = {}
        for path in sorted(
            self.image_root.iterdir(),
            key=lambda item: (item.name.casefold(), item.name),
        ):
            is_reparse = _is_link_or_reparse_point(path)
            if not is_reparse and path.is_dir():
                continue
            if path.suffix.casefold() not in _IMAGE_EXTENSIONS:
                continue
            relative = self._relative(path)
            match = _LEGACY_IMAGE_RE.fullmatch(path.name)
            if match is None:
                skipped.append(
                    {
                        "path": relative,
                        "reason": "unrecognized-flat-image-name",
                    }
                )
                continue
            key = validate_zotero_key(match.group("key"))
            folded = key.casefold()
            plan = plans.get(folded)
            if plan is None or plan.markdown is None or plan.key != key:
                skipped.append(
                    {
                        "path": relative,
                        "zoteroKey": key,
                        "reason": "image-ownership-uncertain",
                    }
                )
                continue
            if is_reparse or _uses_link_or_reparse_point(
                path,
                stop=self.image_root,
            ) or not path.is_file():
                plan.blockers.add("unsafe-flat-image")
                skipped.append(
                    {
                        "path": relative,
                        "zoteroKey": key,
                        "reason": "flat-image-reparse-point",
                    }
                )
                continue
            try:
                sha256 = self.fs.sha256_owned(relative)
            except OSError:
                plan.blockers.add("unsafe-flat-image")
                skipped.append(
                    {
                        "path": relative,
                        "zoteroKey": key,
                        "reason": "flat-image-unreadable",
                    }
                )
                continue
            image = _LegacyImage(
                key=key,
                filename=path.name,
                relative=relative,
                path=path,
                sha256=sha256,
            )
            plan.images.append(image)
            result[relative.casefold()] = image
        return result

    def _scan_legacy_references(
        self,
        plans: dict[str, _PaperPlan],
        flat_by_path: Mapping[str, _LegacyImage],
        missing: list[dict[str, str]],
        skipped: list[dict[str, str]],
    ) -> None:
        image_root = PurePosixPath(self.image_root_relative)
        for plan in plans.values():
            record = plan.markdown
            if record is None:
                continue
            if self._has_legacy_html_image(record):
                plan.blockers.add("html-flat-image-reference")
                skipped.append(
                    {
                        "path": record.relative,
                        "zoteroKey": plan.key,
                        "reason": "html-flat-image-reference",
                    }
                )
                continue
            seen_replacements: dict[tuple[int, int], str] = {}
            for reference in parse_image_references(record.text):
                try:
                    resolved = normalize_vault_relative(
                        resolve_image_reference(record.relative, reference.destination)
                    )
                except (TypeError, ValueError):
                    continue
                destination = PurePosixPath(resolved)
                if (
                    destination.parent.as_posix().casefold()
                    != image_root.as_posix().casefold()
                ):
                    continue
                match = _LEGACY_IMAGE_RE.fullmatch(destination.name)
                if match is None:
                    plan.blockers.add("ambiguous-flat-reference")
                    skipped.append(
                        {
                            "path": record.relative,
                            "zoteroKey": plan.key,
                            "reason": "ambiguous-flat-reference",
                        }
                    )
                    continue
                reference_key = validate_zotero_key(match.group("key"))
                if reference_key != plan.key:
                    plan.blockers.add("reference-key-mismatch")
                    skipped.append(
                        {
                            "path": record.relative,
                            "zoteroKey": plan.key,
                            "reason": "reference-key-mismatch",
                        }
                    )
                    continue
                image = flat_by_path.get(resolved.casefold())
                if image is None:
                    plan.blockers.add("missing-flat-image")
                    missing.append(
                        {
                            "zoteroKey": plan.key,
                            "markdownPath": record.relative,
                            "imagePath": resolved,
                        }
                    )
                    continue
                if (
                    reference.destination_start is None
                    or reference.destination_end is None
                    or reference.destination_start >= reference.destination_end
                ):
                    plan.blockers.add("unrewritable-flat-reference")
                    skipped.append(
                        {
                            "path": record.relative,
                            "zoteroKey": plan.key,
                            "reason": "unrewritable-flat-reference",
                        }
                    )
                    continue
                target = self._target_relative(plan.key, image.filename)
                link = posixpath.relpath(
                    target,
                    start=PurePosixPath(record.relative).parent.as_posix(),
                )
                marker = (
                    reference.destination_start,
                    reference.destination_end,
                )
                existing_link = seen_replacements.get(marker)
                if existing_link is not None:
                    if existing_link != link:
                        plan.blockers.add("unrewritable-flat-reference")
                        skipped.append(
                            {
                                "path": record.relative,
                                "zoteroKey": plan.key,
                                "reason": "conflicting-shared-image-reference",
                            }
                        )
                    continue
                seen_replacements[marker] = link
                plan.replacements.append(
                    (
                        reference.destination_start,
                        reference.destination_end,
                        link,
                    )
                )

    def _has_legacy_html_image(self, record: _MarkdownRecord) -> bool:
        image_root = PurePosixPath(self.image_root_relative).as_posix().casefold()
        for match in _HTML_IMAGE_SOURCE_RE.finditer(record.text):
            raw_destination = next(
                (
                    value
                    for value in (
                        match.group("double"),
                        match.group("single"),
                        match.group("bare"),
                    )
                    if value is not None
                ),
                "",
            )
            try:
                resolved = normalize_vault_relative(
                    resolve_image_reference(
                        record.relative,
                        unescape(raw_destination),
                    )
                )
            except (TypeError, ValueError):
                continue
            destination = PurePosixPath(resolved)
            if (
                destination.parent.as_posix().casefold() == image_root
                and _LEGACY_IMAGE_RE.fullmatch(destination.name) is not None
            ):
                return True
        return False

    def _protect_external_references(
        self,
        plans: Mapping[str, _PaperPlan],
        flat_by_path: Mapping[str, _LegacyImage],
        skipped: list[dict[str, str]],
    ) -> None:
        """Do not move a flat image while another owned Vault note still links to it."""

        if not flat_by_path:
            return
        files, rejected = self.fs.scan_owned_files(recursive=True)
        if rejected:
            for plan in plans.values():
                if plan.images:
                    plan.blockers.add("vault-reference-scan-incomplete")
            skipped.extend(
                {
                    "path": relative,
                    "reason": "vault-reference-scan-incomplete",
                }
                for relative in rejected
            )
            return

        seen: set[tuple[str, str]] = set()
        for relative in files:
            portable = PurePosixPath(relative)
            if portable.suffix.casefold() != ".md":
                continue
            if portable.parts and portable.parts[0].casefold() == self.transactions.paths.internal_root.casefold():
                continue
            try:
                text = self.fs.read_text_owned(relative)
            except (OSError, UnicodeError):
                for plan in plans.values():
                    if plan.images:
                        plan.blockers.add("vault-reference-scan-incomplete")
                skipped.append(
                    {
                        "path": relative,
                        "reason": "vault-reference-scan-incomplete",
                    }
                )
                continue

            destinations = [
                (reference.destination, reference.syntax)
                for reference in parse_image_references(text)
            ]
            destinations.extend(
                (
                    unescape(
                        next(
                            value
                            for value in (
                                match.group("double"),
                                match.group("single"),
                                match.group("bare"),
                            )
                            if value is not None
                        )
                    ),
                    "html",
                )
                for match in _HTML_IMAGE_SOURCE_RE.finditer(text)
            )
            for destination, kind in destinations:
                image = self._referenced_flat_image(
                    relative,
                    destination,
                    kind=kind,
                    flat_by_path=flat_by_path,
                )
                if image is None:
                    continue
                owner = plans.get(image.key.casefold())
                if (
                    owner is None
                    or owner.markdown is None
                    or relative.casefold() == owner.markdown.relative.casefold()
                ):
                    continue
                marker = (relative.casefold(), image.relative.casefold())
                if marker in seen:
                    continue
                seen.add(marker)
                owner.blockers.add("external-flat-image-reference")
                skipped.append(
                    {
                        "path": relative,
                        "zoteroKey": owner.key,
                        "imagePath": image.relative,
                        "reason": "external-flat-image-reference",
                    }
                )

    @staticmethod
    def _referenced_flat_image(
        source_relative: str,
        destination: str,
        *,
        kind: str,
        flat_by_path: Mapping[str, _LegacyImage],
    ) -> _LegacyImage | None:
        try:
            resolved = normalize_vault_relative(
                resolve_image_reference(source_relative, destination)
            )
        except (TypeError, ValueError):
            resolved = ""
        image = flat_by_path.get(resolved.casefold())
        if image is not None or kind != "wiki":
            return image

        portable = destination.strip().replace("\\", "/")
        try:
            vault_relative = normalize_vault_relative(portable)
        except (TypeError, ValueError):
            return None
        image = flat_by_path.get(vault_relative.casefold())
        if image is not None:
            return image
        if "/" in portable:
            return None
        matches = {
            item.relative.casefold(): item
            for item in flat_by_path.values()
            if item.filename.casefold() == portable.casefold()
        }
        return next(iter(matches.values())) if len(matches) == 1 else None

    def _validate_targets(
        self,
        plans: dict[str, _PaperPlan],
        skipped: list[dict[str, str]],
    ) -> None:
        image_root_entries: dict[str, list[Path]] | None = None
        for plan in plans.values():
            if not plan.images:
                continue
            if image_root_entries is None:
                image_root_entries = self._casefold_children(self.image_root)
            key_folder_relative = normalize_vault_relative(
                f"{self.image_root_relative}/{plan.key}"
            )
            key_folder = self._lexical(key_folder_relative)
            key_aliases = [
                path
                for path in image_root_entries.get(plan.key.casefold(), ())
                if path.name != plan.key
            ]
            if key_aliases:
                plan.blockers.add("target-collision")
                skipped.append(
                    {
                        "path": self._relative(key_aliases[0]),
                        "zoteroKey": plan.key,
                        "reason": "key-folder-case-collision",
                    }
                )
                continue
            if _uses_link_or_reparse_point(key_folder, stop=self.image_root):
                plan.blockers.add("unsafe-key-folder")
                skipped.append(
                    {
                        "path": key_folder_relative,
                        "zoteroKey": plan.key,
                        "reason": "key-folder-reparse-point",
                    }
                )
                continue
            if key_folder.exists() and not _is_directory(key_folder):
                plan.blockers.add("unsafe-key-folder")
                skipped.append(
                    {
                        "path": key_folder_relative,
                        "zoteroKey": plan.key,
                        "reason": "key-folder-not-directory",
                    }
                )
                continue

            targets: set[str] = set()
            existing_targets = (
                self._casefold_children(key_folder)
                if _is_directory(key_folder)
                else {}
            )
            for image in plan.images:
                target_relative = self._target_relative(plan.key, image.filename)
                folded_target = target_relative.casefold()
                target = self._lexical(target_relative)
                if folded_target in targets:
                    plan.blockers.add("target-collision")
                    skipped.append(
                        {
                            "path": target_relative,
                            "zoteroKey": plan.key,
                            "reason": "target-case-collision",
                        }
                    )
                    continue
                targets.add(folded_target)
                case_aliases = [
                    path
                    for path in existing_targets.get(image.filename.casefold(), ())
                    if path.name != image.filename
                ]
                if case_aliases:
                    plan.blockers.add("target-collision")
                    skipped.append(
                        {
                            "path": self._relative(case_aliases[0]),
                            "zoteroKey": plan.key,
                            "reason": "target-case-collision",
                        }
                    )
                    continue
                if _is_link_or_reparse_point(target):
                    plan.blockers.add("target-collision")
                    skipped.append(
                        {
                            "path": target_relative,
                            "zoteroKey": plan.key,
                            "reason": "target-reparse-point",
                        }
                    )
                    continue
                if target.exists():
                    if not _is_regular_file(target):
                        plan.blockers.add("target-collision")
                        skipped.append(
                            {
                                "path": target_relative,
                                "zoteroKey": plan.key,
                                "reason": "target-not-regular-file",
                            }
                        )
                        continue
                    try:
                        target_sha256 = self.fs.sha256_owned(target_relative)
                    except OSError:
                        target_sha256 = ""
                    if target_sha256 == image.sha256:
                        plan.existing_copies.add(folded_target)
                        continue
                    plan.blockers.add("target-collision")
                    skipped.append(
                        {
                            "path": target_relative,
                            "zoteroKey": plan.key,
                            "reason": "target-content-conflict",
                        }
                    )

            if plan.blockers:
                for image in plan.images:
                    skipped.append(
                        {
                            "path": image.relative,
                            "zoteroKey": plan.key,
                            "reason": "paper-migration-blocked",
                        }
                    )

    def _recheck_safe_plans(
        self,
        plans: Mapping[str, _PaperPlan],
        flat_by_path: Mapping[str, _LegacyImage],
        *,
        cleanup_legacy: bool,
    ) -> None:
        active_plans = [
            plan
            for plan in plans.values()
            if (
                not plan.blockers
                and plan.markdown is not None
                and (plan.images or plan.replacements)
            )
        ]
        if not active_plans:
            return
        if cleanup_legacy:
            active_by_key = {plan.key.casefold(): plan for plan in active_plans}
            active_flat_images = {
                relative: image
                for relative, image in flat_by_path.items()
                if image.key.casefold() in active_by_key
            }
            reference_scan: list[dict[str, str]] = []
            self._protect_external_references(
                active_by_key,
                active_flat_images,
                reference_scan,
            )
            unsafe_reasons = sorted(
                {
                    blocker
                    for plan in active_plans
                    for blocker in plan.blockers
                    if blocker
                    in {
                        "external-flat-image-reference",
                        "vault-reference-scan-incomplete",
                    }
                }
            )
            if unsafe_reasons:
                raise RuntimeError(
                    "Vault flat-image reference safety changed after planning: "
                    + ", ".join(unsafe_reasons)
                )
        if _uses_link_or_reparse_point(self.image_root, stop=self.vault_path):
            raise RuntimeError("MinerU image root became a symbolic link or reparse point")
        image_root_entries = self._casefold_children(self.image_root)
        for plan in active_plans:
            record = plan.markdown
            if record is None:
                continue
            if (
                _uses_link_or_reparse_point(
                    record.path,
                    stop=self.markdown_root,
                )
                or not _is_regular_file(record.path)
            ):
                raise RuntimeError(f"MinerU Markdown became unsafe for {plan.key}")
            if self.fs.sha256_owned(record.relative) != record.sha256:
                raise RuntimeError(f"MinerU Markdown changed after planning for {plan.key}")
            key_folder = self._lexical(
                normalize_vault_relative(f"{self.image_root_relative}/{plan.key}")
            )
            if any(
                path.name != plan.key
                for path in image_root_entries.get(plan.key.casefold(), ())
            ):
                raise RuntimeError(
                    f"MinerU image folder case-collided after planning for {plan.key}"
                )
            if _uses_link_or_reparse_point(key_folder, stop=self.image_root):
                raise RuntimeError(f"MinerU image folder became unsafe for {plan.key}")
            if key_folder.exists() and not _is_directory(key_folder):
                raise RuntimeError(f"MinerU image folder became invalid for {plan.key}")
            existing_targets = (
                self._casefold_children(key_folder)
                if _is_directory(key_folder)
                else {}
            )
            for image in plan.images:
                if (
                    _uses_link_or_reparse_point(image.path, stop=self.image_root)
                    or not _is_regular_file(image.path)
                ):
                    raise RuntimeError(f"legacy MinerU image became unsafe for {plan.key}")
                if self.fs.sha256_owned(image.relative) != image.sha256:
                    raise RuntimeError(
                        f"legacy MinerU image changed after planning for {plan.key}"
                    )
                target_relative = self._target_relative(plan.key, image.filename)
                target = self._lexical(target_relative)
                if any(
                    path.name != image.filename
                    for path in existing_targets.get(image.filename.casefold(), ())
                ):
                    raise RuntimeError(
                        f"MinerU image target case-collided after planning for {plan.key}"
                    )
                target_was_present = target_relative.casefold() in plan.existing_copies
                if target_was_present:
                    if (
                        _is_link_or_reparse_point(target)
                        or not _is_regular_file(target)
                        or self.fs.sha256_owned(target_relative) != image.sha256
                    ):
                        raise RuntimeError(
                            f"MinerU image migration target changed for {plan.key}"
                        )
                elif _is_link_or_reparse_point(target) or target.exists():
                    raise RuntimeError(f"MinerU image migration target appeared for {plan.key}")

    @staticmethod
    def _casefold_children(folder: Path) -> dict[str, list[Path]]:
        try:
            metadata = folder.lstat()
        except OSError as exc:
            raise RuntimeError(f"cannot inspect MinerU migration folder: {folder}") from exc
        if _is_link_or_reparse_metadata(metadata) or not stat.S_ISDIR(metadata.st_mode):
            raise RuntimeError(f"MinerU migration folder is not an owned directory: {folder}")
        result: dict[str, list[Path]] = {}
        for child in folder.iterdir():
            result.setdefault(child.name.casefold(), []).append(child)
        return result

    def _target_relative(self, key: str, filename: str) -> str:
        return normalize_vault_relative(f"{self.image_root_relative}/{key}/{filename}")

    def _relative(self, path: Path) -> str:
        try:
            relative = path.relative_to(self.vault_path)
        except ValueError as exc:
            raise RuntimeError("MinerU migration path escaped the Vault") from exc
        return normalize_vault_relative(relative.as_posix())

    def _lexical(self, relative: str) -> Path:
        portable = normalize_vault_relative(relative)
        return self.vault_path.joinpath(*PurePosixPath(portable).parts)


def _is_link_or_reparse_point(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except OSError:
        return False
    return _is_link_or_reparse_metadata(metadata)


def _is_link_or_reparse_metadata(metadata: os.stat_result) -> bool:
    return stat.S_ISLNK(metadata.st_mode) or bool(
        getattr(metadata, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def _is_regular_file(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except OSError:
        return False
    return not _is_link_or_reparse_metadata(metadata) and stat.S_ISREG(
        metadata.st_mode
    )


def _is_directory(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except OSError:
        return False
    return not _is_link_or_reparse_metadata(metadata) and stat.S_ISDIR(
        metadata.st_mode
    )


def _uses_link_or_reparse_point(path: Path, *, stop: Path) -> bool:
    try:
        path.relative_to(stop)
    except ValueError:
        return True
    current = path
    while True:
        if _is_link_or_reparse_point(current):
            return True
        if current == stop:
            return False
        current = current.parent


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()
