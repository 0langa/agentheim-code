"""Tests for backend API routes not covered by other test modules."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

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


def test_health_endpoint(client: TestClient, workspace_dir: str) -> None:
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert workspace_dir in data["workspace"]
    assert resp.headers["x-request-id"]


def test_config_endpoint_reads_and_updates_ui_config(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "config.toml"
    monkeypatch.setattr("agentheim_code.config._config_file", lambda: config_path)

    resp = client.get("/api/config")
    assert resp.status_code == 200
    data = resp.json()
    assert data["onboarding_complete"] is False
    assert data["onboarding_dismissed"] is False
    assert data["theme"] == "dark"

    resp = client.patch(
        "/api/config",
        json={
            "onboarding_dismissed": True,
            "theme": "light",
            "default_workspace": str(tmp_path),
        },
    )
    assert resp.status_code == 200
    updated = resp.json()
    assert updated["onboarding_dismissed"] is True
    assert updated["theme"] == "light"
    assert updated["default_workspace"] == str(tmp_path)

    resp = client.patch("/api/config", json={"theme": "sepia"})
    assert resp.status_code == 400


def test_onboarding_complete_marks_config_complete(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "config.toml"
    monkeypatch.setattr("agentheim_code.config._config_file", lambda: config_path)

    resp = client.post("/api/onboarding/complete", json={"default_workspace": str(tmp_path)})

    assert resp.status_code == 200
    data = resp.json()
    assert data["onboarding_complete"] is True
    assert data["onboarding_dismissed"] is False
    assert data["default_workspace"] == str(tmp_path)


def test_local_provider_detection_reports_ollama_models(client: TestClient) -> None:
    class _Response:
        def __enter__(self) -> _Response:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"models":[{"name":"llama3.2"},{"name":"codellama"}]}'

    with patch("agentheim_code.backend.urllib.request.urlopen", return_value=_Response()):
        resp = client.get("/api/onboarding/local-providers")

    assert resp.status_code == 200
    providers = resp.json()
    assert providers == [
        {
            "kind": "ollama",
            "display_name": "Ollama Local",
            "detected": True,
            "endpoint": "http://localhost:11434/v1",
            "models": ["llama3.2", "codellama"],
        }
    ]


def test_list_sessions_empty(client: TestClient) -> None:
    resp = client.get("/api/coder/sessions")
    assert resp.status_code == 200
    assert resp.json() == []


def test_files_endpoint(client: TestClient) -> None:
    resp = client.get("/api/coder/files")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_files_search_filters_workspace_paths(client: TestClient, workspace_dir: str) -> None:
    workspace = Path(workspace_dir)
    (workspace / "src").mkdir()
    (workspace / "src" / "app.py").write_text("print('hi')", encoding="utf-8")
    (workspace / ".git").mkdir()
    (workspace / ".git" / "config").write_text("secret", encoding="utf-8")

    resp = client.get("/api/coder/files/search", params={"q": "app", "limit": 10})

    assert resp.status_code == 200
    assert resp.json() == [{"path": "src/app.py", "type": "file"}]


def test_runs_endpoint_empty(client: TestClient) -> None:
    resp = client.get("/api/coder/runs")
    assert resp.status_code == 200
    assert resp.json() == []


def test_models_endpoint(client: TestClient) -> None:
    resp = client.get("/api/coder/models")
    assert resp.status_code == 200
    data = resp.json()
    assert "models" in data or "profiles" in data or "default_profile" in data


def test_commands_endpoint(client: TestClient) -> None:
    resp = client.get("/api/coder/commands")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_provider_templates_endpoint(client: TestClient) -> None:
    resp = client.get("/api/providers/templates")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_wizard_templates_endpoint(client: TestClient) -> None:
    resp = client.get("/api/providers/wizard-templates")
    assert resp.status_code == 200
    templates = resp.json()
    assert isinstance(templates, list)
    assert len(templates) > 0
    kinds = [t["kind"] for t in templates]
    assert "openai_v1" in kinds


def test_provider_profiles_unconfigured(client: TestClient) -> None:
    resp = client.get("/api/providers/profiles")
    assert resp.status_code == 200
    data = resp.json()
    assert data["configured"] is False or isinstance(data.get("profiles"), list)


def test_create_and_delete_provider_profile(client: TestClient, workspace_dir: str) -> None:
    profile_path = Path(workspace_dir) / "profiles.json"
    from config.config import ProfilesDocument, save_profiles_document

    doc = ProfilesDocument(version=1, default_profile="default", profiles={})
    save_profiles_document(doc, path=profile_path)

    def _mock_path():
        return profile_path

    with (
        patch("agentheim_code.provider_wizard._profiles_path", _mock_path),
        patch("config.config.get_profiles_path", _mock_path),
        patch("agentheim_code.provider_wizard.get_secret_store", return_value=MagicMock()),
    ):
        resp = client.post(
            "/api/providers/profiles",
            json={
                "name": "test-profile",
                "provider_kind": "openai_v1",
                "provider_id": "my-openai",
                "model_id": "gpt-4o",
                "fields": {"api_key": "sk-test", "endpoint": "https://api.openai.com/v1"},
                "set_as_default": True,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["profile"]["name"] == "test-profile"

        # Delete it
        resp = client.delete("/api/providers/profiles/test-profile")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True


def test_test_provider_endpoint(client: TestClient) -> None:
    resp = client.post(
        "/api/providers/test",
        json={
            "provider_kind": "openai_v1",
            "fields": {"api_key": "invalid", "endpoint": "https://invalid.example.com"},
            "model_id": "gpt-4o-mini",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "ok" in data


def test_index_fallback_no_build(client: TestClient) -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Agentheim Code" in resp.text


def test_coder_index_fallback(client: TestClient) -> None:
    resp = client.get("/coder")
    assert resp.status_code == 200
    assert "Agentheim Code" in resp.text


def test_create_session_and_get_session(client: TestClient) -> None:
    """Create a session and retrieve it."""
    resp = client.post(
        "/api/coder/sessions",
        json={"trust_mode": "ask", "mode": "code"},
    )
    assert resp.status_code == 200
    session = resp.json()
    session_id = session["session_id"]

    # Get the session
    resp = client.get(f"/api/coder/sessions/{session_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == session_id

    # Get session view
    resp = client.get(f"/api/coder/sessions/{session_id}/view")
    assert resp.status_code == 200
    view = resp.json()
    assert view["session"]["session_id"] == session_id

    # Cancel it
    resp = client.post(f"/api/coder/sessions/{session_id}/cancel")
    assert resp.status_code == 200


def test_update_session_mode(client: TestClient) -> None:
    resp = client.post(
        "/api/coder/sessions",
        json={"trust_mode": "ask", "mode": "code"},
    )
    session_id = resp.json()["session_id"]

    resp = client.patch(
        f"/api/coder/sessions/{session_id}/mode",
        json={"mode": "review"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "review"


def test_session_view_enriches_pending_approval_details(
    client: TestClient, workspace_dir: str
) -> None:
    resp = client.post(
        "/api/coder/sessions",
        json={"trust_mode": "ask", "mode": "code"},
    )
    session_id = resp.json()["session_id"]

    from workflows.coder.models import PendingApproval
    from workflows.coder.runtime import _save_session, get_session

    workspace = Path(workspace_dir)
    session = get_session(workspace, session_id).model_copy(
        update={
            "pending_approval": PendingApproval(
                request_id="req-1",
                tool_id="shell.execute",
                params={"command": ["pytest", "-q"], "cwd": "."},
                risk_level="medium",
                reason="Run tests",
                action_index=0,
            )
        }
    )
    _save_session(workspace, session)

    resp = client.get(f"/api/coder/sessions/{session_id}/view")

    assert resp.status_code == 200
    approval = resp.json()["approvals"][0]
    assert approval["params"] == {"command": ["pytest", "-q"], "cwd": "."}
    assert approval["target"] == "pytest -q"
    assert approval["action_kind"] == "shell"


def test_stream_message_endpoint_emits_sse_tokens(client: TestClient, workspace_dir: str) -> None:
    resp = client.post(
        "/api/coder/sessions",
        json={"trust_mode": "ask", "mode": "code"},
    )
    session_id = resp.json()["session_id"]

    from workflows.coder.runtime import get_session

    session = get_session(Path(workspace_dir), session_id).model_copy(
        update={"current_assistant_message": "Hello streaming world"}
    )

    with (
        patch("agentheim_code.backend.post_message", return_value=session),
        client.stream(
            "POST",
            f"/api/coder/sessions/{session_id}/messages/stream",
            json={"prompt": "say hello"},
        ) as response,
    ):
        body = response.read().decode("utf-8")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: start" in body
    assert "event: token" in body
    assert "Hello" in body
    assert "streaming" in body
    assert "event: done" in body


def test_stream_message_includes_selected_context_in_prompt(
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

    from workflows.coder.runtime import get_session

    session = get_session(Path(workspace_dir), session_id).model_copy(
        update={"current_assistant_message": "ok"}
    )

    with (
        patch("agentheim_code.backend.post_message", return_value=session) as post,
        client.stream(
            "POST",
            f"/api/coder/sessions/{session_id}/messages/stream",
            json={"prompt": "explain this", "context_files": ["src/app.py"]},
        ) as response,
    ):
        response.read()

    assert response.status_code == 200
    prompt = post.call_args.args[2]
    assert "<context_files>" in prompt
    assert 'path="src/app.py"' in prompt
    assert "User prompt:\nexplain this" in prompt
