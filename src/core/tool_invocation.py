"""Central policy-gated tool invocation service."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from core.approval_workflow import ApprovalRequest
from core.events import EventType
from core.ledger import RunLedger
from core.policy_engine import PolicyConfig, PolicyDecision, PolicyEngine
from core.redaction import redact_dict
from core.tool_protocol import (
    AsyncBaseTool,
    RiskLevel,
    ToolContext,
    ToolRegistry,
    ToolResult,
)


@dataclass(frozen=True)
class ToolInvocationResult:
    success: bool
    data: Any = None
    error: str | None = None
    metadata: dict[str, Any] | None = None
    requires_approval: bool = False
    policy: PolicyDecision | None = None


def interface_policy_config() -> PolicyConfig:
    """Policy defaults for non-interactive interfaces.

    LOW/NONE operations run, MEDIUM operations return an approval request, and
    HIGH/CRITICAL operations are denied until an explicit approval path exists.
    """
    return PolicyConfig(
        risk_rules={
            RiskLevel.NONE: "allow",
            RiskLevel.LOW: "allow",
            RiskLevel.MEDIUM: "ask",
            RiskLevel.HIGH: "deny",
            RiskLevel.CRITICAL: "deny",
        }
    )


class ToolInvoker:
    """Policy, audit, and execution wrapper for tool calls."""

    def __init__(
        self,
        *,
        registry: ToolRegistry,
        policy_engine: PolicyEngine | None = None,
        policy_config: PolicyConfig | None = None,
    ) -> None:
        self.registry = registry
        self.policy_engine = policy_engine or PolicyEngine(policy_config)

    def invoke(
        self,
        tool_id: str,
        params: dict[str, Any],
        context: ToolContext,
        *,
        ledger: RunLedger | None = None,
        step_id: str | None = None,
        agent_id: str | None = None,
        granted_request: ApprovalRequest | None = None,
    ) -> ToolInvocationResult:
        tool = self.registry.get(tool_id)
        if isinstance(tool, AsyncBaseTool):
            return ToolInvocationResult(
                success=False, error=f"Tool '{tool_id}' requires async invocation"
            )

        risk_level = resolve_operation_risk(tool.tool_id, params, tool.risk_level)
        decision: PolicyDecision | None = None

        if granted_request is not None:
            decision = PolicyDecision(
                decision="allow",
                reason=f"Granted by approval request {granted_request.request_id}",
                policy_id="approval_override",
                risk_level=granted_request.risk_level,
                suggested_approval=None,
                override_possible=False,
            )
        else:
            policy_params = _policy_params(params, context)
            decision = self.policy_engine.evaluate(
                tool.tool_id,
                policy_params,
                context,
                risk_level,
                ledger=ledger,
                step_id=step_id,
                agent_id=agent_id,
            )
            if decision.decision == "ask":
                return ToolInvocationResult(
                    success=False,
                    error="approval_required",
                    metadata={"suggested_approval": decision.suggested_approval},
                    requires_approval=True,
                    policy=decision,
                )
            if decision.decision == "deny":
                return ToolInvocationResult(
                    success=False,
                    error=decision.reason,
                    metadata={},
                    requires_approval=False,
                    policy=decision,
                )

        _emit_tool_called(ledger, tool.tool_id, params, step_id, agent_id, risk_level)
        result = tool.invoke(params, context)
        _emit_tool_result(ledger, tool.tool_id, result, step_id, agent_id)
        return ToolInvocationResult(
            success=result.success,
            data=result.data,
            error=result.error,
            metadata=result.metadata,
            requires_approval=False,
            policy=decision,
        )


def resolve_operation_risk(tool_id: str, params: dict[str, Any], default: RiskLevel) -> RiskLevel:
    """Return operation-specific risk when a tool has mixed-risk actions."""
    if tool_id == "filesystem":
        operation = str(params.get("operation", "")).lower()
        if operation in {"read", "list", "stat"}:
            return RiskLevel.NONE
        if operation in {"write", "copy"}:
            return RiskLevel.MEDIUM
    if tool_id == "shell.execute" and _shell_command_is_read_only(params.get("command")):
        return RiskLevel.LOW
    return default


def _shell_command_is_read_only(command: Any) -> bool:
    if not isinstance(command, list) or not command:
        return False
    parts = [str(part) for part in command]
    head = parts[0].lower()
    joined = " ".join(parts).lower()
    if head in {"dir", "type", "cat", "ls", "rg"}:
        return True
    if head == "git" and any(token in joined for token in ("status", "diff", "show", "log")):
        return True
    if head == "python" and len(parts) >= 3 and parts[1] == "-c":
        snippet = parts[2].lower()
        if not re.search(r"\b(open|read|assert|pathlib|exists|is_file|is_dir)\b", snippet):
            return False
        blocked = (
            "write(",
            "unlink(",
            "remove(",
            "rename(",
            "replace(",
            "mkdir(",
            "rmdir(",
            "touch(",
            "chmod(",
            "subprocess",
            "os.system",
        )
        return not any(token in snippet for token in blocked)
    return False


def _policy_params(params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    """Normalize relative filesystem paths before policy boundary checks."""
    normalized = dict(params)
    raw_path = normalized.get("path")
    if isinstance(raw_path, str) and raw_path:
        path = (context.workspace / raw_path).resolve()
        normalized["path"] = str(path)
    return normalized


def _emit_tool_called(
    ledger: RunLedger | None,
    tool_id: str,
    params: dict[str, Any],
    step_id: str | None,
    agent_id: str | None,
    risk_level: RiskLevel,
) -> None:
    if ledger is None:
        return
    ledger.emit_event(
        EventType.TOOL_CALLED,
        step_id=step_id,
        agent_id=agent_id,
        tool_id=tool_id,
        payload={"params_redacted": redact_dict(params), "risk_level": risk_level.value},
    )


def _emit_tool_result(
    ledger: RunLedger | None,
    tool_id: str,
    result: ToolResult,
    step_id: str | None,
    agent_id: str | None,
) -> None:
    if ledger is None:
        return
    ledger.emit_event(
        EventType.TOOL_RESULT_RECEIVED,
        step_id=step_id,
        agent_id=agent_id,
        tool_id=tool_id,
        payload={
            "success": result.success,
            "error": result.error,
            "metadata": result.metadata,
        },
    )
