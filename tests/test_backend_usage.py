"""Tests for the session usage API endpoint."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agentheim_code.backend import create_app
from core.events import EventType
from core.ledger import RunLedger


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    app = create_app(workspace=str(tmp_path))
    client = TestClient(app)
    client.cookies.set("agentheim_session", app.state.session_secret)
    client.headers["x-csrf-token"] = app.state.csrf_token
    return client


class TestSessionUsageEndpoint:
    def test_no_session_returns_zeros(self, client: TestClient) -> None:
        resp = client.get("/api/coder/sessions/nonexistent/usage")
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == "nonexistent"
        assert data["input_tokens"] == 0
        assert data["output_tokens"] == 0
        assert data["total_tokens"] == 0
        assert data["calls"] == 0
        assert data["breakdown"] == []

    def test_aggregates_agent_invoked_events(self, client: TestClient, tmp_path: Path) -> None:
        # Create a session run directory with a ledger containing AGENT_INVOKED events
        run_dir = tmp_path / ".ai-team" / "runs" / "test-session"
        run_dir.mkdir(parents=True)
        ledger = RunLedger(repo_root=tmp_path, run_dir=run_dir)
        ledger.emit_event(
            EventType.AGENT_INVOKED,
            payload={
                "model": "gpt-4o",
                "provider": "openai",
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "total_tokens": 150,
                    "model": "gpt-4o",
                    "provider": "openai",
                    "total_cost_usd": 0.001,
                },
            },
        )
        ledger.emit_event(
            EventType.AGENT_INVOKED,
            payload={
                "model": "gpt-4o",
                "provider": "openai",
                "usage": {
                    "input_tokens": 200,
                    "output_tokens": 100,
                    "total_tokens": 300,
                    "model": "gpt-4o",
                    "provider": "openai",
                    "total_cost_usd": 0.002,
                },
            },
        )

        resp = client.get("/api/coder/sessions/test-session/usage")
        assert resp.status_code == 200
        data = resp.json()
        assert data["input_tokens"] == 300
        assert data["output_tokens"] == 150
        assert data["total_tokens"] == 450
        assert data["calls"] == 2
        assert data["estimated_cost_usd"] == pytest.approx(0.003)
        assert len(data["breakdown"]) == 2

    def test_ignores_other_event_types(self, client: TestClient, tmp_path: Path) -> None:
        run_dir = tmp_path / ".ai-team" / "runs" / "mixed-session"
        run_dir.mkdir(parents=True)
        ledger = RunLedger(repo_root=tmp_path, run_dir=run_dir)
        ledger.emit_event(EventType.RUN_INITIATED, payload={})
        ledger.emit_event(
            EventType.AGENT_INVOKED,
            payload={
                "model": "x",
                "provider": "y",
                "usage": {
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "total_tokens": 15,
                    "model": "x",
                    "provider": "y",
                },
            },
        )

        resp = client.get("/api/coder/sessions/mixed-session/usage")
        assert resp.status_code == 200
        data = resp.json()
        assert data["calls"] == 1
        assert data["input_tokens"] == 10
