"""Structured run errors for Agentheim Code.

Each error carries a machine code, human message, technical detail,
recovery action, and optional related session event id.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StructuredError:
    error_code: str
    message: str
    technical_detail: str = ""
    recovery_action: str = ""
    related_event_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_code": self.error_code,
            "message": self.message,
            "technical_detail": self.technical_detail,
            "recovery_action": self.recovery_action,
            "related_event_id": self.related_event_id,
        }


# Error catalog
E_SESSION_NOT_FOUND = StructuredError(
    error_code="E2001",
    message="Session not found.",
    technical_detail="The requested session ID does not exist in the workspace.",
    recovery_action="Create a new session or select an existing one from the run list.",
)

E_SESSION_LOCKED = StructuredError(
    error_code="E2002",
    message="Session is already running.",
    technical_detail="Another turn is in progress for this session.",
    recovery_action="Wait for the current turn to finish, or cancel it and retry.",
)

E_CONTEXT_VALIDATION_FAILED = StructuredError(
    error_code="E2003",
    message="Some selected context files could not be used.",
    technical_detail="One or more files were missing, binary, too large, ignored, or outside the workspace.",
    recovery_action="Review the context file list and remove or replace the rejected files.",
)

E_CANCELLATION_FAILED = StructuredError(
    error_code="E2004",
    message="Could not cancel the session.",
    technical_detail="The cancel request failed, possibly because the session no longer exists.",
    recovery_action="Refresh the session list and try again.",
)

E_PROVIDER_ERROR = StructuredError(
    error_code="E2005",
    message="The AI provider returned an error.",
    technical_detail="",
    recovery_action="Check your provider settings, network connection, and try again.",
)

E_RUNTIME_ERROR = StructuredError(
    error_code="E2006",
    message="An unexpected error occurred during the agent turn.",
    technical_detail="",
    recovery_action="Try again with a simpler prompt, or check the session timeline for details.",
)

E_RESUME_INVALID_STATE = StructuredError(
    error_code="E2007",
    message="Session is not in a resumable state.",
    technical_detail="The session may be running, already completed, or in an inconsistent state.",
    recovery_action="Wait for the session to finish, or create a new session.",
)

E_REQUEST_TOO_LARGE = StructuredError(
    error_code="E2008",
    message="Request body is too large.",
    technical_detail="The request payload exceeded the configured body limit.",
    recovery_action="Reduce the prompt size or attached context and retry.",
)

E_NETWORK_ERROR = StructuredError(
    error_code="E2009",
    message="A network error occurred while contacting the provider.",
    technical_detail="",
    recovery_action="Check your network connection and provider endpoint, then retry.",
)

E_FILESYSTEM_ERROR = StructuredError(
    error_code="E2010",
    message="A filesystem error occurred while reading or writing session data.",
    technical_detail="",
    recovery_action="Check disk space, file permissions, and workspace path.",
)


def redact_text(text: str) -> str:
    """Remove common secret patterns from text."""
    import re

    patterns = [
        (r"sk-[a-zA-Z0-9]{20,}", "sk-***"),
        (r"Bearer\s+[a-zA-Z0-9_-]+", "Bearer ***"),
        (r"api[_-]?key[:\s=]+[a-zA-Z0-9_-]+", "api_key=***"),
    ]
    result = text
    for pattern, replacement in patterns:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    return result


def from_exception(exc: Exception, *, event_id: str = "") -> StructuredError:
    """Build a structured error from an arbitrary exception."""
    name = type(exc).__name__
    return StructuredError(
        error_code="E2099",
        message=str(exc) or f"Unexpected error: {name}",
        technical_detail=name,
        recovery_action="Check the session timeline and try again.",
        related_event_id=event_id,
    )
