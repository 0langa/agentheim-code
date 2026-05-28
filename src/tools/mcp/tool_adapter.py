from __future__ import annotations

import asyncio
import logging
from typing import Any

from core.tool_protocol import (
    AsyncBaseTool,
    BaseTool,
    ParamSchema,
    ReturnSchema,
    RiskLevel,
    ToolContext,
    ToolResult,
    ToolSchema,
)
from tools.mcp.config import MCPServerConfig
from tools.mcp.pool import MCPConnectionPool

logger = logging.getLogger(__name__)


def _mcp_type_to_param_type(mcp_type: str) -> str:
    mapping = {
        "string": "str",
        "integer": "int",
        "number": "float",
        "boolean": "bool",
        "array": "list",
        "object": "dict",
    }
    return mapping.get(mcp_type, "str")


def _convert_schema(mcp_input_schema: dict[str, Any]) -> dict[str, ParamSchema]:
    """Convert MCP JSON Schema input to our ParamSchema dict."""
    parameters: dict[str, ParamSchema] = {}
    properties = mcp_input_schema.get("properties", {})
    required = set(mcp_input_schema.get("required", []))

    for name, prop in properties.items():
        ptype = _mcp_type_to_param_type(prop.get("type", "string"))
        description = prop.get("description", "")
        enum = prop.get("enum")
        parameters[name] = ParamSchema(
            type=ptype,
            description=description,
            required=name in required,
            enum=list(enum) if enum else None,
        )
    return parameters


class MCPTool(BaseTool):
    """Wraps an MCP server tool as a BaseTool.

    Holds a reference to an :class:`MCPConnectionPool` rather than a raw
    :class:`MCPClient` so that the underlying stdio transport stays alive
    across multiple invocations.
    """

    def __init__(
        self,
        pool: MCPConnectionPool,
        server: MCPServerConfig,
        tool_info: dict[str, Any],
    ) -> None:
        self._pool = pool
        self._server = server
        self._tool_info = tool_info
        name = tool_info.get("name", "unknown")
        description = tool_info.get("description", "MCP tool")
        input_schema = tool_info.get("inputSchema", {})
        parameters = _convert_schema(input_schema)
        schema = ToolSchema(
            description=description,
            parameters=parameters,
            returns=ReturnSchema(type="dict", description="MCP tool result"),
        )
        super().__init__(tool_id=f"mcp.{name}", schema=schema, risk_level=RiskLevel.MEDIUM)

    def invoke(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        name = self._tool_info.get("name", "")
        client = self._pool.get_client(self._server)
        try:
            result = client.call_tool(name, params)
            return ToolResult(success=True, data=result, metadata={"source": "mcp"})
        except Exception as exc:
            logger.warning("MCP tool '%s' invocation failed: %s", name, exc)
            return ToolResult(
                success=False,
                error=str(exc),
                metadata={"source": "mcp", "tool": name},
            )
        finally:
            self._pool.release_client(self._server.name)


class AsyncMCPTool(AsyncBaseTool):
    """Async variant of :class:`MCPTool`.

    Runs the underlying synchronous MCP client in a thread pool so that
    async callers do not block the event loop during stdio JSON-RPC.
    """

    def __init__(
        self,
        pool: MCPConnectionPool,
        server: MCPServerConfig,
        tool_info: dict[str, Any],
    ) -> None:
        self._pool = pool
        self._server = server
        self._tool_info = tool_info
        name = tool_info.get("name", "unknown")
        description = tool_info.get("description", "MCP tool")
        input_schema = tool_info.get("inputSchema", {})
        parameters = _convert_schema(input_schema)
        schema = ToolSchema(
            description=description,
            parameters=parameters,
            returns=ReturnSchema(type="dict", description="MCP tool result"),
        )
        super().__init__(tool_id=f"mcp.{name}", schema=schema, risk_level=RiskLevel.MEDIUM)

    async def ainvoke(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_invoke, params, context)

    def _sync_invoke(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        """Synchronous helper executed in a thread pool."""
        name = self._tool_info.get("name", "")
        client = self._pool.get_client(self._server)
        try:
            result = client.call_tool(name, params)
            return ToolResult(success=True, data=result, metadata={"source": "mcp"})
        except Exception as exc:
            logger.warning("Async MCP tool '%s' invocation failed: %s", name, exc)
            return ToolResult(
                success=False,
                error=str(exc),
                metadata={"source": "mcp", "tool": name},
            )
        finally:
            self._pool.release_client(self._server.name)
