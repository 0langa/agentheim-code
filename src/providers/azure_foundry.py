from __future__ import annotations

from config.config import AgentModelConfig
from core.errors import ProviderError
from providers.openai_v1 import OpenAIV1Provider


def normalize_azure_foundry_endpoint(endpoint: str) -> str:
    normalized = endpoint.strip().rstrip("/")
    if normalized.endswith("/openai/v1"):
        return normalized
    return f"{normalized}/openai/v1"


class AzureFoundryProvider(OpenAIV1Provider):
    def __init__(self, config: AgentModelConfig) -> None:
        endpoint = normalize_azure_foundry_endpoint(config.endpoint)
        if not endpoint.startswith(("http://", "https://")):
            raise ProviderError(
                f"Azure Foundry endpoint must be a valid HTTP(S) URL, got: {config.endpoint!r}"
            )

        headers = dict(config.headers)
        if config.auth_mode == "api_key":
            if config.api_key == "-" or not config.api_key:
                raise ProviderError(
                    "Azure Foundry auth_mode is 'api_key' but no api_key is configured. "
                    "Set api_key or switch auth_mode to 'none' for keyless endpoints."
                )
            headers.setdefault("api-key", config.api_key)

        normalized_config = config.model_copy(
            update={
                "endpoint": endpoint,
                "headers": headers,
            }
        )
        super().__init__(normalized_config)
        self.config = normalized_config
