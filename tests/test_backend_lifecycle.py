"""Tests for backend lifespan and startup/shutdown hooks."""

from __future__ import annotations

from fastapi.testclient import TestClient

from agentheim_code.backend import create_app


def test_lifespan_shutdown_completes_cleanly(monkeypatch, tmp_path) -> None:
    messages: list[str] = []

    def capture(message: str, *args: object) -> None:
        rendered = message % args if args else message
        messages.append(rendered)

    monkeypatch.setattr("agentheim_code.lifecycle.logger.info", capture)

    with TestClient(create_app(tmp_path)) as client:
        response = client.get("/api/health")
        assert response.status_code == 200

    assert any("backend starting" in message.lower() for message in messages)
    assert any("backend shutting down" in message.lower() for message in messages)
