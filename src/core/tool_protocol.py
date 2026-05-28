"""Mediated tool invocation protocol.

All side effects go through named, policy-checked tools. This is the ONLY path
from agent decision to system action.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


class RiskLevel(Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class ParamSchema:
    type: str
    description: str
    required: bool = True
    default: Any | None = None
    enum: list[str] | None = None


@dataclass(frozen=True)
class ReturnSchema:
    type: str
    description: str


@dataclass(frozen=True)
class ToolExample:
    params: dict[str, Any]
    result: Any


@dataclass(frozen=True)
class ToolSchema:
    description: str
    parameters: dict[str, ParamSchema]
    returns: ReturnSchema
    examples: list[ToolExample] = field(default_factory=list)


@dataclass
class ToolBudget:
    max_calls: int | None = None
    calls_used: int = 0


@dataclass
class ToolContext:
    run_id: str = ""
    step_id: str = ""
    agent_id: str = ""
    allowed_paths: list[str] = field(default_factory=list)
    denied_paths: list[str] = field(default_factory=list)
    allowed_commands: list[str] = field(default_factory=list)
    denied_commands: list[str] = field(default_factory=list)
    network_allowed: bool = False
    max_file_size: int = 1_000_000
    budget: ToolBudget = field(default_factory=lambda: ToolBudget())
    workspace: Path = field(default_factory=lambda: Path(".").resolve())

    def path_allowed(self, target: str | Path) -> bool:
        """Check if a path is within allowed boundaries."""
        target = Path(target).resolve()
        # Check denied paths first
        for denied in self.denied_paths:
            denied_path = Path(denied).resolve()
            try:
                target.relative_to(denied_path)
                return False
            except ValueError:
                pass
        # Check allowed paths
        if not self.allowed_paths:
            return True
        for allowed in self.allowed_paths:
            allowed_path = Path(allowed).resolve()
            try:
                target.relative_to(allowed_path)
                return True
            except ValueError:
                pass
        return False

    def command_allowed(self, command: list[str]) -> bool:
        """Check if a command passes allowlist/denylist."""
        if not command:
            return False
        cmd_str = " ".join(command)
        # Check denylist
        for denied in self.denied_commands:
            if denied in cmd_str:
                return False
        # Check allowlist
        if self.allowed_commands:
            first = command[0]
            if first not in self.allowed_commands:
                return False
        return True


@dataclass(frozen=True)
class ToolResult:
    success: bool
    data: Any = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class ToolProtocol(Protocol):
    @property
    def tool_id(self) -> str: ...

    @property
    def schema(self) -> ToolSchema: ...

    @property
    def risk_level(self) -> RiskLevel: ...

    def invoke(self, params: dict[str, Any], context: ToolContext) -> ToolResult: ...


class BaseTool(ABC):
    """Abstract base for all synchronous tools."""

    def __init__(self, tool_id: str, schema: ToolSchema, risk_level: RiskLevel) -> None:
        self._tool_id = tool_id
        self._schema = schema
        self._risk_level = risk_level

    @property
    def tool_id(self) -> str:
        return self._tool_id

    @property
    def schema(self) -> ToolSchema:
        return self._schema

    @property
    def risk_level(self) -> RiskLevel:
        return self._risk_level

    @abstractmethod
    def invoke(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        raise NotImplementedError

    def validate_params(self, params: dict[str, Any]) -> tuple[bool, str]:
        """Validate parameters against schema."""
        for name, param_schema in self._schema.parameters.items():
            if param_schema.required and name not in params:
                return False, f"Missing required parameter: {name}"
        return True, ""


@runtime_checkable
class AsyncToolProtocol(Protocol):
    """Protocol for async-capable tools."""

    @property
    def tool_id(self) -> str: ...

    @property
    def schema(self) -> ToolSchema: ...

    @property
    def risk_level(self) -> RiskLevel: ...

    async def ainvoke(self, params: dict[str, Any], context: ToolContext) -> ToolResult: ...


class AsyncBaseTool(ABC):
    """Abstract base for all async tools."""

    def __init__(self, tool_id: str, schema: ToolSchema, risk_level: RiskLevel) -> None:
        self._tool_id = tool_id
        self._schema = schema
        self._risk_level = risk_level

    @property
    def tool_id(self) -> str:
        return self._tool_id

    @property
    def schema(self) -> ToolSchema:
        return self._schema

    @property
    def risk_level(self) -> RiskLevel:
        return self._risk_level

    @abstractmethod
    async def ainvoke(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        raise NotImplementedError

    def validate_params(self, params: dict[str, Any]) -> tuple[bool, str]:
        """Validate parameters against schema."""
        for name, param_schema in self._schema.parameters.items():
            if param_schema.required and name not in params:
                return False, f"Missing required parameter: {name}"
        return True, ""


class ToolRegistry:
    """Registry for tool discovery and lookup. Supports both sync and async tools."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool | AsyncBaseTool] = {}

    def register(self, tool: BaseTool | AsyncBaseTool) -> None:
        if tool.tool_id in self._tools:
            raise ValueError(f"Tool '{tool.tool_id}' already registered.")
        self._tools[tool.tool_id] = tool

    def get(self, tool_id: str) -> BaseTool | AsyncBaseTool:
        if tool_id not in self._tools:
            raise KeyError(f"Tool '{tool_id}' not found.")
        return self._tools[tool_id]

    def get_async(self, tool_id: str) -> AsyncBaseTool:
        """Retrieve a tool and assert it supports async invocation."""
        tool = self.get(tool_id)
        if not isinstance(tool, AsyncBaseTool):
            raise TypeError(f"Tool '{tool_id}' is not an async tool.")
        return tool

    def list_tools(self) -> list[str]:
        return sorted(self._tools.keys())

    def discover_by_prefix(self, prefix: str) -> list[BaseTool | AsyncBaseTool]:
        return [tool for tid, tool in self._tools.items() if tid.startswith(prefix)]
