from __future__ import annotations

import re
from pathlib import Path

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def safe_run_id(value: str) -> str:
    """Validate an externally supplied run id before path composition."""
    run_id = str(value).strip()
    if not _SAFE_ID.fullmatch(run_id):
        raise ValueError("run_id must contain only letters, numbers, dots, underscores, or hyphens")
    if run_id in {".", ".."} or run_id.startswith("."):
        raise ValueError("run_id must not be hidden or relative")
    return run_id


def safe_child_path(root: str | Path, *parts: str | Path) -> Path:
    """Resolve a child path and reject traversal outside *root*."""
    root_path = Path(root).resolve()
    candidate = root_path.joinpath(*parts).resolve()
    if candidate != root_path and root_path not in candidate.parents:
        raise ValueError(f"path escapes allowed root: {candidate}")
    return candidate


def safe_project_path(value: str | Path) -> Path:
    """Resolve a user supplied project path to an existing directory."""
    # Project paths are intentionally user-selected roots. This helper only
    # canonicalizes them before explicit existence/type checks.
    project = Path(value).expanduser().resolve()  # lgtm[py/path-injection]
    if not project.exists():
        raise ValueError(f"project path does not exist: {project}")
    if not project.is_dir():
        raise ValueError(f"project path is not a directory: {project}")
    return project
