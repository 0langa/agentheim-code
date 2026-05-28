from __future__ import annotations

import time
from typing import Any

import requests

from core.errors import ProviderError
from providers.base import ModelProvider, ModelRequest, ModelResponse


class CohereProvider(ModelProvider):
    def invoke(self, request: ModelRequest) -> ModelResponse:
        self.validate_request(request)
        message = request.user_prompt
        if request.content:
            extra = " ".join(part.text or "" for part in request.content if part.type == "text")
            message = f"{message}\n{extra}".strip()
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": [{"role": "user", "content": message}],
            "temperature": request.temperature,
        }
        if request.system_prompt:
            payload["preamble"] = request.system_prompt
        if request.max_output_tokens is not None:
            payload["max_tokens"] = request.max_output_tokens
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "content-type": "application/json",
            **self.config.headers,
        }
        url = f"{self.config.endpoint.rstrip('/')}/v2/chat"
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
                f"Cohere invocation failed after retries: {last_error}",
                http_status=status,
            ) from last_error
        content = raw.get("message", {}).get("content", [])
        text = "".join(block.get("text", "") for block in content if isinstance(block, dict))
        return ModelResponse(
            role=request.role,
            model=self.config.model,
            provider=self.config.provider,
            content=text,
            raw=raw,
        )
