"""Git diff utilities."""

from __future__ import annotations

import subprocess
from pathlib import Path


def get_git_diff(repo_root: Path, base: str = "HEAD~1") -> str:
    """Return the unified diff against *base*."""
    result = subprocess.run(
        ["git", "-C", str(repo_root), "diff", base],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout
