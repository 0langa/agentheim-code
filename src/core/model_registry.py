from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module

from config.config import AgentModelConfig, TeamConfig, load_team_config
from providers.base import ModelProvider, ModelRequest, ModelResponse
from providers.usage import extract_usage, get_pricing_registry


@dataclass(frozen=True)
class ProviderDescriptor:
    id: str
    import_path: str


@dataclass(frozen=True)
class ModelDescriptor:
    id: str
    role: str
    capabilities: frozenset[str]
    config: AgentModelConfig


class _MeteredProvider(ModelProvider):
    """Wrapper that extracts usage metadata after every invoke call."""

    def __init__(self, inner: ModelProvider, config: AgentModelConfig) -> None:
        super().__init__(config)
        self._inner = inner

    def invoke(self, request: ModelRequest) -> ModelResponse:
        response = self._inner.invoke(request)
        usage = extract_usage(
            self.config.provider_type,
            response.raw,
            model=self.config.model,
            provider=self.config.provider,
        )
        if usage is not None:
            registry = get_pricing_registry()
            usage = registry.estimate_cost(usage)
        return ModelResponse(
            role=response.role,
            model=response.model,
            provider=response.provider,
            content=response.content,
            raw=response.raw,
            usage=usage,
        )


class ModelRegistry:
    def __init__(
        self, providers: dict[str, ProviderDescriptor], models: dict[str, ModelDescriptor]
    ) -> None:
        self._providers = providers
        self._models = models

    @classmethod
    def from_team_config(
        cls,
        config: TeamConfig | None = None,
        provider_map: dict[str, ProviderDescriptor] | None = None,
    ) -> ModelRegistry:
        config = config or load_team_config()
        providers = provider_map or {}
        models = {}
        for model in config.models.values():
            models[model.id] = ModelDescriptor(
                id=model.id,
                role=model.role.value,
                capabilities=frozenset(model.capabilities),
                config=config.resolve_role(model.role),
            )
        return cls(providers=providers, models=models)

    def list_models(self) -> list[ModelDescriptor]:
        """Return all registered models."""
        return list(self._models.values())

    def resolve_model(self, role: str, required_capability: str) -> ModelDescriptor:
        candidates = [
            model
            for model in self._models.values()
            if model.role == role and required_capability in model.capabilities
        ]
        if not candidates:
            raise ValueError(f"No model for role='{role}' with capability='{required_capability}'.")
        return candidates[0]

    def create_provider(self, config: AgentModelConfig) -> ModelProvider:
        descriptor = self._providers.get(config.provider_type)
        if descriptor is None:
            supported = ", ".join(sorted(self._providers))
            raise ValueError(
                f"Unsupported provider type '{config.provider_type}'. Supported provider types: {supported}"
            )
        module_name, class_name = descriptor.import_path.split(":", 1)
        module = import_module(module_name)
        provider_type = getattr(module, class_name)
        inner = provider_type(config)
        return _MeteredProvider(inner, config)


DEFAULT_PROVIDER_MAP: dict[str, ProviderDescriptor] = {
    "openai_compatible": ProviderDescriptor(
        id="openai_compatible", import_path="providers.openai_v1:OpenAIV1Provider"
    ),
    "openai_v1": ProviderDescriptor(
        id="openai_v1", import_path="providers.openai_v1:OpenAIV1Provider"
    ),
    "azure_foundry": ProviderDescriptor(
        id="azure_foundry", import_path="providers.azure_foundry:AzureFoundryProvider"
    ),
    "oci_genai": ProviderDescriptor(
        id="oci_genai", import_path="providers.oci_genai:OCIGenAIProvider"
    ),
    "aws_bedrock": ProviderDescriptor(
        id="aws_bedrock", import_path="providers.aws_bedrock:AWSBedrockProvider"
    ),
    "anthropic": ProviderDescriptor(
        id="anthropic", import_path="providers.anthropic:AnthropicProvider"
    ),
    "gemini": ProviderDescriptor(id="gemini", import_path="providers.gemini:GeminiProvider"),
    "vertex_ai": ProviderDescriptor(
        id="vertex_ai", import_path="providers.gemini:VertexAIProvider"
    ),
    "cohere": ProviderDescriptor(id="cohere", import_path="providers.cohere:CohereProvider"),
    "perplexity": ProviderDescriptor(
        id="perplexity", import_path="providers.perplexity:PerplexityProvider"
    ),
    "ollama_cloud": ProviderDescriptor(
        id="ollama_cloud", import_path="providers.ollama_cloud:OllamaCloudProvider"
    ),
}


def build_model_registry(config: TeamConfig | None = None) -> ModelRegistry:
    return ModelRegistry.from_team_config(config=config, provider_map=DEFAULT_PROVIDER_MAP)
