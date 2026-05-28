from __future__ import annotations

import json
import logging
import platform
import subprocess
import threading
import time
from contextlib import suppress
from typing import Any, cast

logger = logging.getLogger(__name__)


class MCPError(Exception):
    """Raised when MCP protocol communication fails."""


class MCPClient:
    """Lightweight MCP client using stdio JSON-RPC transport.

    Does not require the official `mcp` package. Implements the subset
    of the protocol needed for tool discovery and invocation.
    """

    def __init__(
        self,
        command: list[str],
        env: dict[str, str] | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.command = command
        self.env = env
        self.timeout = timeout
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._msg_id = 0

    def _next_id(self) -> int:
        with self._lock:
            self._msg_id += 1
            return self._msg_id

    def connect(self) -> None:
        """Spawn the MCP server process and perform initialize handshake."""
        if self._proc is not None:
            return

        try:
            self._proc = subprocess.Popen(
                self.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=self.env,
            )
        except FileNotFoundError as exc:
            raise MCPError(f"MCP server command not found: {self.command[0]}") from exc

        # Send initialize request
        init_id = self._next_id()
        init_req = {
            "jsonrpc": "2.0",
            "id": init_id,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "agentheim-code", "version": "1.5.0"},
            },
        }
        self._send(init_req)
        init_resp = self._read_response(init_id)
        if init_resp is None:
            raise MCPError("MCP initialize timed out")
        if "error" in init_resp:
            raise MCPError(f"MCP initialize error: {init_resp['error']}")

        # Send initialized notification
        self._send(
            {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
            }
        )

    def _kill_proc_tree(self, pid: int) -> None:
        """Kill process *pid* and all descendants. Windows-safe."""
        try:
            import psutil

            parent = psutil.Process(pid)
            for child in parent.children(recursive=True):
                try:
                    child.kill()
                    child.wait(timeout=2)
                except psutil.NoSuchProcess:
                    pass
            parent.kill()
            parent.wait(timeout=2)
        except ImportError:
            # Fallback without psutil
            if platform.system() == "Windows":
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    capture_output=True,
                )
            else:
                import os
                import signal

                killpg = getattr(os, "killpg", None)
                getpgid = getattr(os, "getpgid", None)
                sigkill = getattr(signal, "SIGKILL", None)
                if callable(killpg) and callable(getpgid) and sigkill is not None:
                    with suppress(ProcessLookupError):
                        killpg(getpgid(pid), sigkill)
                else:
                    with suppress(ProcessLookupError):
                        os.kill(pid, signal.SIGTERM)
        except psutil.NoSuchProcess:
            pass

    def disconnect(self) -> None:
        """Terminate the MCP server process and its children."""
        proc = self._proc
        if proc is None:
            return
        self._proc = None

        # Close pipes first to avoid the child blocking on I/O
        for pipe in (proc.stdin, proc.stdout, proc.stderr):
            if pipe is not None:
                with suppress(Exception):
                    pipe.close()

        try:
            # Graceful termination first
            proc.terminate()
            proc.wait(timeout=3.0)
        except subprocess.TimeoutExpired:
            # Hard kill — entire tree on Windows, direct process on Unix
            try:
                if platform.system() == "Windows":
                    self._kill_proc_tree(proc.pid)
                else:
                    proc.kill()
                    proc.wait(timeout=2.0)
            except Exception as exc:
                logger.warning("MCP disconnect kill error: %s", exc)
        except Exception as exc:
            logger.warning("MCP disconnect error: %s", exc)

    def __enter__(self) -> MCPClient:
        self.connect()
        return self

    def __exit__(self, *args: Any) -> None:
        self.disconnect()

    def list_tools(self) -> list[dict[str, Any]]:
        """Discover tools exposed by the MCP server."""
        self._ensure_connected()
        req_id = self._next_id()
        req = {"jsonrpc": "2.0", "id": req_id, "method": "tools/list"}
        self._send(req)
        resp = self._read_response(req_id)
        if resp is None:
            raise MCPError("tools/list timed out")
        if "error" in resp:
            raise MCPError(f"tools/list error: {resp['error']}")
        result = resp.get("result", {})
        return list(result.get("tools", []))

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Invoke an MCP tool by name with arguments."""
        self._ensure_connected()
        req_id = self._next_id()
        req = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
        self._send(req)
        resp = self._read_response(req_id)
        if resp is None:
            raise MCPError(f"tools/call({name}) timed out")
        if "error" in resp:
            raise MCPError(f"tools/call({name}) error: {resp['error']}")
        return dict(resp.get("result", {}))

    def _ensure_connected(self) -> None:
        if self._proc is None or self._proc.poll() is not None:
            raise MCPError("MCP client not connected")

    def _send(self, msg: dict[str, Any]) -> None:
        if self._proc is None or self._proc.stdin is None:
            raise MCPError("MCP stdin not available")
        line = json.dumps(msg, ensure_ascii=False)
        self._proc.stdin.write(line + "\n")
        self._proc.stdin.flush()

    def _read_response(self, expected_id: int) -> dict[str, Any] | None:
        if self._proc is None or self._proc.stdout is None:
            return None
        deadline = time.time() + self.timeout
        while time.time() < deadline:
            try:
                line = self._proc.stdout.readline()
            except Exception:
                return None
            if not line:
                time.sleep(0.05)
                continue
            try:
                data = cast(dict[str, Any], json.loads(line))
            except json.JSONDecodeError:
                continue
            if data.get("id") == expected_id:
                return cast(dict[str, Any], data)
            # Ignore notifications / unsolicited messages
        return None
