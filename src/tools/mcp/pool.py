"""Persistent MCP connection pool.

Manages long-lived MCPClient connections so that registered MCPTools
do not hold references to disconnected clients.
"""

from __future__ import annotations

import atexit
import logging
import threading
from typing import Any

from tools.mcp.client import MCPClient, MCPError
from tools.mcp.config import MCPServerConfig

logger = logging.getLogger(__name__)


class MCPConnectionPool:
    """Pool of persistent MCP connections keyed by server name.

    Usage:
        pool = MCPConnectionPool()
        client = pool.get_client(server)
        try:
            tools = client.list_tools()
            result = client.call_tool("echo", {"msg": "hi"})
        finally:
            pool.release_client(server.name)
    """

    def __init__(self) -> None:
        self._clients: dict[str, MCPClient] = {}
        self._lock = threading.Lock()
        self._refs: dict[str, int] = {}
        atexit.register(self._atexit_cleanup)

    def get_client(self, server: MCPServerConfig) -> MCPClient:
        """Return an active MCPClient for *server*, reconnecting if needed."""
        with self._lock:
            client = self._clients.get(server.name)
            if client is not None:
                # Check if process is still alive
                if client._proc is not None and client._proc.poll() is None:
                    self._refs[server.name] = self._refs.get(server.name, 0) + 1
                    return client
                # Dead connection — clean up and reconnect
                self._disconnect_locked(server.name)

            logger.info("Connecting to MCP server '%s'", server.name)
            client = MCPClient(server.command, env=server.env)
            try:
                client.connect()
            except MCPError:
                logger.warning("Failed to connect to MCP server '%s'", server.name)
                raise
            self._clients[server.name] = client
            self._refs[server.name] = 1
            return client

    def release_client(self, name: str) -> None:
        """Decrement reference count for *name*."""
        with self._lock:
            self._refs[name] = max(0, self._refs.get(name, 0) - 1)

    def disconnect(self, name: str) -> None:
        """Forcefully disconnect a named server."""
        with self._lock:
            self._disconnect_locked(name)

    def disconnect_all(self) -> None:
        """Disconnect all pooled clients."""
        with self._lock:
            for name in list(self._clients.keys()):
                self._disconnect_locked(name)

    def _atexit_cleanup(self) -> None:
        """Emergency cleanup registered with atexit.

        Prevents MCP server child-process leaks when the interpreter
        exits without an explicit disconnect_all() call.
        """
        try:
            self.disconnect_all()
        except Exception as exc:
            logger.warning("MCP pool atexit cleanup error: %s", exc)

    def _disconnect_locked(self, name: str) -> None:
        client = self._clients.pop(name, None)
        self._refs.pop(name, None)
        if client is not None:
            try:
                client.disconnect()
            except Exception as exc:
                logger.warning("Error disconnecting MCP server '%s': %s", name, exc)

    def __enter__(self) -> MCPConnectionPool:
        return self

    def __exit__(self, *args: Any) -> None:
        self.disconnect_all()
