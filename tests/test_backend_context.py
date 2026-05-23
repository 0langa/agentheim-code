"""Tests for backend context bundle, cancellation, structured errors, and resume."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

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


def test_context_validation_endpoint_rejects_bad_files(
    client: TestClient, workspace_dir: str
) -> None:
    resp = client.post(
        "/api/coder/sessions",
        json={"trust_mode": "ask", "mode": "code"},
    )
    session_id = resp.json()["session_id"]

    resp = client.post(
        f"/api/coder/sessions/{session_id}/context/validate",
        json={"paths": ["missing.txt", ".git/config"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == session_id
    assert len(data["errors"]) == 2
    assert data["total_token_estimate"] == 0


def test_context_validation_endpoint_accepts_good_files(
    client: TestClient, workspace_dir: str
) -> None:
    workspace = Path(workspace_dir)
    (workspace / "src").mkdir()
    (workspace / "src" / "app.py").write_text("print('hi')", encoding="utf-8")

    resp = client.post(
        "/api/coder/sessions",
        json={"trust_mode": "ask", "mode": "code"},
    )
    session_id = resp.json()["session_id"]

    resp = client.post(
        f"/api/coder/sessions/{session_id}/context/validate",
        json={"paths": ["src/app.py"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["status"] == "ok"
    assert data["total_token_estimate"] > 0


def test_cancel_session_endpoint(client: TestClient, workspace_dir: str) -> None:
    resp = client.post(
        "/api/coder/sessions",
        json={"trust_mode": "ask", "mode": "code"},
    )
    session_id = resp.json()["session_id"]

    resp = client.post(f"/api/coder/sessions/{session_id}/cancel")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "cancelled"


def test_cancel_session_returns_structured_error_on_failure(
    client: TestClient, workspace_dir: str
) -> None:
    with patch("agentheim_code.backend.cancel_session", side_effect=RuntimeError("boom")):
        resp = client.post("/api/coder/sessions/nonexistent/cancel")
    assert resp.status_code == 500
    data = resp.json()
    assert "detail" in data
    detail = data["detail"]
    assert detail["error_code"] == "E2004"


def test_post_message_returns_structured_error_on_locked_session(
    client: TestClient, workspace_dir: str
) -> None:
    resp = client.post(
        "/api/coder/sessions",
        json={"trust_mode": "ask", "mode": "code"},
    )
    session_id = resp.json()["session_id"]

    with patch(
        "agentheim_code.backend.post_message",
        side_effect=ValueError("Coder session already running"),
    ):
        resp = client.post(
            f"/api/coder/sessions/{session_id}/messages",
            json={"prompt": "hello"},
        )
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["error_code"] == "E2002"


def test_stream_returns_structured_context_error(client: TestClient, workspace_dir: str) -> None:
    resp = client.post(
        "/api/coder/sessions",
        json={"trust_mode": "ask", "mode": "code"},
    )
    session_id = resp.json()["session_id"]

    with client.stream(
        "POST",
        f"/api/coder/sessions/{session_id}/messages/stream",
        json={"prompt": "hello", "context_files": ["missing.txt"]},
    ) as response:
        body = response.read().decode("utf-8")

    assert response.status_code == 200
    assert "structured_error" in body
    assert "E2003" in body


def test_resume_session_endpoint_for_blocked_session(
    client: TestClient, workspace_dir: str
) -> None:
    from workflows.coder.models import SessionStatus
    from workflows.coder.runtime import _save_session, get_session

    resp = client.post(
        "/api/coder/sessions",
        json={"trust_mode": "ask", "mode": "code"},
    )
    session_id = resp.json()["session_id"]

    workspace = Path(workspace_dir)
    session = get_session(workspace, session_id).model_copy(
        update={"status": SessionStatus.BLOCKED}
    )
    _save_session(workspace, session)

    resp = client.post(f"/api/coder/sessions/{session_id}/resume")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "idle"


def test_resume_session_rejects_running_session(client: TestClient, workspace_dir: str) -> None:
    from workflows.coder.models import SessionStatus
    from workflows.coder.runtime import _save_session, get_session

    resp = client.post(
        "/api/coder/sessions",
        json={"trust_mode": "ask", "mode": "code"},
    )
    session_id = resp.json()["session_id"]

    workspace = Path(workspace_dir)
    session = get_session(workspace, session_id).model_copy(
        update={"status": SessionStatus.RUNNING}
    )
    _save_session(workspace, session)

    resp = client.post(f"/api/coder/sessions/{session_id}/resume")
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["error_code"] == "E2007"


def test_get_session_returns_structured_error_not_found(client: TestClient) -> None:
    resp = client.get("/api/coder/sessions/nonexistent")
    assert resp.status_code == 404
    detail = resp.json()["detail"]
    assert detail["error_code"] == "E2001"


def test_legacy_prompt_only_payload_still_works(client: TestClient, workspace_dir: str) -> None:
    workspace = Path(workspace_dir)
    (workspace / "src").mkdir()
    (workspace / "src" / "app.py").write_text("print('hi')", encoding="utf-8")

    resp = client.post(
        "/api/coder/sessions",
        json={"trust_mode": "ask", "mode": "code"},
    )
    session_id = resp.json()["session_id"]

    from workflows.coder.runtime import get_session

    session = get_session(Path(workspace_dir), session_id).model_copy(
        update={"current_assistant_message": "ok"}
    )

    with (
        patch("agentheim_code.backend.post_message", return_value=session) as post,
        client.stream(
            "POST",
            f"/api/coder/sessions/{session_id}/messages/stream",
            json={
                "prompt": "explain this",
                "context_files": ["src/app.py"],
                "use_context_bundle": False,
            },
        ) as response,
    ):
        response.read()

    assert response.status_code == 200
    prompt = post.call_args.args[2]
    assert "Selected context files:\n- src/app.py" in prompt
    assert "User prompt:\nexplain this" in prompt
