from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class MCPServerConfig:
    name: str
    command: list[str]
    env: dict[str, str] | None = None
    enabled: bool = True


def load_mcp_config(path: str | Path) -> list[MCPServerConfig]:
    """Load MCP server configurations from a JSON file.

    Also checks AI_TEAM_MCP_SERVERS_JSON env var for override.
    """
    env_override = os.getenv("AI_TEAM_MCP_SERVERS_JSON", "").strip()
    if env_override:
        raw = json.loads(env_override)
    else:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))

    servers: list[MCPServerConfig] = []
    for item in raw.get("servers", []):
        servers.append(
            MCPServerConfig(
                name=item.get("name", "unnamed"),
                command=list(item.get("command", [])),
                env=item.get("env"),
                enabled=item.get("enabled", True),
            )
        )
    return servers
