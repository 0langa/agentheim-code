from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agentheim_code import _serve


class TestServeArgs:
    def test_parse_valid_args(self, tmp_path: Path) -> None:
        workspace, port = _serve._parse_args(["_serve", str(tmp_path), "8765"])
        assert workspace == tmp_path.resolve()
        assert port == 8765

    def test_rejects_missing_args(self) -> None:
        with pytest.raises(SystemExit, match="Usage"):
            _serve._parse_args(["_serve"])

    def test_rejects_missing_workspace(self, tmp_path: Path) -> None:
        with pytest.raises(SystemExit, match="Workspace does not exist"):
            _serve._parse_args(["_serve", str(tmp_path / "missing"), "8765"])

    def test_rejects_invalid_port(self, tmp_path: Path) -> None:
        with pytest.raises(SystemExit, match="Port must be an integer"):
            _serve._parse_args(["_serve", str(tmp_path), "nope"])

    def test_rejects_port_out_of_range(self, tmp_path: Path) -> None:
        with pytest.raises(SystemExit, match="Port must be between"):
            _serve._parse_args(["_serve", str(tmp_path), "70000"])

    @patch("agentheim_code._serve.uvicorn.run")
    def test_main_starts_local_backend(self, mock_run: MagicMock, tmp_path: Path) -> None:
        _serve.main(["_serve", str(tmp_path), "8765"])
        mock_run.assert_called_once()
        _, kwargs = mock_run.call_args
        assert kwargs["host"] == "127.0.0.1"
        assert kwargs["port"] == 8765
