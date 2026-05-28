from __future__ import annotations

import re
import time
from typing import Any

import requests

from config.config import AgentModelConfig
from core.errors import ProviderError
from providers.base import ModelProvider, ModelRequest, ModelResponse

_DATA_URL_RE = re.compile(r"^data:(?P<mime>[^;]+);base64,(?P<data>.+)$")


def _build_parts(request: ModelRequest) -> list[dict[str, Any]]:
    parts: list[dict[str, Any]] = [{"text": request.user_prompt}]
    for part in request.content:
        if part.type == "text" and part.text:
            parts.append({"text": part.text})
        elif part.type == "image_url" and part.image_url:
            match = _DATA_URL_RE.match(part.image_url)
            if match:
                parts.append(
                    {
                        "inline_data": {
                            "mime_type": match.group("mime"),
                            "data": match.group("data"),
                        }
                    }
                )
            else:
                parts.append({"file_data": {"file_uri": part.image_url}})
    return parts


def _build_payload(request: ModelRequest, config: AgentModelConfig) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "contents": [{"role": "user", "parts": _build_parts(request)}],
        "generationConfig": {"temperature": request.temperature},
    }
    if request.max_output_tokens is not None:
        payload["generationConfig"]["maxOutputTokens"] = request.max_output_tokens
    if request.system_prompt:
        payload["systemInstruction"] = {"parts": [{"text": request.system_prompt}]}
    capabilities = {str(item) for item in config.metadata.get("capabilities", [])}
    if "json" in capabilities:
        payload["generationConfig"]["responseMimeType"] = "application/json"
        if request.response_schema:
            payload["generationConfig"]["responseSchema"] = request.response_schema
    return payload


def _parse_response(raw: dict[str, Any]) -> str:
    content = ""
    for candidate in raw.get("candidates", []):
        for part in candidate.get("content", {}).get("parts", []):
            content += part.get("text", "")
    return content


def _is_non_retryable_http_error(exc: requests.exceptions.HTTPError) -> bool:
    response = getattr(exc, "response", None)
    if response is None:
        return False
    return response.status_code in (400, 401, 403, 404, 422, 409)


class GeminiProvider(ModelProvider):
    def __init__(self, config: AgentModelConfig) -> None:
        super().__init__(config)

    def invoke(self, request: ModelRequest) -> ModelResponse:
        self.validate_request(request)
        payload = _build_payload(request, self.config)
        url = (
            f"{self.config.endpoint.rstrip('/')}/v1beta/models/{self.config.model}:generateContent"
        )
        headers = {"x-goog-api-key": self.config.api_key, **self.config.headers}
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
            except requests.exceptions.HTTPError as exc:
                if _is_non_retryable_http_error(exc):
                    status = getattr(getattr(exc, "response", None), "status_code", None)
                    raise ProviderError(
                        f"Gemini request failed: {exc}",
                        http_status=status,
                    ) from exc
                last_error = exc
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
                last_error = exc
            except Exception as exc:  # pragma: no cover - unexpected
                last_error = exc
        else:
            raise ProviderError(
                f"Gemini invocation failed after retries: {last_error}",
                http_status=getattr(getattr(last_error, "response", None), "status_code", None),
            ) from last_error  # type: ignore[arg-type]

        content = _parse_response(raw)
        return ModelResponse(
            role=request.role,
            model=self.config.model,
            provider=self.config.provider,
            content=content,
            raw=raw,
        )


class VertexAIProvider(ModelProvider):
    def __init__(self, config: AgentModelConfig) -> None:
        super().__init__(config)

    def invoke(self, request: ModelRequest) -> ModelResponse:
        self.validate_request(request)
        if not self.config.model or self.config.model == "-":
            raise ProviderError(
                "Vertex AI provider requires a model name. Set model in the provider config."
            )
        try:
            import google.auth
            from google.auth.transport.requests import Request
        except ImportError as exc:
            raise ImportError(
                "Vertex AI provider requires google-auth. Install google-auth and configure ADC."
            ) from exc

        try:
            credentials, project = google.auth.default(
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
            credentials.refresh(Request())
        except Exception as exc:
            if type(exc).__name__ == "DefaultCredentialsError":
                raise ProviderError(
                    "Vertex AI ADC not found. Run 'gcloud auth application-default login' "
                    "or set GOOGLE_APPLICATION_CREDENTIALS to a service-account key file."
                ) from exc
            raise ProviderError(f"Vertex AI authentication failed: {exc}") from exc

        location = self.config.metadata.get("location", "us-central1")
        project_id = self.config.metadata.get("project_id") or project
        if not project_id:
            raise ProviderError("Vertex AI provider requires ADC project or metadata.project_id.")
        endpoint = self.config.endpoint
        if endpoint == "-":
            endpoint = f"https://{location}-aiplatform.googleapis.com"
        payload = _build_payload(request, self.config)
        url = f"{endpoint.rstrip('/')}/v1/projects/{project_id}/locations/{location}/publishers/google/models/{self.config.model}:generateContent"
        headers = {"Authorization": f"Bearer {credentials.token}", **self.config.headers}
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
            except requests.exceptions.HTTPError as exc:
                resp = getattr(exc, "response", None)
                if resp is not None and resp.status_code == 403:
                    raise ProviderError(
                        "Vertex AI permission denied. Ensure the account has 'aiplatform.endpoints.predict' "
                        f"permission for project '{project_id}' and location '{location}'.",
                        http_status=resp.status_code,
                    ) from exc
                if _is_non_retryable_http_error(exc):
                    raise ProviderError(
                        f"Vertex AI request failed: {exc}",
                        http_status=getattr(resp, "status_code", None),
                    ) from exc
                last_error = exc
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
                last_error = exc
            except Exception as exc:  # pragma: no cover - unexpected
                last_error = exc
        else:
            raise ProviderError(
                f"Vertex AI invocation failed after retries: {last_error}",
                http_status=getattr(getattr(last_error, "response", None), "status_code", None),
            ) from last_error  # type: ignore[arg-type]

        content = _parse_response(raw)
        return ModelResponse(
            role=request.role,
            model=self.config.model,
            provider=self.config.provider,
            content=content,
            raw=raw,
        )
