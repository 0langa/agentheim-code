"""Error taxonomy and classification for the Agentheim Code runtime.

Maps exceptions to canonical categories that drive retry strategy, alerting,
and graceful degradation.
"""

from __future__ import annotations

import socket
import ssl
from enum import Enum
from typing import Any

from core.errors import (
    ConfigError,
    ExecutionError,
    IntegrationError,
    PatchApplicationError,
    PlanningError,
    ProviderError,
    RepoInspectionError,
    ResumeError,
    ToolSafetyError,
    VerificationError,
)


class ErrorCategory(Enum):
    """Canonical error categories.

    Each category maps to a runtime strategy:

    - TRANSIENT:    Exponential backoff + provider switch
    - RECOVERABLE:  Retry with same/mildly modified prompt
    - VERIFICATION: Enter FIX_LOOP (bounded retries)
    - CONFIGURATION: Halt + report
    - PERMISSION:   Log + request approval
    - FATAL:        Halt + preserve state
    """

    TRANSIENT = "transient"
    RECOVERABLE = "recoverable"
    VERIFICATION = "verification"
    CONFIGURATION = "configuration"
    PERMISSION = "permission"
    FATAL = "fatal"


# Exception-type → category mapping (most specific first)
_CATEGORY_MAP: dict[type[BaseException], ErrorCategory] = {
    # Transient (network / service flakes)
    ConnectionError: ErrorCategory.TRANSIENT,
    TimeoutError: ErrorCategory.TRANSIENT,
    socket.timeout: ErrorCategory.TRANSIENT,
    ssl.SSLError: ErrorCategory.TRANSIENT,
    OSError: ErrorCategory.TRANSIENT,
    # Permission
    PermissionError: ErrorCategory.PERMISSION,
    # Configuration
    FileNotFoundError: ErrorCategory.CONFIGURATION,
    ImportError: ErrorCategory.CONFIGURATION,
    ModuleNotFoundError: ErrorCategory.CONFIGURATION,
    KeyError: ErrorCategory.CONFIGURATION,
    ValueError: ErrorCategory.CONFIGURATION,
    # Verification
    AssertionError: ErrorCategory.VERIFICATION,
    # Fatal
    MemoryError: ErrorCategory.FATAL,
    RecursionError: ErrorCategory.FATAL,
    NotImplementedError: ErrorCategory.FATAL,
    RuntimeError: ErrorCategory.FATAL,
    # Agentheim-specific
    ConfigError: ErrorCategory.CONFIGURATION,
    ToolSafetyError: ErrorCategory.PERMISSION,
    PlanningError: ErrorCategory.RECOVERABLE,
    ExecutionError: ErrorCategory.FATAL,
    PatchApplicationError: ErrorCategory.VERIFICATION,
    VerificationError: ErrorCategory.VERIFICATION,
    ResumeError: ErrorCategory.CONFIGURATION,
    IntegrationError: ErrorCategory.CONFIGURATION,
    RepoInspectionError: ErrorCategory.CONFIGURATION,
}


def _classify_provider_error(exc: ProviderError) -> ErrorCategory:
    """Sub-classify a ProviderError based on message content."""
    http_status = getattr(exc, "http_status", None)
    if http_status is not None:
        if http_status == 429:
            return ErrorCategory.TRANSIENT
        if http_status == 401:
            return ErrorCategory.CONFIGURATION
        if http_status == 403:
            return ErrorCategory.PERMISSION
        if http_status in (404, 422):
            return ErrorCategory.CONFIGURATION
        if http_status in (500, 502, 503, 504):
            return ErrorCategory.TRANSIENT

    msg = str(exc).lower()
    if any(
        k in msg
        for k in ("rate limit", "quota", "too many", "temporarily unavailable", "server overloaded")
    ):
        return ErrorCategory.TRANSIENT
    if any(k in msg for k in ("timeout", "timed out", "deadline exceeded")):
        return ErrorCategory.TRANSIENT
    if any(
        k in msg
        for k in ("connection", "network", "unreachable", "connection reset", "service unavailable")
    ):
        return ErrorCategory.TRANSIENT
    if any(k in msg for k in ("permission denied", "forbidden", "access denied")):
        return ErrorCategory.PERMISSION
    if any(
        k in msg
        for k in (
            "authentication",
            "auth",
            "api_key",
            "credentials",
            "invalid api key",
            "unauthorized",
        )
    ):
        return ErrorCategory.CONFIGURATION
    if any(
        k in msg
        for k in (
            "model",
            "deployment",
            "not found",
            "unsupported",
            "invalid request",
            "bad request",
        )
    ):
        return ErrorCategory.CONFIGURATION
    return ErrorCategory.FATAL


def _troubleshooting_section(exc: BaseException, category: ErrorCategory) -> str:
    """Return the best matching troubleshooting section label."""
    if isinstance(exc, ProviderError):
        msg = str(exc).lower()
        if any(k in msg for k in ("permission denied", "forbidden", "access denied")):
            return "Provider permission denied / forbidden"
        if any(
            k in msg
            for k in (
                "authentication",
                "auth",
                "api_key",
                "credentials",
                "invalid api key",
                "unauthorized",
            )
        ):
            return "Provider authentication failed"
        if any(
            k in msg
            for k in (
                "rate limit",
                "quota",
                "too many",
                "temporarily unavailable",
                "service unavailable",
                "timeout",
                "timed out",
            )
        ):
            return "Provider rate limit or temporary outage"
        if any(
            k in msg
            for k in (
                "model",
                "deployment",
                "not found",
                "unsupported",
                "invalid request",
                "bad request",
            )
        ):
            return "Provider endpoint/model mismatch"
    if isinstance(exc, ToolSafetyError) or category == ErrorCategory.PERMISSION:
        return "Tool call blocked"
    if isinstance(exc, ResumeError):
        return "Recovering from a failed run"
    if isinstance(exc, (PatchApplicationError, VerificationError)):
        return "Run fails mid-execution"
    if category == ErrorCategory.CONFIGURATION:
        return "Configuration Issues"
    if category == ErrorCategory.TRANSIENT:
        return "Provider rate limit or temporary outage"
    return "Run fails mid-execution"


def _next_action_for(category: ErrorCategory) -> str:
    return {
        ErrorCategory.TRANSIENT: "Retry operation after backoff or switch provider if issue persists.",
        ErrorCategory.RECOVERABLE: "Retry step with adjusted input or prompt.",
        ErrorCategory.VERIFICATION: "Inspect verification output, fix issue, rerun bounded fix loop.",
        ErrorCategory.CONFIGURATION: "Fix local/provider configuration before retrying.",
        ErrorCategory.PERMISSION: "Grant approval or update credentials/permissions before retrying.",
        ErrorCategory.FATAL: "Inspect run diagnostics and error context before rerunning.",
    }[category]


def error_summary_from_text(message: str, error_type: str | None = None) -> dict[str, Any]:
    """Best-effort error summary when only serialized error text is available."""
    error_map: dict[str, type[BaseException]] = {
        "AssertionError": AssertionError,
        "ConfigError": ConfigError,
        "ExecutionError": ExecutionError,
        "FileNotFoundError": FileNotFoundError,
        "ImportError": ImportError,
        "IntegrationError": IntegrationError,
        "KeyError": KeyError,
        "MemoryError": MemoryError,
        "ModuleNotFoundError": ModuleNotFoundError,
        "NotImplementedError": NotImplementedError,
        "PatchApplicationError": PatchApplicationError,
        "PermissionError": PermissionError,
        "PlanningError": PlanningError,
        "ProviderError": ProviderError,
        "RecursionError": RecursionError,
        "RepoInspectionError": RepoInspectionError,
        "ResumeError": ResumeError,
        "RuntimeError": RuntimeError,
        "TimeoutError": TimeoutError,
        "ToolSafetyError": ToolSafetyError,
        "ValueError": ValueError,
        "VerificationError": VerificationError,
    }
    exc_cls = error_map.get(error_type or "")
    if exc_cls is None:
        lowered = message.lower()
        if any(
            token in lowered
            for token in (
                "auth",
                "api key",
                "credential",
                "forbidden",
                "rate limit",
                "quota",
                "model",
                "deployment",
                "timeout",
                "network",
            )
        ):
            exc: BaseException = ProviderError(message)
        elif "permission" in lowered or "approval denied" in lowered:
            exc = PermissionError(message)
        elif "verify" in lowered or "patch" in lowered:
            exc = VerificationError(message)
        else:
            exc = RuntimeError(message)
    else:
        exc = exc_cls(message)
    return error_summary(exc)


def classify_error(exc: BaseException) -> ErrorCategory:
    """Classify an exception into a canonical error category.

    Walks the exception's MRO and returns the first matching category.
    Falls back to FATAL for unmapped exceptions.
    """
    if isinstance(exc, ProviderError):
        return _classify_provider_error(exc)
    for cls in type(exc).__mro__:
        if cls in _CATEGORY_MAP:
            return _CATEGORY_MAP[cls]
    return ErrorCategory.FATAL


# ------------------------------------------------------------------
# Strategy helpers
# ------------------------------------------------------------------


def should_retry(category: ErrorCategory) -> bool:
    """Whether this category warrants automatic retry."""
    return category in {
        ErrorCategory.TRANSIENT,
        ErrorCategory.RECOVERABLE,
        ErrorCategory.VERIFICATION,
    }


def max_retries_for(category: ErrorCategory, default: int = 3) -> int:
    """Suggested max retry count per category."""
    return {
        ErrorCategory.TRANSIENT: 5,
        ErrorCategory.RECOVERABLE: 3,
        ErrorCategory.VERIFICATION: 3,
    }.get(category, default)


def backoff_for(category: ErrorCategory, default: float = 2.0) -> float:
    """Suggested initial backoff (seconds) per category."""
    return {
        ErrorCategory.TRANSIENT: 1.0,
        ErrorCategory.RECOVERABLE: 2.0,
        ErrorCategory.VERIFICATION: 1.5,
    }.get(category, default)


def should_halt(category: ErrorCategory) -> bool:
    """Whether this category should stop the run."""
    return category in {
        ErrorCategory.CONFIGURATION,
        ErrorCategory.PERMISSION,
        ErrorCategory.FATAL,
    }


def error_summary(exc: BaseException) -> dict[str, Any]:
    """Produce a JSON-safe summary of an exception for ledger payloads."""
    category = classify_error(exc)
    troubleshooting_section = _troubleshooting_section(exc, category)
    return {
        "type": type(exc).__name__,
        "message": str(exc),
        "category": category.value,
        "retryable": should_retry(category),
        "halt": should_halt(category),
        "next_action": _next_action_for(category),
        "troubleshooting_doc": "docs/TROUBLESHOOTING.md",
        "troubleshooting_section": troubleshooting_section,
    }
