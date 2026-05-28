"""Privacy enforcement — structured privacy modes and sensitive-data protection.

Replaces the boolean ``local_only`` / ``strict_private`` flags with a typed
``PrivacyMode`` and a reusable ``PrivacyEnforcer`` that can redact, block,
and audit privacy decisions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from fnmatch import fnmatch
from typing import Any, cast

from core.redaction import redact_dict
from core.tool_protocol import ToolContext


class PrivacyMode(Enum):
    """Structured privacy modes."""

    STANDARD = "standard"
    LOCAL_ONLY = "local_only"
    STRICT_PRIVATE = "strict_private"
    ENCRYPTED = "encrypted"


@dataclass
class PrivacyEnforcer:
    """Enforces privacy constraints based on a structured mode.

    Attributes:
        mode: The active privacy mode.
        sensitive_patterns: fnmatch patterns for sensitive file paths.
    """

    mode: PrivacyMode = PrivacyMode.STANDARD
    sensitive_patterns: list[str] = field(
        default_factory=lambda: [
            "*.key",
            "*.pem",
            "*.env",
            "*secret*",
            "*password*",
            "*token*",
            "*.p12",
            "*.pfx",
            "*.crt",
        ]
    )

    def evaluate(
        self,
        tool_id: str,
        params: dict[str, Any],
        context: ToolContext,
    ) -> dict[str, Any]:
        """Evaluate privacy constraints and return a privacy report.

        The report contains:
        - ``allowed``: bool — whether the call passes privacy checks.
        - ``violations``: list[str] — human-readable violation messages.
        - ``redacted``: bool — whether params must be redacted in all outputs.
        - ``mode``: str — the mode that produced this report.
        """
        violations: list[str] = []
        redacted = False

        if self.mode == PrivacyMode.LOCAL_ONLY and (
            tool_id.startswith("http.") or tool_id in {"git.push", "git.clone"}
        ):
            violations.append(f"Network tool '{tool_id}' blocked in local_only mode.")

        if self.mode in {PrivacyMode.STRICT_PRIVATE, PrivacyMode.ENCRYPTED}:
            path = params.get("path", "")
            if path and self._is_sensitive(str(path)):
                violations.append(f"Sensitive path '{path}' blocked in {self.mode.value} mode.")

        if self.mode == PrivacyMode.ENCRYPTED:
            redacted = True

        return {
            "allowed": len(violations) == 0,
            "violations": violations,
            "redacted": redacted,
            "mode": self.mode.value,
        }

    def redact_params(self, params: dict[str, Any]) -> dict[str, Any]:
        """Return a redacted copy of params safe for logging / auditing."""
        return cast(dict[str, Any], redact_dict(params))

    def _is_sensitive(self, path: str) -> bool:
        """Check if *path* matches any sensitive pattern."""
        return any(fnmatch(path.lower(), pattern.lower()) for pattern in self.sensitive_patterns)
