from __future__ import annotations

from typing import Any

from core.ledger import RunLedger


class WorkingMemory:
    """Ephemeral single-run memory used by copied workflow boundaries."""

    def __init__(self, ledger: RunLedger | None = None) -> None:
        self._store: dict[str, Any] = {}
        self._lists: dict[str, list[Any]] = {}
        self._ledger = ledger

    def set(self, key: str, value: Any) -> None:
        self._store[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self._store.get(key, default)

    def append(self, key: str, item: Any) -> None:
        self._lists.setdefault(key, []).append(item)

    def get_list(self, key: str) -> list[Any]:
        return list(self._lists.get(key, []))

    def snapshot(self) -> dict[str, Any]:
        return {
            "store": dict(self._store),
            "lists": {key: list(value) for key, value in self._lists.items()},
        }

    def flush(self) -> None:
        if self._ledger is not None:
            self._ledger.write_json("working_memory.json", self.snapshot())

    def clear(self) -> None:
        self._store.clear()
        self._lists.clear()
