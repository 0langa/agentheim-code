from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol, TypeVar

T = TypeVar("T")


@dataclass
class RegistryEntry:
    kind: str
    id: str
    factory: Callable[..., Any]
    metadata: dict[str, Any] = field(default_factory=dict)


class CapabilityRegistry:
    def __init__(self) -> None:
        self._entries: dict[str, RegistryEntry] = {}

    def register(
        self,
        kind: str,
        id: str,
        factory: Callable[..., Any],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        key = f"{kind}:{id}"
        if key in self._entries:
            raise ValueError(f"Capability '{key}' already registered")
        self._entries[key] = RegistryEntry(
            kind=kind,
            id=id,
            factory=factory,
            metadata=metadata or {},
        )

    def get(self, kind: str, id: str) -> RegistryEntry:
        key = f"{kind}:{id}"
        if key not in self._entries:
            raise KeyError(f"Capability '{key}' not found")
        return self._entries[key]

    def list_by_kind(self, kind: str) -> list[RegistryEntry]:
        return [e for e in self._entries.values() if e.kind == kind]

    def ids_by_kind(self, kind: str) -> list[str]:
        return [e.id for e in self._entries.values() if e.kind == kind]

    def has(self, kind: str, id: str) -> bool:
        return f"{kind}:{id}" in self._entries

    def build(self, kind: str, id: str, *args: Any, **kwargs: Any) -> Any:
        entry = self.get(kind, id)
        return entry.factory(*args, **kwargs)


_global_registry: CapabilityRegistry | None = None


class WorkflowFactory(Protocol):
    workflow_id: str


def get_registry() -> CapabilityRegistry:
    global _global_registry
    if _global_registry is None:
        _global_registry = CapabilityRegistry()
    return _global_registry


def register_workflow(
    workflow_cls: type[WorkflowFactory], metadata: dict[str, Any] | None = None
) -> None:
    get_registry().register(
        kind="workflow",
        id=workflow_cls.workflow_id,
        factory=workflow_cls,
        metadata=metadata or {},
    )


def register_preset(
    preset_id: str, factory: Callable[..., Any], metadata: dict[str, Any] | None = None
) -> None:
    get_registry().register(
        kind="preset",
        id=preset_id,
        factory=factory,
        metadata=metadata or {},
    )


def register_memory_backend(
    backend_id: str, factory: Callable[..., Any], metadata: dict[str, Any] | None = None
) -> None:
    get_registry().register(
        kind="memory_backend",
        id=backend_id,
        factory=factory,
        metadata=metadata or {},
    )


def get_workflow(id: str) -> RegistryEntry:
    return get_registry().get("workflow", id)


def list_workflows() -> list[RegistryEntry]:
    return get_registry().list_by_kind("workflow")


def get_preset(id: str) -> RegistryEntry:
    return get_registry().get("preset", id)


def list_presets() -> list[RegistryEntry]:
    return get_registry().list_by_kind("preset")


def get_memory_backend(id: str) -> RegistryEntry:
    return get_registry().get("memory_backend", id)


def list_memory_backends() -> list[RegistryEntry]:
    return get_registry().list_by_kind("memory_backend")
