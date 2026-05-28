from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from config.config import AgentModelConfig, ModelRole
from providers.usage import Usage


class ContentPart(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: Literal["text", "image_url"] = "text"
    text: str | None = None
    image_url: str | None = None


class ModelRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: ModelRole
    system_prompt: str | None = None
    user_prompt: str = Field(min_length=1)
    content: list[ContentPart] = Field(default_factory=list)
    temperature: float = 0.0
    max_output_tokens: int | None = None
    response_schema: dict[str, Any] | None = None

    def user_content(self) -> str | list[dict[str, Any]]:
        if not self.content:
            return self.user_prompt
        parts: list[dict[str, Any]] = []
        if self.user_prompt:
            parts.append({"type": "text", "text": self.user_prompt})
        for part in self.content:
            if part.type == "text" and part.text:
                parts.append({"type": "text", "text": part.text})
            if part.type == "image_url" and part.image_url:
                parts.append({"type": "image_url", "image_url": {"url": part.image_url}})
        return parts


class ModelResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: ModelRole
    model: str
    provider: str
    content: str
    raw: dict[str, Any] | None = None
    usage: Usage | None = None


class ModelProvider(ABC):
    def __init__(self, config: AgentModelConfig) -> None:
        self.config = config

    def validate_request(self, request: ModelRequest) -> None:
        if any(part.type == "image_url" for part in request.content):
            capabilities = {str(item) for item in self.config.metadata.get("capabilities", [])}
            if "vision" not in capabilities and not self.config.metadata.get(
                "allow_unlisted_vision", False
            ):
                raise ValueError(
                    f"Model '{self.config.model}' is not configured with vision capability."
                )

    @abstractmethod
    def invoke(self, request: ModelRequest) -> ModelResponse:
        raise NotImplementedError
