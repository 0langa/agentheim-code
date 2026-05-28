from __future__ import annotations

import time
from typing import Any

import requests

from core.errors import ProviderError
from providers.base import ModelProvider, ModelRequest, ModelResponse


class AnthropicProvider(ModelProvider):
    def invoke(self, request: ModelRequest) -> ModelResponse:
        self.validate_request(request)
        blocks: list[dict[str, Any]] = [{"type": "text", "text": request.user_prompt}]
        for part in request.content:
            if part.type == "text" and part.text:
                blocks.append({"type": "text", "text": part.text})
            elif part.type == "image_url" and part.image_url:
                blocks.append({"type": "image", "source": {"type": "url", "url": part.image_url}})

        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": [{"role": "user", "content": blocks}],
            "temperature": request.temperature,
            "max_tokens": request.max_output_tokens or 4096,
        }
        if request.system_prompt:
            payload["system"] = request.system_prompt

        headers = {
            "x-api-key": self.config.api_key,
            "anthropic-version": self.config.metadata.get("anthropic_version", "2023-06-01"),
            "content-type": "application/json",
            **self.config.headers,
        }
        url = f"{self.config.endpoint.rstrip('/')}/v1/messages"
        last_error: Exception | None = None
        for delay in (0.0, 1.0, 2.0):
            if delay:
                time.sleep(delay)
            try:
                response = requests.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=self.config.timeout_seconds,
                    allow_redirects=False,
                )
                response.raise_for_status()
                raw = response.json()
                break
            except Exception as exc:  # pragma: no cover - network/provider dependent
                last_error = exc
        else:  # pragma: no cover - network/provider dependent
            status = getattr(getattr(last_error, "response", None), "status_code", None)
            raise ProviderError(
                f"Anthropic invocation failed after retries: {last_error}",
                http_status=status,
            ) from last_error

        content = "".join(
            block.get("text", "") for block in raw.get("content", []) if block.get("type") == "text"
        )
        return ModelResponse(
            role=request.role,
            model=self.config.model,
            provider=self.config.provider,
            content=content,
            raw=raw,
        )
