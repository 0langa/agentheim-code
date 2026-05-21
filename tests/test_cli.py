from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from agentheim_code.backend import create_app
from agentheim_code.cli import app

runner = CliRunner()


class TestHelp:
    def test_help_lists_focused_commands(self) -> None:
        result = runner.invoke(app, ["--help"])

        assert result.exit_code == 0
        assert "coder" in result.output
        assert "models" in result.output
        assert "doctor" in result.output


class TestVersion:
    def test_version_command(self) -> None:
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "agentheim-code" in result.output
        assert "0.1.0" in result.output


class TestModels:
    def test_models_json_uses_shared_runtime(self) -> None:
        result = runner.invoke(app, ["models", "--json"])

        assert result.exit_code == 0
        assert "configured" in result.output


class TestDoctor:
    def test_doctor_table_output(self) -> None:
        result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 0
        assert "status:" in result.output

    def test_doctor_json_output(self) -> None:
        result = runner.invoke(app, ["doctor", "--json"])
        assert result.exit_code == 0
        assert "status" in result.output


class TestRuns:
    def test_runs_table_output(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["runs", "--workspace", str(tmp_path)])
        assert result.exit_code == 0
        assert "Agentheim Code Runs" in result.output

    def test_runs_json_output(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["runs", "--workspace", str(tmp_path), "--json"])
        assert result.exit_code == 0
        assert "run_id" in result.output or "[]" in result.output


class TestAppCommand:
    @patch("agentheim_code.cli.launch_desktop")
    def test_app_command_launches_desktop(self, mock_launch: MagicMock, tmp_path: Path) -> None:
        result = runner.invoke(app, ["app", "--workspace", str(tmp_path)])
        assert result.exit_code == 0
        mock_launch.assert_called_once()

    @patch("agentheim_code.cli.launch_desktop")
    def test_app_command_with_web_fallback(self, mock_launch: MagicMock, tmp_path: Path) -> None:
        result = runner.invoke(app, ["app", "--workspace", str(tmp_path), "--web"])
        assert result.exit_code == 0
        _, kwargs = mock_launch.call_args
        assert kwargs["web_fallback"] is True


class TestCompletions:
    def test_completions_bash(self) -> None:
        result = runner.invoke(app, ["completions", "bash"])
        assert result.exit_code == 0
        assert "agentheim-code" in result.output

    def test_completions_zsh(self) -> None:
        result = runner.invoke(app, ["completions", "zsh"])
        assert result.exit_code == 0
        assert "agentheim-code" in result.output


class TestWorkspaceValidation:
    def test_app_rejects_nonexistent_workspace(self) -> None:
        result = runner.invoke(app, ["app", "--workspace", "/nonexistent/path/12345"])
        assert result.exit_code != 0
        assert "does not exist" in result.output

    def test_app_rejects_file_as_workspace(self, tmp_path: Path) -> None:
        file_path = tmp_path / "not_a_dir.txt"
        file_path.write_text("hello")
        result = runner.invoke(app, ["app", "--workspace", str(file_path)])
        assert result.exit_code != 0
        assert "must be a directory" in result.output


class TestBackendHealth:
    def test_backend_health_uses_shared_coder_hub(self, tmp_path: Path) -> None:
        client = TestClient(create_app(tmp_path))

        health = client.get("/api/health")
        coder = client.get("/coder")

        assert health.status_code == 200
        assert coder.status_code == 200
        assert "Agentheim Coder" in coder.text

    def test_backend_rejects_nonexistent_workspace(self) -> None:
        with pytest.raises(FileNotFoundError):
            create_app("/nonexistent/path/12345")

    def test_backend_rejects_file_as_workspace(self, tmp_path: Path) -> None:
        file_path = tmp_path / "not_a_dir.txt"
        file_path.write_text("hello")
        with pytest.raises(NotADirectoryError):
            create_app(file_path)
