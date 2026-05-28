"""Shell tool implementing ToolProtocol.

Command execution with process-level sandbox, allowlist/denylist enforcement,
and command classification.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from core.tool_protocol import (
    BaseTool,
    ParamSchema,
    ReturnSchema,
    RiskLevel,
    ToolContext,
    ToolResult,
    ToolSchema,
)
from tools.shell.sandbox import SandboxConfig, SandboxViolation, ShellSandbox


class ShellResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    command: list[str]
    returncode: int
    stdout: str
    stderr: str


class ShellTool(BaseTool):
    """Shell command execution with process-level sandbox.

    Every command runs through ``ShellSandbox`` which enforces:
    - Strict command prefix allowlist (no broad ``SAFE_PREFIXES`` bypass)
    - Shell metacharacter injection prevention
    - Path traversal blocking
    - Environment variable filtering
    - Process group isolation for reliable cleanup
    - Working directory confinement
    - Output size limits
    """

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self._sandbox = ShellSandbox(
            SandboxConfig(
                workspace=self.repo_root,
                policy_mode="strict",
            )
        )
        schema = ToolSchema(
            description="Execute shell commands within the workspace via process-level sandbox.",
            parameters={
                "command": ParamSchema(
                    type="array", description="Command as list of strings", required=True
                ),
                "timeout_seconds": ParamSchema(
                    type="integer", description="Timeout in seconds", default=120, required=False
                ),
            },
            returns=ReturnSchema(type="object", description="{returncode, stdout, stderr}"),
        )
        super().__init__("shell.execute", schema, RiskLevel.HIGH)

    def invoke(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        valid, err = self.validate_params(params)
        if not valid:
            return ToolResult(success=False, error=err)

        command = params.get("command", [])
        timeout = params.get("timeout_seconds", 120)

        if not command:
            return ToolResult(success=False, error="Command cannot be empty.")

        # Policy-level command allowlist/denylist (from ToolContext)
        if not context.command_allowed(command):
            return ToolResult(success=False, error="Command blocked by policy.")

        try:
            result = self._sandbox.execute(command, timeout=timeout)
            shell_result = ShellResult(
                command=command,
                returncode=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
            )
            return ToolResult(
                success=True,
                data=shell_result,
                metadata={
                    "returncode": result.returncode,
                },
            )
        except SandboxViolation as exc:
            return ToolResult(success=False, error=str(exc))

    def execute(self, command: list[str], timeout_seconds: int = 120) -> ShellResult:
        result = self._sandbox.execute(command, timeout=timeout_seconds)
        return ShellResult(
            command=command,
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )
