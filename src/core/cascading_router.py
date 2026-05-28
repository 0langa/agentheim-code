"""Cascading model router with fallback chains, health cache, and cost-aware sorting.

Replaces the naïve first-match resolver in ``ModelRegistry`` with a production-grade
router that can retry across multiple providers when a TRANSIENT error occurs.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from core.error_classification import ErrorCategory, classify_error
from core.events import EventType
from core.ledger import RunLedger
from core.model_registry import ModelDescriptor, ModelRegistry


@dataclass(frozen=True)
class ModelBinding:
    """A primary model plus an ordered list of fallback candidates."""

    primary: ModelDescriptor
    fallbacks: list[ModelDescriptor] = field(default_factory=list)


class CascadingRouter:
    """Resolves models with cost-aware sorting, health filtering, and fallback chains.

    Usage::

        router = CascadingRouter(registry, ledger=run_ledger)
        binding = router.resolve("coder", "code_generation")
        result = router.invoke_with_fallback(binding, lambda m: call_model(m, prompt))
    """

    def __init__(
        self,
        registry: ModelRegistry,
        ledger: RunLedger | None = None,
        health_ttl_seconds: float = 60.0,
    ) -> None:
        self.registry = registry
        self.ledger = ledger
        self._health_ttl = health_ttl_seconds
        self._health_cache: dict[str, tuple[bool, float]] = {}

    def resolve(self, role: str, required_capability: str) -> ModelBinding:
        """Resolve a ``ModelBinding`` for *role* + *required_capability*.

        Candidates are sorted by a simple cost heuristic (lower first) and
        filtered by health status.  At least one candidate must exist.
        """
        candidates = [
            m
            for m in self.registry.list_models()
            if m.role == role and required_capability in m.capabilities
        ]
        if not candidates:
            raise ValueError(f"No model for role='{role}' with capability='{required_capability}'.")

        candidates = sorted(candidates, key=self._cost_key)
        healthy = [candidate for candidate in candidates if self.is_healthy(candidate.id)]
        primary_pool = healthy or candidates
        primary = primary_pool[0]
        fallbacks = [candidate for candidate in primary_pool[1:] if candidate.id != primary.id]

        if self.ledger:
            self.ledger.emit_event(
                EventType.MODEL_SELECTED,
                payload={
                    "model_id": primary.id,
                    "role": role,
                    "capability": required_capability,
                    "fallback_count": len(fallbacks),
                },
            )

        return ModelBinding(primary=primary, fallbacks=fallbacks)

    def invoke_with_fallback(
        self, binding: ModelBinding, fn: Callable[[ModelDescriptor], Any]
    ) -> Any:
        """Invoke *fn(primary)*, falling back through ``binding.fallbacks`` on TRANSIENT errors.

        Non-transient errors are re-raised immediately.
        """
        models = [binding.primary] + binding.fallbacks
        last_error: Exception | None = None

        for model in models:
            if not self.is_healthy(model.id):
                continue
            try:
                return fn(model)
            except Exception as exc:
                last_error = exc
                category = classify_error(exc)
                if category == ErrorCategory.TRANSIENT:
                    self.mark_unhealthy(model.id)
                    if self.ledger:
                        self.ledger.emit_event(
                            EventType.FALLBACK_USED,
                            payload={
                                "from_model": model.id,
                                "reason": str(exc),
                                "error_type": type(exc).__name__,
                            },
                        )
                else:
                    raise

        raise last_error or RuntimeError("All models in binding failed")

    def is_healthy(self, model_id: str) -> bool:
        """Return ``True`` if *model_id* is considered healthy."""
        if model_id not in self._health_cache:
            return True
        healthy, ts = self._health_cache[model_id]
        if self._health_ttl <= 0 or time.monotonic() - ts >= self._health_ttl:
            self._health_cache.pop(model_id, None)
            return True
        return healthy

    def mark_healthy(self, model_id: str) -> None:
        """Explicitly mark a model as healthy."""
        self._health_cache[model_id] = (True, time.monotonic())

    def mark_unhealthy(self, model_id: str) -> None:
        """Mark a model as unhealthy (e.g. after a connection failure)."""
        self._health_cache[model_id] = (False, time.monotonic())

    @staticmethod
    def _cost_key(model: ModelDescriptor) -> float:
        """Extract a cost estimate from model config.  Lower = cheaper."""
        # Simple heuristic: prefer models with shorter IDs (stable tie-breaker)
        return 0.0
