"""Structured event schema for the Agentheim Code event-sourced ledger.

All runtime activity is recorded as immutable, sequenced, hash-chained events.
This is the source of truth for replay, resume, and audit.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4


class EventType(StrEnum):
    """Canonical event types for the unified ledger.

    Every significant action in the system emits one of these events.
    """

    # Run lifecycle
    RUN_INITIATED = "run_initiated"
    CONFIG_LOADED = "config_loaded"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"
    RUN_RESUMED = "run_resumed"
    RUN_CANCELLED = "run_cancelled"

    # Phase / workflow
    PHASE_TRANSITION = "phase_transition"
    WORKFLOW_REGISTERED = "workflow_registered"
    PRESET_LOADED = "preset_loaded"

    # Agent / model
    AGENT_INVOKED = "agent_invoked"
    MODEL_SELECTED = "model_selected"
    FALLBACK_USED = "fallback_used"

    # Tool / safety
    TOOL_CALLED = "tool_called"
    TOOL_RESULT_RECEIVED = "tool_result_received"
    POLICY_EVALUATED = "policy_evaluated"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_GRANTED = "approval_granted"
    APPROVAL_DENIED = "approval_denied"

    # Budget / resource
    BUDGET_CHECKED = "budget_checked"
    BUDGET_EXCEEDED = "budget_exceeded"

    # Retry / error
    ERROR_CLASSIFIED = "error_classified"
    RETRY_ATTEMPTED = "retry_attempted"
    RETRY_EXHAUSTED = "retry_exhausted"

    # Artifact / context
    ARTIFACT_CREATED = "artifact_created"
    CONTEXT_PACKED = "context_packed"
    CONTEXT_SCANNED = "context_scanned"
    CONTEXT_GENERATED = "context_generated"
    CONTEXT_WRITTEN = "context_written"
    CONTEXT_VERIFIED = "context_verified"
    CONTEXT_INITIALIZED = "context_initialized"
    CONTEXT_PLANNED = "context_planned"
    CONTEXT_STALE_DETECTED = "context_stale_detected"
    PUBLIC_DOCS_IMPACT_MAPPED = "public_docs_impact_mapped"
    PUBLIC_DOCS_UPDATED = "public_docs_updated"

    # State / memory
    STATE_TRANSITION = "state_transition"
    CHECKPOINT_SAVED = "checkpoint_saved"
    MEMORY_ACCESSED = "memory_accessed"

    # Meta
    LEDGER_VERIFIED = "ledger_verified"


@dataclass(frozen=True, slots=True)
class Event:
    """Immutable event record for the unified ledger.

    Attributes:
        event_id: Unique identifier (UUID4).
        sequence: Monotonic sequence number within a run (0-indexed).
        timestamp: UTC datetime of creation.
        event_type: Canonical event type.
        run_id: Run identifier (typically run directory name).
        step_id: Optional step identifier (for step-scoped events).
        agent_id: Optional agent identifier.
        tool_id: Optional tool identifier.
        phase: Optional workflow phase name.
        payload: Event-specific data (dict).
        metadata: System metadata (dict).
        parent_event_id: Optional parent event (for causal chains).
        previous_hash: SHA-256 hash of the previous event (hash chain).
    """

    event_id: UUID
    sequence: int
    timestamp: datetime
    event_type: EventType
    run_id: str
    step_id: str | None = None
    agent_id: str | None = None
    tool_id: str | None = None
    phase: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    parent_event_id: str | None = None
    previous_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict suitable for JSON."""
        return {
            "event_id": str(self.event_id),
            "sequence": self.sequence,
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type.value,
            "run_id": self.run_id,
            "step_id": self.step_id,
            "agent_id": self.agent_id,
            "tool_id": self.tool_id,
            "phase": self.phase,
            "payload": self.payload,
            "metadata": self.metadata,
            "parent_event_id": self.parent_event_id,
            "previous_hash": self.previous_hash,
        }

    def to_json(self) -> str:
        """Serialize to compact JSON string (sorted keys for determinism)."""
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

    def compute_hash(self) -> str:
        """Compute SHA-256 of this event's canonical JSON representation.

        The hash is computed over the event WITHOUT its own previous_hash field
        to avoid circular dependency. The previous_hash is included in the
        *next* event's hash computation implicitly by being part of that event's data.
        """
        # Create a copy without previous_hash for hash computation
        data = self.to_dict()
        data.pop("previous_hash", None)
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Event:
        """Deserialize from a plain dict."""
        return cls(
            event_id=UUID(data["event_id"]),
            sequence=data["sequence"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            event_type=EventType(data["event_type"]),
            run_id=data["run_id"],
            step_id=data.get("step_id"),
            agent_id=data.get("agent_id"),
            tool_id=data.get("tool_id"),
            phase=data.get("phase"),
            payload=data.get("payload", {}),
            metadata=data.get("metadata", {}),
            parent_event_id=data.get("parent_event_id"),
            previous_hash=data.get("previous_hash"),
        )

    @classmethod
    def from_json(cls, raw: str) -> Event:
        """Deserialize from a JSON string."""
        return cls.from_dict(json.loads(raw))

    @classmethod
    def create(
        cls,
        *,
        sequence: int,
        event_type: EventType,
        run_id: str,
        step_id: str | None = None,
        agent_id: str | None = None,
        tool_id: str | None = None,
        phase: str | None = None,
        payload: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        parent_event_id: str | None = None,
        previous_hash: str | None = None,
    ) -> Event:
        """Factory for creating a new event with auto-generated UUID and timestamp."""
        return cls(
            event_id=uuid4(),
            sequence=sequence,
            timestamp=datetime.now(UTC),
            event_type=event_type,
            run_id=run_id,
            step_id=step_id,
            agent_id=agent_id,
            tool_id=tool_id,
            phase=phase,
            payload=payload or {},
            metadata=metadata or {},
            parent_event_id=parent_event_id,
            previous_hash=previous_hash,
        )
