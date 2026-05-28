from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from core.errors import IntegrationError


class GitHubCliAdapter:
    def __init__(self, repo_root: str | Path, enabled: bool = True) -> None:
        self.repo_root = Path(repo_root)
        self.enabled = enabled

    @property
    def available(self) -> bool:
        if not self.enabled:
            return False
        if shutil.which("gh") is not None:
            return True
        return bool(os.getenv("GITHUB_TOKEN"))

    def _require_available(self) -> None:
        if not self.enabled:
            raise IntegrationError(
                "GitHub integration is not enabled. "
                "Set enabled=True when creating the adapter, or configure GITHUB_TOKEN."
            )
        if not self.available:
            raise IntegrationError(
                "GitHub CLI (gh) is not installed or not authenticated, and GITHUB_TOKEN is not set. "
                "Install gh and run `gh auth login`, or set the GITHUB_TOKEN environment variable."
            )

    def _run(self, args: list[str]) -> str:
        self._require_available()
        result = subprocess.run(
            ["gh", *args],
            cwd=self.repo_root,
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
        )
        if result.returncode != 0:
            raise IntegrationError(result.stderr.strip() or "GitHub CLI command failed.")
        return result.stdout.strip()

    def view_issue(self, issue: str) -> str:
        return self._run(["issue", "view", issue])

    def view_pr(self, pr: str) -> str:
        return self._run(["pr", "view", pr])

    def view_workflow_run(self, run_id: str) -> str:
        return self._run(["run", "view", run_id])
