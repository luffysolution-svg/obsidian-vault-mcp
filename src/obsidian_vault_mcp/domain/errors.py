"""Domain-specific exceptions for the literature pipeline."""

from __future__ import annotations

from typing import Any


class ObsidianVaultMcpError(Exception):
    """Base class for all expected application errors."""


class IdentityError(ObsidianVaultMcpError, ValueError):
    """Raised when an item identity or naming pattern is unsafe."""


class PathValidationError(ObsidianVaultMcpError, ValueError):
    """Raised when a Vault-relative path is invalid or escapes the Vault."""


class FrontmatterError(ObsidianVaultMcpError, ValueError):
    """Raised when Markdown frontmatter is malformed."""


class ConfigurationError(ObsidianVaultMcpError, ValueError):
    """Raised when the Vault configuration file is invalid."""


class AtomicWriteError(ObsidianVaultMcpError, OSError):
    """Raised when an atomic replacement cannot be completed."""


class LockError(ObsidianVaultMcpError):
    """Base class for lock acquisition and release failures."""


class LockTimeoutError(LockError, TimeoutError):
    """Raised when a Vault lock cannot be acquired before its timeout."""


class TransactionError(ObsidianVaultMcpError):
    """A transaction failed at a known stage."""

    def __init__(
        self,
        message: str,
        *,
        transaction_id: str = "",
        stage: str = "",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.transaction_id = transaction_id
        self.stage = stage
        self.details = details or {}

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable failure payload."""

        return {
            "ok": False,
            "transactionId": self.transaction_id,
            "stage": self.stage,
            "error": str(self),
            "details": self.details,
        }


class TransactionConflictError(TransactionError):
    """Raised when a transaction id or destination is already in use."""


class TransactionRollbackError(TransactionError):
    """Raised when a committed transaction cannot be fully restored."""


# Short compatibility alias for callers that prefer the project acronym.
OvmError = ObsidianVaultMcpError
