"""Validation report generation."""

from __future__ import annotations

import json
from pathlib import Path


def write_validation_report(
    out_path: Path,
    result: str,
    details: dict[str, object],
) -> None:
    """Write a human-readable validation report to *out_path*."""
    lines = ["# Validation Report", "", f"Result: {result}", ""]
    for key in sorted(details):
        value = details[key]
        lines.append(f"## {key}")
        if isinstance(value, dict):
            lines.append("```json")
            lines.append(json.dumps(value, indent=2, sort_keys=True))
            lines.append("```")
        elif isinstance(value, list):
            lines.extend([f"- {item}" for item in value] or ["- none"])
        else:
            lines.append(str(value))
        lines.append("")
    out_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
