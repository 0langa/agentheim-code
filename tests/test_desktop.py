from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agentheim_code.desktop import _find_desktop_dir, _find_free_port, launch_desktop, serve_web


class TestFindDesktopDir:
    def test_env_override(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        desktop_dir = tmp_path / "apps" / "desktop"
        desktop_dir.mkdir(parents=True)
        (desktop_dir / "package.json").write_text("{}")
        monkeypatch.setenv("AGENTHEIM_CODE_DESKTOP_DIR", str(desktop_dir))
        assert _find_desktop_dir() == desktop_dir

    def test_returns_none_when_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("AGENTHEIM_CODE_DESKTOP_DIR", raising=False)
        # Patch __file__ to a location where no repo structure exists
        with patch("agentheim_code.desktop.__file__", "/tmp/fake_package/desktop.py"):
            assert _find_desktop_dir() is None


class TestFindFreePort:
    def test_returns_start_when_available(self) -> None:
        port = _find_free_port(65432)
        assert port == 65432

    def test_increments_when_in_use(self) -> None:
        import socket

        # Bind a socket and keep it bound to tie up a port
        sock1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock1.bind(("127.0.0.1", 0))
        sock1.listen(1)
        _, used_port = sock1.getsockname()
        try:
            # _find_free_port should skip the used port
            found = _find_free_port(used_port)
            assert found > used_port
        finally:
            sock1.close()


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


class TestLaunchDesktop:
    @patch("agentheim_code.desktop.serve_web")
    def test_web_fallback_skips_tauri(self, mock_serve: MagicMock) -> None:
        launch_desktop(web_fallback=True)
        mock_serve.assert_called_once()
        _, kwargs = mock_serve.call_args
        assert kwargs["port"] == 8765
        assert kwargs["open_browser"] is True

    @patch("agentheim_code.desktop._find_desktop_dir")
    @patch("agentheim_code.desktop.serve_web")
    def test_fallback_when_desktop_dir_not_found(
        self, mock_serve: MagicMock, mock_find: MagicMock
    ) -> None:
        mock_find.return_value = None
        launch_desktop()
        mock_serve.assert_called_once()

    @patch("agentheim_code.desktop._find_desktop_dir")
    @patch("agentheim_code.desktop.subprocess.run")
    @patch("agentheim_code.desktop.serve_web")
    def test_tauri_success(
        self, mock_serve: MagicMock, mock_run: MagicMock, mock_find: MagicMock, tmp_path: Path
    ) -> None:
        desktop_dir = tmp_path / "desktop"
        desktop_dir.mkdir()
        (desktop_dir / "package.json").write_text("{}")
        mock_find.return_value = desktop_dir
        launch_desktop()
        mock_run.assert_called_once()
        mock_serve.assert_not_called()

    @patch("agentheim_code.desktop._find_desktop_dir")
    @patch("agentheim_code.desktop.subprocess.run")
    @patch("agentheim_code.desktop.serve_web")
    def test_tauri_timeout_fallback(
        self, mock_serve: MagicMock, mock_run: MagicMock, mock_find: MagicMock, tmp_path: Path
    ) -> None:
        desktop_dir = tmp_path / "desktop"
        desktop_dir.mkdir()
        (desktop_dir / "package.json").write_text("{}")
        mock_find.return_value = desktop_dir
        mock_run.side_effect = subprocess.TimeoutExpired("npm", 120)
        launch_desktop()
        mock_serve.assert_called_once()

    @patch("agentheim_code.desktop._find_desktop_dir")
    @patch("agentheim_code.desktop.subprocess.run")
    @patch("agentheim_code.desktop.serve_web")
    def test_tauri_called_process_error_fallback(
        self, mock_serve: MagicMock, mock_run: MagicMock, mock_find: MagicMock, tmp_path: Path
    ) -> None:
        desktop_dir = tmp_path / "desktop"
        desktop_dir.mkdir()
        (desktop_dir / "package.json").write_text("{}")
        mock_find.return_value = desktop_dir
        mock_run.side_effect = subprocess.CalledProcessError(1, "npm")
        launch_desktop()
        mock_serve.assert_called_once()
