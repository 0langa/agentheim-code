from __future__ import annotations

import re
from pathlib import Path

SECRET_FILE_NAMES = {
    ".env",
    ".gr" + "okrc",
    "id_rsa",
    "id_dsa",
    "id_ed25519",
    "secrets.yml",
    "secrets.yaml",
    "appsettings.secrets.json",
}

_MAX_EXCERPT_SCAN = 20_000
_MAX_SECRET_VALUE = 512


def _compile_multiline_secret_pattern(label: str) -> re.Pattern[str]:
    return re.compile(
        rf"(?is)-----BEGIN {label}-----[\s\S]{{1,{_MAX_EXCERPT_SCAN}}}?-----END {label}-----"
    )


SECRET_PATTERNS = [
    re.compile(
        rf"(?i)(api[_-]?key|token|password|secret)(\s*[:=]\s*['\"]?)([^\s'\"\r\n]{{8,{_MAX_SECRET_VALUE}}})"
    ),
    re.compile(rf"(?i)(password)(\s*[:=]\s*)([^\s\r\n]{{1,{_MAX_SECRET_VALUE}}})"),
    re.compile(rf"(?i)(connection\s*string)(\s*[:=]\s*)([^\r\n]{{1,{_MAX_SECRET_VALUE}}})"),
    _compile_multiline_secret_pattern("[A-Z ]+PRIVATE KEY"),
    _compile_multiline_secret_pattern("CERTIFICATE"),
]


def is_secret_file(path: Path) -> bool:
    name = path.name.lower()
    if name in SECRET_FILE_NAMES:
        return True
    return any(part.lower() in {"secrets", ".ssh"} for part in path.parts)


def redact_text(text: str) -> str:
    if len(text) > _MAX_EXCERPT_SCAN:
        return "[REDACTED-LARGE-BLOB]"
    redacted = text
    for pattern in SECRET_PATTERNS:

        def _replace(match: re.Match[str]) -> str:
            if match.lastindex and match.lastindex >= 3:
                return f"{match.group(1)}{match.group(2)}[REDACTED]"
            if match.lastindex:
                return f"{match.group(1)}[REDACTED]"
            return "[REDACTED]"

        redacted = pattern.sub(_replace, redacted)
    return redacted


def safe_text_excerpt(text: str, limit: int = 4000) -> str:
    excerpt = redact_text(text)
    if len(excerpt) <= limit:
        return excerpt
    return excerpt[:limit] + "\n...[truncated]"
