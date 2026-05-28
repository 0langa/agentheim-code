"""Tests for new provider management API routes."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from agentheim_code.backend import create_app
from config.config import ProfilesDocument, save_profiles_document


@pytest.fixture
def workspace_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def client(workspace_dir: str):
    app = create_app(workspace_dir)
    client = TestClient(app)
    client.cookies.set("agentheim_session", app.state.session_secret)
    client.headers["x-csrf-token"] = app.state.csrf_token
    return client


@pytest.fixture
def profiles_path(workspace_dir: str):
    path = Path(workspace_dir) / "profiles.json"
    doc = ProfilesDocument(version=1, default_profile="default", profiles={})
    save_profiles_document(doc, path=path)

    def _path() -> Path:
        return path

    with patch("config.config.get_profiles_path", _path):
        yield path


class TestManagementProfiles:
    def test_list_profiles(self, client: TestClient, profiles_path: Path) -> None:
        resp = client.get("/api/provider-management/profiles")
        assert resp.status_code == 200
        data = resp.json()
        assert data["configured"] is False

    def test_create_profile(self, client: TestClient, profiles_path: Path) -> None:
        resp = client.post(
            "/api/provider-management/profiles", json={"name": "dev", "set_as_default": True}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["profile"]["name"] == "dev"

    def test_first_created_profile_becomes_default(
        self, client: TestClient, profiles_path: Path
    ) -> None:
        client.post("/api/provider-management/profiles", json={"name": "dev"})
        resp = client.get("/api/provider-management/profiles")
        assert resp.status_code == 200
        assert resp.json()["default_profile"] == "dev"

    def test_invalid_default_profile_is_normalized_on_load(
        self, client: TestClient, profiles_path: Path
    ) -> None:
        save_profiles_document(
            ProfilesDocument(
                version=1,
                default_profile="default",
                profiles={
                    "Azure 5.4": {
                        "name": "Azure 5.4",
                        "providers": {},
                        "models": {},
                        "privacy_mode": "standard",
                    }
                },
            ),
            path=profiles_path,
        )
        resp = client.get("/api/provider-management/profiles")
        assert resp.status_code == 200
        assert resp.json()["default_profile"] == "Azure 5.4"
        assert '"default_profile": "Azure 5.4"' in profiles_path.read_text(encoding="utf-8")

    def test_legacy_planner_capabilities_are_normalized_on_load(
        self, client: TestClient, profiles_path: Path
    ) -> None:
        save_profiles_document(
            ProfilesDocument(
                version=1,
                default_profile="Azure 5.4",
                profiles={
                    "Azure 5.4": {
                        "name": "Azure 5.4",
                        "providers": {
                            "Azure-Foundry-Account": {
                                "id": "Azure-Foundry-Account",
                                "kind": "azure_foundry",
                                "endpoint": "https://coding-eu-resource.openai.azure.com/openai/v1",
                                "auth_mode": "api_key",
                                "timeout_seconds": 60,
                                "headers": {},
                                "metadata": {"template": "azure_foundry", "deployment": "gpt-5.4"},
                            }
                        },
                        "models": {
                            "gpt-5.4": {
                                "id": "gpt-5.4",
                                "role": "planner",
                                "provider": "Azure-Foundry-Account",
                                "model": "gpt-5.4",
                                "capabilities": ["text"],
                            }
                        },
                        "privacy_mode": "standard",
                    }
                },
            ),
            path=profiles_path,
        )
        resp = client.get("/api/provider-management/profiles/Azure%205.4")
        assert resp.status_code == 200
        model = resp.json()["profile"]["models"][0]
        assert "json" in model["capabilities"]
        assert '"json"' in profiles_path.read_text(encoding="utf-8")

    def test_duplicate_profile(self, client: TestClient, profiles_path: Path) -> None:
        client.post("/api/provider-management/profiles", json={"name": "orig"})
        resp = client.post(
            "/api/provider-management/profiles/orig/duplicate", json={"target_name": "copy"}
        )
        assert resp.status_code == 200
        assert resp.json()["profile"]["name"] == "copy"

    def test_export_import(self, client: TestClient, profiles_path: Path) -> None:
        client.post("/api/provider-management/profiles", json={"name": "exp"})
        export = client.get("/api/provider-management/profiles/exp/export")
        assert export.status_code == 200
        data = export.json()["data"]
        assert data["name"] == "exp"

        imp = client.post(
            "/api/provider-management/profiles/import", json={"data": data, "name": "imp"}
        )
        assert imp.status_code == 200
        assert imp.json()["profile"]["name"] == "imp"


class TestManagementAccounts:
    def test_add_account(self, client: TestClient, profiles_path: Path) -> None:
        client.post("/api/provider-management/profiles", json={"name": "p"})
        resp = client.post(
            "/api/provider-management/profiles/p/accounts",
            json={
                "id": "a1",
                "kind": "openai_v1",
                "endpoint": "https://api.openai.com/v1",
                "auth_mode": "bearer",
                "timeout_seconds": 60,
                "headers": {},
                "metadata": {"template": "openai_v1"},
            },
        )
        assert resp.status_code == 200
        assert resp.json()["account"]["id"] == "a1"

    def test_delete_account_with_dependent_models(
        self, client: TestClient, profiles_path: Path
    ) -> None:
        client.post("/api/provider-management/profiles", json={"name": "p"})
        client.post(
            "/api/provider-management/profiles/p/accounts",
            json={
                "id": "a1",
                "kind": "openai_v1",
                "endpoint": "https://example.com/v1",
                "auth_mode": "bearer",
                "timeout_seconds": 60,
                "headers": {},
                "metadata": {},
            },
        )
        client.post(
            "/api/provider-management/profiles/p/models",
            json={
                "id": "m1",
                "role": "planner",
                "provider": "a1",
                "model": "gpt-4",
                "capabilities": ["text"],
            },
        )
        resp = client.delete("/api/provider-management/profiles/p/accounts/a1")
        assert resp.status_code == 400
        assert "detail" in resp.json()

    def test_rotate_secret(self, client: TestClient, profiles_path: Path) -> None:
        client.post("/api/provider-management/profiles", json={"name": "p"})
        client.post(
            "/api/provider-management/profiles/p/accounts",
            json={
                "id": "a1",
                "kind": "openai_v1",
                "endpoint": "https://example.com/v1",
                "auth_mode": "bearer",
                "timeout_seconds": 60,
                "headers": {},
                "metadata": {},
            },
        )
        with patch("agentheim_code.provider_management.get_secret_store", return_value=MagicMock()):
            resp = client.post(
                "/api/provider-management/profiles/p/accounts/a1/rotate-secret",
                json={"secret_name": "api_key", "secret_value": "example-secret-123"},
            )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_test_draft_account(self, client: TestClient, profiles_path: Path) -> None:
        with patch("agentheim_code.backend.validate_account_draft") as test_draft:
            test_draft.return_value = {"ok": True, "latency_ms": 88}
            resp = client.post(
                "/api/provider-management/accounts/test-draft",
                json={
                    "account": {
                        "id": "draft-openai",
                        "kind": "openai_v1",
                        "endpoint": "https://api.openai.com/v1",
                        "auth_mode": "bearer",
                        "timeout_seconds": 60,
                        "headers": {},
                        "metadata": {"template": "openai_v1"},
                    },
                    "secret_value": "example-draft-secret",
                    "profile_name": "p",
                    "existing_account_id": "openai",
                },
            )
        assert resp.status_code == 200
        assert resp.json()["result"]["ok"] is True


class TestManagementModels:
    def test_add_model(self, client: TestClient, profiles_path: Path) -> None:
        client.post("/api/provider-management/profiles", json={"name": "p"})
        client.post(
            "/api/provider-management/profiles/p/accounts",
            json={
                "id": "a1",
                "kind": "openai_v1",
                "endpoint": "https://example.com/v1",
                "auth_mode": "bearer",
                "timeout_seconds": 60,
                "headers": {},
                "metadata": {},
            },
        )
        resp = client.post(
            "/api/provider-management/profiles/p/models",
            json={
                "id": "m1",
                "role": "planner",
                "provider": "a1",
                "model": "gpt-4",
                "capabilities": ["text"],
            },
        )
        assert resp.status_code == 200
        assert resp.json()["model"]["id"] == "m1"

    def test_set_default_model(self, client: TestClient, profiles_path: Path) -> None:
        client.post("/api/provider-management/profiles", json={"name": "p"})
        client.post(
            "/api/provider-management/profiles/p/accounts",
            json={
                "id": "a1",
                "kind": "openai_v1",
                "endpoint": "https://example.com/v1",
                "auth_mode": "bearer",
                "timeout_seconds": 60,
                "headers": {},
                "metadata": {},
            },
        )
        client.post(
            "/api/provider-management/profiles/p/models",
            json={
                "id": "m1",
                "role": "planner",
                "provider": "a1",
                "model": "gpt-4",
                "capabilities": ["text"],
            },
        )
        resp = client.post("/api/provider-management/profiles/p/models/m1/set-default")
        assert resp.status_code == 200
        assert resp.json()["model"]["is_default"] is True

    def test_delete_model(self, client: TestClient, profiles_path: Path) -> None:
        client.post("/api/provider-management/profiles", json={"name": "p"})
        client.post(
            "/api/provider-management/profiles/p/accounts",
            json={
                "id": "a1",
                "kind": "openai_v1",
                "endpoint": "https://example.com/v1",
                "auth_mode": "bearer",
                "timeout_seconds": 60,
                "headers": {},
                "metadata": {},
            },
        )
        client.post(
            "/api/provider-management/profiles/p/models",
            json={
                "id": "m1",
                "role": "planner",
                "provider": "a1",
                "model": "gpt-4",
                "capabilities": ["text"],
            },
        )
        resp = client.delete("/api/provider-management/profiles/p/models/m1")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True


class TestManagementTemplates:
    def test_list_templates(self, client: TestClient) -> None:
        resp = client.get("/api/provider-management/templates")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert any(t["kind"] == "openai_v1" for t in data)

    def test_get_template(self, client: TestClient) -> None:
        resp = client.get("/api/provider-management/templates/openai_v1")
        assert resp.status_code == 200
        assert resp.json()["template"]["kind"] == "openai_v1"

    def test_get_unknown_template(self, client: TestClient) -> None:
        resp = client.get("/api/provider-management/templates/nonexistent")
        assert resp.status_code == 404
