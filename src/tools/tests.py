from __future__ import annotations

from core.repo.command_detect import DetectedCommand
from tools.shell import ShellResult, ShellTool


class TestTool:
    def __init__(self, shell_tool: ShellTool) -> None:
        self.shell_tool = shell_tool

    def run_safe_command(self, command: DetectedCommand) -> ShellResult:
        if command.risk_level != "safe":
            raise ValueError(f"Only safe commands can run. Got: {command.risk_level}")
        return self.shell_tool.execute(command.command)
