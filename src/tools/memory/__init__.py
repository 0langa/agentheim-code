"""Memory tool implementing ToolProtocol.

Structured memory read/write with scope: run, repository, global.
"""

from __future__ import annotations

import json
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


class MemoryTool(BaseTool):
    """Read and write structured memory scoped to run, repo, or global."""

    def __init__(self, base_dir: str | Path = ".ai-team/memory") -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        schema = ToolSchema(
            description="Read and write structured memory.",
            parameters={
                "operation": ParamSchema(
                    type="string",
                    description="Operation: read, write",
                    enum=["read", "write"],
                    required=True,
                ),
                "key": ParamSchema(type="string", description="Memory key", required=True),
                "scope": ParamSchema(
                    type="string",
                    description="Scope: run, repository, global",
                    enum=["run", "repository", "global"],
                    required=True,
                ),
                "value": ParamSchema(
                    type="any", description="Value for write operation", required=False
                ),
                "run_id": ParamSchema(
                    type="string", description="Run ID for run-scoped memory", required=False
                ),
            },
            returns=ReturnSchema(type="any", description="Memory value or confirmation"),
        )
        super().__init__("memory", schema, RiskLevel.LOW)

    def _path(self, key: str, scope: str, run_id: str | None = None) -> Path:
        scope_dir = self.base_dir / scope
        if scope == "run" and run_id:
            scope_dir = scope_dir / run_id
        scope_dir.mkdir(parents=True, exist_ok=True)
        # Sanitize key for filesystem
        safe_key = "".join(c if c.isalnum() or c in "-_./" else "_" for c in key)
        if not safe_key.endswith(".json"):
            safe_key += ".json"
        return scope_dir / safe_key

    def invoke(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        valid, err = self.validate_params(params)
        if not valid:
            return ToolResult(success=False, error=err)

        operation = params.get("operation")
        key = params.get("key", "")
        scope = params.get("scope", "global")
        run_id = params.get("run_id", context.run_id) or "default"

        path = self._path(key, scope, run_id if scope == "run" else None)

        if operation == "read":
            if not path.exists():
                return ToolResult(success=False, error=f"Memory key not found: {key}")
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return ToolResult(success=True, data=data)
            except (json.JSONDecodeError, OSError) as exc:
                return ToolResult(success=False, error=str(exc))

        if operation == "write":
            value = params.get("value")
            try:
                path.write_text(json.dumps(value, indent=2, default=str), encoding="utf-8")
                return ToolResult(
                    success=True, data={"key": key, "scope": scope, "path": str(path)}
                )
            except OSError as exc:
                return ToolResult(success=False, error=str(exc))

        return ToolResult(success=False, error=f"Unknown memory operation: {operation}")
