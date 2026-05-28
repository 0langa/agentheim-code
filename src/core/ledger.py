"""Tamper-evident, indexed, checkpoint-aware run ledger.

Replaces the thin file-writing helper with a production-grade event-sourced
ledger: unified JSONL event log, SHA-256 hash chain, multi-dimensional index,
and periodic checkpoints.
"""

from __future__ import annotations

import json
import re
import threading
from _thread import LockType
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from core.events import Event, EventType
from core.path_security import safe_child_path, safe_project_path


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "run"


@dataclass
class RunLedger:
    """Production run ledger with hash chain, indexing, and checkpoints.

    Backward-compatible: all pre-Phase 7 methods (`write_json`, `write_text`,
    `append_jsonl`) continue to work exactly as before.
    """

    repo_root: Path
    run_dir: Path

    # Internal mutable state (not part of the public dataclass interface)
    _sequence: int = field(default=0, repr=False)
    _lock: LockType = field(default_factory=threading.Lock, repr=False)
    _index: dict[str, dict[str, list[int]]] = field(
        default_factory=lambda: {
            "event_type": {},
            "phase": {},
            "agent_id": {},
            "tool_id": {},
            "step_id": {},
        },
        repr=False,
    )

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def create(cls, repo_root: Path, purpose: str) -> RunLedger:
        repo_root = safe_project_path(repo_root)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        run_dir = safe_child_path(repo_root, ".ai-team", "runs", f"{timestamp}-{slugify(purpose)}")
        run_dir.mkdir(parents=True, exist_ok=True)

        # Legacy files (backward compatibility)
        for filename in ("tool_calls.jsonl", "state_transitions.jsonl"):
            (run_dir / filename).touch(exist_ok=True)

        instance = cls(repo_root=repo_root, run_dir=run_dir)

        # Ensure unified ledger and checkpoint dir exist
        (run_dir / "checkpoints").mkdir(exist_ok=True)

        # If a previous ledger exists (resume), restore sequence from it
        if (run_dir / "ledger.jsonl").exists():
            instance._restore_sequence_from_ledger()

        return instance

    # ------------------------------------------------------------------
    # Legacy helpers (unchanged API, unchanged behaviour)
    # ------------------------------------------------------------------

    def _sanitize_value(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {key: self._sanitize_value(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._sanitize_value(item) for item in value]
        if isinstance(value, str):
            repo_prefix = str(self.repo_root)
            if value == repo_prefix:
                return "${REPO_ROOT}"
            if value.startswith(repo_prefix + "\\") or value.startswith(repo_prefix + "/"):
                relative = value[len(repo_prefix) :].lstrip("\\/")
                return f"${{REPO_ROOT}}/{relative.replace('\\', '/')}"
        return value

    def write_json(self, name: str, payload: dict[str, Any]) -> Path:
        path = self.run_dir / name
        sanitized = self._sanitize_value(payload)
        path.write_text(json.dumps(sanitized, indent=2, sort_keys=True), encoding="utf-8")
        return path

    def write_text(self, name: str, content: str) -> Path:
        path = self.run_dir / name
        path.write_text(content, encoding="utf-8")
        return path

    def append_jsonl(self, name: str, payload: dict[str, Any]) -> Path:
        path = self.run_dir / name
        sanitized = self._sanitize_value(payload)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(sanitized, sort_keys=True) + "\n")
        return path

    # ------------------------------------------------------------------
    # Unified event ledger (new in Phase 7)
    # ------------------------------------------------------------------

    def emit_event(
        self,
        event_type: EventType,
        *,
        step_id: str | None = None,
        agent_id: str | None = None,
        tool_id: str | None = None,
        phase: str | None = None,
        payload: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        parent_event_id: str | None = None,
    ) -> Event:
        """Append a structured event to the unified ledger.

        Thread-safe. Automatically manages sequence numbers, hash chain,
        and index updates.
        """
        with self._lock:
            previous_hash = self._read_last_hash()
            event = Event.create(
                sequence=self._sequence,
                event_type=event_type,
                run_id=self.run_dir.name,
                step_id=step_id,
                agent_id=agent_id,
                tool_id=tool_id,
                phase=phase,
                payload=payload,
                metadata=metadata,
                parent_event_id=parent_event_id,
                previous_hash=previous_hash,
            )

            self._append_to_ledger(event)
            self._update_index(event)
            self._append_hash(event)
            self._sequence += 1
            return event

    def append_event(
        self,
        event_type: EventType,
        payload: dict[str, Any],
    ) -> Event:
        """Convenience alias for emit_event with a positional event_type and payload."""
        return self.emit_event(event_type, payload=payload)

    def read_ledger(self) -> list[Event]:
        """Read all events from the unified ledger."""
        path = self.run_dir / "ledger.jsonl"
        if not path.exists():
            return []
        events = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    events.append(Event.from_json(line))
        return events

    # ------------------------------------------------------------------
    # Hash chain
    # ------------------------------------------------------------------

    def verify_chain(self) -> tuple[bool, list[str]]:
        """Verify the integrity of the hash chain.

        Checks both the event-to-event linkage AND that the parallel
        hash file entries match recomputed hashes.

        Returns:
            (is_valid, list_of_broken_links)
            Each broken link is a human-readable string describing where
            the chain was broken.
        """
        events = self.read_ledger()
        if not events:
            return True, []

        broken: list[str] = []

        # 1. Verify event-to-event linkage
        for i, event in enumerate(events):
            if i == 0:
                if event.previous_hash is not None and event.previous_hash != "0" * 64:
                    broken.append(
                        f"Event {event.sequence} (seq={event.sequence}): "
                        f"first event has unexpected previous_hash={event.previous_hash}"
                    )
                continue

            prev_event = events[i - 1]
            prev_expected = prev_event.compute_hash()

            if event.previous_hash != prev_expected:
                broken.append(
                    f"Event {event.sequence} (seq={event.sequence}): "
                    f"previous_hash={event.previous_hash} != expected={prev_expected}"
                )

        # 2. Verify hash file matches recomputed hashes
        hash_path = self.run_dir / "ledger.hash"
        if hash_path.exists():
            hash_lines = hash_path.read_text(encoding="utf-8").strip().split("\n")
            hash_lines = [h.strip() for h in hash_lines if h.strip()]
            if len(hash_lines) != len(events):
                broken.append(
                    f"Hash file length mismatch: {len(hash_lines)} hashes vs {len(events)} events"
                )
            else:
                for i, (event, h) in enumerate(zip(events, hash_lines, strict=True)):
                    expected = event.compute_hash()
                    if h != expected:
                        broken.append(
                            f"Hash file mismatch at event {i} "
                            f"(seq={event.sequence}): stored={h} != computed={expected}"
                        )

        is_valid = len(broken) == 0
        return is_valid, broken

    def _read_last_hash(self) -> str | None:
        """Return the hash of the most recent event, or None if ledger is empty."""
        hash_path = self.run_dir / "ledger.hash"
        if not hash_path.exists():
            return None
        lines = hash_path.read_text(encoding="utf-8").strip().split("\n")
        if not lines or not lines[-1].strip():
            return None
        return lines[-1].strip()

    def _append_to_ledger(self, event: Event) -> None:
        path = self.run_dir / "ledger.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(event.to_json() + "\n")

    def _append_hash(self, event: Event) -> None:
        path = self.run_dir / "ledger.hash"
        event_hash = event.compute_hash()
        with path.open("a", encoding="utf-8") as handle:
            handle.write(event_hash + "\n")

    def _restore_sequence_from_ledger(self) -> None:
        """Set _sequence to one past the last event in an existing ledger."""
        events = self.read_ledger()
        if events:
            self._sequence = max(e.sequence for e in events) + 1

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    def _update_index(self, event: Event) -> None:
        """Incrementally update the in-memory index (persisted on checkpoint)."""
        seq = event.sequence

        if event.event_type.value not in self._index["event_type"]:
            self._index["event_type"][event.event_type.value] = []
        self._index["event_type"][event.event_type.value].append(seq)

        if event.phase is not None:
            if event.phase not in self._index["phase"]:
                self._index["phase"][event.phase] = []
            self._index["phase"][event.phase].append(seq)

        if event.agent_id is not None:
            if event.agent_id not in self._index["agent_id"]:
                self._index["agent_id"][event.agent_id] = []
            self._index["agent_id"][event.agent_id].append(seq)

        if event.tool_id is not None:
            if event.tool_id not in self._index["tool_id"]:
                self._index["tool_id"][event.tool_id] = []
            self._index["tool_id"][event.tool_id].append(seq)

        if event.step_id is not None:
            if event.step_id not in self._index["step_id"]:
                self._index["step_id"][event.step_id] = []
            self._index["step_id"][event.step_id].append(seq)

    def _persist_index(self) -> None:
        path = self.run_dir / "ledger.index"
        path.write_text(json.dumps(self._index, indent=2, sort_keys=True), encoding="utf-8")

    def _load_index(self) -> None:
        path = self.run_dir / "ledger.index"
        if path.exists():
            self._index = json.loads(path.read_text(encoding="utf-8"))

    def query_index(
        self,
        *,
        event_type: str | EventType | None = None,
        phase: str | None = None,
        agent_id: str | None = None,
        tool_id: str | None = None,
        step_id: str | None = None,
    ) -> list[Event]:
        """Query events by indexed dimensions.

        If multiple filters are provided, the intersection is returned
        (events matching ALL criteria).
        """
        events = self.read_ledger()
        if not events:
            return []

        # Build candidate sets from index
        candidates: set[int] | None = None

        if event_type is not None:
            key = event_type.value if isinstance(event_type, EventType) else event_type
            seqs = set(self._index.get("event_type", {}).get(key, []))
            candidates = seqs if candidates is None else candidates & seqs

        if phase is not None:
            seqs = set(self._index.get("phase", {}).get(phase, []))
            candidates = seqs if candidates is None else candidates & seqs

        if agent_id is not None:
            seqs = set(self._index.get("agent_id", {}).get(agent_id, []))
            candidates = seqs if candidates is None else candidates & seqs

        if tool_id is not None:
            seqs = set(self._index.get("tool_id", {}).get(tool_id, []))
            candidates = seqs if candidates is None else candidates & seqs

        if step_id is not None:
            seqs = set(self._index.get("step_id", {}).get(step_id, []))
            candidates = seqs if candidates is None else candidates & seqs

        if candidates is None:
            return events

        return [e for e in events if e.sequence in candidates]

    def events_after(self, sequence: int) -> list[Event]:
        """Return all events with sequence number strictly greater than *sequence*."""
        return [e for e in self.read_ledger() if e.sequence > sequence]

    # ------------------------------------------------------------------
    # Checkpoints
    # ------------------------------------------------------------------

    def save_checkpoint(self, state: dict[str, Any], sequence_num: int) -> Path:
        """Save a state snapshot at the given sequence number.

        Also persists the current index and emits a ``CHECKPOINT_SAVED`` event
        so the checkpoint is discoverable via the ledger.
        """
        checkpoint_dir = self.run_dir / "checkpoints"
        checkpoint_dir.mkdir(exist_ok=True)
        path = checkpoint_dir / f"{sequence_num:08d}.json"
        payload = {
            "sequence": sequence_num,
            "timestamp": datetime.now().isoformat(),
            "state": state,
        }
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        self._persist_index()
        self.emit_event(
            EventType.CHECKPOINT_SAVED,
            payload={"sequence": sequence_num, "checkpoint_path": str(path.name)},
        )
        return path

    def load_last_checkpoint(self) -> tuple[dict[str, Any], int] | None:
        """Load the most recent checkpoint.

        Returns:
            (state_dict, sequence_num) or None if no checkpoints exist.
        """
        checkpoint_dir = self.run_dir / "checkpoints"
        if not checkpoint_dir.exists():
            return None

        checkpoints = sorted(checkpoint_dir.glob("*.json"))
        if not checkpoints:
            return None

        path = checkpoints[-1]
        data = json.loads(path.read_text(encoding="utf-8"))
        state = data.get("state", {})
        sequence = data.get("sequence", 0)
        return state, sequence

    def list_checkpoints(self) -> list[tuple[Path, int]]:
        """List all checkpoints as (path, sequence_num) tuples, sorted ascending."""
        checkpoint_dir = self.run_dir / "checkpoints"
        if not checkpoint_dir.exists():
            return []
        checkpoints = sorted(checkpoint_dir.glob("*.json"))
        result = []
        for path in checkpoints:
            seq = int(path.stem)
            result.append((path, seq))
        return result
