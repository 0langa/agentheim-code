from __future__ import annotations

from config.config import AgentModelConfig
from providers.openai_v1 import OpenAIV1Provider


class PerplexityProvider(OpenAIV1Provider):
    def __init__(self, config: AgentModelConfig) -> None:
        normalized = config.model_copy(update={"endpoint": f"{config.endpoint.rstrip('/')}"})
        super().__init__(normalized)
        self.config = normalized
