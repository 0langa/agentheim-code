"""Tests for verify_provider_connection success paths."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from agentheim_code.provider_wizard import verify_provider_connection
from providers.base import ModelProvider, ModelRequest, ModelResponse
from providers.usage import Usage


class FakeProvider(ModelProvider):
    """A fake provider that returns usage metadata."""

    def __init__(self, config=None):
        self.config = config

    def invoke(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(
            role=request.role,
            model="fake-model",
            provider="test",
            content="ok",
            raw={"usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8}},
            usage=Usage(
                input_tokens=5,
                output_tokens=3,
                total_tokens=8,
                model="fake-model",
                provider="test",
                input_cost_usd=0.0000005,
                output_cost_usd=0.0000003,
                total_cost_usd=0.0000008,
            ),
        )


class FakeProviderNoUsage(ModelProvider):
    """A fake provider that returns no usage metadata."""

    def __init__(self, config=None):
        self.config = config

    def invoke(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(
            role=request.role,
            model="fake-model",
            provider="test",
            content="ok",
            raw={},
            usage=None,
        )


class TestVerifyProviderConnection:
    def test_success_with_usage(self) -> None:
        with patch("core.model_registry.ModelRegistry.create_provider") as mock_create:
            mock_create.return_value = FakeProvider()
            result = verify_provider_connection(
                "openai_v1",
                {"api_key": "test", "endpoint": "https://api.openai.com/v1"},
                model_id="gpt-4o-mini",
            )
            assert result["ok"] is True
            assert "latency_ms" in result
            assert result["model"] == "fake-model"
            assert result["usage"]["input_tokens"] == 5
            assert result["usage"]["total_tokens"] == 8
            assert result["usage"]["estimated_cost_usd"] == 0.0000008

    def test_success_without_usage_warning(self) -> None:
        with patch("core.model_registry.ModelRegistry.create_provider") as mock_create:
            mock_create.return_value = FakeProviderNoUsage()
            result = verify_provider_connection(
                "openai_v1",
                {"api_key": "test", "endpoint": "https://api.openai.com/v1"},
                model_id="gpt-4o-mini",
            )
            assert result["ok"] is True
            assert "usage_warning" in result
            assert "did not return token usage" in result["usage_warning"]

    def test_initialization_failure(self) -> None:
        with patch("core.model_registry.ModelRegistry.create_provider") as mock_create:
            mock_create.side_effect = ValueError("bad config")
            result = verify_provider_connection(
                "openai_v1",
                {"api_key": "test", "endpoint": "https://api.openai.com/v1"},
            )
            assert result["ok"] is False
            assert "Failed to initialize" in result["error"]

    def test_inference_failure(self) -> None:
        with patch("core.model_registry.ModelRegistry.create_provider") as mock_create:
            mock_create.return_value = MagicMock()
            mock_create.return_value.invoke.side_effect = RuntimeError("network error")
            result = verify_provider_connection(
                "openai_v1",
                {"api_key": "test", "endpoint": "https://api.openai.com/v1"},
            )
            assert result["ok"] is False
            assert "Inference failed" in result["error"]

    def test_empty_response_warning(self) -> None:
        with patch("core.model_registry.ModelRegistry.create_provider") as mock_create:
            mock_create.return_value = MagicMock()
            mock_create.return_value.invoke.return_value = MagicMock(
                content="",
                model="m",
                provider="p",
                usage=None,
                raw={},
            )
            result = verify_provider_connection(
                "openai_v1",
                {"api_key": "test", "endpoint": "https://api.openai.com/v1"},
            )
            assert result["ok"] is True
            assert "warning" in result
            assert "empty" in result["warning"].lower()
