"""Token usage extraction and cost tracking for all LLM providers.

UsageExtractor: provider-agnostic extraction from ModelResponse.raw
PricingRegistry: model pricing lookup with user overrides
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class Usage:
    """Normalized token usage from any provider."""

    input_tokens: int
    output_tokens: int
    total_tokens: int
    model: str
    provider: str
    provider_type: str = ""
    input_cost_usd: float | None = None
    output_cost_usd: float | None = None
    total_cost_usd: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "model": self.model,
            "provider": self.provider,
            "provider_type": self.provider_type,
            "input_cost_usd": self.input_cost_usd,
            "output_cost_usd": self.output_cost_usd,
            "total_cost_usd": self.total_cost_usd,
        }


# ------------------------------------------------------------------
# Provider-specific extraction helpers
# ------------------------------------------------------------------


def _extract_openai(raw: dict[str, Any]) -> tuple[int, int] | None:
    usage = raw.get("usage")
    if not usage:
        return None
    return int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0))


def _extract_anthropic(raw: dict[str, Any]) -> tuple[int, int] | None:
    usage = raw.get("usage")
    if not usage:
        return None
    return int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0))


def _extract_gemini(raw: dict[str, Any]) -> tuple[int, int] | None:
    meta = raw.get("usageMetadata")
    if not meta:
        return None
    return int(meta.get("promptTokenCount", 0)), int(meta.get("candidatesTokenCount", 0))


def _extract_bedrock(raw: dict[str, Any]) -> tuple[int, int] | None:
    # Bedrock populates raw with a custom dict that already has extracted fields
    inp = raw.get("input_tokens")
    out = raw.get("output_tokens")
    if inp is None or out is None:
        return None
    return int(inp), int(out)


def _extract_cohere(raw: dict[str, Any]) -> tuple[int, int] | None:
    usage = raw.get("usage")
    if not usage:
        return None
    tokens = usage.get("tokens", {})
    inp = tokens.get("input_tokens")
    out = tokens.get("output_tokens")
    if inp is None and out is None:
        # Cohere v2 sometimes uses top-level keys
        inp = usage.get("input_tokens")
        out = usage.get("output_tokens")
    if inp is None or out is None:
        return None
    return int(inp), int(out)


def _extract_ollama(raw: dict[str, Any]) -> tuple[int, int] | None:
    inp = raw.get("prompt_eval_count")
    out = raw.get("eval_count")
    if inp is None or out is None:
        return None
    return int(inp), int(out)


def _extract_oci(raw: dict[str, Any]) -> tuple[int, int] | None:
    inp = raw.get("input_tokens")
    out = raw.get("output_tokens")
    if inp is None or out is None:
        return None
    return int(inp), int(out)


_EXTRACTORS: dict[str, Any] = {
    "openai_v1": _extract_openai,
    "openai_compatible": _extract_openai,
    "azure_foundry": _extract_openai,
    "perplexity": _extract_openai,
    "anthropic": _extract_anthropic,
    "gemini": _extract_gemini,
    "vertex_ai": _extract_gemini,
    "aws_bedrock": _extract_bedrock,
    "cohere": _extract_cohere,
    "ollama_cloud": _extract_ollama,
    "oci_genai": _extract_oci,
}


def extract_usage(
    provider_type: str,
    raw: dict[str, Any] | None,
    *,
    model: str,
    provider: str,
) -> Usage | None:
    """Extract normalized Usage from a provider's raw response dict.

    Returns ``None`` when the provider response does not contain usage metadata
    (e.g. local providers, proxies, or older API versions).
    """
    if not raw:
        return None
    extractor = _EXTRACTORS.get(provider_type)
    if extractor is None:
        return None
    result = extractor(raw)
    if result is None:
        return None
    input_tokens, output_tokens = result
    total_tokens = input_tokens + output_tokens
    return Usage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        model=model,
        provider=provider,
        provider_type=provider_type,
    )


# ------------------------------------------------------------------
# Pricing registry
# ------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Rate:
    input_per_1m: float
    output_per_1m: float
    currency: str = "USD"

    def cost(self, input_tokens: int, output_tokens: int) -> float:
        """Return total cost in currency units."""
        return (input_tokens * self.input_per_1m + output_tokens * self.output_per_1m) / 1_000_000.0


def _default_pricing_path() -> Path:
    here = Path(__file__).resolve()
    # src/providers/usage.py -> src/agentheim_code/pricing.json
    candidate = here.parents[1] / "agentheim_code" / "pricing.json"
    if candidate.exists():
        return candidate
    # Fallback for installed package
    pkg = Path(__file__).resolve().parent.parent / "agentheim_code" / "pricing.json"
    return pkg


class PricingRegistry:
    """Model pricing lookup with optional user overrides."""

    def __init__(
        self,
        data: dict[str, Any] | None = None,
        overrides: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self._rates: dict[str, Rate] = {}
        self._overrides: dict[str, Rate] = {}
        if data:
            self._load(data)
        if overrides:
            self._load_overrides(overrides)

    @classmethod
    def from_json(cls, path: str | Path | None = None) -> PricingRegistry:
        path = path or _default_pricing_path()
        if isinstance(path, str):
            path = Path(path)
        data: dict[str, Any] = {}
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
        return cls(data=data)

    def _load(self, data: dict[str, Any]) -> None:
        models = data.get("models", {})
        for key, value in models.items():
            self._rates[key] = Rate(
                input_per_1m=float(value.get("input_per_1m", 0)),
                output_per_1m=float(value.get("output_per_1m", 0)),
                currency=value.get("currency", "USD"),
            )

    def _load_overrides(self, overrides: dict[str, dict[str, Any]]) -> None:
        for key, value in overrides.items():
            self._overrides[key] = Rate(
                input_per_1m=float(value.get("input_per_1m", 0)),
                output_per_1m=float(value.get("output_per_1m", 0)),
                currency=value.get("currency", "USD"),
            )

    def _key(self, model: str, provider_type: str) -> str:
        # Prefer provider-prefixed key, fallback to bare model name
        return f"{provider_type}/{model}"

    def get_rate(self, model: str, provider_type: str) -> Rate | None:
        key = self._key(model, provider_type)
        if key in self._overrides:
            return self._overrides[key]
        if key in self._rates:
            return self._rates[key]
        # Fallback: bare model name
        if model in self._overrides:
            return self._overrides[model]
        if model in self._rates:
            return self._rates[model]
        return None

    def estimate_cost(self, usage: Usage) -> Usage:
        """Return a new Usage with cost fields populated (if rate known)."""
        rate = self.get_rate(usage.model, usage.provider_type)
        if rate is None:
            return usage
        cost = rate.cost(usage.input_tokens, usage.output_tokens)
        return Usage(
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            total_tokens=usage.total_tokens,
            model=usage.model,
            provider=usage.provider,
            provider_type=usage.provider_type,
            input_cost_usd=round(usage.input_tokens * rate.input_per_1m / 1_000_000.0, 8),
            output_cost_usd=round(usage.output_tokens * rate.output_per_1m / 1_000_000.0, 8),
            total_cost_usd=round(cost, 8),
        )

    def set_override(
        self,
        model: str,
        provider_type: str,
        input_per_1m: float,
        output_per_1m: float,
        currency: str = "USD",
    ) -> None:
        """Set a user override rate."""
        self._overrides[self._key(model, provider_type)] = Rate(
            input_per_1m=input_per_1m,
            output_per_1m=output_per_1m,
            currency=currency,
        )


# ------------------------------------------------------------------
# Singleton registry
# ------------------------------------------------------------------

_DEFAULT_REGISTRY: PricingRegistry | None = None


def get_pricing_registry() -> PricingRegistry:
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        _DEFAULT_REGISTRY = PricingRegistry.from_json()
    return _DEFAULT_REGISTRY


def reset_pricing_registry() -> None:
    global _DEFAULT_REGISTRY
    _DEFAULT_REGISTRY = None
