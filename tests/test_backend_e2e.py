"""Backend end-to-end tests exercising the full coder flow.

Uses FastAPI TestClient with mocked providers to avoid external calls.
"""

from __future__ import annotations

import tempfile
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from agentheim_code.backend import create_app


@pytest.fixture
def workspace_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


def _make_provider_response(content: str, provider: str = "mock"):
    from providers.base import ModelProvider, ModelRequest, ModelResponse
    from providers.usage import Usage

    class FakeProvider(ModelProvider):
        def __init__(self, config=None):
            self.config = config

        def invoke(self, request: ModelRequest) -> ModelResponse:
            return ModelResponse(
                role=request.role,
                model="mock-model",
                provider=provider,
                content=content,
                raw={
                    "usage": {
                        "prompt_tokens": 15,
                        "completion_tokens": 10,
                        "total_tokens": 25,
                    }
                },
                usage=Usage(
                    input_tokens=15,
                    output_tokens=10,
                    total_tokens=25,
                    model="mock-model",
                    provider=provider,
                    input_cost_usd=0.0000015,
                    output_cost_usd=0.0000020,
                    total_cost_usd=0.0000035,
                ),
            )

    return FakeProvider


def test_coder_session_and_usage_endpoint(workspace_dir: str) -> None:
    """Start a session, run a coder command, verify usage appears in the API."""
    app = create_app(workspace_dir)
    client = TestClient(app)
    client.cookies.set("agentheim_session", app.state.session_secret)
    client.headers["x-csrf-token"] = app.state.csrf_token
    fake_provider_cls = _make_provider_response("ok")

    with patch("core.model_registry.ModelRegistry.create_provider") as mock_create:
        mock_create.return_value = fake_provider_cls()

        # Step 1: Create a session
        resp = client.post(
            "/api/coder/sessions",
            json={"trust_mode": "ask", "mode": "code"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        session_id = data["session_id"]
        assert session_id

        # Step 2: Start a coder turn
        resp = client.post(
            f"/api/coder/sessions/{session_id}/messages",
            json={"prompt": "Create a hello world file"},
        )
        assert resp.status_code == 200, resp.text

        # Step 3: Query usage endpoint
        resp = client.get(f"/api/coder/sessions/{session_id}/usage")
        assert resp.status_code == 200, resp.text
        usage = resp.json()
        assert usage["session_id"] == session_id
        assert usage["input_tokens"] >= 0
        assert usage["output_tokens"] >= 0
        assert usage["total_tokens"] >= 0


def test_usage_endpoint_no_session(workspace_dir: str) -> None:
    """Querying usage for a non-existent session returns zeros."""
    app = create_app(workspace_dir)
    client = TestClient(app)
    client.cookies.set("agentheim_session", app.state.session_secret)
    client.headers["x-csrf-token"] = app.state.csrf_token

    resp = client.get("/api/coder/sessions/nonexistent/usage")
    assert resp.status_code == 200, resp.text
    usage = resp.json()
    assert usage["input_tokens"] == 0
    assert usage["output_tokens"] == 0
    assert usage["total_tokens"] == 0
    assert usage["estimated_cost_usd"] is None
