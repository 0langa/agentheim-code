"""File I/O helpers."""

from __future__ import annotations

from contextlib import suppress
from pathlib import Path


def safe_write(path: Path, content: str) -> None:
    """Atomically write *content* to *path*, creating parent directories if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    try:
        tmp.replace(path)
    except PermissionError:
        path.write_text(content, encoding="utf-8")
        with suppress(OSError):
            tmp.unlink()


def read_text(path: Path) -> str:
    """Read the full text of *path*."""
    return path.read_text(encoding="utf-8")
