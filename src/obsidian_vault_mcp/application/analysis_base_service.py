"""Transactional lifecycle for the one V3 ``Analysis.base`` file."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from ..adapters.obsidian.analysis_base_renderer import (
    ANALYSIS_BASE_TEMPLATE_VERSION,
    render_analysis_base,
)
from ..adapters.vault.filesystem import VaultFilesystem, VaultPathSafetyError
from ..adapters.vault.lock import GlobalLock
from ..config.loader import load_config
from ..domain.analysis import AnalysisValidationError
from ..domain.errors import TransactionConflictError
from ..domain.paths import normalize_vault_relative
from .transaction_service import TransactionService

_CONFLICT_POLICIES = frozenset({"preserve-user", "overwrite-managed", "fail"})


class AnalysisBaseService:
    """Create or upgrade the single recursive Analysis Base contract."""

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
        analysis = self.config.get("analysis")
        section = analysis if isinstance(analysis, Mapping) else {}
        self.analysis_folder = normalize_vault_relative(
            str(section.get("folder", "Literature/Analysis"))
        )
        self.base_path = normalize_vault_relative(
            str(section.get("base", "Literature/Analysis/Analysis.base"))
        )
        try:
            PurePosixPath(self.base_path).relative_to(PurePosixPath(self.analysis_folder))
        except ValueError as exc:
            raise AnalysisValidationError(
                "analysis.base must stay inside analysis.folder"
            ) from exc
        if not self.base_path.casefold().endswith(".base"):
            raise AnalysisValidationError("analysis.base must be a .base file")
        self.fs = VaultFilesystem(self.vault_path)
        self.transactions = transaction_service or TransactionService(self.vault_path)

    def rebuild(
        self,
        *,
        dry_run: bool = False,
        transaction_id: str | None = None,
        conflict_policy: str = "preserve-user",
    ) -> dict[str, Any]:
        """Create or upgrade ``Analysis.base`` without generating an index."""

        _validate_conflict_policy(conflict_policy)
        try:
            existing_bytes = self.fs.read_bytes_owned(self.base_path)
        except FileNotFoundError:
            existing_bytes = None
        except (OSError, VaultPathSafetyError) as exc:
            raise AnalysisValidationError(
                f"unsafe Analysis Base path: {self.base_path}"
            ) from exc
        existing = (
            existing_bytes.decode("utf-8")
            .replace("\r\n", "\n")
            .replace("\r", "\n")
            if existing_bytes is not None
            else None
        )
        rendered = render_analysis_base(self.analysis_folder)
        if existing is not None and conflict_policy == "fail":
            raise TransactionConflictError(
                f"Analysis Base already exists: {self.base_path}",
                stage="plan",
            )
        preserved = (
            existing is not None
            and existing != rendered
            and conflict_policy == "preserve-user"
        )
        expected_sha256 = (
            hashlib.sha256(existing_bytes).hexdigest()
            if existing_bytes is not None
            else None
        )
        transaction = self.transactions.begin(
            transaction_id=transaction_id,
            dry_run=dry_run,
        )
        if not preserved:
            transaction.write_text(
                self.base_path,
                rendered,
            )
        transaction.guard(
            lambda: self._assert_snapshot(expected_sha256)
        )
        if dry_run:
            result = transaction.commit()
        else:
            with GlobalLock(self.vault_path, "base"):
                result = transaction.commit()
        return {
            **result,
            "analysisFolder": self.analysis_folder,
            "analysisBasePath": self.base_path,
            "templateVersion": ANALYSIS_BASE_TEMPLATE_VERSION,
            "preservedUserBase": preserved,
            "warnings": (
                [
                    {
                        "code": "analysis-base-user-content-preserved",
                        "path": self.base_path,
                        "message": "Existing Analysis Base differs from the managed template.",
                    }
                ]
                if preserved
                else []
            ),
        }

    def rollback(
        self,
        transaction_id: str,
        *,
        dry_run: bool = False,
        conflict_policy: str = "preserve-user",
    ) -> dict[str, Any]:
        _validate_conflict_policy(conflict_policy)
        if dry_run:
            return self.transactions.rollback(
                transaction_id,
                dry_run=True,
                conflict_policy=conflict_policy,
            )
        with GlobalLock(self.vault_path, "base"):
            return self.transactions.rollback(
                transaction_id,
                conflict_policy=conflict_policy,
            )

    def _assert_snapshot(self, expected_sha256: str | None) -> None:
        if expected_sha256 is None:
            try:
                base_exists = self.fs.is_file_owned(self.base_path)
            except (OSError, VaultPathSafetyError) as exc:
                raise RuntimeError("Analysis Base path became unsafe") from exc
            if base_exists:
                raise RuntimeError("Analysis Base appeared after planning")
            return
        try:
            actual = self.fs.sha256_owned(self.base_path)
        except FileNotFoundError as exc:
            raise RuntimeError("Analysis Base disappeared after planning") from exc
        except (OSError, VaultPathSafetyError) as exc:
            raise RuntimeError("Analysis Base path became unsafe") from exc
        if actual != expected_sha256:
            raise RuntimeError("Analysis Base changed after planning")


def _validate_conflict_policy(value: str) -> None:
    if value not in _CONFLICT_POLICIES:
        raise ValueError(
            f"conflict_policy must be one of: {', '.join(sorted(_CONFLICT_POLICIES))}"
        )
