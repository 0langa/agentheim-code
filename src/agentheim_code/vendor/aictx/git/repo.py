"""Git repository root detection and basic queries."""

from __future__ import annotations

import subprocess
from pathlib import Path

from agentheim_code.vendor.aictx.errors import AictxError


def find_git_root(start: Path | None = None) -> Path:
    """Find the git root starting from *start* or the current directory."""
    cwd = start or Path.cwd()
    result = subprocess.run(
        ["git", "-C", str(cwd), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AictxError(f"Not a git repository: {cwd}")
    return Path(result.stdout.strip())
