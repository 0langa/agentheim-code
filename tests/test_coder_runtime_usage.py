"""Tests for usage tracking integration in the coder runtime."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from core.events import EventType
from core.ledger import RunLedger
from providers.usage import Usage
from workflows.coder import runtime
from workflows.coder.models import CoderTurnPlan


class FakeProvider:
    def __init__(self, content: str, usage: Usage | None = None) -> None:
        self._content = content
        self._usage = usage

    def invoke(self, request: Any) -> Any:
        response = MagicMock()
        response.content = self._content
        response.usage = self._usage
        response.model = "gpt-4o"
        response.provider = "openai"
        return response


class TestInvokePlannerJsonUsage:
    def test_emits_agent_invoked_event_with_usage(self, tmp_path: Any) -> None:
        ledger = RunLedger.create(tmp_path, "coder")
        usage = Usage(
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
            model="gpt-4o",
            provider="openai",
            total_cost_usd=0.001,
        )
        provider = FakeProvider(
            content='{"assistant_message": "hi", "summary": "test", "actions": []}',
            usage=usage,
        )
        runtime._invoke_planner_json(
            provider=provider,
            role="planner",
            system_prompt="sys",
            user_prompt="user",
            max_output_tokens=1000,
            ledger=ledger,
        )
        events = ledger.query_index(event_type=EventType.AGENT_INVOKED)
        assert len(events) == 1
        assert events[0].payload["usage"]["input_tokens"] == 100
        assert events[0].payload["usage"]["total_cost_usd"] == 0.001

    def test_no_event_when_usage_is_none(self, tmp_path: Any) -> None:
        ledger = RunLedger.create(tmp_path, "coder")
        provider = FakeProvider(
            content='{"assistant_message": "hi", "summary": "test", "actions": []}',
            usage=None,
        )
        runtime._invoke_planner_json(
            provider=provider,
            role="planner",
            system_prompt="sys",
            user_prompt="user",
            max_output_tokens=1000,
            ledger=ledger,
        )
        events = ledger.query_index(event_type=EventType.AGENT_INVOKED)
        assert len(events) == 0

    def test_no_event_when_ledger_is_none(self, tmp_path: Any) -> None:
        usage = Usage(
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
            model="gpt-4o",
            provider="openai",
        )
        provider = FakeProvider(
            content='{"assistant_message": "hi", "summary": "test", "actions": []}',
            usage=usage,
        )
        # Should not raise even without ledger
        runtime._invoke_planner_json(
            provider=provider,
            role="planner",
            system_prompt="sys",
            user_prompt="user",
            max_output_tokens=1000,
            ledger=None,
        )

    def test_emits_events_for_retry_and_compact(self, tmp_path: Any) -> None:
        ledger = RunLedger.create(tmp_path, "coder")
        # First response is bad JSON, second is also bad, third is good
        usage = Usage(
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
            model="gpt-4o",
            provider="openai",
        )

        class MultiProvider:
            def __init__(self) -> None:
                self._calls = 0

            def invoke(self, request: Any) -> Any:
                self._calls += 1
                response = MagicMock()
                response.usage = usage
                response.model = "gpt-4o"
                response.provider = "openai"
                if self._calls <= 2:
                    response.content = "not json"
                else:
                    response.content = '{"assistant_message": "ok", "summary": "ok", "actions": []}'
                return response

        provider = MultiProvider()
        runtime._invoke_planner_json(
            provider=provider,
            role="planner",
            system_prompt="sys",
            user_prompt="user",
            max_output_tokens=1000,
            ledger=ledger,
        )
        events = ledger.query_index(event_type=EventType.AGENT_INVOKED)
        assert len(events) == 3  # original + retry + compact


class TestFillMissingWriteContentsUsage:
    def test_emits_agent_invoked_event(self, tmp_path: Any) -> None:
        ledger = RunLedger.create(tmp_path, "coder")
        usage = Usage(
            input_tokens=50,
            output_tokens=25,
            total_tokens=75,
            model="gpt-4o",
            provider="openai",
        )
        provider = FakeProvider(content="file content here", usage=usage)
        plan = CoderTurnPlan(
            assistant_message="ok",
            summary="ok",
            actions=[
                runtime.CoderAction(kind="write_file", path="test.txt", summary="write", content="")
            ],
        )
        runtime._fill_missing_write_contents(
            provider=provider,
            role="planner",
            prompt="build it",
            plan=plan,
            max_output_tokens=1000,
            ledger=ledger,
        )
        events = ledger.query_index(event_type=EventType.AGENT_INVOKED)
        assert len(events) == 1
        assert events[0].payload["usage"]["input_tokens"] == 50
