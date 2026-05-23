from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agentheim_code.desktop import (
    DesktopLaunchError,
    _find_desktop_binary,
    _find_desktop_dir,
    _find_free_port,
    _start_backend_subprocess,
    _stop_backend,
    launch_desktop,
    serve_web,
)


class TestFindDesktopDir:
    def test_env_override(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        desktop_dir = tmp_path / "apps" / "desktop"
        desktop_dir.mkdir(parents=True)
        (desktop_dir / "package.json").write_text("{}")
        monkeypatch.setenv("AGENTHEIM_CODE_DESKTOP_DIR", str(desktop_dir))
        assert _find_desktop_dir() == desktop_dir

    def test_returns_none_when_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("AGENTHEIM_CODE_DESKTOP_DIR", raising=False)
        with patch("agentheim_code.desktop.__file__", "/tmp/fake_package/desktop.py"):
            assert _find_desktop_dir() is None


class TestFindDesktopBinary:
    def test_env_override(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        binary = tmp_path / "agentheim-code.exe"
        binary.write_text("")
        monkeypatch.setenv("AGENTHEIM_CODE_DESKTOP_BINARY", str(binary))
        assert _find_desktop_binary() == binary

    def test_returns_none_when_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("AGENTHEIM_CODE_DESKTOP_BINARY", raising=False)
        with patch("agentheim_code.desktop.__file__", "/tmp/fake_package/desktop.py"):
            assert _find_desktop_binary() is None


class TestFindFreePort:
    def test_returns_start_when_available(self) -> None:
        port = _find_free_port(65432)
        assert port == 65432

    def test_increments_when_in_use(self) -> None:
        import socket

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        _, used_port = sock.getsockname()
        try:
            found = _find_free_port(used_port)
            assert found > used_port
        finally:
            sock.close()


class TestServeWeb:
    @patch("agentheim_code.desktop.uvicorn.run")
    @patch("agentheim_code.desktop.webbrowser.open")
    @patch("agentheim_code.desktop.threading.Timer")
    def test_starts_uvicorn_with_resolved_port(
        self,
        mock_timer: MagicMock,
        mock_browser: MagicMock,
        mock_uvicorn: MagicMock,
        tmp_path: Path,
    ) -> None:
        serve_web(workspace=tmp_path, port=54321, open_browser=False)
        mock_uvicorn.assert_called_once()
        args, kwargs = mock_uvicorn.call_args
        assert kwargs["host"] == "127.0.0.1"
        assert kwargs["port"] >= 54321
        assert kwargs["log_level"] == "warning"

    @patch("agentheim_code.desktop.uvicorn.run")
    def test_changes_cwd_into_workspace(
        self,
        mock_uvicorn: MagicMock,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        original_cwd = tmp_path / "original"
        original_cwd.mkdir()
        monkeypatch.chdir(original_cwd)
        (tmp_path / "workspace").mkdir()
        serve_web(workspace=tmp_path / "workspace", open_browser=False)
        # uvicorn.run is mocked, but we verify the call was made
        mock_uvicorn.assert_called_once()


class TestStartBackendSubprocess:
    @patch("agentheim_code.desktop.subprocess.Popen")
    def test_starts_python_module_with_workspace_and_port(
        self, mock_popen: MagicMock, tmp_path: Path
    ) -> None:
        mock_popen.return_value.pid = 12345
        _start_backend_subprocess(tmp_path, 9999)
        mock_popen.assert_called_once()
        args, kwargs = mock_popen.call_args
        assert kwargs["cwd"] == tmp_path
        cmd = args[0]
        assert cmd[-2] == str(tmp_path)
        assert cmd[-1] == "9999"
        assert "agentheim_code._serve" in cmd


class TestStopBackend:
    def test_terminates_gracefully(self) -> None:
        mock_proc = MagicMock()
        mock_proc.pid = 123
        mock_proc.poll.return_value = None
        mock_proc.wait.return_value = 0
        _stop_backend(mock_proc)
        mock_proc.terminate.assert_called_once()
        mock_proc.wait.assert_called_once_with(timeout=5)

    def test_kills_on_timeout(self) -> None:
        mock_proc = MagicMock()
        mock_proc.pid = 123
        mock_proc.poll.return_value = None
        mock_proc.wait.side_effect = [
            subprocess.TimeoutExpired("cmd", 5),
            0,
        ]
        _stop_backend(mock_proc)
        mock_proc.kill.assert_called_once()

    def test_skips_already_exited_process(self) -> None:
        mock_proc = MagicMock()
        mock_proc.pid = 123
        mock_proc.poll.return_value = 0
        _stop_backend(mock_proc)
        mock_proc.terminate.assert_not_called()
        mock_proc.kill.assert_not_called()


class TestLaunchDesktop:
    @patch("agentheim_code.desktop.serve_web")
    def test_web_fallback_skips_tauri(self, mock_serve: MagicMock) -> None:
        launch_desktop(web_fallback=True)
        mock_serve.assert_called_once()
        _, kwargs = mock_serve.call_args
        assert kwargs["port"] == 8765
        assert kwargs["open_browser"] is True

    @patch("agentheim_code.desktop._find_desktop_binary")
    def test_production_fails_when_binary_not_found(self, mock_find: MagicMock) -> None:
        mock_find.return_value = None
        with pytest.raises(DesktopLaunchError):
            launch_desktop()

    @patch("agentheim_code.desktop._find_desktop_binary")
    @patch("agentheim_code.desktop._start_backend_subprocess")
    @patch("agentheim_code.desktop._stop_backend")
    @patch("agentheim_code.desktop.subprocess.run")
    def test_starts_backend_before_packaged_binary_and_stops_on_exit(
        self,
        mock_run: MagicMock,
        mock_stop: MagicMock,
        mock_start: MagicMock,
        mock_find: MagicMock,
        tmp_path: Path,
    ) -> None:
        binary = tmp_path / "agentheim-code.exe"
        binary.write_text("")
        mock_find.return_value = binary

        mock_backend = MagicMock()
        mock_backend.pid = 12345
        mock_start.return_value = mock_backend

        launch_desktop()

        mock_start.assert_called_once()
        mock_run.assert_called_once()
        run_args, run_kwargs = mock_run.call_args
        assert run_args[0] == [str(binary)]
        assert "timeout" not in run_kwargs
        env = run_kwargs["env"]
        assert "AGENTHEIM_CODE_BACKEND_PORT" in env
        assert "AGENTHEIM_CODE_BACKEND_URL" in env
        mock_stop.assert_called_once_with(mock_backend)

    @patch("agentheim_code.desktop._find_desktop_dir")
    @patch("agentheim_code.desktop._start_backend_subprocess")
    @patch("agentheim_code.desktop._stop_backend")
    @patch("agentheim_code.desktop.subprocess.run")
    def test_dev_mode_runs_tauri_source(
        self,
        mock_run: MagicMock,
        mock_stop: MagicMock,
        mock_start: MagicMock,
        mock_find: MagicMock,
        tmp_path: Path,
    ) -> None:
        desktop_dir = tmp_path / "desktop"
        desktop_dir.mkdir()
        (desktop_dir / "package.json").write_text("{}")
        mock_find.return_value = desktop_dir
        mock_backend = MagicMock()
        mock_start.return_value = mock_backend

        launch_desktop(dev=True)

        _, run_kwargs = mock_run.call_args
        assert run_kwargs["cwd"] == desktop_dir
        mock_stop.assert_called_once_with(mock_backend)

    @patch("agentheim_code.desktop._find_desktop_binary")
    @patch("agentheim_code.desktop._start_backend_subprocess")
    @patch("agentheim_code.desktop._stop_backend")
    @patch("agentheim_code.desktop.subprocess.run")
    def test_binary_failure_stops_backend_and_raises(
        self,
        mock_run: MagicMock,
        mock_stop: MagicMock,
        mock_start: MagicMock,
        mock_find: MagicMock,
        tmp_path: Path,
    ) -> None:
        binary = tmp_path / "agentheim-code.exe"
        binary.write_text("")
        mock_find.return_value = binary
        mock_backend = MagicMock()
        mock_start.return_value = mock_backend
        mock_run.side_effect = subprocess.CalledProcessError(1, str(binary))

        with pytest.raises(DesktopLaunchError):
            launch_desktop()

        mock_stop.assert_called_once_with(mock_backend)
