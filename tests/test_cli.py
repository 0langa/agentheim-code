from __future__ import annotations

from typer.testing import CliRunner
from fastapi.testclient import TestClient

from agentheim_code.backend import create_app
from agentheim_code.cli import app


runner = CliRunner()


def test_help_lists_focused_commands() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "coder" in result.output
    assert "models" in result.output
    assert "doctor" in result.output


def test_models_json_uses_shared_runtime() -> None:
    result = runner.invoke(app, ["models", "--json"])

    assert result.exit_code == 0
    assert "configured" in result.output


def test_backend_health_uses_shared_coder_hub(tmp_path) -> None:
    client = TestClient(create_app(tmp_path))

    health = client.get("/api/health")
    coder = client.get("/coder")

    assert health.status_code == 200
    assert coder.status_code == 200
    assert "Agentheim Coder" in coder.text
