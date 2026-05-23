"""Tests for provider-agnostic usage extraction."""

from __future__ import annotations

from providers.usage import Usage, extract_usage


class TestExtractUsageOpenAI:
    def test_extracts_prompt_and_completion_tokens(self) -> None:
        raw = {"usage": {"prompt_tokens": 42, "completion_tokens": 17, "total_tokens": 59}}
        usage = extract_usage("openai_v1", raw, model="gpt-4o", provider="openai")
        assert usage is not None
        assert usage.input_tokens == 42
        assert usage.output_tokens == 17
        assert usage.total_tokens == 59
        assert usage.model == "gpt-4o"
        assert usage.provider == "openai"

    def test_openai_compatible_alias(self) -> None:
        raw = {"usage": {"prompt_tokens": 10, "completion_tokens": 5}}
        usage = extract_usage("openai_compatible", raw, model="x", provider="y")
        assert usage is not None
        assert usage.input_tokens == 10
        assert usage.output_tokens == 5

    def test_missing_usage_returns_none(self) -> None:
        usage = extract_usage("openai_v1", {}, model="gpt-4o", provider="openai")
        assert usage is None

    def test_none_raw_returns_none(self) -> None:
        usage = extract_usage("openai_v1", None, model="gpt-4o", provider="openai")
        assert usage is None


class TestExtractUsageAnthropic:
    def test_extracts_input_and_output_tokens(self) -> None:
        raw = {"usage": {"input_tokens": 100, "output_tokens": 50}}
        usage = extract_usage("anthropic", raw, model="claude-sonnet-4", provider="anthropic")
        assert usage is not None
        assert usage.input_tokens == 100
        assert usage.output_tokens == 50
        assert usage.total_tokens == 150

    def test_missing_usage_returns_none(self) -> None:
        usage = extract_usage("anthropic", {"content": []}, model="claude", provider="anthropic")
        assert usage is None


class TestExtractUsageGemini:
    def test_extracts_prompt_and_candidates_tokens(self) -> None:
        raw = {
            "usageMetadata": {
                "promptTokenCount": 33,
                "candidatesTokenCount": 12,
                "totalTokenCount": 45,
            }
        }
        usage = extract_usage("gemini", raw, model="gemini-flash", provider="google")
        assert usage is not None
        assert usage.input_tokens == 33
        assert usage.output_tokens == 12
        assert usage.total_tokens == 45

    def test_vertex_alias(self) -> None:
        raw = {"usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 3}}
        usage = extract_usage("vertex_ai", raw, model="gemini-pro", provider="vertex")
        assert usage is not None
        assert usage.input_tokens == 5
        assert usage.output_tokens == 3


class TestExtractUsageBedrock:
    def test_extracts_from_custom_raw(self) -> None:
        raw = {"input_tokens": 20, "output_tokens": 10, "total_tokens": 30}
        usage = extract_usage("aws_bedrock", raw, model="nova-pro", provider="aws")
        assert usage is not None
        assert usage.input_tokens == 20
        assert usage.output_tokens == 10

    def test_missing_keys_returns_none(self) -> None:
        usage = extract_usage("aws_bedrock", {"region": "us-east-1"}, model="x", provider="y")
        assert usage is None


class TestExtractUsageCohere:
    def test_extracts_v2_tokens(self) -> None:
        raw = {"usage": {"tokens": {"input_tokens": 15, "output_tokens": 8}}}
        usage = extract_usage("cohere", raw, model="command-r", provider="cohere")
        assert usage is not None
        assert usage.input_tokens == 15
        assert usage.output_tokens == 8

    def test_extracts_top_level_tokens(self) -> None:
        raw = {"usage": {"input_tokens": 7, "output_tokens": 4}}
        usage = extract_usage("cohere", raw, model="command-r", provider="cohere")
        assert usage is not None
        assert usage.input_tokens == 7
        assert usage.output_tokens == 4

    def test_missing_returns_none(self) -> None:
        usage = extract_usage("cohere", {"message": {}}, model="x", provider="y")
        assert usage is None


class TestExtractUsageOllama:
    def test_extracts_eval_counts(self) -> None:
        raw = {"prompt_eval_count": 25, "eval_count": 14}
        usage = extract_usage("ollama_cloud", raw, model="llama3", provider="ollama")
        assert usage is not None
        assert usage.input_tokens == 25
        assert usage.output_tokens == 14

    def test_missing_returns_none(self) -> None:
        usage = extract_usage("ollama_cloud", {"response": "hi"}, model="x", provider="y")
        assert usage is None


class TestExtractUsageOCI:
    def test_extracts_legacy_wrapper_tokens(self) -> None:
        raw = {"input_tokens": 9, "output_tokens": 3, "finish_reason": "stop"}
        usage = extract_usage("oci_genai", raw, model="command-r", provider="oci")
        assert usage is not None
        assert usage.input_tokens == 9
        assert usage.output_tokens == 3

    def test_missing_returns_none(self) -> None:
        usage = extract_usage("oci_genai", {"content": "hi"}, model="x", provider="y")
        assert usage is None


class TestExtractUsageUnknownProvider:
    def test_returns_none_for_unknown_provider(self) -> None:
        usage = extract_usage("unknown_provider", {"usage": {"tokens": 1}}, model="x", provider="y")
        assert usage is None


class TestUsageDataclass:
    def test_to_dict(self) -> None:
        usage = Usage(
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
            model="gpt-4o",
            provider="openai",
            input_cost_usd=0.00001,
            output_cost_usd=0.00002,
            total_cost_usd=0.00003,
        )
        d = usage.to_dict()
        assert d["input_tokens"] == 10
        assert d["output_tokens"] == 5
        assert d["total_cost_usd"] == 0.00003
