"""Approval workflow — 6-field disclosure and mediated approval.

Transforms a ``PolicyDecision`` with ``decision == "ask"`` into a structured
``ApprovalRequest`` that exposes exactly six fields for user disclosure:

1. **tool_id** — what tool is being requested
2. **action** — what operation (read, write, invoke, delete, …)
3. **target** — what resource (path, URL, command, …)
4. **risk_level** — the assessed risk (NONE → CRITICAL)
5. **justification** — why approval is required
6. **params_redacted** — redacted snapshot of invocation parameters

The ``ApprovalWorkflow`` class tracks pending requests and emits
``APPROVAL_REQUESTED``, ``APPROVAL_GRANTED``, and ``APPROVAL_DENIED`` events
to a ``RunLedger`` when one is provided.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

from core.events import EventType
from core.ledger import RunLedger
from core.policy_engine import PolicyDecision
from core.redaction import redact_dict
from core.tool_protocol import RiskLevel


def _policy_explanation(risk_level: RiskLevel) -> str:
    """Return a human-readable policy explanation for the given risk level."""
    explanations = {
        RiskLevel.NONE: "No risk. Operation is safe and does not require approval.",
        RiskLevel.LOW: "Low risk. Read-only or non-destructive operation.",
        RiskLevel.MEDIUM: "Medium risk. This operation can modify files or execute commands. Review the target and parameters before approving.",
        RiskLevel.HIGH: "High risk. This operation can cause significant changes or access sensitive resources. Explicit approval is required.",
        RiskLevel.CRITICAL: "Critical risk. This operation can cause irreversible damage or expose secrets. Maximum scrutiny is required.",
    }
    return explanations.get(risk_level, "Review carefully.")


@dataclass(frozen=True)
class ApprovalRequest:
    """Structured approval request with 6-field disclosure.

    All fields are immutable. ``params_redacted`` is pre-redacted so that
    the request object is safe to log, serialise, or display without
    leaking secrets.
    """

    request_id: str
    tool_id: str
    action: str
    target: str
    risk_level: RiskLevel
    justification: str
    params_redacted: dict[str, Any]
    timestamp: str
    decision: str
    policy_id: str
    override_possible: bool

    @classmethod
    def from_decision(
        cls,
        decision: PolicyDecision,
        tool_id: str,
        params: dict[str, Any],
    ) -> ApprovalRequest:
        """Build an ``ApprovalRequest`` from a policy ``ask`` / ``deny`` decision."""
        action = params.get("operation", "invoke")
        target = params.get("path", params.get("url", params.get("command", tool_id)))
        explanation = _policy_explanation(decision.risk_level)
        return cls(
            request_id=str(uuid4()),
            tool_id=tool_id,
            action=str(action),
            target=str(target),
            risk_level=decision.risk_level,
            justification=(
                f"{decision.reason}"
                f" | Suggested: {decision.suggested_approval or 'Review carefully'}"
                f" | Policy: {explanation}"
            ),
            params_redacted=cast(dict[str, Any], redact_dict(params)),
            timestamp=datetime.now(UTC).isoformat(),
            decision=decision.decision,
            policy_id=decision.policy_id,
            override_possible=decision.override_possible,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict (safe for JSON / ledger payload)."""
        return {
            "request_id": self.request_id,
            "tool_id": self.tool_id,
            "action": self.action,
            "target": self.target,
            "risk_level": self.risk_level.value,
            "justification": self.justification,
            "params_redacted": self.params_redacted,
            "timestamp": self.timestamp,
            "decision": self.decision,
            "policy_id": self.policy_id,
            "override_possible": self.override_possible,
        }


@dataclass
class ApprovalWorkflow:
    """Manages pending approval requests and emits ledger events.

    Usage::

        workflow = ApprovalWorkflow(ledger=run_ledger)
        req = workflow.request(policy_decision, tool_id, params)
        # … present ``req`` to user …
        workflow.grant(req.request_id)   # or workflow.deny(...)
    """

    ledger: RunLedger | None = None
    _pending: dict[str, ApprovalRequest] = field(default_factory=dict, repr=False)

    def request(
        self,
        decision: PolicyDecision,
        tool_id: str,
        params: dict[str, Any],
    ) -> ApprovalRequest:
        """Create an approval request from a policy decision."""
        req = ApprovalRequest.from_decision(decision, tool_id, params)
        self._pending[req.request_id] = req

        if self.ledger:
            self.ledger.emit_event(
                EventType.APPROVAL_REQUESTED,
                tool_id=tool_id,
                payload=req.to_dict(),
            )
        return req

    def grant(self, request_id: str) -> ApprovalRequest | None:
        """Grant a pending approval request.

        Returns the request object or ``None`` if the request_id is unknown.
        """
        req = self._pending.pop(request_id, None)
        if req is None:
            return None

        if self.ledger:
            self.ledger.emit_event(
                EventType.APPROVAL_GRANTED,
                tool_id=req.tool_id,
                payload={"request_id": request_id, "tool_id": req.tool_id},
            )
        return req

    def deny(self, request_id: str) -> ApprovalRequest | None:
        """Deny a pending approval request.

        Returns the request object or ``None`` if the request_id is unknown.
        """
        req = self._pending.pop(request_id, None)
        if req is None:
            return None

        if self.ledger:
            self.ledger.emit_event(
                EventType.APPROVAL_DENIED,
                tool_id=req.tool_id,
                payload={
                    "request_id": request_id,
                    "tool_id": req.tool_id,
                    "reason": "User denied",
                },
            )
        return req

    def get_pending(self, request_id: str) -> ApprovalRequest | None:
        """Look up a pending request by id."""
        return self._pending.get(request_id)

    def list_pending(self) -> list[ApprovalRequest]:
        """Return all currently pending requests."""
        return list(self._pending.values())
