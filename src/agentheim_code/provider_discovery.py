"""Provider model discovery adapters.

Implements capability-driven remote model listing with normalization
into a common DiscoveredModel shape.
"""

from __future__ import annotations

import contextlib
import json
import logging
import urllib.request
from dataclasses import dataclass
from typing import Any

from config.config import ProviderAccount, ProviderTemplate, get_secret_store

logger = logging.getLogger("agentheim_code.provider_discovery")


@dataclass
class DiscoveredModel:
    id: str
    display_name: str
    provider_model_name: str
    capabilities: list[str]
    context_window: int | None = None
    max_output_tokens: int | None = None
    supports_tools: bool | None = None
    supports_vision: bool | None = None
    supports_streaming: bool | None = None
    deprecation_status: str | None = None
    source: str = "discovered"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "display_name": self.display_name,
            "provider_model_name": self.provider_model_name,
            "capabilities": self.capabilities,
            "context_window": self.context_window,
            "max_output_tokens": self.max_output_tokens,
            "supports_tools": self.supports_tools,
            "supports_vision": self.supports_vision,
            "supports_streaming": self.supports_streaming,
            "deprecation_status": self.deprecation_status,
            "source": self.source,
        }


def _fetch_json(url: str, headers: dict[str, str], timeout: float = 15.0) -> dict[str, Any] | None:
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
            return data if isinstance(data, dict) else None
    except Exception as exc:
        logger.debug("Discovery fetch failed for %s: %s", url, exc)
        return None


def _auth_headers(account: ProviderAccount) -> dict[str, str]:
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if account.auth_mode in {"api_key", "bearer", "x_api_key", "bedrock_api_key"}:
        api_key = "-"
        if account.secret_ref:
            with contextlib.suppress(Exception):
                api_key = get_secret_store().get(account.secret_ref) or "-"
        if api_key and api_key != "-":
            if account.auth_mode == "x_api_key":
                headers["x-api-key"] = api_key
            else:
                headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _openai_compatible_list(account: ProviderAccount) -> list[DiscoveredModel]:
    """Generic OpenAI-compatible /v1/models discovery."""
    base = account.endpoint.rstrip("/")
    url = f"{base}/models" if base.endswith("/v1") else f"{base}/v1/models"
    headers = _auth_headers(account)
    data = _fetch_json(url, headers)
    if not data:
        return []
    models = data.get("data", []) if isinstance(data, dict) else []
    result: list[DiscoveredModel] = []
    for item in models:
        if not isinstance(item, dict):
            continue
        model_id = str(item.get("id", ""))
        if not model_id:
            continue
        result.append(
            DiscoveredModel(
                id=model_id,
                display_name=model_id,
                provider_model_name=model_id,
                capabilities=["text"],
                deprecation_status=str(item.get("status", "")) or None,
            )
        )
    return result


def _gemini_list(account: ProviderAccount) -> list[DiscoveredModel]:
    base = account.endpoint.rstrip("/")
    url = f"{base}/v1beta/models?key={account.secret_ref or ''}"
    # Gemini prefers header auth but also accepts query param
    headers: dict[str, str] = {}
    if account.secret_ref:
        try:
            key = get_secret_store().get(account.secret_ref) or ""
            headers["x-goog-api-key"] = key
            url = f"{base}/v1beta/models"
        except Exception:
            pass
    data = _fetch_json(url, headers)
    if not data:
        return []
    models = data.get("models", []) if isinstance(data, dict) else []
    result: list[DiscoveredModel] = []
    for item in models:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).replace("models/", "")
        if not name or name.startswith("embed") or "embedding" in name.lower():
            continue
        methods = item.get("supportedGenerationMethods", [])
        caps = ["text"]
        if "generateContent" in methods:
            caps.append("json")
        if "countTokens" in methods:
            caps.append("streaming")
        result.append(
            DiscoveredModel(
                id=name,
                display_name=item.get("displayName") or name,
                provider_model_name=name,
                capabilities=caps,
                context_window=item.get("inputTokenLimit") or None,
                max_output_tokens=item.get("outputTokenLimit") or None,
                supports_vision="vision" in name.lower() or "image" in str(methods).lower(),
                supports_tools="tool" in str(methods).lower(),
                supports_streaming="stream" in str(methods).lower(),
            )
        )
    return result


def _ollama_list(account: ProviderAccount) -> list[DiscoveredModel]:
    base = account.endpoint.rstrip("/")
    # Prefer native Ollama API
    native_base = base.replace("/v1", "") if "/v1" in base else base
    url = f"{native_base}/api/tags"
    data = _fetch_json(url, {})
    if not data:
        # Fallback to OpenAI-compatible
        return _openai_compatible_list(account)
    models = data.get("models", []) if isinstance(data, dict) else []
    result: list[DiscoveredModel] = []
    for item in models:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", ""))
        if not name:
            continue
        details = item.get("details") or {}
        family = str(details.get("family", "")).lower()
        caps = ["text", "json"]
        if "vision" in family or "llava" in name.lower():
            caps.append("vision")
        result.append(
            DiscoveredModel(
                id=name,
                display_name=name,
                provider_model_name=name,
                capabilities=caps,
                source="discovered",
            )
        )
    return result


def _ollama_cloud_list(account: ProviderAccount) -> list[DiscoveredModel]:
    base = account.endpoint.rstrip("/")
    data = _fetch_json(f"{base}/api/tags", _auth_headers(account))
    if not data:
        return []
    models = data.get("models", []) if isinstance(data, dict) else []
    result: list[DiscoveredModel] = []
    for item in models:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", ""))
        if not name:
            continue
        result.append(
            DiscoveredModel(
                id=name,
                display_name=name,
                provider_model_name=name,
                capabilities=["text", "json"],
                source="discovered",
            )
        )
    return result


def _groq_list(account: ProviderAccount) -> list[DiscoveredModel]:
    # Groq exposes OpenAI-compatible /models but with richer metadata
    models = _openai_compatible_list(account)
    for m in models:
        m.capabilities = ["text", "json", "streaming"]
        if "vision" in m.id.lower():
            m.capabilities.append("vision")
        if "tool" in m.id.lower():
            m.capabilities.append("tools")
    return models


def _anthropic_list(account: ProviderAccount) -> list[DiscoveredModel]:
    base = account.endpoint.rstrip("/")
    url = f"{base}/v1/models"
    headers = _auth_headers(account)
    data = _fetch_json(url, headers)
    if not data:
        return []
    models = data.get("data", []) if isinstance(data, dict) else []
    result: list[DiscoveredModel] = []
    for item in models:
        if not isinstance(item, dict):
            continue
        model_id = str(item.get("id", ""))
        if not model_id:
            continue
        result.append(
            DiscoveredModel(
                id=model_id,
                display_name=item.get("display_name") or model_id,
                provider_model_name=model_id,
                capabilities=["text", "json", "vision", "tools", "streaming"],
                context_window=item.get("max_input_tokens") or None,
                max_output_tokens=item.get("max_tokens") or None,
            )
        )
    return result


def _cohere_list(account: ProviderAccount) -> list[DiscoveredModel]:
    base = account.endpoint.rstrip("/")
    url = f"{base}/v1/models"
    headers = _auth_headers(account)
    data = _fetch_json(url, headers)
    if not data:
        return []
    models = data.get("models", []) if isinstance(data, dict) else []
    result: list[DiscoveredModel] = []
    for item in models:
        if not isinstance(item, dict):
            continue
        model_id = str(item.get("name", ""))
        if not model_id:
            continue
        caps = ["text", "json"]
        if item.get("endpoints") and isinstance(item["endpoints"], list):
            for ep in item["endpoints"]:
                if isinstance(ep, dict):
                    if "chat" in str(ep.get("type", "")).lower():
                        caps.append("tools")
                    if "embed" in str(ep.get("type", "")).lower():
                        caps.append("embeddings")
                    if "rerank" in str(ep.get("type", "")).lower():
                        caps.append("rerank")
        result.append(
            DiscoveredModel(
                id=model_id,
                display_name=item.get("display_name") or model_id,
                provider_model_name=model_id,
                capabilities=list(set(caps)),
            )
        )
    return result


def _azure_list(account: ProviderAccount) -> list[DiscoveredModel]:
    # Azure OpenAI supports /openai/v1/models on data plane
    base = account.endpoint.rstrip("/")
    url = f"{base}/openai/v1/models"
    headers = _auth_headers(account)
    data = _fetch_json(url, headers)
    if not data:
        return []
    models = data.get("data", []) if isinstance(data, dict) else []
    result: list[DiscoveredModel] = []
    for item in models:
        if not isinstance(item, dict):
            continue
        model_id = str(item.get("id", ""))
        if not model_id:
            continue
        result.append(
            DiscoveredModel(
                id=model_id,
                display_name=model_id,
                provider_model_name=model_id,
                capabilities=["text", "json", "vision", "tools"],
            )
        )
    return result


def list_remote_models(
    account: ProviderAccount, template: ProviderTemplate | None = None
) -> list[DiscoveredModel]:
    """Best-effort remote model listing for a provider account.

    Returns an empty list when discovery is unsupported or fails.
    """
    template_id = account.metadata.get("template", account.kind)
    kind = account.kind

    # Route by template / kind
    if template_id in {"openai_v1"}:
        return _openai_compatible_list(account)
    if (
        template_id
        in {
            "openai_compatible",
            "xai_grok",
            "mistral",
            "groq",
            "openrouter",
            "together",
            "lm_studio",
            "vllm",
        }
        or kind == "openai_compatible"
    ):
        return _openai_compatible_list(account)
    if template_id == "deepseek":
        return []
    if kind == "gemini" or template_id == "gemini":
        return _gemini_list(account)
    if kind == "anthropic" or template_id == "anthropic":
        return _anthropic_list(account)
    if kind == "ollama" or template_id == "ollama":
        return _ollama_list(account)
    if kind == "ollama_cloud" or template_id == "ollama_cloud":
        return _ollama_cloud_list(account)
    if kind == "groq" or template_id == "groq":
        return _groq_list(account)
    if kind == "cohere" or template_id == "cohere":
        return _cohere_list(account)
    if kind == "azure_foundry" or template_id == "azure_foundry":
        return _azure_list(account)
    if template_id in {
        "aws_bedrock",
        "oci_genai",
        "vertex_ai",
        "kimi_moonshot",
        "perplexity",
        "tgi",
        "llama_cpp",
    } or kind in {
        "aws_bedrock",
        "oci_genai",
        "vertex_ai",
        "perplexity",
    }:
        return []

    # Unknown providers default to manual entry instead of overclaiming discovery.
    return []


def normalize_remote_model(
    raw: dict[str, Any], template: ProviderTemplate | None = None
) -> DiscoveredModel:
    """Normalize an arbitrary raw dict into a DiscoveredModel."""
    model_id = str(raw.get("id", raw.get("name", "")))
    display = raw.get("display_name") or raw.get("displayName") or model_id
    caps = raw.get("capabilities", ["text"])
    if isinstance(caps, str):
        caps = [caps]
    return DiscoveredModel(
        id=model_id,
        display_name=display,
        provider_model_name=model_id,
        capabilities=list(caps),
        context_window=raw.get("context_window") or raw.get("inputTokenLimit") or None,
        max_output_tokens=raw.get("max_output_tokens") or raw.get("outputTokenLimit") or None,
        supports_tools=raw.get("supports_tools") or raw.get("supportsTools") or None,
        supports_vision=raw.get("supports_vision") or raw.get("supportsVision") or None,
        supports_streaming=raw.get("supports_streaming") or raw.get("supportsStreaming") or None,
        deprecation_status=raw.get("deprecation_status") or raw.get("status") or None,
        source="discovered",
    )
