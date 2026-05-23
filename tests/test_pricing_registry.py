"""Tests for the pricing registry and cost estimation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from providers.usage import (
    PricingRegistry,
    Rate,
    Usage,
    get_pricing_registry,
    reset_pricing_registry,
)


class TestRate:
    def test_cost_calculation(self) -> None:
        rate = Rate(input_per_1m=2.50, output_per_1m=10.00)
        # 1000 input + 500 output tokens
        assert rate.cost(1000, 500) == pytest.approx((1000 * 2.50 + 500 * 10.00) / 1_000_000)

    def test_zero_tokens(self) -> None:
        rate = Rate(input_per_1m=1.0, output_per_1m=2.0)
        assert rate.cost(0, 0) == 0.0


class TestPricingRegistryFromDict:
    def test_loads_rates(self) -> None:
        data = {
            "models": {
                "openai_v1/gpt-4o": {
                    "input_per_1m": 2.50,
                    "output_per_1m": 10.00,
                    "currency": "USD",
                },
                "anthropic/claude-sonnet": {"input_per_1m": 3.00, "output_per_1m": 15.00},
            }
        }
        registry = PricingRegistry(data=data)
        rate = registry.get_rate("gpt-4o", "openai_v1")
        assert rate is not None
        assert rate.input_per_1m == 2.50
        assert rate.output_per_1m == 10.00

    def test_bare_model_fallback(self) -> None:
        data = {"models": {"gpt-4o": {"input_per_1m": 1.0, "output_per_1m": 2.0}}}
        registry = PricingRegistry(data=data)
        rate = registry.get_rate("gpt-4o", "some_provider")
        assert rate is not None
        assert rate.input_per_1m == 1.0

    def test_unknown_model_returns_none(self) -> None:
        registry = PricingRegistry(data={"models": {}})
        assert registry.get_rate("unknown", "openai_v1") is None

    def test_override_takes_precedence(self) -> None:
        data = {"models": {"gpt-4o": {"input_per_1m": 1.0, "output_per_1m": 2.0}}}
        overrides = {"gpt-4o": {"input_per_1m": 5.0, "output_per_1m": 10.0}}
        registry = PricingRegistry(data=data, overrides=overrides)
        rate = registry.get_rate("gpt-4o", "openai_v1")
        assert rate is not None
        assert rate.input_per_1m == 5.0

    def test_set_override(self) -> None:
        registry = PricingRegistry(data={"models": {}})
        registry.set_override("custom-model", "custom_provider", 1.0, 2.0)
        rate = registry.get_rate("custom-model", "custom_provider")
        assert rate is not None
        assert rate.input_per_1m == 1.0
        assert rate.output_per_1m == 2.0


class TestPricingRegistryEstimateCost:
    def test_populates_cost_fields(self) -> None:
        registry = PricingRegistry(
            data={"models": {"openai_v1/gpt-4o": {"input_per_1m": 2.50, "output_per_1m": 10.00}}}
        )
        usage = Usage(
            input_tokens=1000,
            output_tokens=500,
            total_tokens=1500,
            model="gpt-4o",
            provider="openai",
            provider_type="openai_v1",
        )
        estimated = registry.estimate_cost(usage)
        assert estimated.input_cost_usd is not None
        assert estimated.output_cost_usd is not None
        assert estimated.total_cost_usd is not None
        assert estimated.total_cost_usd == pytest.approx((1000 * 2.50 + 500 * 10.00) / 1_000_000)

    def test_unknown_model_returns_unchanged(self) -> None:
        registry = PricingRegistry(data={"models": {}})
        usage = Usage(
            input_tokens=10, output_tokens=5, total_tokens=15, model="unknown", provider="x"
        )
        estimated = registry.estimate_cost(usage)
        assert estimated.input_cost_usd is None
        assert estimated.output_cost_usd is None
        assert estimated.total_cost_usd is None


class TestPricingRegistryFromJson:
    def test_loads_from_file(self, tmp_path: Path) -> None:
        path = tmp_path / "pricing.json"
        path.write_text(
            json.dumps({"models": {"gpt-4o": {"input_per_1m": 2.5, "output_per_1m": 10}}})
        )
        registry = PricingRegistry.from_json(path)
        rate = registry.get_rate("gpt-4o", "any")
        assert rate is not None
        assert rate.input_per_1m == 2.5

    def test_missing_file_returns_empty_registry(self, tmp_path: Path) -> None:
        path = tmp_path / "nonexistent.json"
        registry = PricingRegistry.from_json(path)
        assert registry.get_rate("x", "y") is None


class TestGetPricingRegistry:
    def test_singleton(self) -> None:
        reset_pricing_registry()
        r1 = get_pricing_registry()
        r2 = get_pricing_registry()
        assert r1 is r2
