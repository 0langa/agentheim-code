"""Bounded context bundle pipeline for selected files.

Validates workspace-relative paths, rejects bad files, and produces
metadata-rich context blocks with previews and truncation reasons.
"""

from __future__ import annotations

import mimetypes
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

MAX_FILE_BYTES = 128_000
MAX_PREVIEW_CHARS = 4_000
BINARY_HINT_BYTES = 8_192
TOKEN_ESTIMATE_CHARS_PER_TOKEN = 4


def _is_binary(path: Path) -> bool:
    """Heuristic: read first 8KB and look for null bytes."""
    try:
        with path.open("rb") as f:
            chunk = f.read(BINARY_HINT_BYTES)
    except Exception:
        return True
    return b"\x00" in chunk


def _is_ignored(path: Path, workspace: Path) -> bool:
    """Check if path is under .git or .ai-team."""
    try:
        rel = path.relative_to(workspace)
    except ValueError:
        return True
    parts = set(rel.parts)
    return ".git" in parts or ".ai-team" in parts


def _safe_relative(path: Path, workspace: Path) -> str | None:
    """Return a POSIX relative path if the file is inside workspace."""
    try:
        resolved = path.resolve()
        ws = workspace.resolve()
        resolved.relative_to(ws)
        return path.relative_to(ws).as_posix()
    except (ValueError, RuntimeError):
        return None


@dataclass(frozen=True)
class ContextItem:
    path: str
    status: Literal["ok", "missing", "binary", "huge", "ignored", "outside_workspace"]
    size: int = 0
    preview: str = ""
    truncation_reason: str = ""
    language: str = ""

    @property
    def is_usable(self) -> bool:
        return self.status == "ok"

    def token_estimate(self) -> int:
        return max(1, len(self.preview) // TOKEN_ESTIMATE_CHARS_PER_TOKEN)


@dataclass(frozen=True)
class ContextBundle:
    items: list[ContextItem] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def usable_items(self) -> list[ContextItem]:
        return [item for item in self.items if item.is_usable]

    @property
    def rejected_items(self) -> list[ContextItem]:
        return [item for item in self.items if not item.is_usable]

    def total_token_estimate(self) -> int:
        return sum(item.token_estimate() for item in self.usable_items)

    def to_prompt_block(self) -> str:
        """Produce an explicit runtime context block for the planner."""
        lines: list[str] = []
        usable = self.usable_items
        if not usable:
            return ""
        lines.append("<context_files>")
        for item in usable:
            lines.append(f'<file path="{item.path}" language="{item.language}">')
            lines.append(item.preview)
            if item.truncation_reason:
                lines.append(f"<!-- truncation: {item.truncation_reason} -->")
            lines.append("</file>")
        lines.append("</context_files>")
        return "\n".join(lines)

    def to_preview_payload(self) -> list[dict]:
        """Payload for the frontend context preview panel."""
        return [
            {
                "path": item.path,
                "status": item.status,
                "size": item.size,
                "preview": item.preview[:200] + "..." if len(item.preview) > 200 else item.preview,
                "truncation_reason": item.truncation_reason,
                "token_estimate": item.token_estimate(),
            }
            for item in self.items
        ]


def build_context_bundle(
    workspace: Path,
    raw_paths: list[str],
) -> ContextBundle:
    """Validate and read files, producing a bounded context bundle."""
    items: list[ContextItem] = []
    errors: list[str] = []
    seen: set[str] = set()

    for raw in raw_paths:
        raw = raw.strip().lstrip("/")
        if not raw or raw in seen:
            continue
        seen.add(raw)

        # Path must be relative
        if raw.startswith("..") or "/../" in raw or "\\..\\" in raw:
            items.append(ContextItem(path=raw, status="outside_workspace", size=0, preview=""))
            errors.append(f"'{raw}' traverses outside the workspace.")
            continue

        candidate = workspace / raw
        rel = _safe_relative(candidate, workspace)
        if rel is None:
            items.append(ContextItem(path=raw, status="outside_workspace", size=0, preview=""))
            errors.append(f"'{raw}' is outside the workspace.")
            continue

        if _is_ignored(candidate, workspace):
            items.append(ContextItem(path=raw, status="ignored", size=0, preview=""))
            errors.append(f"'{raw}' is in an ignored directory (.git or .ai-team).")
            continue

        if not candidate.exists():
            items.append(ContextItem(path=raw, status="missing", size=0, preview=""))
            errors.append(f"'{raw}' does not exist.")
            continue

        if not candidate.is_file():
            items.append(ContextItem(path=raw, status="missing", size=0, preview=""))
            errors.append(f"'{raw}' is not a file.")
            continue

        size = candidate.stat().st_size

        if _is_binary(candidate):
            items.append(
                ContextItem(
                    path=raw,
                    status="binary",
                    size=size,
                    preview="",
                    truncation_reason="binary file",
                )
            )
            errors.append(f"'{raw}' appears to be a binary file.")
            continue

        if size > MAX_FILE_BYTES:
            items.append(
                ContextItem(
                    path=raw,
                    status="huge",
                    size=size,
                    preview="",
                    truncation_reason=f"{size} bytes exceeds {MAX_FILE_BYTES} byte limit",
                )
            )
            errors.append(f"'{raw}' is too large ({size} bytes).")
            continue

        # Read preview
        try:
            text = candidate.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            items.append(
                ContextItem(
                    path=raw,
                    status="binary",
                    size=size,
                    preview="",
                    truncation_reason=f"read error: {exc}",
                )
            )
            errors.append(f"'{raw}' could not be read: {exc}.")
            continue

        preview = text
        truncation_reason = ""
        if len(preview) > MAX_PREVIEW_CHARS:
            preview = preview[:MAX_PREVIEW_CHARS]
            truncation_reason = f"truncated from {len(text)} to {MAX_PREVIEW_CHARS} characters"

        lang_guess = mimetypes.guess_type(str(candidate))[0] or ""
        language = lang_guess.split("/")[-1] if "/" in lang_guess else lang_guess

        items.append(
            ContextItem(
                path=raw,
                status="ok",
                size=size,
                preview=preview,
                truncation_reason=truncation_reason,
                language=language,
            )
        )

    return ContextBundle(items=items, errors=errors)
