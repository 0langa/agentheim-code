"""Tests for backend request size limits and request ID propagation."""

from __future__ import annotations

import tempfile

import pytest
from fastapi.testclient import TestClient

from agentheim_code.backend import create_app


@pytest.fixture
def workspace_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def client(workspace_dir: str):
    app = create_app(workspace_dir)
    return TestClient(app)


def test_health_includes_request_id_header(client: TestClient) -> None:
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.headers["x-request-id"]


def test_large_message_request_is_rejected(client: TestClient) -> None:
    resp = client.post("/api/coder/sessions", json={"trust_mode": "ask", "mode": "code"})
    assert resp.status_code == 200
    session_id = resp.json()["session_id"]
    payload = {"prompt": "x" * 300_000}
    resp = client.post(f"/api/coder/sessions/{session_id}/messages", json=payload)
    assert resp.status_code == 413
    detail = resp.json()["detail"]
    assert detail["error_code"] == "E2008"


def test_large_stream_message_request_is_rejected(client: TestClient) -> None:
    resp = client.post("/api/coder/sessions", json={"trust_mode": "ask", "mode": "code"})
    assert resp.status_code == 200
    session_id = resp.json()["session_id"]
    payload = {"prompt": "x" * 300_000}
    resp = client.post(f"/api/coder/sessions/{session_id}/messages/stream", json=payload)
    assert resp.status_code == 413
    detail = resp.json()["detail"]
    assert detail["error_code"] == "E2008"


def test_large_queue_request_is_rejected(client: TestClient) -> None:
    resp = client.post("/api/coder/sessions", json={"trust_mode": "ask", "mode": "code"})
    assert resp.status_code == 200
    session_id = resp.json()["session_id"]
    payload = {"prompt": "x" * 300_000}
    resp = client.post(f"/api/coder/sessions/{session_id}/queue", json=payload)
    assert resp.status_code == 413
    detail = resp.json()["detail"]
    assert detail["error_code"] == "E2008"


def test_large_content_length_header_is_rejected(client: TestClient) -> None:
    resp = client.post(
        "/api/coder/sessions",
        json={"trust_mode": "ask", "mode": "code"},
        headers={"content-length": "999999"},
    )
    assert resp.status_code == 413
    detail = resp.json()["detail"]
    assert detail["error_code"] == "E2008"
    assert resp.headers["x-request-id"]
