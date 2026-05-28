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


_DEFAULT_DENIED_NAMES = frozenset({".git", ".ai-team"})


def safe_workspace_file_path(
    root: str | Path,
    raw_path: str,
    *,
    denied_names: set[str] | frozenset[str] | None = None,
) -> Path:
    """Resolve *raw_path* inside *root* and reject traversal or protected names.

    - Follows symlinks via ``resolve()`` and verifies the final path stays
      inside *root*.
    - Rejects paths whose first component is in *denied_names* (default:
      ``.git`` and ``.ai-team``).

    Raises ``ValueError`` on any violation.
    """
    root_path = Path(root).resolve()
    target = (root_path / raw_path).resolve()

    try:
        target.relative_to(root_path)
    except ValueError as exc:
        raise ValueError(f"path escapes allowed root: {raw_path}") from exc

    denied = _DEFAULT_DENIED_NAMES if denied_names is None else denied_names
    rel_parts = target.relative_to(root_path).parts
    if rel_parts and rel_parts[0] in denied:
        raise ValueError(f"access denied to protected path: {raw_path}")

    return target
