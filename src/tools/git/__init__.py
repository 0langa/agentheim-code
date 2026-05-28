"""Git tool implementing ToolProtocol.

Operations: clone, diff, commit, status, push with policy integration.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from core.tool_protocol import (
    BaseTool,
    ParamSchema,
    ReturnSchema,
    RiskLevel,
    ToolContext,
    ToolResult,
    ToolSchema,
)


class GitTool(BaseTool):
    """Git operations with risk-appropriate policies."""

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        schema = ToolSchema(
            description="Git operations: status, diff, commit, clone, push.",
            parameters={
                "operation": ParamSchema(
                    type="string",
                    description="Operation: status, diff, diff_patch, commit, clone, push",
                    enum=["status", "diff", "diff_patch", "commit", "clone", "push"],
                    required=True,
                ),
                "message": ParamSchema(type="string", description="Commit message", required=False),
                "url": ParamSchema(type="string", description="Clone URL", required=False),
                "target": ParamSchema(
                    type="string", description="Target directory for clone", required=False
                ),
            },
            returns=ReturnSchema(type="string", description="Command output"),
        )
        # Base risk is NONE for read-only ops; individual ops override
        super().__init__("git", schema, RiskLevel.NONE)

    def _run(self, args: list[str]) -> tuple[int, str, str]:
        result = subprocess.run(
            ["git", *args],
            cwd=self.repo_root,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        return result.returncode, result.stdout, result.stderr

    def invoke(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        valid, err = self.validate_params(params)
        if not valid:
            return ToolResult(success=False, error=err)

        operation = params.get("operation")

        if operation == "status":
            return self._status()
        if operation == "diff":
            return self._diff()
        if operation == "diff_patch":
            return self._diff_patch()
        if operation == "commit":
            return self._commit(params.get("message", " Automated commit"))
        if operation == "clone":
            return self._clone(params.get("url", ""), params.get("target", "."))
        if operation == "push":
            return self._push()

        return ToolResult(success=False, error=f"Unknown git operation: {operation}")

    def _status(self) -> ToolResult:
        rc, out, err = self._run(["status", "--short"])
        return ToolResult(
            success=rc == 0, data=out, error=err or None, metadata={"risk": RiskLevel.NONE.value}
        )

    def _diff(self) -> ToolResult:
        rc, out, err = self._run(["diff", "--stat"])
        return ToolResult(
            success=rc == 0, data=out, error=err or None, metadata={"risk": RiskLevel.NONE.value}
        )

    def _diff_patch(self) -> ToolResult:
        rc, out, err = self._run(["diff", "--no-ext-diff", "--binary"])
        return ToolResult(
            success=rc == 0, data=out, error=err or None, metadata={"risk": RiskLevel.NONE.value}
        )

    def _commit(self, message: str) -> ToolResult:
        rc, _, err = self._run(["add", "-A"])
        if rc != 0:
            return ToolResult(success=False, error=f"git add failed: {err}")
        rc, out, err = self._run(["commit", "-m", message])
        return ToolResult(
            success=rc == 0, data=out, error=err or None, metadata={"risk": RiskLevel.LOW.value}
        )

    def _clone(self, url: str, target: str) -> ToolResult:
        if not url:
            return ToolResult(success=False, error="Clone URL is required.")
        target_path = (self.repo_root / target).resolve()
        try:
            target_path.relative_to(self.repo_root)
        except ValueError:
            return ToolResult(success=False, error="Clone target escapes workspace.")
        rc, out, err = self._run(["clone", url, str(target_path)])
        return ToolResult(
            success=rc == 0, data=out, error=err or None, metadata={"risk": RiskLevel.MEDIUM.value}
        )

    def _push(self) -> ToolResult:
        # HIGH risk — policy engine should gate this
        rc, out, err = self._run(["push"])
        return ToolResult(
            success=rc == 0, data=out, error=err or None, metadata={"risk": RiskLevel.HIGH.value}
        )
