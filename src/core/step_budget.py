"""Step and run-level budget enforcement.

Tracks cumulative consumption of tokens, time, tool calls, and agent invocations.
Emits structured events before every check and on exhaustion.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from core.events import EventType
from core.ledger import RunLedger


@dataclass
class BudgetSnapshot:
    """Immutable snapshot of current budget consumption."""

    tokens_used: int = 0
    time_elapsed_seconds: float = 0.0
    tool_calls_used: int = 0
    agent_invocations_used: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "tokens_used": self.tokens_used,
            "time_elapsed_seconds": round(self.time_elapsed_seconds, 3),
            "tool_calls_used": self.tool_calls_used,
            "agent_invocations_used": self.agent_invocations_used,
        }


@dataclass
class BudgetLimits:
    """Configurable budget limits for a run or step."""

    max_tokens: int | None = None
    max_time_seconds: int | None = None
    max_tool_calls: int | None = None
    max_agent_invocations: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_tokens": self.max_tokens,
            "max_time_seconds": self.max_time_seconds,
            "max_tool_calls": self.max_tool_calls,
            "max_agent_invocations": self.max_agent_invocations,
        }


class BudgetExceededError(RuntimeError):
    """Raised when a budget limit is exceeded."""

    def __init__(self, message: str, limit_name: str, limit_value: int, current_value: int) -> None:
        super().__init__(message)
        self.limit_name = limit_name
        self.limit_value = limit_value
        self.current_value = current_value


class StepBudgetEnforcer:
    """Enforces budgets before every agent invocation and tool call.

    Thread-safe: all mutable state is local to the instance; external
    synchronization is required if the same enforcer is shared across
    threads.
    """

    def __init__(
        self,
        limits: BudgetLimits,
        ledger: RunLedger | None = None,
        run_id: str | None = None,
    ) -> None:
        self.limits = limits
        self.ledger = ledger
        self.run_id = run_id
        self._snapshot = BudgetSnapshot()
        self._start_time = time.monotonic()

    # ------------------------------------------------------------------
    # Consumption tracking
    # ------------------------------------------------------------------

    def record_tokens(self, count: int, step_id: str | None = None) -> None:
        """Record token consumption."""
        self._snapshot.tokens_used += count
        self._check_and_emit(
            "max_tokens", self._snapshot.tokens_used, self.limits.max_tokens, step_id
        )

    def record_tool_call(self, step_id: str | None = None) -> None:
        """Record a tool call."""
        self._snapshot.tool_calls_used += 1
        self._check_and_emit(
            "max_tool_calls", self._snapshot.tool_calls_used, self.limits.max_tool_calls, step_id
        )

    def record_agent_invocation(self, step_id: str | None = None) -> None:
        """Record an agent invocation."""
        self._snapshot.agent_invocations_used += 1
        self._check_and_emit(
            "max_agent_invocations",
            self._snapshot.agent_invocations_used,
            self.limits.max_agent_invocations,
            step_id,
        )

    def record_time(self, elapsed_seconds: float, step_id: str | None = None) -> None:
        """Record elapsed time (or let the enforcer measure it)."""
        self._snapshot.time_elapsed_seconds = elapsed_seconds
        self._check_and_emit(
            "time",
            int(self._snapshot.time_elapsed_seconds),
            self.limits.max_time_seconds,
            step_id,
        )

    # ------------------------------------------------------------------
    # Pre-operation checks
    # ------------------------------------------------------------------

    def check_budget(self, operation: str, step_id: str | None = None) -> bool:
        """Check whether all budget limits are still respected.

        Returns True if within budget, False if any limit exceeded.
        Emits BUDGET_CHECKED on every call; emits BUDGET_EXCEEDED and
        raises BudgetExceededError if over.
        """
        # Update elapsed time
        self._snapshot.time_elapsed_seconds = time.monotonic() - self._start_time

        # Check each limit
        exceeded: tuple[str, int, int] | None = None

        if (
            self.limits.max_tokens is not None
            and self._snapshot.tokens_used >= self.limits.max_tokens
        ):
            exceeded = ("max_tokens", self.limits.max_tokens, self._snapshot.tokens_used)
        elif (
            self.limits.max_time_seconds is not None
            and int(self._snapshot.time_elapsed_seconds) >= self.limits.max_time_seconds
        ):
            exceeded = (
                "max_time_seconds",
                self.limits.max_time_seconds,
                int(self._snapshot.time_elapsed_seconds),
            )
        elif (
            self.limits.max_tool_calls is not None
            and self._snapshot.tool_calls_used >= self.limits.max_tool_calls
        ):
            exceeded = (
                "max_tool_calls",
                self.limits.max_tool_calls,
                self._snapshot.tool_calls_used,
            )
        elif (
            self.limits.max_agent_invocations is not None
            and self._snapshot.agent_invocations_used >= self.limits.max_agent_invocations
        ):
            exceeded = (
                "max_agent_invocations",
                self.limits.max_agent_invocations,
                self._snapshot.agent_invocations_used,
            )

        # Emit checked event
        if self.ledger is not None:
            self.ledger.emit_event(
                EventType.BUDGET_CHECKED,
                step_id=step_id,
                payload={
                    "operation": operation,
                    "snapshot": self._snapshot.to_dict(),
                    "limits": self.limits.to_dict(),
                    "exceeded": exceeded is not None,
                },
            )

        if exceeded is not None:
            name, limit, current = exceeded
            if self.ledger is not None:
                self.ledger.emit_event(
                    EventType.BUDGET_EXCEEDED,
                    step_id=step_id,
                    payload={
                        "limit_name": name,
                        "limit_value": limit,
                        "current_value": current,
                        "operation": operation,
                    },
                )
            raise BudgetExceededError(
                f"Budget exceeded: {name} (limit={limit}, current={current})",
                name,
                limit,
                current,
            )

        return True

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _check_and_emit(
        self,
        name: str,
        current: int,
        limit: int | None,
        step_id: str | None = None,
    ) -> None:
        """Internal: check a single dimension and emit if exceeded."""
        if limit is None:
            return
        if current >= limit:
            if self.ledger is not None:
                self.ledger.emit_event(
                    EventType.BUDGET_EXCEEDED,
                    step_id=step_id,
                    payload={
                        "limit_name": name,
                        "limit_value": limit,
                        "current_value": current,
                    },
                )
            raise BudgetExceededError(
                f"Budget exceeded: {name} (limit={limit}, current={current})",
                name,
                limit,
                current,
            )

    def snapshot(self) -> BudgetSnapshot:
        """Return a copy of the current consumption snapshot."""
        self._snapshot.time_elapsed_seconds = time.monotonic() - self._start_time
        return BudgetSnapshot(
            tokens_used=self._snapshot.tokens_used,
            time_elapsed_seconds=self._snapshot.time_elapsed_seconds,
            tool_calls_used=self._snapshot.tool_calls_used,
            agent_invocations_used=self._snapshot.agent_invocations_used,
        )
