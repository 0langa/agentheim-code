"""Misc backend tests for small uncovered paths."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from agentheim_code.backend import (
    _approval_display_fields,
    _chunk_text,
    _prompt_with_context,
    _version,
    _workspace,
    create_app,
)


class TestVersion:
    def test_version_returns_string(self) -> None:
        v = _version()
        assert isinstance(v, str)
        assert v != ""
        assert v == "1.5.0"


class TestWorkspace:
    def test_workspace_with_none(self) -> None:
        base = Path("/tmp/workspace")
        result = _workspace(base, None)
        assert result == base

    def test_workspace_with_dot(self) -> None:
        base = Path("/tmp/workspace")
        result = _workspace(base, ".")
        assert result == base

    def test_workspace_with_relative_path(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            subdir = base / "subdir"
            subdir.mkdir()
            result = _workspace(base, "subdir")
            assert result == subdir.resolve()

    def test_workspace_with_absolute_path(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            abs_path = Path(d) / "workspace"
            abs_path.mkdir()
            result = _workspace(Path("/other"), str(abs_path))
            assert result == abs_path.resolve()

    def test_workspace_nonexistent_raises(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            _workspace(Path("/tmp"), "nonexistent_dir_xyz")
        assert exc_info.value.status_code == 400


class TestCreateApp:
    def test_create_app_with_nonexistent_workspace(self) -> None:
        with pytest.raises(FileNotFoundError):
            create_app("/nonexistent/path/xyz")

    def test_create_app_with_file_workspace(self) -> None:
        with tempfile.NamedTemporaryFile() as f, pytest.raises(NotADirectoryError):
            create_app(f.name)


class TestHelpers:
    def test_chunk_text_handles_empty_and_split_text(self) -> None:
        assert _chunk_text("") == []
        assert _chunk_text("abcdefgh", size=3) == ["abc", "def", "gh"]

    def test_prompt_with_context_uses_legacy_path_listing(self, tmp_path: Path) -> None:
        prompt, errors = _prompt_with_context(
            "Fix auth",
            ["src/app.py", " README.md "],
            tmp_path,
            use_bundle=False,
        )

        assert errors == []
        assert "Selected context files:" in prompt
        assert "- src/app.py" in prompt
        assert "- README.md" in prompt

    def test_prompt_with_context_returns_bundle_errors_without_block(self, tmp_path: Path) -> None:
        bundle = type(
            "Bundle",
            (),
            {
                "errors": ["missing file"],
                "to_prompt_block": staticmethod(lambda: ""),
            },
        )()

        with patch("agentheim_code.backend.build_context_bundle", return_value=bundle):
            prompt, errors = _prompt_with_context("Fix auth", ["src/app.py"], tmp_path)

        assert prompt == "Fix auth"
        assert errors == ["missing file"]

    def test_approval_display_fields_cover_file_and_tool_targets(self) -> None:
        approval = {"tool_id": "browser.open"}

        file_payload = _approval_display_fields(
            approval,
            {"pending_approval": {"params": {"path": "README.md"}}},
        )
        tool_payload = _approval_display_fields(
            approval,
            {"pending_approval": {"params": {"url": "https://example.test"}}},
        )

        assert file_payload["action_kind"] == "file"
        assert file_payload["target"] == "README.md"
        assert tool_payload["action_kind"] == "tool"
        assert tool_payload["target"] == "https://example.test"
