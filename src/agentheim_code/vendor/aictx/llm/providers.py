"""Model provider factory — DEPRECATED.

Provider creation is now unified under Agentheim's provider layer.
Use `core.model_registry.build_model_registry()` and `ModelRegistry.create_provider()`
or pass an `AgentheimToAictxAdapter` wrapped provider to AICtx pipelines.
"""

from __future__ import annotations

from agentheim_code.vendor.aictx.llm.base import ModelProvider

__all__ = ["ModelProvider"]
