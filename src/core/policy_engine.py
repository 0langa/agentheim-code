"""Policy engine — gatekeeper for all tool invocations.

Evaluates every tool call against configured policies and returns a decision.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal

from core.events import EventType
from core.ledger import RunLedger
from core.tool_protocol import RiskLevel, ToolContext


class DecisionType(Enum):
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"
    PATH_BOUNDARY = "path_boundary"
    COMMAND_ALLOWLIST = "command_allowlist"
    COMMAND_DENYLIST = "command_denylist"
    NETWORK_RESTRICTION = "network_restriction"
    DELETE_RESTRICTION = "delete_restriction"
    BUDGET_LIMIT = "budget_limit"
    LOCAL_ONLY = "local_only"
    STRICT_PRIVATE = "strict_private"


@dataclass(frozen=True)
class PolicyDecision:
    decision: Literal["allow", "deny", "ask"]
    reason: str
    policy_id: str
    risk_level: RiskLevel
    suggested_approval: str | None = None
    override_possible: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PolicyConfig:
    """Runtime policy configuration."""

    risk_rules: dict[RiskLevel, Literal["allow", "ask", "deny"]] = field(
        default_factory=lambda: {
            RiskLevel.NONE: "allow",
            RiskLevel.LOW: "allow",
            RiskLevel.MEDIUM: "ask",
            RiskLevel.HIGH: "ask",
            RiskLevel.CRITICAL: "deny",
        }
    )
    path_boundaries_allowed: list[str] = field(default_factory=list)
    path_boundaries_denied: list[str] = field(default_factory=list)
    command_allowlist: list[str] = field(default_factory=list)
    command_denylist: list[str] = field(default_factory=list)
    network_allowed: bool = False
    network_allowed_hosts: list[str] = field(default_factory=list)
    delete_allowed: bool = False
    delete_require_reason: bool = True
    budget_max_tokens: int | None = None
    budget_max_cost: float | None = None
    budget_max_wall_time: int | None = None
    local_only: bool = False
    strict_private: bool = False
    sensitive_patterns: list[str] = field(
        default_factory=lambda: ["*.key", "*.pem", "*.env", "*secret*"]
    )


class PolicyEngine:
    """Evaluates tool calls against policies."""

    def __init__(self, config: PolicyConfig | None = None) -> None:
        self.config = config or PolicyConfig()

    def evaluate(
        self,
        tool_id: str,
        params: dict[str, Any],
        context: ToolContext,
        risk_level: RiskLevel,
        *,
        ledger: RunLedger | None = None,
        step_id: str | None = None,
        agent_id: str | None = None,
    ) -> PolicyDecision:
        """Evaluate a tool call against all policies.

        Evaluation order follows the flow in 10_TOOL_AND_POLICY_SYSTEM.md:
        1. local_only
        2. strict_private
        3. budget limits
        4. path boundaries
        5. command allowlist/denylist
        6. network restrictions
        7. delete restrictions
        8. risk level

        If *ledger* is provided, a ``POLICY_EVALUATED`` event is emitted
        automatically.  All new keyword arguments are optional and fully
        backward-compatible.
        """
        # 1. local_only mode
        if self.config.local_only and (
            tool_id in {"http.request", "git.push", "git.clone"} or tool_id.startswith("http.")
        ):
            decision = PolicyDecision(
                decision="deny",
                reason=f"Tool '{tool_id}' requires network access but local_only mode is enabled.",
                policy_id="local_only",
                risk_level=RiskLevel.HIGH,
                override_possible=False,
            )
            self._emit_policy_event(decision, tool_id, params, ledger, step_id, agent_id)
            return decision

        # 2. strict_private mode
        if self.config.strict_private:
            path = params.get("path", "")
            if path and self._is_sensitive(str(path)):
                decision = PolicyDecision(
                    decision="deny",
                    reason=f"Access to sensitive file '{path}' blocked by strict_private policy.",
                    policy_id="strict_private",
                    risk_level=RiskLevel.CRITICAL,
                    override_possible=False,
                )
                self._emit_policy_event(decision, tool_id, params, ledger, step_id, agent_id)
                return decision

        # 3. budget limits
        budget_reason = self._check_budget(context)
        if budget_reason:
            decision = PolicyDecision(
                decision="deny",
                reason=budget_reason,
                policy_id="budget_limit",
                risk_level=RiskLevel.HIGH,
                override_possible=False,
            )
            self._emit_policy_event(decision, tool_id, params, ledger, step_id, agent_id)
            return decision

        # 4. path boundaries
        path = params.get("path", "")
        if path and not context.path_allowed(path):
            decision = PolicyDecision(
                decision="deny",
                reason=f"Path '{path}' is outside allowed boundaries.",
                policy_id="path_boundary",
                risk_level=RiskLevel.HIGH,
                override_possible=False,
            )
            self._emit_policy_event(decision, tool_id, params, ledger, step_id, agent_id)
            return decision

        # 5. command allowlist/denylist
        command = params.get("command", [])
        if command:
            cmd_str = " ".join(command) if isinstance(command, list) else str(command)
            for denied in self.config.command_denylist:
                if denied in cmd_str:
                    decision = PolicyDecision(
                        decision="deny",
                        reason=f"Command contains denied pattern: '{denied}'.",
                        policy_id="command_denylist",
                        risk_level=RiskLevel.CRITICAL,
                        override_possible=False,
                    )
                    self._emit_policy_event(decision, tool_id, params, ledger, step_id, agent_id)
                    return decision
            if self.config.command_allowlist:
                first = command[0] if isinstance(command, list) else cmd_str.split()[0]
                if first not in self.config.command_allowlist:
                    decision = PolicyDecision(
                        decision="deny",
                        reason=f"Command '{first}' is not in the allowlist.",
                        policy_id="command_allowlist",
                        risk_level=RiskLevel.HIGH,
                        override_possible=False,
                    )
                    self._emit_policy_event(decision, tool_id, params, ledger, step_id, agent_id)
                    return decision

        # 6. network restrictions
        if tool_id.startswith("http.") and not self.config.network_allowed:
            decision = PolicyDecision(
                decision="deny",
                reason="Network access is not allowed by policy.",
                policy_id="network_restriction",
                risk_level=RiskLevel.HIGH,
                override_possible=False,
            )
            self._emit_policy_event(decision, tool_id, params, ledger, step_id, agent_id)
            return decision

        # 7. delete restrictions
        if "delete" in tool_id and not self.config.delete_allowed:
            decision = PolicyDecision(
                decision="deny" if not self.config.delete_require_reason else "ask",
                reason="Delete operations require explicit approval.",
                policy_id="delete_restriction",
                risk_level=RiskLevel.HIGH,
                suggested_approval="Provide a reason for deletion.",
                override_possible=True,
            )
            self._emit_policy_event(decision, tool_id, params, ledger, step_id, agent_id)
            return decision

        # 8. risk level evaluation
        action = self.config.risk_rules.get(risk_level, "deny")
        if action == "deny":
            decision = PolicyDecision(
                decision="deny",
                reason=f"Risk level '{risk_level.value}' is configured to deny by default.",
                policy_id="risk_level",
                risk_level=risk_level,
                override_possible=False,
            )
            self._emit_policy_event(decision, tool_id, params, ledger, step_id, agent_id)
            return decision
        if action == "ask":
            decision = PolicyDecision(
                decision="ask",
                reason=f"Risk level '{risk_level.value}' requires approval.",
                policy_id="risk_level",
                risk_level=risk_level,
                suggested_approval=f"Review the {tool_id} invocation before proceeding.",
                override_possible=True,
            )
            self._emit_policy_event(decision, tool_id, params, ledger, step_id, agent_id)
            return decision

        decision = PolicyDecision(
            decision="allow",
            reason=f"Tool '{tool_id}' passed all policy checks.",
            policy_id="default",
            risk_level=risk_level,
            override_possible=False,
        )
        self._emit_policy_event(decision, tool_id, params, ledger, step_id, agent_id)
        return decision

    def _emit_policy_event(
        self,
        decision: PolicyDecision,
        tool_id: str,
        params: dict[str, Any],
        ledger: RunLedger | None,
        step_id: str | None,
        agent_id: str | None,
    ) -> None:
        """Emit a POLICY_EVALUATED event to the ledger if one is available."""
        if ledger is None:
            return
        from core.redaction import redact_dict

        ledger.emit_event(
            EventType.POLICY_EVALUATED,
            step_id=step_id,
            agent_id=agent_id,
            tool_id=tool_id,
            payload={
                "decision": decision.decision,
                "reason": decision.reason,
                "policy_id": decision.policy_id,
                "risk_level": decision.risk_level.value,
                "override_possible": decision.override_possible,
                "params_redacted": redact_dict(params),
            },
        )

    def _check_budget(self, context: ToolContext) -> str | None:
        """Check if budget limits are exceeded. Returns reason or None."""
        budget = context.budget
        if budget.max_calls is not None and budget.calls_used >= budget.max_calls:
            return f"Tool call budget exceeded ({budget.calls_used}/{budget.max_calls})."
        return None

    def _is_sensitive(self, path: str) -> bool:
        """Check if a path matches sensitive patterns."""
        from fnmatch import fnmatch

        for pattern in self.config.sensitive_patterns:
            if fnmatch(path.lower(), pattern.lower()):
                return True
        return False
