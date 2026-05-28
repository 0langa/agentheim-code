from __future__ import annotations

from pathlib import Path
from typing import cast

from core.tool_protocol import AsyncBaseTool, BaseTool
from core.tool_protocol import ToolRegistry as CoreToolRegistry
from tools.browser import BrowserTool
from tools.filesystem import FilesystemTool
from tools.git import GitTool
from tools.http import HttpTool
from tools.local_db import LocalDBTool
from tools.memory import MemoryTool
from tools.shell import ShellTool
from tools.tests import TestTool


def _default_tool_specs(
    repo_root: str | Path,
    *,
    include_http: bool = True,
    include_memory: bool = True,
) -> list[tuple[str, object]]:
    root = Path(repo_root).resolve()
    specs: list[tuple[str, object]] = [
        ("filesystem", FilesystemTool(root)),
        ("git", GitTool(root)),
        ("shell", ShellTool(root)),
        ("browser", BrowserTool(root)),
        ("local_db", LocalDBTool(root)),
    ]
    if include_http:
        specs.append(("http_request", HttpTool()))
    if include_memory:
        specs.append(("memory", MemoryTool(root / ".ai-team" / "memory")))
    return specs


class ToolRegistry:
    """Canonical default tool container for interfaces.

    This class keeps attribute-based access for API/Web UI callers while sharing
    the same default tool set as workflow-side registries.
    """

    def __init__(
        self,
        repo_root: str | Path = ".",
        *,
        include_http: bool = True,
        include_memory: bool = True,
        include_mcp: bool = False,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.include_http = include_http
        self.include_memory = include_memory
        self.include_mcp = include_mcp
        self._tool_attrs: list[str] = []
        self.shell: ShellTool

        for attr_name, tool in _default_tool_specs(
            self.repo_root,
            include_http=include_http,
            include_memory=include_memory,
        ):
            setattr(self, attr_name, tool)
            self._tool_attrs.append(attr_name)
            if attr_name == "shell":
                self.shell = cast(ShellTool, tool)

        self.tests = TestTool(self.shell)

    def tool_objects(self) -> list[object]:
        return [getattr(self, attr_name) for attr_name in self._tool_attrs]


def create_core_tool_registry(
    repo_root: str | Path = ".",
    *,
    include_http: bool = True,
    include_memory: bool = True,
    include_mcp: bool = False,
) -> CoreToolRegistry:
    """Build the canonical CoreToolRegistry from the shared default tool set."""

    registry = CoreToolRegistry()
    for _, tool in _default_tool_specs(
        repo_root,
        include_http=include_http,
        include_memory=include_memory,
    ):
        registry.register(cast(BaseTool | AsyncBaseTool, tool))

    if include_mcp:
        from tools.mcp import register_mcp_tools

        register_mcp_tools(registry, Path(repo_root).resolve())

    return registry
