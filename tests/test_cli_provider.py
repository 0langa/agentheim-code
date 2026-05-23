"""Tests for the CLI provider-test subcommand."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
import typer

from agentheim_code.cli import provider_test


class TestProviderTestCommand:
    def test_successful_connection(self, capsys: Any) -> None:
        with patch("agentheim_code.cli.verify_provider_connection") as mock_test:
            mock_test.return_value = {
                "ok": True,
                "latency_ms": 123,
                "usage": {
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "total_tokens": 15,
                    "estimated_cost_usd": 0.0001,
                },
            }
            provider_test("openai_v1", endpoint="", api_key="sk-test", model="gpt-4o", region="")
        mock_test.assert_called_once_with(
            provider_kind="openai_v1",
            fields={"api_key": "sk-test"},
            model_id="gpt-4o",
        )

    def test_failed_connection_raises_exit(self) -> None:
        with patch("agentheim_code.cli.verify_provider_connection") as mock_test:
            mock_test.return_value = {"ok": False, "error": "Connection refused"}
            with pytest.raises(typer.Exit):
                provider_test("openai_v1", endpoint="", api_key="", model="", region="")

    def test_with_endpoint_and_region(self) -> None:
        with patch("agentheim_code.cli.verify_provider_connection") as mock_test:
            mock_test.return_value = {"ok": True, "latency_ms": 200}
            provider_test(
                "aws_bedrock",
                endpoint="-",
                api_key="k",
                model="nova-pro",
                region="us-west-2",
            )
        mock_test.assert_called_once_with(
            provider_kind="aws_bedrock",
            fields={"endpoint": "-", "api_key": "k", "region": "us-west-2"},
            model_id="nova-pro",
        )

    def test_usage_warning_displayed(self, capsys: Any) -> None:
        with patch("agentheim_code.cli.verify_provider_connection") as mock_test:
            mock_test.return_value = {
                "ok": True,
                "latency_ms": 50,
                "usage_warning": "Provider did not return token usage metadata.",
            }
            provider_test("ollama", endpoint="", api_key="", model="", region="")
