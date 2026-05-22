"""High-confidence secret scanning."""

from __future__ import annotations

import re
from pathlib import Path

SELF_MATCH_EXCLUDED_PARTS = {"tests", "unit", "fixtures"}
IGNORE_MARKER = "aictx-secret-ignore"

PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    (
        "private_key_header",
        re.compile(r"-----BEGIN (RSA |DSA |EC |OPENSSH )?PRIVATE KEY-----"),
        "high",
    ),
    (
        "oci_api_key",
        re.compile(r"OCI_API_KEY"),
        "high",
    ),
    (
        "github_token",
        re.compile(r"gh[pousr]_[A-Za-z0-9_]{36,}"),
        "high",
    ),
    (
        "generic_api_key",
        re.compile(r"(?i)(api[_-]?key|apikey|secret[_-]?key|auth[_-]?token)\s*[:=]\s*[\"']?\S+"),
        "medium",
    ),
    (
        "connection_string",
        re.compile(r"(?i)(mongodb(\+srv)?://|postgres(ql)?://|mysql://|sqlserver://)\S+"),
        "medium",
    ),
    (
        "env_file_secret",
        re.compile(
            r"(?i)^(AWS_SECRET_ACCESS_KEY|AZURE_CLIENT_SECRET|GOOGLE_API_KEY|OPENAI_API_KEY)\s*=\s*\S+"
        ),
        "high",
    ),
]


def scan_for_secrets(content: str, file_path: Path) -> list[dict[str, str | int | None]]:
    """Scan *content* for high-confidence secrets.

    Returns a list of findings with ``detector_name``, ``severity``, and
    ``line_number`` keys. Does **not** return the secret value itself.
    """
    if _should_skip_secret_scan(file_path):
        return []

    findings: list[dict[str, str | int | None]] = []
    lines = content.splitlines()
    for detector_name, pattern, severity in PATTERNS:
        # Check file path first for .env-like files
        if detector_name == "env_file_secret":
            if file_path.name.startswith(".env") or file_path.suffix == ".env":
                for line_no, line in enumerate(lines, start=1):
                    if pattern.search(line) and not _is_suppressed(lines, line_no):
                        findings.append(
                            {
                                "path": file_path.as_posix(),
                                "detector_name": detector_name,
                                "severity": severity,
                                "line_number": line_no,
                            }
                        )
            continue

        for line_no, line in enumerate(lines, start=1):
            if pattern.search(line) and not _is_suppressed(lines, line_no):
                findings.append(
                    {
                        "path": file_path.as_posix(),
                        "detector_name": detector_name,
                        "severity": severity,
                        "line_number": line_no,
                    }
                )
    return findings


def _should_skip_secret_scan(file_path: Path) -> bool:
    """Skip files that intentionally embed detector examples or fixtures."""
    normalized_parts = {part.casefold() for part in file_path.parts}
    return (
        file_path.name == "secrets.py" and {"src", "aictx", "scan"}.issubset(normalized_parts)
    ) or bool(normalized_parts & SELF_MATCH_EXCLUDED_PARTS)


def _is_suppressed(lines: list[str], line_no: int) -> bool:
    indexes = [line_no - 2, line_no - 1, line_no]
    return any(0 <= index < len(lines) and IGNORE_MARKER in lines[index] for index in indexes)
