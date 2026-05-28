"""Provider package with lazy loading.

Concrete provider classes are loaded on-demand via `create_provider()`.
Only the base protocol classes (`ModelProvider`, `ModelRequest`, `ModelResponse`)
are eagerly imported.
"""

from __future__ import annotations

import importlib
from typing import Any, cast

from providers.base import ModelProvider, ModelRequest, ModelResponse

# Metadata for lazy provider loading
_PROVIDER_METADATA: dict[str, dict[str, str]] = {
    "openai_v1": {"module": "providers.openai_v1", "class": "OpenAIV1Provider"},
    "aws_bedrock": {"module": "providers.aws_bedrock", "class": "AWSBedrockProvider"},
    "azure_foundry": {"module": "providers.azure_foundry", "class": "AzureFoundryProvider"},
    "oci_genai": {"module": "providers.oci_genai", "class": "OCIGenAIProvider"},
    "anthropic": {"module": "providers.anthropic", "class": "AnthropicProvider"},
    "cohere": {"module": "providers.cohere", "class": "CohereProvider"},
    "gemini": {"module": "providers.gemini", "class": "GeminiProvider"},
    "vertex_ai": {"module": "providers.gemini", "class": "VertexAIProvider"},
    "perplexity": {"module": "providers.perplexity", "class": "PerplexityProvider"},
    "ollama_cloud": {"module": "providers.ollama_cloud", "class": "OllamaCloudProvider"},
}


def create_provider(provider_id: str, *args: Any, **kwargs: Any) -> ModelProvider:
    """Load and instantiate a provider by ID.

    Args:
        provider_id: One of the keys in `list_providers()`.
        *args, **kwargs: Passed to the provider constructor.

    Raises:
        KeyError: If provider_id is not known.
        ImportError: If the provider module cannot be loaded.
    """
    if provider_id not in _PROVIDER_METADATA:
        known = ", ".join(sorted(_PROVIDER_METADATA.keys()))
        raise KeyError(f"Unknown provider '{provider_id}'. Known: {known}")

    meta = _PROVIDER_METADATA[provider_id]
    module = importlib.import_module(meta["module"])
    cls = getattr(module, meta["class"])
    return cast(ModelProvider, cls(*args, **kwargs))


def list_providers() -> list[str]:
    """Return the IDs of all available providers (without loading them)."""
    return list(_PROVIDER_METADATA.keys())


def get_provider_metadata(provider_id: str) -> dict[str, str]:
    """Return metadata for a provider without loading it."""
    if provider_id not in _PROVIDER_METADATA:
        raise KeyError(f"Unknown provider '{provider_id}'")
    return dict(_PROVIDER_METADATA[provider_id])


__all__ = [
    "ModelProvider",
    "ModelRequest",
    "ModelResponse",
    "create_provider",
    "list_providers",
    "get_provider_metadata",
]
