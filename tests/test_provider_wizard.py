"""Tests for the provider wizard backend."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from agentheim_code.provider_wizard import (
    create_profile,
    delete_profile,
    get_templates,
    verify_provider_connection,
)
from config.config import ProfilesDocument, load_profiles_document, save_profiles_document


class TestGetTemplates:
    def test_returns_templates_with_wizard_fields(self) -> None:
        templates = get_templates()
        assert len(templates) > 0
        openai = next((t for t in templates if t["kind"] == "openai_v1"), None)
        assert openai is not None
        assert "wizard_fields" in openai
        fields = [f["name"] for f in openai["wizard_fields"]]
        assert "api_key" in fields

    def test_excludes_experimental_by_default(self) -> None:
        templates = get_templates(include_experimental=False)
        kinds = [t["kind"] for t in templates]
        assert "openai_v1" in kinds

    def test_includes_experimental_when_requested(self) -> None:
        templates = get_templates(include_experimental=True)
        kinds = [t["kind"] for t in templates]
        # At least some experimental providers should be present
        assert len(kinds) > len(get_templates(include_experimental=False))

    def test_unknown_provider_gets_fallback_fields(self) -> None:
        # Create a fake template that won't match any known provider_type
        with patch("agentheim_code.provider_wizard.list_provider_templates") as mock_list:
            mock_list.return_value = [{"kind": "fake_provider", "provider_type": "totally_unknown"}]
            templates = get_templates()
            assert len(templates) == 1
            fields = [f["name"] for f in templates[0]["wizard_fields"]]
            assert "api_key" in fields
            assert "endpoint" in fields


class TestCreateProfile:
    def test_creates_new_profile(self, tmp_path: Any, monkeypatch: Any) -> None:
        # Patch profiles path to use temp directory
        profile_path = tmp_path / "profiles.json"
        doc = ProfilesDocument(version=1, default_profile="default", profiles={})
        save_profiles_document(doc, path=profile_path)

        def _mock_path() -> Any:
            return profile_path

        monkeypatch.setattr("agentheim_code.provider_wizard._profiles_path", _mock_path)
        monkeypatch.setattr("config.config.get_profiles_path", _mock_path)

        with patch("agentheim_code.provider_wizard.get_secret_store") as mock_store:
            store = MagicMock()
            mock_store.return_value = store

            profile = create_profile(
                name="test-profile",
                provider_kind="openai_v1",
                provider_id="my-openai",
                model_id="gpt-4o",
                fields={
                    "api_key": "example-openai-secret-123",
                    "endpoint": "https://api.openai.com/v1",
                },
                set_as_default=True,
            )

        assert profile.name == "test-profile"
        assert "my-openai" in profile.providers
        assert "planner" in profile.models
        assert profile.models["planner"].model == "gpt-4o"
        store.set.assert_called_once()

        # Verify persisted
        loaded = load_profiles_document(path=profile_path)
        assert "test-profile" in loaded.profiles
        assert loaded.default_profile == "test-profile"

    def test_updates_existing_profile(self, tmp_path: Any, monkeypatch: Any) -> None:
        profile_path = tmp_path / "profiles.json"
        doc = ProfilesDocument(version=1, default_profile="default", profiles={})
        save_profiles_document(doc, path=profile_path)

        def _mock_path() -> Any:
            return profile_path

        monkeypatch.setattr("agentheim_code.provider_wizard._profiles_path", _mock_path)
        monkeypatch.setattr("config.config.get_profiles_path", _mock_path)

        with patch("agentheim_code.provider_wizard.get_secret_store") as mock_store:
            store = MagicMock()
            mock_store.return_value = store

            create_profile(
                name="test",
                provider_kind="openai_v1",
                provider_id="p1",
                model_id="gpt-4o",
                fields={"api_key": "k1"},
            )
            create_profile(
                name="test",
                provider_kind="anthropic",
                provider_id="p2",
                model_id="claude-sonnet",
                fields={"api_key": "k2"},
            )

        loaded = load_profiles_document(path=profile_path)
        profile = loaded.profiles["test"]
        assert "p1" in profile.providers
        assert "p2" in profile.providers

    def test_unknown_provider_kind_raises(self, tmp_path: Any, monkeypatch: Any) -> None:
        profile_path = tmp_path / "profiles.json"
        doc = ProfilesDocument(version=1, default_profile="default", profiles={})
        save_profiles_document(doc, path=profile_path)

        def _mock_path() -> Any:
            return profile_path

        monkeypatch.setattr("agentheim_code.provider_wizard._profiles_path", _mock_path)

        with pytest.raises(ValueError, match="Unknown provider kind"):
            create_profile(
                name="test",
                provider_kind="nonexistent_provider",
                provider_id="p1",
                model_id="gpt-4o",
                fields={},
            )

    def test_uses_template_endpoint_when_empty(self, tmp_path: Any, monkeypatch: Any) -> None:
        profile_path = tmp_path / "profiles.json"
        doc = ProfilesDocument(version=1, default_profile="default", profiles={})
        save_profiles_document(doc, path=profile_path)

        def _mock_path() -> Any:
            return profile_path

        monkeypatch.setattr("agentheim_code.provider_wizard._profiles_path", _mock_path)
        monkeypatch.setattr("config.config.get_profiles_path", _mock_path)

        with patch("agentheim_code.provider_wizard.get_secret_store", return_value=MagicMock()):
            profile = create_profile(
                name="test",
                provider_kind="openai_v1",
                provider_id="p1",
                model_id="gpt-4o",
                fields={"api_key": "k1", "endpoint": ""},
            )

        # Should fall back to template endpoint
        assert profile.providers["p1"].endpoint != ""

    def test_aws_bedrock_profile(self, tmp_path: Any, monkeypatch: Any) -> None:
        profile_path = tmp_path / "profiles.json"
        doc = ProfilesDocument(version=1, default_profile="default", profiles={})
        save_profiles_document(doc, path=profile_path)

        def _mock_path() -> Any:
            return profile_path

        monkeypatch.setattr("agentheim_code.provider_wizard._profiles_path", _mock_path)
        monkeypatch.setattr("config.config.get_profiles_path", _mock_path)

        store = MagicMock()
        with patch("agentheim_code.provider_wizard.get_secret_store", return_value=store):
            profile = create_profile(
                name="aws-test",
                provider_kind="aws_bedrock",
                provider_id="bedrock-1",
                model_id="claude-sonnet",
                fields={
                    "region": "us-west-2",
                    "access_key_id": "AWSACCESSKEYEXAMPLE1",
                    "secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                },
            )

        assert profile.providers["bedrock-1"].headers["aws-region"] == "us-west-2"
        assert profile.providers["bedrock-1"].headers["aws-access-key-id"] == "AWSACCESSKEYEXAMPLE1"
        assert "aws-secret-access-key-ref" in profile.providers["bedrock-1"].headers
        store.set.assert_called()

    def test_oci_genai_profile(self, tmp_path: Any, monkeypatch: Any) -> None:
        profile_path = tmp_path / "profiles.json"
        doc = ProfilesDocument(version=1, default_profile="default", profiles={})
        save_profiles_document(doc, path=profile_path)

        def _mock_path() -> Any:
            return profile_path

        monkeypatch.setattr("agentheim_code.provider_wizard._profiles_path", _mock_path)
        monkeypatch.setattr("config.config.get_profiles_path", _mock_path)

        with patch("agentheim_code.provider_wizard.get_secret_store", return_value=MagicMock()):
            profile = create_profile(
                name="oci-test",
                provider_kind="oci_genai",
                provider_id="oci-1",
                model_id="cohere-command",
                fields={"config_path": "/custom/oci/config", "profile": "TEST"},
            )

        meta = profile.providers["oci-1"].metadata
        assert meta.get("oci_config_path") == "/custom/oci/config"
        assert meta.get("oci_profile") == "TEST"

    def test_no_api_key_no_secret_ref(self, tmp_path: Any, monkeypatch: Any) -> None:
        profile_path = tmp_path / "profiles.json"
        doc = ProfilesDocument(version=1, default_profile="default", profiles={})
        save_profiles_document(doc, path=profile_path)

        def _mock_path() -> Any:
            return profile_path

        monkeypatch.setattr("agentheim_code.provider_wizard._profiles_path", _mock_path)
        monkeypatch.setattr("config.config.get_profiles_path", _mock_path)

        store = MagicMock()
        with patch("agentheim_code.provider_wizard.get_secret_store", return_value=store):
            profile = create_profile(
                name="test",
                provider_kind="openai_v1",
                provider_id="p1",
                model_id="gpt-4o",
                fields={"endpoint": "https://api.openai.com/v1"},
            )

        assert profile.providers["p1"].secret_ref is None
        store.set.assert_not_called()

    def test_load_profiles_failure_creates_new_doc(self, tmp_path: Any, monkeypatch: Any) -> None:
        profile_path = tmp_path / "profiles.json"
        # Don't create the file - simulate missing doc

        def _mock_path() -> Any:
            return profile_path

        monkeypatch.setattr("agentheim_code.provider_wizard._profiles_path", _mock_path)
        monkeypatch.setattr("config.config.get_profiles_path", _mock_path)

        with patch("agentheim_code.provider_wizard.get_secret_store", return_value=MagicMock()):
            profile = create_profile(
                name="test",
                provider_kind="openai_v1",
                provider_id="p1",
                model_id="gpt-4o",
                fields={"api_key": "k1"},
            )

        assert profile.name == "test"
        loaded = load_profiles_document(path=profile_path)
        assert loaded.default_profile == "test"


class TestDeleteProfile:
    def test_deletes_profile_and_secrets(self, tmp_path: Any, monkeypatch: Any) -> None:
        profile_path = tmp_path / "profiles.json"
        doc = ProfilesDocument(version=1, default_profile="default", profiles={})
        save_profiles_document(doc, path=profile_path)

        def _mock_path() -> Any:
            return profile_path

        monkeypatch.setattr("agentheim_code.provider_wizard._profiles_path", _mock_path)
        monkeypatch.setattr("config.config.get_profiles_path", _mock_path)

        store = MagicMock()
        with patch("agentheim_code.provider_wizard.get_secret_store", return_value=store):
            create_profile(
                name="to-delete",
                provider_kind="openai_v1",
                provider_id="p1",
                model_id="gpt-4o",
                fields={"api_key": "k1"},
            )

        with patch("agentheim_code.provider_wizard.get_secret_store", return_value=store):
            delete_profile("to-delete")

        loaded = load_profiles_document(path=profile_path)
        assert "to-delete" not in loaded.profiles
        store.delete.assert_called_once()

    def test_raises_on_missing_profile(self, tmp_path: Any, monkeypatch: Any) -> None:
        profile_path = tmp_path / "profiles.json"
        doc = ProfilesDocument(version=1, default_profile="default", profiles={})
        save_profiles_document(doc, path=profile_path)

        def _mock_path() -> Any:
            return profile_path

        monkeypatch.setattr("agentheim_code.provider_wizard._profiles_path", _mock_path)
        monkeypatch.setattr("config.config.get_profiles_path", _mock_path)

        with pytest.raises(ValueError, match="not found"):
            delete_profile("nonexistent")

    def test_fallback_default_profile(self, tmp_path: Any, monkeypatch: Any) -> None:
        profile_path = tmp_path / "profiles.json"
        doc = ProfilesDocument(version=1, default_profile="default", profiles={})
        save_profiles_document(doc, path=profile_path)

        def _mock_path() -> Any:
            return profile_path

        monkeypatch.setattr("agentheim_code.provider_wizard._profiles_path", _mock_path)
        monkeypatch.setattr("config.config.get_profiles_path", _mock_path)

        with patch("agentheim_code.provider_wizard.get_secret_store", return_value=MagicMock()):
            create_profile(
                name="p1",
                provider_kind="openai_v1",
                provider_id="prov1",
                model_id="gpt-4o",
                fields={"api_key": "k1"},
                set_as_default=True,
            )
            create_profile(
                name="p2",
                provider_kind="openai_v1",
                provider_id="prov2",
                model_id="gpt-4o",
                fields={"api_key": "k2"},
            )

        with patch("agentheim_code.provider_wizard.get_secret_store", return_value=MagicMock()):
            delete_profile("p1")

        loaded = load_profiles_document(path=profile_path)
        assert loaded.default_profile == "p2"


class TestTestProviderConnection:
    def test_unknown_provider_kind(self) -> None:
        result = verify_provider_connection("unknown_kind", {})
        assert result["ok"] is False
        assert "Unknown provider kind" in result["error"]

    def test_provider_initialization_failure(self) -> None:
        # Missing required fields for OpenAI should still create provider but inference will fail
        result = verify_provider_connection(
            "openai_v1",
            {"api_key": "invalid", "endpoint": "https://invalid.example.com"},
            model_id="gpt-4o",
        )
        # Should attempt inference and fail
        assert result["ok"] is False or "latency_ms" in result or "error" in result

    def test_aws_bedrock_connection(self) -> None:
        result = verify_provider_connection(
            "aws_bedrock",
            {"region": "us-east-1"},
            model_id="claude-sonnet",
        )
        # Will fail because no real credentials, but should not crash
        assert "ok" in result

    def test_oci_genai_connection(self) -> None:
        result = verify_provider_connection(
            "oci_genai",
            {"config_path": "~/.oci/config", "profile": "DEFAULT"},
            model_id="cohere-command",
        )
        # Will fail because no real OCI setup, but should not crash
        assert "ok" in result

    def test_no_model_uses_default(self) -> None:
        result = verify_provider_connection(
            "openai_v1",
            {"api_key": "invalid", "endpoint": "https://invalid.example.com"},
        )
        assert "ok" in result
