"""Git worktree status inspection."""

from __future__ import annotations

import subprocess
from pathlib import Path


class WorktreeStatus:
    """Represents the current git worktree state."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()
        self.branch = self._git("branch", "--show-current").strip()
        self.head_commit = self._git("rev-parse", "HEAD").strip()
        self.dirty = bool(self._git("status", "--short", "--untracked-files=all").strip())
        self.untracked_files: list[str] = []
        self.modified_files: list[str] = []
        self.deleted_files: list[str] = []
        self.renamed_files: list[dict[str, str]] = []
        self.tracked_files = self._get_tracked_files()
        self._parse_status()

    def _git(self, *args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(self.repo_root), *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Git command failed: git {' '.join(args)}: {result.stderr}")
        return result.stdout

    def _get_tracked_files(self) -> list[str]:
        output = self._git("ls-files", "--exclude-standard")
        return [line for line in output.splitlines() if line]

    def _parse_status(self) -> None:
        output = self._git("status", "--short", "--untracked-files=all")
        for line in output.splitlines():
            if len(line) < 3:
                continue
            status = line[:2]
            path = line[3:]
            if status == "??":
                self.untracked_files.append(path)
            elif "M" in status:
                self.modified_files.append(path)
            elif status == " D" or status == "D ":
                self.deleted_files.append(path)
            elif status.startswith("R"):
                # Renamed lines look like: "R  old -> new"
                if " -> " in path:
                    old, new = path.split(" -> ", 1)
                    self.renamed_files.append({"from": old, "to": new})
                else:
                    self.renamed_files.append({"from": path, "to": path})
