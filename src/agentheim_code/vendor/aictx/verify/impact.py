"""Change-impact mapping and stale detection."""

from __future__ import annotations

from fnmatch import fnmatch
from pathlib import Path

from agentheim_code.vendor.aictx.models.context_lock import ContextLock


def detect_impact(
    changed_files: list[Path],
    lock: ContextLock,
) -> dict[str, list[str]]:
    """Map changed files to impacted AI context and public docs."""
    changed = {_to_posix(path) for path in changed_files}
    ai_context: set[str] = set()
    public_docs: set[str] = set()
    for entry in lock.change_impact_map:
        if any(_matches(path, entry.source_glob) for path in changed):
            ai_context.update(entry.ai_context_sections)
            public_docs.update(entry.public_doc_paths)
    return {"ai_context": sorted(ai_context), "public_docs": sorted(public_docs)}


def _to_posix(path: Path) -> str:
    return path.as_posix()


def _matches(path: str, pattern: str) -> bool:
    return path == pattern or fnmatch(path, pattern)
