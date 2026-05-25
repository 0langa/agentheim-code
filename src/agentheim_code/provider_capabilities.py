"""Provider capability matrix and discovery metadata.

This module maps every built-in provider template to its real-world
management capabilities so the backend and frontend can make honest,
capability-driven UI decisions instead of guessing.
"""

from __future__ import annotations

from typing import Any, Literal

DiscoveryMode = Literal[
    "remote_list",
    "remote_list_with_manual_fallback",
    "manual_only",
    "local_scan",
    "sdk_hybrid",
]


class ProviderCapabilities:
    """Capability descriptor for a provider family."""

    def __init__(
        self,
        *,
        supports_connection_test: bool = True,
        supports_remote_model_listing: bool = False,
        supports_manual_model_entry: bool = True,
        supports_endpoint_edit: bool = True,
        supports_secret_rotation: bool = True,
        discovery_mode: DiscoveryMode = "manual_only",
        docs_url: str = "",
        notes: str = "",
    ) -> None:
        self.supports_connection_test = supports_connection_test
        self.supports_remote_model_listing = supports_remote_model_listing
        self.supports_manual_model_entry = supports_manual_model_entry
        self.supports_endpoint_edit = supports_endpoint_edit
        self.supports_secret_rotation = supports_secret_rotation
        self.discovery_mode = discovery_mode
        self.docs_url = docs_url
        self.notes = notes

    def to_dict(self) -> dict[str, Any]:
        return {
            "supports_connection_test": self.supports_connection_test,
            "supports_remote_model_listing": self.supports_remote_model_listing,
            "supports_manual_model_entry": self.supports_manual_model_entry,
            "supports_endpoint_edit": self.supports_endpoint_edit,
            "supports_secret_rotation": self.supports_secret_rotation,
            "discovery_mode": self.discovery_mode,
            "docs_url": self.docs_url,
            "notes": self.notes,
        }


# Capability matrix derived from official documentation research.
# Sources:
# - OpenAI: https://platform.openai.com/docs/api-reference/models/list
# - Azure OpenAI: https://learn.microsoft.com/en-us/azure/foundry/openai/latest
# - Anthropic: https://docs.anthropic.com/en/api/models-list
# - Google Gemini: https://ai.google.dev/gemini-api/docs/models
# - Vertex AI: https://cloud.google.com/vertex-ai/docs/generative-ai/learn/models
# - AWS Bedrock: https://docs.aws.amazon.com/bedrock/latest/APIReference/API_ListFoundationModels.html
# - OCI GenAI: https://docs.oracle.com/en-us/iaas/Content/generative-ai/home.htm
# - Cohere: https://docs.cohere.com/reference/list-models
# - Groq: https://console.groq.com/docs/api-reference#models
# - Ollama: https://docs.ollama.com/api/tags
# - LM Studio: https://lmstudio.ai/docs/local-server (OpenAI-compatible)
# - vLLM: https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html
# - TGI: https://huggingface.co/docs/text-generation-inference/basic_tutorials/consuming_tgi
# - llama.cpp: https://github.com/ggerganov/llama.cpp/blob/master/examples/server/README.md
# - Perplexity: https://docs.perplexity.ai/docs/admin/api-key-management (no public model list)
# - OpenRouter: https://openrouter.ai/docs/api-keys (has model list)
# - Together: https://docs.together.ai/docs/api-keys (has model list)
# - DeepSeek: https://api-docs.deepseek.com/api/deepseek-api (no public model list)
# - Mistral: https://docs.mistral.ai/api/ (has model list)
# - xAI: https://docs.x.ai/docs/ (OpenAI-compatible)

CAPABILITIES: dict[str, ProviderCapabilities] = {
    "openai_v1": ProviderCapabilities(
        supports_connection_test=True,
        supports_remote_model_listing=True,
        supports_manual_model_entry=True,
        supports_endpoint_edit=True,
        supports_secret_rotation=True,
        discovery_mode="remote_list",
        docs_url="https://platform.openai.com/docs/api-reference/models/list",
    ),
    "openai_compatible": ProviderCapabilities(
        supports_connection_test=True,
        supports_remote_model_listing=True,
        supports_manual_model_entry=True,
        supports_endpoint_edit=True,
        supports_secret_rotation=True,
        discovery_mode="remote_list_with_manual_fallback",
        notes="OpenAI-compatible endpoints vary in /models fidelity. Fallback to manual entry when listing fails.",
    ),
    "azure_foundry": ProviderCapabilities(
        supports_connection_test=True,
        supports_remote_model_listing=True,
        supports_manual_model_entry=True,
        supports_endpoint_edit=True,
        supports_secret_rotation=True,
        discovery_mode="remote_list_with_manual_fallback",
        docs_url="https://learn.microsoft.com/en-us/azure/foundry/openai/latest",
        notes="Azure OpenAI supports /openai/v1/models. Deployments may need explicit creation before use.",
    ),
    "aws_bedrock": ProviderCapabilities(
        supports_connection_test=True,
        supports_remote_model_listing=False,
        supports_manual_model_entry=True,
        supports_endpoint_edit=False,
        supports_secret_rotation=True,
        discovery_mode="sdk_hybrid",
        docs_url="https://docs.aws.amazon.com/bedrock/latest/APIReference/API_ListFoundationModels.html",
        notes="Inference uses model ARNs. Manual entry is the stable path until SDK-backed discovery is implemented.",
    ),
    "oci_genai": ProviderCapabilities(
        supports_connection_test=True,
        supports_remote_model_listing=False,
        supports_manual_model_entry=True,
        supports_endpoint_edit=False,
        supports_secret_rotation=True,
        discovery_mode="sdk_hybrid",
        docs_url="https://docs.oracle.com/en-us/iaas/Content/generative-ai/home.htm",
        notes="Discovery via OCI SDK is possible but complex; manual entry is the stable path today.",
    ),
    "xai_grok": ProviderCapabilities(
        supports_connection_test=True,
        supports_remote_model_listing=True,
        supports_manual_model_entry=True,
        supports_endpoint_edit=True,
        supports_secret_rotation=True,
        discovery_mode="remote_list_with_manual_fallback",
        docs_url="https://docs.x.ai/docs/",
        notes="OpenAI-compatible endpoint. /v1/models may be limited.",
    ),
    "gemini": ProviderCapabilities(
        supports_connection_test=True,
        supports_remote_model_listing=True,
        supports_manual_model_entry=True,
        supports_endpoint_edit=True,
        supports_secret_rotation=True,
        discovery_mode="remote_list",
        docs_url="https://ai.google.dev/gemini-api/docs/models",
        notes="GET /v1beta/models returns available models with capabilities.",
    ),
    "vertex_ai": ProviderCapabilities(
        supports_connection_test=True,
        supports_remote_model_listing=False,
        supports_manual_model_entry=True,
        supports_endpoint_edit=False,
        supports_secret_rotation=True,
        discovery_mode="sdk_hybrid",
        docs_url="https://cloud.google.com/vertex-ai/docs/generative-ai/learn/models",
        notes="Vertex AI discovery requires google-auth and project setup. Manual entry is recommended for stability.",
    ),
    "anthropic": ProviderCapabilities(
        supports_connection_test=True,
        supports_remote_model_listing=True,
        supports_manual_model_entry=True,
        supports_endpoint_edit=True,
        supports_secret_rotation=True,
        discovery_mode="remote_list",
        docs_url="https://docs.anthropic.com/en/api/models-list",
    ),
    "kimi_moonshot": ProviderCapabilities(
        supports_connection_test=True,
        supports_remote_model_listing=False,
        supports_manual_model_entry=True,
        supports_endpoint_edit=True,
        supports_secret_rotation=True,
        discovery_mode="manual_only",
        docs_url="https://platform.kimi.ai/docs/api/overview",
        notes="OpenAI-compatible. No official model list endpoint documented as of 2025-06.",
    ),
    "mistral": ProviderCapabilities(
        supports_connection_test=True,
        supports_remote_model_listing=True,
        supports_manual_model_entry=True,
        supports_endpoint_edit=True,
        supports_secret_rotation=True,
        discovery_mode="remote_list_with_manual_fallback",
        docs_url="https://docs.mistral.ai/api/",
    ),
    "groq": ProviderCapabilities(
        supports_connection_test=True,
        supports_remote_model_listing=True,
        supports_manual_model_entry=True,
        supports_endpoint_edit=True,
        supports_secret_rotation=True,
        discovery_mode="remote_list_with_manual_fallback",
        docs_url="https://console.groq.com/docs/api-reference#models",
    ),
    "deepseek": ProviderCapabilities(
        supports_connection_test=True,
        supports_remote_model_listing=False,
        supports_manual_model_entry=True,
        supports_endpoint_edit=True,
        supports_secret_rotation=True,
        discovery_mode="manual_only",
        docs_url="https://api-docs.deepseek.com/api/deepseek-api",
        notes="OpenAI-compatible. No official model list endpoint as of 2025-06.",
    ),
    "openrouter": ProviderCapabilities(
        supports_connection_test=True,
        supports_remote_model_listing=True,
        supports_manual_model_entry=True,
        supports_endpoint_edit=True,
        supports_secret_rotation=True,
        discovery_mode="remote_list_with_manual_fallback",
        docs_url="https://openrouter.ai/docs/api-keys",
        notes="Has /api/v1/models but response shape differs from OpenAI.",
    ),
    "together": ProviderCapabilities(
        supports_connection_test=True,
        supports_remote_model_listing=True,
        supports_manual_model_entry=True,
        supports_endpoint_edit=True,
        supports_secret_rotation=True,
        discovery_mode="remote_list_with_manual_fallback",
        docs_url="https://docs.together.ai/docs/api-keys",
    ),
    "cohere": ProviderCapabilities(
        supports_connection_test=True,
        supports_remote_model_listing=True,
        supports_manual_model_entry=True,
        supports_endpoint_edit=True,
        supports_secret_rotation=True,
        discovery_mode="remote_list_with_manual_fallback",
        docs_url="https://docs.cohere.com/reference/list-models",
    ),
    "perplexity": ProviderCapabilities(
        supports_connection_test=True,
        supports_remote_model_listing=False,
        supports_manual_model_entry=True,
        supports_endpoint_edit=True,
        supports_secret_rotation=True,
        discovery_mode="manual_only",
        docs_url="https://docs.perplexity.ai/docs/admin/api-key-management",
        notes="OpenAI-compatible chat completions only. No public model list endpoint.",
    ),
    "ollama": ProviderCapabilities(
        supports_connection_test=True,
        supports_remote_model_listing=True,
        supports_manual_model_entry=True,
        supports_endpoint_edit=True,
        supports_secret_rotation=False,
        discovery_mode="local_scan",
        docs_url="https://docs.ollama.com/api/tags",
        notes="Lists local models via /api/tags. Also exposes OpenAI-compatible /v1/models.",
    ),
    "ollama_cloud": ProviderCapabilities(
        supports_connection_test=True,
        supports_remote_model_listing=True,
        supports_manual_model_entry=True,
        supports_endpoint_edit=True,
        supports_secret_rotation=True,
        discovery_mode="remote_list_with_manual_fallback",
        docs_url="https://docs.ollama.com/api/tags",
        notes="Ollama Cloud uses /api/tags with Bearer auth.",
    ),
    "lm_studio": ProviderCapabilities(
        supports_connection_test=True,
        supports_remote_model_listing=True,
        supports_manual_model_entry=True,
        supports_endpoint_edit=True,
        supports_secret_rotation=False,
        discovery_mode="remote_list_with_manual_fallback",
        docs_url="https://lmstudio.ai/docs/local-server",
        notes="OpenAI-compatible local server. /v1/models availability depends on version.",
    ),
    "vllm": ProviderCapabilities(
        supports_connection_test=True,
        supports_remote_model_listing=True,
        supports_manual_model_entry=True,
        supports_endpoint_edit=True,
        supports_secret_rotation=False,
        discovery_mode="remote_list_with_manual_fallback",
        docs_url="https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html",
        notes="OpenAI-compatible. /v1/models is supported when --served-model-name is set.",
    ),
    "tgi": ProviderCapabilities(
        supports_connection_test=True,
        supports_remote_model_listing=False,
        supports_manual_model_entry=True,
        supports_endpoint_edit=True,
        supports_secret_rotation=False,
        discovery_mode="manual_only",
        docs_url="https://huggingface.co/docs/text-generation-inference/basic_tutorials/consuming_tgi",
        notes="TGI does not expose a model list endpoint. Manual entry required.",
    ),
    "llama_cpp": ProviderCapabilities(
        supports_connection_test=True,
        supports_remote_model_listing=False,
        supports_manual_model_entry=True,
        supports_endpoint_edit=True,
        supports_secret_rotation=False,
        discovery_mode="manual_only",
        docs_url="https://github.com/ggerganov/llama.cpp/blob/master/examples/server/README.md",
        notes="llama.cpp server does not expose a model list endpoint. Manual entry required.",
    ),
}


def get_capabilities(template_id: str) -> ProviderCapabilities:
    return CAPABILITIES.get(template_id, ProviderCapabilities())
