"""Integration tests against real LLM providers.

These tests require valid API keys in environment variables.
Run with: pytest tests/integration/ -m integration
"""

from __future__ import annotations

import os

import pytest

from config.config import AgentModelConfig, ModelRole
from core.model_registry import DEFAULT_PROVIDER_MAP, ModelRegistry
from providers.base import ModelRequest

pytestmark = pytest.mark.integration


def _has_key(*names: str) -> bool:
    return any(os.getenv(n, "").strip() for n in names)


class TestOpenAIProvider:
    @pytest.mark.skipif(not _has_key("OPENAI_API_KEY"), reason="OPENAI_API_KEY not set")
    def test_inference_and_usage_extraction(self) -> None:
        config = AgentModelConfig(
            role=ModelRole.PLANNER,
            provider="openai",
            provider_type="openai_v1",
            endpoint="https://api.openai.com/v1",
            api_key=os.environ["OPENAI_API_KEY"],
            auth_mode="bearer",
            model="gpt-4o-mini",
            timeout_seconds=60,
            headers={},
            metadata={"capabilities": ["text"]},
        )
        registry = ModelRegistry(providers=DEFAULT_PROVIDER_MAP, models={})
        provider = registry.create_provider(config)
        request = ModelRequest(
            role=ModelRole.PLANNER,
            system_prompt="You are a test assistant.",
            user_prompt="Say 'ok' and nothing else.",
            temperature=0.0,
            max_output_tokens=10,
        )
        response = provider.invoke(request)
        assert response.content.strip()
        assert response.usage is not None
        assert response.usage.input_tokens > 0
        assert response.usage.output_tokens > 0
        assert response.usage.total_cost_usd is not None


class TestAnthropicProvider:
    @pytest.mark.skipif(not _has_key("ANTHROPIC_API_KEY"), reason="ANTHROPIC_API_KEY not set")
    def test_inference_and_usage_extraction(self) -> None:
        config = AgentModelConfig(
            role=ModelRole.PLANNER,
            provider="anthropic",
            provider_type="anthropic",
            endpoint="https://api.anthropic.com",
            api_key=os.environ["ANTHROPIC_API_KEY"],
            auth_mode="x_api_key",
            model="claude-sonnet-4",
            timeout_seconds=60,
            headers={},
            metadata={"capabilities": ["text"]},
        )
        registry = ModelRegistry(providers=DEFAULT_PROVIDER_MAP, models={})
        provider = registry.create_provider(config)
        request = ModelRequest(
            role=ModelRole.PLANNER,
            system_prompt="You are a test assistant.",
            user_prompt="Say 'ok' and nothing else.",
            temperature=0.0,
            max_output_tokens=10,
        )
        response = provider.invoke(request)
        assert response.content.strip()
        assert response.usage is not None
        assert response.usage.input_tokens > 0
        assert response.usage.output_tokens > 0


class TestGeminiProvider:
    @pytest.mark.skipif(not _has_key("GEMINI_API_KEY"), reason="GEMINI_API_KEY not set")
    def test_inference_and_usage_extraction(self) -> None:
        config = AgentModelConfig(
            role=ModelRole.PLANNER,
            provider="gemini",
            provider_type="gemini",
            endpoint="https://generativelanguage.googleapis.com",
            api_key=os.environ["GEMINI_API_KEY"],
            auth_mode="api_key",
            model="gemini-2.0-flash",
            timeout_seconds=60,
            headers={},
            metadata={"capabilities": ["text"]},
        )
        registry = ModelRegistry(providers=DEFAULT_PROVIDER_MAP, models={})
        provider = registry.create_provider(config)
        request = ModelRequest(
            role=ModelRole.PLANNER,
            system_prompt="You are a test assistant.",
            user_prompt="Say 'ok' and nothing else.",
            temperature=0.0,
            max_output_tokens=10,
        )
        response = provider.invoke(request)
        assert response.content.strip()
        assert response.usage is not None
        assert response.usage.input_tokens > 0
        assert response.usage.output_tokens > 0
