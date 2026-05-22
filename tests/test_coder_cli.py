from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from agentheim_code.coder_cli import (
    _open_coder_browser_when_ready,
    _render_models,
    _render_session,
    _render_slash_help,
    _render_view,
    _serve_coder_ui,
    _wait_for_web_server,
    coder_app,
)

runner = CliRunner()


class TestWaitForWebServer:
    def test_returns_true_when_server_responds(self) -> None:
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            assert _wait_for_web_server(8765) is True

    def test_returns_false_on_timeout(self) -> None:
        with patch("urllib.request.urlopen", side_effect=OSError):
            assert _wait_for_web_server(8765) is False


class TestOpenCoderBrowserWhenReady:
    def test_opens_browser_when_server_ready(self) -> None:
        with (
            patch("agentheim_code.coder_cli._wait_for_web_server", return_value=True) as mock_wait,
            patch("agentheim_code.coder_cli.webbrowser.open") as mock_open,
        ):
            _open_coder_browser_when_ready(8765, "http://127.0.0.1:8765/coder")
            mock_wait.assert_called_once_with(8765)
            mock_open.assert_called_once_with("http://127.0.0.1:8765/coder")

    def test_skips_browser_when_server_not_ready(self) -> None:
        with (
            patch("agentheim_code.coder_cli._wait_for_web_server", return_value=False),
            patch("agentheim_code.coder_cli.webbrowser.open") as mock_open,
        ):
            _open_coder_browser_when_ready(8765, "http://127.0.0.1:8765/coder")
            mock_open.assert_not_called()


class TestServeCoderUI:
    def test_starts_uvicorn_with_correct_args(self) -> None:
        workspace = Path("/tmp/workspace")
        with (
            patch("agentheim_code.coder_cli.create_web_app") as mock_app,
            patch("uvicorn.run") as mock_uvicorn,
            patch("agentheim_code.coder_cli.threading.Thread"),
        ):
            _serve_coder_ui(workspace, 8765, open_browser=False)
            mock_app.assert_called_once()
            assert mock_app.call_args[0][0] == workspace.resolve()
            mock_uvicorn.assert_called_once()
            call_args = mock_uvicorn.call_args
            assert call_args.kwargs["host"] == "127.0.0.1"
            assert call_args.kwargs["port"] == 8765
            assert call_args.kwargs["log_level"] == "warning"


class TestRenderSession:
    def test_renders_basic_session(self) -> None:
        session = MagicMock()
        session.session_id = "sess-123"
        session.workspace_root = "/tmp/ws"
        session.trust_mode = MagicMock()
        session.trust_mode.value = "ask"
        session.status = "active"
        session.current_assistant_message = None
        session.pending_approval = None

        output = _render_session(session)
        assert output is None  # function prints, returns None

    def test_renders_session_with_assistant_message(self) -> None:
        session = MagicMock()
        session.session_id = "sess-123"
        session.workspace_root = "/tmp/ws"
        session.trust_mode = MagicMock()
        session.trust_mode.value = "ask"
        session.status = "active"
        session.current_assistant_message = "Hello"
        session.pending_approval = None

        _render_session(session)

    def test_renders_session_with_pending_approval(self) -> None:
        session = MagicMock()
        session.session_id = "sess-123"
        session.workspace_root = "/tmp/ws"
        session.trust_mode = MagicMock()
        session.trust_mode.value = "ask"
        session.status = "active"
        session.current_assistant_message = None
        session.pending_approval = MagicMock()
        session.pending_approval.request_id = "req-456"
        session.pending_approval.tool_id = "tool-789"

        _render_session(session)


class TestRenderView:
    def test_renders_view_with_diffs(self) -> None:
        session = MagicMock()
        session.session_id = "sess-123"
        session.workspace_root = "/tmp/ws"
        session.trust_mode = MagicMock()
        session.trust_mode.value = "ask"
        session.status = "completed"
        session.current_assistant_message = None
        session.pending_approval = None

        diff = MagicMock()
        diff.path = "hello.py"
        diff.status = "added"
        diff.before = ""
        diff.after = "print('hello')"

        view = MagicMock()
        view.session = session
        view.diffs = [diff]
        view.command_results = []

        _render_view(view)

    def test_renders_view_with_command_results(self) -> None:
        session = MagicMock()
        session.session_id = "sess-123"
        session.workspace_root = "/tmp/ws"
        session.trust_mode = MagicMock()
        session.trust_mode.value = "ask"
        session.status = "completed"
        session.current_assistant_message = None
        session.pending_approval = None

        result = MagicMock()
        result.command = ["python", "test.py"]
        result.exit_code = 0

        view = MagicMock()
        view.session = session
        view.diffs = []
        view.command_results = [result]

        _render_view(view)


class TestRenderSlashHelp:
    def test_outputs_help_text(self) -> None:
        _render_slash_help()


class TestRenderModels:
    def test_renders_error_when_not_configured(self) -> None:
        _render_models({"configured": False, "error": "No providers"})

    def test_renders_profiles_and_models(self) -> None:
        options = {
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
        _render_models(options)


class TestCoderRootCallback:
    @patch("agentheim_code.coder_cli.create_session")
    @patch("agentheim_code.coder_cli.post_message")
    @patch("agentheim_code.coder_cli.get_session_view")
    def test_noninteractive_with_prompt(self, mock_view, mock_post, mock_create) -> None:
        session = MagicMock()
        session.session_id = "sess-123"
        session.trust_mode = MagicMock()
        session.trust_mode.value = "ask"
        session.status = "active"
        session.current_assistant_message = None
        session.pending_approval = None
        session.model_selection = MagicMock()
        session.model_selection.provider = "openai"
        session.model_selection.model = "gpt-4.1"
        session.model_selection.profile = "default"

        mock_create.return_value = session
        mock_post.return_value = session

        view = MagicMock()
        view.session = session
        view.diffs = []
        view.command_results = []
        mock_view.return_value = view

        result = runner.invoke(coder_app, ["--workspace", "/tmp/ws", "--prompt", "hello"])
        assert result.exit_code == 0
        mock_create.assert_called_once()
        mock_post.assert_called_once()

    @patch("agentheim_code.coder_cli.create_session")
    @patch("agentheim_code.coder_cli.get_session_view")
    def test_noninteractive_json_output(self, mock_view, mock_create) -> None:
        session = MagicMock()
        session.session_id = "sess-123"
        session.trust_mode = MagicMock()
        session.trust_mode.value = "ask"
        session.status = "active"
        session.current_assistant_message = None
        session.pending_approval = None
        session.model_selection = MagicMock()
        session.model_selection.provider = "openai"
        session.model_selection.model = "gpt-4.1"
        session.model_selection.profile = "default"

        mock_create.return_value = session

        view = MagicMock()
        view.session = session
        view.diffs = []
        view.command_results = []
        view.model_dump = MagicMock(return_value={"session_id": "sess-123", "status": "active"})
        mock_view.return_value = view

        result = runner.invoke(coder_app, ["--workspace", "/tmp/ws", "--json"])
        assert result.exit_code == 0
        assert "sess-123" in result.output


class TestCoderUiCommand:
    @patch("agentheim_code.coder_cli._serve_coder_ui")
    def test_launches_ui(self, mock_serve) -> None:
        result = runner.invoke(coder_app, ["ui", "--workspace", "/tmp/ws", "--port", "9999"])
        assert result.exit_code == 0
        mock_serve.assert_called_once_with(Path("/tmp/ws").resolve(), 9999, open_browser=True)

    @patch("agentheim_code.coder_cli._serve_coder_ui")
    def test_no_browser_flag(self, mock_serve) -> None:
        result = runner.invoke(coder_app, ["ui", "--workspace", "/tmp/ws", "--no-browser"])
        assert result.exit_code == 0
        mock_serve.assert_called_once_with(Path("/tmp/ws").resolve(), 8765, open_browser=False)

    def test_json_output(self) -> None:
        result = runner.invoke(coder_app, ["ui", "--workspace", "/tmp/ws", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert "url" in payload
        assert "workspace" in payload


class TestCoderListCommand:
    @patch("agentheim_code.coder_cli.list_sessions")
    def test_lists_sessions_as_table(self, mock_list) -> None:
        session = MagicMock()
        session.session_id = "sess-123"
        session.status = "active"
        session.trust_mode = MagicMock()
        session.trust_mode.value = "ask"
        mock_list.return_value = [session]

        result = runner.invoke(coder_app, ["list", "--workspace", "/tmp/ws"])
        assert result.exit_code == 0
        assert "sess-123" in result.output

    @patch("agentheim_code.coder_cli.list_sessions")
    @patch("agentheim_code.coder_cli.list_session_views")
    def test_lists_sessions_as_json(self, mock_views, mock_sessions) -> None:
        session = MagicMock()
        session.session_id = "sess-123"
        session.status = "active"
        session.trust_mode = MagicMock()
        session.trust_mode.value = "ask"

        mock_sessions.return_value = [session]

        view = MagicMock()
        view.session = session
        view.model_dump = MagicMock(return_value={"session_id": "sess-123", "status": "active"})
        mock_views.return_value = [view]

        result = runner.invoke(coder_app, ["list", "--workspace", "/tmp/ws", "--json"])
        assert result.exit_code == 0
        assert "sess-123" in result.output


class TestCoderModelsCommand:
    @patch("agentheim_code.coder_cli.list_model_options")
    def test_shows_models_as_table(self, mock_list) -> None:
        mock_list.return_value = {
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
        result = runner.invoke(coder_app, ["models"])
        assert result.exit_code == 0
        assert "openai" in result.output

    @patch("agentheim_code.coder_cli.list_model_options")
    def test_shows_models_as_json(self, mock_list) -> None:
        mock_list.return_value = {"configured": False, "error": "No providers"}
        result = runner.invoke(coder_app, ["models", "--json"])
        assert result.exit_code == 0
        assert "No providers" in result.output


class TestCoderResumeCommand:
    @patch("agentheim_code.coder_cli.approve_request")
    @patch("agentheim_code.coder_cli.get_session_view")
    def test_approve_request(self, mock_view, mock_approve) -> None:
        session = MagicMock()
        session.session_id = "sess-123"
        session.trust_mode = MagicMock()
        session.trust_mode.value = "ask"
        session.status = "active"
        session.current_assistant_message = None
        session.pending_approval = None

        mock_approve.return_value = session
        view = MagicMock()
        view.session = session
        view.diffs = []
        view.command_results = []
        mock_view.return_value = view

        result = runner.invoke(
            coder_app, ["resume", "sess-123", "--workspace", "/tmp/ws", "--approve", "req-456"]
        )
        assert result.exit_code == 0
        mock_approve.assert_called_once()

    @patch("agentheim_code.coder_cli.approve_request")
    @patch("agentheim_code.coder_cli.get_session_view")
    def test_grant_and_deny_conflict(self, mock_view, mock_approve) -> None:
        result = runner.invoke(
            coder_app,
            [
                "resume",
                "sess-123",
                "--workspace",
                "/tmp/ws",
                "--grant",
                "req-456",
                "--deny",
                "req-456",
            ],
        )
        assert result.exit_code != 0
        assert "Use only one of --grant or --deny" in result.output

    @patch("agentheim_code.coder_cli.post_message")
    @patch("agentheim_code.coder_cli.get_session_view")
    def test_resume_with_prompt(self, mock_view, mock_post) -> None:
        session = MagicMock()
        session.session_id = "sess-123"
        session.trust_mode = MagicMock()
        session.trust_mode.value = "ask"
        session.status = "active"
        session.current_assistant_message = None
        session.pending_approval = None

        mock_post.return_value = session
        view = MagicMock()
        view.session = session
        view.diffs = []
        view.command_results = []
        mock_view.return_value = view

        result = runner.invoke(
            coder_app, ["resume", "sess-123", "--workspace", "/tmp/ws", "--prompt", "continue"]
        )
        assert result.exit_code == 0
        mock_post.assert_called_once()

    @patch("agentheim_code.coder_cli.get_session")
    @patch("agentheim_code.coder_cli.get_session_view")
    def test_resume_interactive(self, mock_view, mock_get) -> None:
        session = MagicMock()
        session.session_id = "sess-123"
        session.trust_mode = MagicMock()
        session.trust_mode.value = "ask"
        session.status = "active"
        session.current_assistant_message = None
        session.pending_approval = None

        mock_get.return_value = session
        view = MagicMock()
        view.session = session
        view.diffs = []
        view.command_results = []
        mock_view.return_value = view

        result = runner.invoke(
            coder_app, ["resume", "sess-123", "--workspace", "/tmp/ws"], input="exit\n"
        )
        assert result.exit_code == 0
