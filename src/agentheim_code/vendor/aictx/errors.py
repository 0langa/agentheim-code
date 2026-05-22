"""Custom exceptions for AICtx."""

from __future__ import annotations


class AictxError(Exception):
    """Base exception for all AICtx errors."""

    pass


class SafetyError(AictxError):
    """Raised when a safety check prevents an operation."""

    pass


class ConfigError(AictxError):
    """Raised when configuration is invalid or missing."""

    pass


class ScanError(AictxError):
    """Raised when repository scanning fails."""

    pass


class SecretScanError(SafetyError):
    """Raised when high-confidence secrets are detected."""

    pass


class TokenBudgetExceededError(SafetyError):
    """Raised when a run would exceed configured token limits."""

    pass


class VerificationError(AictxError):
    """Raised when verification fails."""

    pass


class PatchApplyError(AictxError):
    """Raised when a patch cannot be safely applied."""

    pass


class RemoteJobError(AictxError):
    """Raised when a remote OCI job fails."""

    pass
