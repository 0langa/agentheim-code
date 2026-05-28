from __future__ import annotations

import time
from typing import Any

import requests

from core.errors import ProviderError
from providers.base import ModelProvider, ModelRequest, ModelResponse


class OllamaCloudProvider(ModelProvider):
    def invoke(self, request: ModelRequest) -> ModelResponse:
        self.validate_request(request)
        prompt = request.user_prompt
        if request.system_prompt:
            prompt = f"{request.system_prompt}\n\n{prompt}"
        payload: dict[str, Any] = {"model": self.config.model, "prompt": prompt, "stream": False}
        headers = {"Authorization": f"Bearer {self.config.api_key}", **self.config.headers}
        url = f"{self.config.endpoint.rstrip('/')}/generate"
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
                f"Ollama Cloud invocation failed after retries: {last_error}",
                http_status=status,
            ) from last_error
        return ModelResponse(
            role=request.role,
            model=self.config.model,
            provider=self.config.provider,
            content=raw.get("response", ""),
            raw=raw,
        )
