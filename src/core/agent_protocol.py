"""Agent communication protocol schemas.

Defines the message formats for agent request/response cycles.
These are intentionally separate from the workflow-scoped schemas in
`core/schemas.py` to provide a clean runtime protocol boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.ledger import RunLedger
from core.policy_engine import PolicyEngine
from core.tool_protocol import ToolRegistry


@dataclass(frozen=True)
class AgentMessage:
    """A single message in an agent conversation.

    Uses `role` (not `actor`) to align with standard LLM APIs.
    """

    role: str  # e.g. "system", "user", "assistant", "tool"
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentRequest:
    """Request sent to an agent for execution."""

    agent_id: str
    messages: list[AgentMessage] = field(default_factory=list)
    tools: ToolRegistry = field(default_factory=ToolRegistry)
    context: AgentContext = field(default_factory=lambda: AgentContext())


@dataclass
class AgentResponse:
    """Response received from an agent."""

    content: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    finish_reason: str = ""


@dataclass
class AgentContext:
    """Runtime context passed to an agent during execution.

    Mirrors the fields in `StepContext` but as a plain dataclass
    for lightweight serialization and protocol stability.
    """

    run_id: str = ""
    step_id: str = ""
    repo_root: Path = field(default_factory=lambda: Path("."))
    tools: ToolRegistry = field(default_factory=ToolRegistry)
    policy: PolicyEngine | None = None
    ledger: RunLedger | None = None
    working_memory: dict[str, Any] = field(default_factory=dict)
    prior_results: list[AgentMessage] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict (excludes non-serializable objects)."""
        return {
            "run_id": self.run_id,
            "step_id": self.step_id,
            "repo_root": str(self.repo_root),
            "working_memory": self.working_memory,
            "prior_results": [
                {"role": m.role, "content": m.content, "metadata": m.metadata}
                for m in self.prior_results
            ],
        }

    @classmethod
    def from_step_context(cls, step_context: Any) -> AgentContext:
        """Build an AgentContext from a workflows.base.StepContext instance."""
        return cls(
            run_id=step_context.run_id,
            step_id=step_context.step_id,
            repo_root=step_context.repo_root,
            tools=step_context.tools,
            policy=step_context.policy,
            ledger=step_context.ledger,
            working_memory=(
                step_context.working_memory.snapshot()
                if step_context.working_memory is not None
                else {}
            ),
            prior_results=[
                AgentMessage(role="assistant", content=r.output, metadata=r.metadata)
                for r in step_context.prior_results.values()
                if hasattr(r, "output")
            ],
        )
