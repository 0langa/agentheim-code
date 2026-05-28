from __future__ import annotations

import time
from typing import Any

from openai import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    ConflictError,
    InternalServerError,
    NotFoundError,
    OpenAI,
    PermissionDeniedError,
    RateLimitError,
    UnprocessableEntityError,
)

from config.config import AgentModelConfig
from core.errors import ProviderError
from providers.base import ModelProvider, ModelRequest, ModelResponse

_NON_RETRYABLE = (
    AuthenticationError,
    PermissionDeniedError,
    BadRequestError,
    NotFoundError,
    UnprocessableEntityError,
    ConflictError,
)

_RETRYABLE = (
    RateLimitError,
    APITimeoutError,
    APIConnectionError,
    InternalServerError,
)


class OpenAIV1Provider(ModelProvider):
    def __init__(self, config: AgentModelConfig) -> None:
        super().__init__(config)
        api_key = config.api_key
        if getattr(config, "auth_mode", None) == "none":
            api_key = "no-key-required"
        self._client = OpenAI(
            api_key=api_key,
            base_url=config.endpoint,
            timeout=float(config.timeout_seconds),
            default_headers=config.headers or None,
        )

    def invoke(self, request: ModelRequest) -> ModelResponse:
        self.validate_request(request)
        messages: list[dict[str, Any]] = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.append({"role": "user", "content": request.user_content()})

        create_kwargs = {
            "model": self.config.model,
            "messages": messages,
            "temperature": request.temperature,
        }
        if request.max_output_tokens is not None:
            create_kwargs["max_completion_tokens"] = request.max_output_tokens

        last_error: Exception | None = None
        for delay in (0.0, 1.0, 2.0):
            if delay:
                time.sleep(delay)
            try:
                response = self._client.chat.completions.create(**create_kwargs)
                break
            except _NON_RETRYABLE as exc:
                raise ProviderError(
                    f"OpenAI request failed: {exc}",
                    http_status=getattr(exc, "status_code", None),
                ) from exc
            except _RETRYABLE as exc:
                last_error = exc
            except Exception as exc:  # pragma: no cover - unexpected provider errors
                last_error = exc
        else:
            raise ProviderError(
                f"Model invocation failed after retries: {last_error}",
                http_status=getattr(last_error, "status_code", None),
            ) from last_error
        content = response.choices[0].message.content or ""

        return ModelResponse(
            role=request.role,
            model=self.config.model,
            provider=self.config.provider,
            content=content,
            raw=response.model_dump(),
        )
