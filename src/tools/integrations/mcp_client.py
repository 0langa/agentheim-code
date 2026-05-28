from __future__ import annotations

from pathlib import Path
from typing import Any


class MCPClientAdapter:
    def __init__(
        self, repo_root: str | Path, enabled: bool = False, allowlist: list[str] | None = None
    ) -> None:
        self.repo_root = Path(repo_root)
        self.enabled = enabled
        self.allowlist = set(allowlist or [])

    @property
    def available(self) -> bool:
        return self.enabled

    def call(self, tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.enabled:
            raise RuntimeError(
                "MCP adapter is disabled. "
                "To enable MCP, create .ai-team/mcp.json with server configurations, "
                "or use the real MCP stack via tools.mcp.register_mcp_tools()."
            )
        if self.allowlist and tool_name not in self.allowlist:
            raise RuntimeError(f"MCP tool '{tool_name}' is not in allowlist.")
        raise RuntimeError(
            "MCP client adapter has no configured backend. "
            "Create .ai-team/mcp.json with server configurations, "
            "or use tools.mcp.register_mcp_tools(registry, repo_root) to load real MCP servers."
        )
