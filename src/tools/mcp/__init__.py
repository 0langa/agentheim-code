from __future__ import annotations

import logging
from pathlib import Path

from core.tool_protocol import ToolRegistry
from tools.mcp.client import MCPClient
from tools.mcp.config import MCPServerConfig, load_mcp_config
from tools.mcp.pool import MCPConnectionPool
from tools.mcp.tool_adapter import MCPTool

logger = logging.getLogger(__name__)

__all__ = [
    "MCPClient",
    "MCPTool",
    "MCPServerConfig",
    "load_mcp_config",
    "MCPConnectionPool",
    "register_mcp_tools",
]


def register_mcp_tools(registry: ToolRegistry, repo_root: Path) -> MCPConnectionPool:
    """Discover and register MCP tools from configured servers.

    Reads `.ai-team/mcp.json` (if present), connects to enabled servers,
    discovers their tools, and wraps each as an MCPTool in the registry.

    Returns the connection pool so the caller can manage its lifecycle.
    """
    config_path = repo_root / ".ai-team" / "mcp.json"
    if not config_path.exists():
        logger.debug("No MCP config found at %s", config_path)
        return MCPConnectionPool()

    try:
        servers = load_mcp_config(config_path)
    except Exception as exc:
        logger.warning("Failed to load MCP config: %s", exc)
        return MCPConnectionPool()

    pool = MCPConnectionPool()
    for server in servers:
        if not server.enabled:
            continue
        try:
            client = pool.get_client(server)
            tools = client.list_tools()
            for tool_info in tools:
                tool = MCPTool(pool, server, tool_info)
                try:
                    registry.register(tool)
                    logger.info("Registered MCP tool: %s (from %s)", tool.tool_id, server.name)
                except ValueError:
                    # Already registered — skip
                    pass
            pool.release_client(server.name)
        except Exception as exc:
            logger.warning("MCP server '%s' failed: %s", server.name, exc)
    return pool
