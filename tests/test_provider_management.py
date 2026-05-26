"""Tests for provider management service layer and API routes."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from agentheim_code.provider_capabilities import get_capabilities
from agentheim_code.provider_discovery import (
    DiscoveredModel,
    list_remote_models,
    normalize_remote_model,
)
from agentheim_code.provider_management import (
    ValidationError,
    add_account,
    add_model,
    assign_role,
    create_profile,
    delete_account,
    delete_model,
    delete_profile,
    duplicate_profile,
    export_profile,
    get_profile,
    import_discovered_models,
    import_profile,
    list_profiles,
    rotate_secret,
    set_default_model,
    set_default_profile,
    update_account,
    update_model,
    validate_account_draft,
)
from config.config import (
    ModelBinding,
    ProfilesDocument,
    ProviderAccount,
    save_profiles_document,
)


@pytest.fixture
def empty_doc(tmp_path: Path):
    path = tmp_path / "profiles.json"
    doc = ProfilesDocument(version=1, default_profile="default", profiles={})
    save_profiles_document(doc, path=path)

    def _path() -> Path:
        return path

    with patch("config.config.get_profiles_path", _path):
        yield path


@pytest.fixture
def sample_profile(empty_doc: Path):
    create_profile("test-profile", set_as_default=True)
    account = ProviderAccount(
        id="openai",
        kind="openai_v1",
        endpoint="https://api.openai.com/v1",
        auth_mode="bearer",
    )
    add_account("test-profile", account)
    model = ModelBinding(
        id="planner",
        role="planner",
        provider="openai",
        model="gpt-4o-mini",
        capabilities=["text", "json"],
        is_default=True,
    )
    add_model("test-profile", model)
    return empty_doc


class TestProfileCrud:
    def test_list_profiles_empty(self, empty_doc: Path) -> None:
        result = list_profiles()
        assert result["configured"] is False
        assert result["profiles"] == []

    def test_create_profile(self, empty_doc: Path) -> None:
        profile = create_profile("my-profile")
        assert profile.name == "my-profile"
        result = list_profiles()
        assert result["configured"] is True
        assert any(p["name"] == "my-profile" for p in result["profiles"])
        assert result["default_profile"] == "my-profile"

    def test_create_duplicate_raises(self, empty_doc: Path) -> None:
        create_profile("my-profile")
        with pytest.raises(ValidationError, match="already exists"):
            create_profile("my-profile")

    def test_get_profile(self, sample_profile: Path) -> None:
        data = get_profile("test-profile")
        assert data["name"] == "test-profile"
        assert len(data["providers"]) == 1
        assert len(data["models"]) == 1

    def test_get_missing_profile_raises(self, empty_doc: Path) -> None:
        with pytest.raises(ValidationError, match="not found"):
            get_profile("missing")

    def test_delete_profile(self, sample_profile: Path) -> None:
        delete_profile("test-profile")
        result = list_profiles()
        assert all(p["name"] != "test-profile" for p in result["profiles"])

    def test_delete_missing_profile_raises(self, empty_doc: Path) -> None:
        with pytest.raises(ValidationError, match="not found"):
            delete_profile("missing")

    def test_set_default_profile(self, sample_profile: Path) -> None:
        create_profile("other")
        set_default_profile("other")
        result = list_profiles()
        assert result["default_profile"] == "other"

    def test_duplicate_profile(self, sample_profile: Path) -> None:
        dup = duplicate_profile("test-profile", "copy")
        assert dup.name == "copy"
        assert "openai" in dup.providers
        # Secrets should NOT be copied
        assert dup.providers["openai"].secret_ref is None

    def test_export_import_roundtrip(self, sample_profile: Path) -> None:
        exported = export_profile("test-profile")
        assert exported["name"] == "test-profile"
        # Secrets must not be present
        for p in exported["providers"]:
            assert p.get("secret_ref") is None

        imported = import_profile(exported, name="imported")
        assert imported.name == "imported"
        assert "openai" in imported.providers

    def test_import_with_bad_provider_ref_raises(self, sample_profile: Path) -> None:
        exported = export_profile("test-profile")
        exported["models"][0]["provider"] = "nonexistent"
        with pytest.raises((ValidationError, Exception), match="unknown provider"):
            import_profile(exported, name="bad")


class TestAccountCrud:
    def test_add_account(self, empty_doc: Path) -> None:
        create_profile("p")
        account = ProviderAccount(id="a1", kind="openai_v1", endpoint="https://example.com/v1")
        added = add_account("p", account)
        assert added.id == "a1"
        data = get_profile("p")
        assert len(data["providers"]) == 1

    def test_add_duplicate_account_raises(self, empty_doc: Path) -> None:
        create_profile("p")
        account = ProviderAccount(id="a1", kind="openai_v1", endpoint="https://example.com/v1")
        add_account("p", account)
        with pytest.raises(ValidationError, match="already exists"):
            add_account("p", account)

    def test_update_account(self, empty_doc: Path) -> None:
        create_profile("p")
        account = ProviderAccount(id="a1", kind="openai_v1", endpoint="https://example.com/v1")
        add_account("p", account)
        updated = update_account("p", "a1", {"endpoint": "https://new.com/v1", "notes": "hello"})
        assert updated.endpoint == "https://new.com/v1"
        assert updated.notes == "hello"

    def test_delete_account(self, empty_doc: Path) -> None:
        create_profile("p")
        account = ProviderAccount(id="a1", kind="openai_v1", endpoint="https://example.com/v1")
        add_account("p", account)
        delete_account("p", "a1")
        data = get_profile("p")
        assert len(data["providers"]) == 0

    def test_delete_account_with_dependent_models_warns(self, sample_profile: Path) -> None:
        with pytest.raises(ValidationError, match="model bindings"):
            delete_account("test-profile", "openai")

    def test_delete_account_cascade(self, sample_profile: Path) -> None:
        delete_account("test-profile", "openai", cascade=True)
        data = get_profile("test-profile")
        assert len(data["providers"]) == 0
        assert len(data["models"]) == 0

    def test_rotate_secret(self, empty_doc: Path) -> None:
        create_profile("p")
        account = ProviderAccount(id="a1", kind="openai_v1", endpoint="https://example.com/v1")
        add_account("p", account)
        rotate_secret("p", "a1", "api_key", "secret123")
        data = get_profile("p")
        acct = next(a for a in data["providers"] if a["id"] == "a1")
        assert acct["has_secret"] is True

    def test_test_account_draft_uses_existing_secret(self, empty_doc: Path) -> None:
        create_profile("p")
        account = ProviderAccount(
            id="a1",
            kind="openai_v1",
            endpoint="https://example.com/v1",
            auth_mode="bearer",
            secret_ref="secret://provider/a1/api_key",
        )
        add_account("p", account)
        with (
            patch("agentheim_code.provider_management.get_secret_store") as mock_store,
            patch("agentheim_code.provider_wizard.verify_provider_connection") as verify,
        ):
            mock_store.return_value.get.return_value = "example-existing-secret"
            verify.return_value = {"ok": True, "latency_ms": 101}
            result = validate_account_draft(
                account.model_copy(update={"endpoint": "https://draft.example/v1"}),
                profile_name="p",
                existing_account_id="a1",
            )
        assert result["ok"] is True
        verify.assert_called_once()
        assert verify.call_args.kwargs["fields"]["api_key"] == "example-existing-secret"
        assert verify.call_args.kwargs["fields"]["endpoint"] == "https://draft.example/v1"

    def test_test_account_draft_uses_deployment_as_sample_model(self, empty_doc: Path) -> None:
        create_profile("p")
        account = ProviderAccount(
            id="azure",
            kind="azure_foundry",
            endpoint="https://example.openai.azure.com",
            auth_mode="api_key",
            metadata={"template": "azure_foundry", "deployment": "gpt-4o-deploy"},
        )
        with patch("agentheim_code.provider_wizard.verify_provider_connection") as verify:
            verify.return_value = {"ok": False, "error": "bad deployment"}
            validate_account_draft(account, secret_value="example-secret")
        assert verify.call_args.kwargs["model_id"] == "gpt-4o-deploy"


class TestModelCrud:
    def test_add_model(self, empty_doc: Path) -> None:
        create_profile("p")
        account = ProviderAccount(id="a1", kind="openai_v1", endpoint="https://example.com/v1")
        add_account("p", account)
        model = ModelBinding(id="m1", role="planner", provider="a1", model="gpt-4")
        add_model("p", model)
        data = get_profile("p")
        assert len(data["models"]) == 1

    def test_add_model_unknown_provider_raises(self, empty_doc: Path) -> None:
        create_profile("p")
        model = ModelBinding(id="m1", role="planner", provider="a1", model="gpt-4")
        with pytest.raises(ValidationError, match="unknown provider"):
            add_model("p", model)

    def test_update_model(self, empty_doc: Path) -> None:
        create_profile("p")
        account = ProviderAccount(id="a1", kind="openai_v1", endpoint="https://example.com/v1")
        add_account("p", account)
        model = ModelBinding(id="m1", role="planner", provider="a1", model="gpt-4")
        add_model("p", model)
        updated = update_model("p", "m1", {"model": "gpt-4o"})
        assert updated.model == "gpt-4o"

    def test_set_default_model(self, empty_doc: Path) -> None:
        create_profile("p")
        account = ProviderAccount(id="a1", kind="openai_v1", endpoint="https://example.com/v1")
        add_account("p", account)
        m1 = ModelBinding(id="m1", role="planner", provider="a1", model="gpt-4")
        m2 = ModelBinding(id="m2", role="planner", provider="a1", model="gpt-4o")
        add_model("p", m1)
        add_model("p", m2)
        set_default_model("p", "m2")
        data = get_profile("p")
        defaults = [m for m in data["models"] if m.get("is_default")]
        assert len(defaults) == 1
        assert defaults[0]["id"] == "m2"

    def test_delete_model(self, empty_doc: Path) -> None:
        create_profile("p")
        account = ProviderAccount(id="a1", kind="openai_v1", endpoint="https://example.com/v1")
        add_account("p", account)
        model = ModelBinding(id="m1", role="planner", provider="a1", model="gpt-4")
        add_model("p", model)
        delete_model("p", "m1")
        data = get_profile("p")
        assert len(data["models"]) == 0

    def test_import_discovered_models(self, empty_doc: Path) -> None:
        create_profile("p")
        account = ProviderAccount(id="a1", kind="openai_v1", endpoint="https://example.com/v1")
        add_account("p", account)
        discovered = [
            {
                "id": "gpt-4",
                "display_name": "GPT-4",
                "provider_model_name": "gpt-4",
                "capabilities": ["text"],
            },
            {
                "id": "gpt-4o",
                "display_name": "GPT-4o",
                "provider_model_name": "gpt-4o",
                "capabilities": ["text", "vision"],
            },
        ]
        imported = import_discovered_models("p", "a1", discovered)
        assert len(imported) == 2
        data = get_profile("p")
        assert len(data["models"]) == 2

    def test_assign_role_rejects_removed_roles(self, empty_doc: Path) -> None:
        create_profile("p")
        account = ProviderAccount(id="a1", kind="openai_v1", endpoint="https://example.com/v1")
        add_account("p", account)
        model = ModelBinding(id="m1", role="planner", provider="a1", model="gpt-4")
        add_model("p", model)
        with pytest.raises(ValidationError, match="Unknown model role 'reviewer'"):
            assign_role("p", "m1", "reviewer")


class TestDiscoveryAdapter:
    def test_capabilities_only_claim_remote_listing_when_real(self) -> None:
        assert get_capabilities("aws_bedrock").supports_remote_model_listing is False
        assert get_capabilities("openai_compatible").supports_remote_model_listing is True

    def test_bedrock_discovery_falls_back_to_empty_manual_flow(self) -> None:
        account = ProviderAccount(
            id="bedrock",
            kind="aws_bedrock",
            endpoint="-",
            auth_mode="aws_chain",
            metadata={"template": "aws_bedrock"},
        )
        assert list_remote_models(account) == []

    def test_normalize_remote_model(self) -> None:
        raw = {
            "id": "gpt-4",
            "display_name": "GPT-4",
            "capabilities": ["text", "json"],
            "context_window": 8192,
            "supports_tools": True,
        }
        dm = normalize_remote_model(raw)
        assert dm.id == "gpt-4"
        assert dm.context_window == 8192
        assert dm.supports_tools is True

    def test_discovered_model_to_dict(self) -> None:
        dm = DiscoveredModel(
            id="x", display_name="X", provider_model_name="x", capabilities=["text"]
        )
        d = dm.to_dict()
        assert d["id"] == "x"
        assert d["source"] == "discovered"


class TestValidationErrors:
    def test_validation_error_to_dict(self) -> None:
        err = ValidationError("E001", "Bad thing", "field1")
        d = err.to_dict()
        assert d["code"] == "E001"
        assert d["field"] == "field1"
