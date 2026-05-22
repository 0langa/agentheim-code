from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from agentheim_code.bakeoff import (
    BakeOffResult,
    render_bakeoff_json,
    render_bakeoff_table,
    run_bakeoff,
)
from agentheim_code.cli import app

runner = CliRunner()


class TestRunBakeoff:
    @patch("agentheim_code.bakeoff.create_session")
    @patch("agentheim_code.bakeoff.post_message")
    @patch("agentheim_code.bakeoff.get_session_view")
    def test_single_provider_pass(self, mock_view, mock_post, mock_create) -> None:
        session = MagicMock()
        session.session_id = "sess-1"
        session.status = "completed"
        mock_create.return_value = session
        mock_post.return_value = session

        diff = MagicMock()
        diff.path = "hello.py"
        diff2 = MagicMock()
        diff2.path = "test_hello.py"

        cmd_result = MagicMock()
        cmd_result.exit_code = 0
        cmd_result.command = ["pytest"]

        view = MagicMock()
        view.session = session
        view.diffs = [diff, diff2]
        view.command_results = [cmd_result]
        mock_view.return_value = view

        payload = {
            "configured": True,
            "profiles": [
                {
                    "name": "default",
                    "models": [
                        {"role": "planner", "provider": "openai", "model": "gpt-4.1"},
                    ],
                }
            ],
        }
        results = run_bakeoff(payload, timeout=1.0)
        assert len(results) == 1
        assert results[0].passed is True
        assert results[0].provider == "openai"
        assert results[0].model == "gpt-4.1"

    @patch("agentheim_code.bakeoff.create_session")
    @patch("agentheim_code.bakeoff.post_message")
    @patch("agentheim_code.bakeoff.get_session_view")
    def test_single_provider_fail_missing_files(self, mock_view, mock_post, mock_create) -> None:
        session = MagicMock()
        session.session_id = "sess-1"
        session.status = "completed"
        mock_create.return_value = session
        mock_post.return_value = session

        view = MagicMock()
        view.session = session
        view.diffs = []
        view.command_results = []
        mock_view.return_value = view

        payload = {
            "configured": True,
            "profiles": [
                {
                    "name": "default",
                    "models": [
                        {"role": "planner", "provider": "openai", "model": "gpt-4.1"},
                    ],
                }
            ],
        }
        results = run_bakeoff(payload, timeout=1.0)
        assert len(results) == 1
        assert results[0].passed is False
        assert "Missing files" in results[0].error

    @patch("agentheim_code.bakeoff.create_session")
    @patch("agentheim_code.bakeoff.post_message")
    @patch("agentheim_code.bakeoff.get_session_view")
    def test_filters_by_profile(self, mock_view, mock_post, mock_create) -> None:
        session = MagicMock()
        session.session_id = "sess-1"
        session.status = "completed"
        mock_create.return_value = session
        mock_post.return_value = session

        diff = MagicMock()
        diff.path = "hello.py"
        diff2 = MagicMock()
        diff2.path = "test_hello.py"

        cmd_result = MagicMock()
        cmd_result.exit_code = 0
        cmd_result.command = ["pytest"]

        view = MagicMock()
        view.session = session
        view.diffs = [diff, diff2]
        view.command_results = [cmd_result]
        mock_view.return_value = view

        payload = {
            "configured": True,
            "profiles": [
                {
                    "name": "default",
                    "models": [
                        {"role": "planner", "provider": "openai", "model": "gpt-4.1"},
                    ],
                },
                {
                    "name": "other",
                    "models": [
                        {"role": "planner", "provider": "azure", "model": "gpt-4.1"},
                    ],
                },
            ],
        }
        results = run_bakeoff(payload, profile_filter="default", timeout=1.0)
        assert len(results) == 1
        assert results[0].profile == "default"

    def test_returns_empty_when_not_configured(self) -> None:
        results = run_bakeoff({"configured": False})
        assert results == []


class TestRenderBakeoffTable:
    def test_renders_results(self) -> None:
        results = [
            BakeOffResult(
                profile="default",
                provider="openai",
                model="gpt-4.1",
                passed=True,
                duration=12.5,
            ),
            BakeOffResult(
                profile="default",
                provider="azure",
                model="gpt-4.1",
                passed=False,
                error="Verification failed",
                duration=8.0,
            ),
        ]
        render_bakeoff_table(results)

    def test_handles_empty_results(self) -> None:
        render_bakeoff_table([])


class TestRenderBakeoffJson:
    def test_renders_json(self) -> None:
        results = [
            BakeOffResult(
                profile="default",
                provider="openai",
                model="gpt-4.1",
                passed=True,
                files_created=["hello.py"],
                verification_exit=0,
                duration=12.5,
            ),
        ]
        render_bakeoff_json(results)


class TestBakeOffCli:
    @patch("agentheim_code.cli.run_bakeoff")
    @patch("agentheim_code.cli.list_model_options")
    def test_bake_off_table_output(self, mock_list, mock_run) -> None:
        mock_list.return_value = {
            "configured": True,
            "profiles": [],
        }
        mock_run.return_value = [
            BakeOffResult(
                profile="default",
                provider="openai",
                model="gpt-4.1",
                passed=True,
                duration=10.0,
            ),
        ]
        result = runner.invoke(app, ["bake-off"])
        assert result.exit_code == 0

    @patch("agentheim_code.cli.run_bakeoff")
    @patch("agentheim_code.cli.list_model_options")
    def test_bake_off_json_output(self, mock_list, mock_run) -> None:
        mock_list.return_value = {
            "configured": True,
            "profiles": [],
        }
        mock_run.return_value = [
            BakeOffResult(
                profile="default",
                provider="openai",
                model="gpt-4.1",
                passed=True,
                duration=10.0,
            ),
        ]
        result = runner.invoke(app, ["bake-off", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload[0]["provider"] == "openai"

    @patch("agentheim_code.cli.list_model_options")
    def test_bake_off_exits_when_no_providers(self, mock_list) -> None:
        mock_list.return_value = {"configured": False}
        result = runner.invoke(app, ["bake-off"])
        assert result.exit_code == 1
        assert "No provider profiles configured" in result.output

    @patch("agentheim_code.cli.run_bakeoff")
    @patch("agentheim_code.cli.list_model_options")
    def test_bake_off_exits_with_failure(self, mock_list, mock_run) -> None:
        mock_list.return_value = {"configured": True, "profiles": []}
        mock_run.return_value = [
            BakeOffResult(
                profile="default",
                provider="openai",
                model="gpt-4.1",
                passed=False,
                error="timeout",
            ),
        ]
        result = runner.invoke(app, ["bake-off"])
        assert result.exit_code == 1
