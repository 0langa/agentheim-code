"""Patch generation for public docs updates."""

from __future__ import annotations

from pathlib import Path

from agentheim_code.vendor.aictx.io.patches import make_unified_diff


def generate_doc_patch(original: Path, updated: str, relative_path: str | None = None) -> str:
    """Return a unified diff between *original* and *updated*."""
    original_text = original.read_text(encoding="utf-8") if original.exists() else ""
    diff_path = relative_path or original.as_posix()
    original_name = f"a/{diff_path}" if original.exists() else "/dev/null"
    updated_name = f"b/{diff_path}"
    return make_unified_diff(original_text, updated, original_name, updated_name)
