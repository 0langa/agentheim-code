"""Deterministic replay engine — reconstruct run state from ledger events.

Given a sequence of immutable ``Event`` records, ``ReplayEngine`` rebuilds the
``RunState`` that existed at the end of the sequence.  This is the foundation
for resuming interrupted workflows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.events import Event, EventType
from workflows.base import StepResult


@dataclass
class RunState:
    """Reconstructed state of a workflow run from its event ledger.

    Attributes:
        prior_results:      Map of step_id → StepResult for every step that
                            emitted a ``STATE_TRANSITION`` event.
        completed_steps:    Steps that transitioned to "completed".
        failed_steps:       Steps that transitioned to "failed".
        skipped_steps:      Steps that transitioned to "skipped".
        checkpoint_sequence: Highest checkpoint sequence observed.
        metadata:           Arbitrary metadata extracted from ``RUN_INITIATED``.
    """

    prior_results: dict[str, StepResult] = field(default_factory=dict)
    completed_steps: set[str] = field(default_factory=set)
    failed_steps: set[str] = field(default_factory=set)
    skipped_steps: set[str] = field(default_factory=set)
    checkpoint_sequence: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class ReplayEngine:
    """Replays ledger events to reconstruct a ``RunState``."""

    def replay(self, events: list[Event]) -> RunState:
        """Reconstruct state from an ordered list of events.

        Idempotent: replaying the same event list twice yields the same state.
        """
        state = RunState()

        for event in events:
            if event.event_type == EventType.STATE_TRANSITION:
                self._apply_state_transition(event, state)
            elif event.event_type == EventType.CHECKPOINT_SAVED:
                seq = event.payload.get("sequence", 0)
                state.checkpoint_sequence = max(state.checkpoint_sequence, seq)
            elif event.event_type == EventType.RUN_INITIATED:
                state.metadata["workflow_id"] = event.payload.get("workflow_id")
                state.metadata["repo_root"] = event.payload.get("repo_root")
                state.metadata["run_id"] = event.run_id

        return state

    @staticmethod
    def _apply_state_transition(event: Event, state: RunState) -> None:
        step_id = event.step_id or ""
        status = event.payload.get("to", "")

        if status == "completed":
            state.completed_steps.add(step_id)
            state.prior_results[step_id] = StepResult(
                step_id=step_id,
                success=True,
                output=event.payload.get("output_preview", ""),
            )
        elif status == "failed":
            state.failed_steps.add(step_id)
            state.prior_results[step_id] = StepResult(
                step_id=step_id,
                success=False,
                output="",
                metadata={"error": event.payload.get("reason", "step failed")},
            )
        elif status == "skipped":
            state.skipped_steps.add(step_id)
            state.prior_results[step_id] = StepResult(
                step_id=step_id,
                success=True,
                output="Skipped by condition",
            )
