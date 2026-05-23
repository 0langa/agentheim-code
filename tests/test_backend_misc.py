"""Misc backend tests for small uncovered paths."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from agentheim_code.backend import _version, _workspace, create_app


class TestVersion:
    def test_version_returns_string(self) -> None:
        v = _version()
        assert isinstance(v, str)
        assert v != ""

    def test_version_fallback_when_not_installed(self) -> None:
        from importlib.metadata import PackageNotFoundError

        with patch("agentheim_code.backend.package_version") as mock_ver:
            mock_ver.side_effect = PackageNotFoundError("not found")
            v = _version()
            assert v == "0.8.0"


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
