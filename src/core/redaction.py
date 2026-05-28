"""Secret redaction for logs, artifacts, and model context.

Replaces sensitive patterns with [REDACTED-<hash>] to preserve uniqueness
without leaking secrets.
"""

from __future__ import annotations

import hashlib
import re

_MAX_REDACTION_INPUT = 200_000
_MAX_SECRET_VALUE = 512


def _compile_multiline_secret_pattern(label: str) -> re.Pattern[str]:
    return re.compile(
        rf"(?is)-----BEGIN {label}-----[\s\S]{{1,{_MAX_REDACTION_INPUT}}}?-----END {label}-----"
    )


SECRET_PATTERNS = [
    # API keys, tokens, passwords, secrets
    re.compile(
        rf"(?i)(api[_-]?key|token|password|secret|auth)(\s*[:=]\s*['\"]?)([^\s'\"\r\n]{{8,{_MAX_SECRET_VALUE}}})"
    ),
    # Connection strings
    re.compile(rf"(?i)(connection\s*string)(\s*[:=]\s*)([^\r\n]{{1,{_MAX_SECRET_VALUE}}})"),
    # Private keys
    _compile_multiline_secret_pattern("[A-Z ]+PRIVATE KEY"),
    # Certificates
    _compile_multiline_secret_pattern("CERTIFICATE"),
    # AWS access key ID
    re.compile(r"(?i)(AKIA[0-9A-Z]{16})"),
    # Generic hex tokens (64-256 chars)
    re.compile(r"\b([a-f0-9]{64,256})\b"),
    # Bearer tokens
    re.compile(rf"(?i)(bearer\s+)([a-zA-Z0-9_\-./=]{{8,{_MAX_SECRET_VALUE}}})"),
]


def _hash_secret(secret: str) -> str:
    """Create a short deterministic hash for a secret."""
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()[:8]


def redact_text(text: str) -> str:
    """Redact secrets from text, replacing with [REDACTED-<hash>]."""
    if len(text) > _MAX_REDACTION_INPUT:
        return text
    redacted = text
    for pattern in SECRET_PATTERNS:

        def replacer(match: re.Match) -> str:
            # Find the secret portion of the match
            groups = match.groups()
            if len(groups) >= 3:
                secret = groups[-1]
                return f"{groups[0]}{groups[1]}[REDACTED-{_hash_secret(secret)}]"
            if len(groups) == 2:
                secret = groups[-1]
                return f"{groups[0]}[REDACTED-{_hash_secret(secret)}]"
            # Single group or full match
            secret = match.group(0)
            return f"[REDACTED-{_hash_secret(secret)}]"

        redacted = pattern.sub(replacer, redacted)
    return redacted


def redact_dict(data: dict | list) -> dict | list:
    """Recursively redact secrets from a JSON-serializable structure."""
    if isinstance(data, str):
        return redact_text(data)
    if isinstance(data, dict):
        return {k: redact_dict(v) for k, v in data.items()}
    if isinstance(data, list):
        return [redact_dict(item) for item in data]
    return data
