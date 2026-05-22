"""`.gitignore` and `.aictxignore` matching."""

from __future__ import annotations

from pathlib import Path

import pathspec

BUILTIN_HARD_EXCLUDES = [
    ".git",
    ".aictx",
    ".ai-team",
    ".pytest-tmp",
    ".pytest_cache",
    ".coverage",
    "agentheim.egg-info",
    "bin",
    "obj",
    "node_modules",
    "dist",
    "build",
    ".vs",
    ".idea",
    "__pycache__",
    "*.pyc",
    "*.pyo",
    "*.pfx",
    "*.snk",
    "*.key",
    "*.pem",
    ".env",
    ".env.*",
    "*.sqlite",
    "*.sqlite3",
    "*.db",
]


def _load_spec(path: Path) -> pathspec.PathSpec | None:  # type: ignore[type-arg]
    """Load a gitignore-style pathspec from *path* if it exists."""
    if not path.exists():
        return None
    lines = path.read_text(encoding="utf-8").splitlines()
    return pathspec.PathSpec.from_lines("gitignore", lines)


class IgnoreMatcher:
    """Matches paths against built-in, .gitignore, and .aictxignore patterns."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root
        self.builtin = pathspec.PathSpec.from_lines("gitignore", BUILTIN_HARD_EXCLUDES)
        self.gitignore = _load_spec(repo_root / ".gitignore")
        self.aictxignore = _load_spec(repo_root / ".aictxignore")

    def is_ignored(self, relative_path: str, is_dir: bool = False) -> bool:
        """Return True if *relative_path* (POSIX, repo-relative) should be ignored.

        When *is_dir* is True a trailing slash is appended so that
        directory-only patterns (e.g. ``node_modules/``) match correctly.
        """
        check = relative_path if not is_dir else relative_path + "/"
        if self.builtin.match_file(check):
            return True
        if self.gitignore is not None and self.gitignore.match_file(check):
            return True
        return self.aictxignore is not None and self.aictxignore.match_file(check)
