"""Patch creation and application helpers."""

from __future__ import annotations

import difflib
import os
import re
import subprocess
from contextlib import suppress
from pathlib import Path

from agentheim_code.vendor.aictx.errors import PatchApplyError
from agentheim_code.vendor.aictx.io.files import safe_write


def make_unified_diff(original: str, updated: str, original_path: str, updated_path: str) -> str:
    """Return a unified diff between *original* and *updated*."""
    return "".join(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            updated.splitlines(keepends=True),
            fromfile=original_path,
            tofile=updated_path,
        )
    )


def apply_patch(patch_text: str, target_dir: Path) -> None:
    """Apply a unified diff patch to files in *target_dir*."""
    target_dir = target_dir.resolve()
    if not patch_text.strip():
        return
    _validate_patch_paths(patch_text)

    tmp_dir = target_dir / ".aictx" / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    patch_path = tmp_dir / f"apply-{os.getpid()}.patch"
    safe_write(patch_path, patch_text)
    try:
        _run_git_apply(target_dir, patch_path, check_only=True)
        _run_git_apply(target_dir, patch_path, check_only=False)
    finally:
        with suppress(OSError):
            patch_path.unlink()


def _run_git_apply(target_dir: Path, patch_path: Path, check_only: bool) -> None:
    args = ["git", "-C", str(target_dir), "apply"]
    if check_only:
        args.append("--check")
    args.extend(["--whitespace=nowarn", str(patch_path)])
    result = subprocess.run(args, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        action = "validate" if check_only else "apply"
        detail = (result.stderr or result.stdout).strip()
        raise PatchApplyError(f"Could not {action} patch: {detail}")


def _validate_patch_paths(patch_text: str) -> None:
    for line in patch_text.splitlines():
        if not (line.startswith("--- ") or line.startswith("+++ ")):
            continue
        path = line[4:].split("\t", 1)[0].strip()
        if path == "/dev/null":
            continue
        if path.startswith(("a/", "b/")):
            path = path[2:]
        _validate_relative_patch_path(path)


def _validate_relative_patch_path(path: str) -> None:
    if not path:
        raise PatchApplyError("Patch contains an empty path.")
    if path.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", path):
        raise PatchApplyError(f"Patch contains absolute path: {path}")
    parts = Path(path).parts
    if ".." in parts:
        raise PatchApplyError(f"Patch escapes target directory: {path}")
