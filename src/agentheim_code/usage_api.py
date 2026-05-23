"""Session usage aggregation from the RunLedger."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.events import EventType
from core.ledger import RunLedger
from core.public_api import safe_project_path


def aggregate_session_usage(workspace_root: str | Path, session_id: str) -> dict[str, Any]:
    """Read the session ledger and aggregate all AGENT_INVOKED events.

    Returns a dict with token totals, cost totals, and per-call breakdown.
    """
    workspace = safe_project_path(workspace_root)
    run_dir = workspace / ".ai-team" / "runs" / session_id
    if not run_dir.exists():
        return {
            "session_id": session_id,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "estimated_cost_usd": None,
            "calls": 0,
            "breakdown": [],
        }

    ledger = RunLedger(repo_root=workspace, run_dir=run_dir)
    # Load index if persisted, otherwise fall back to scanning all events
    ledger._load_index()
    events = ledger.query_index(event_type=EventType.AGENT_INVOKED)
    # If index is empty (no persisted index), scan all events directly
    if not events:
        events = [e for e in ledger.read_ledger() if e.event_type == EventType.AGENT_INVOKED]

    total_input = 0
    total_output = 0
    total_cost: float | None = 0.0
    breakdown: list[dict[str, Any]] = []

    for event in events:
        usage = event.payload.get("usage") or {}
        inp = usage.get("input_tokens", 0) or 0
        out = usage.get("output_tokens", 0) or 0
        cost = usage.get("total_cost_usd")
        total_input += inp
        total_output += out
        total_cost = (total_cost or 0.0) + cost if cost is not None else None
        breakdown.append(
            {
                "sequence": event.sequence,
                "timestamp": event.timestamp.isoformat(),
                "model": usage.get("model"),
                "provider": usage.get("provider"),
                "input_tokens": inp,
                "output_tokens": out,
                "total_tokens": usage.get("total_tokens", 0),
                "estimated_cost_usd": cost,
            }
        )

    return {
        "session_id": session_id,
        "input_tokens": total_input,
        "output_tokens": total_output,
        "total_tokens": total_input + total_output,
        "estimated_cost_usd": total_cost,
        "calls": len(breakdown),
        "breakdown": breakdown,
    }
