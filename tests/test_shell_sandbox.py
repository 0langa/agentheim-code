from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from tools.shell.sandbox import SandboxConfig, ShellSandbox


def test_resolves_windows_cmd_shims_before_launch(tmp_path: Path) -> None:
    sandbox = ShellSandbox(SandboxConfig(workspace=tmp_path))
    env = {"PATH": "C:\\fake\\node"}

    with (
        patch("tools.shell.sandbox.shutil.which", return_value="C:\\fake\\node\\npm.cmd"),
        patch("tools.shell.sandbox.subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(stdout="", stderr="", returncode=0)
        sandbox.execute(["npm", "test"], env_override=env)

    command = mock_run.call_args.args[0]
    assert command == ["C:\\fake\\node\\npm.cmd", "test"]


def test_allows_python_c_inline_script_arguments(tmp_path: Path) -> None:
    sandbox = ShellSandbox(SandboxConfig(workspace=tmp_path))

    with patch("tools.shell.sandbox.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="['app.js']", stderr="", returncode=0)
        sandbox.execute(
            [
                "python",
                "-c",
                "from pathlib import Path; files=sorted(p.name for p in Path('.').iterdir() if p.is_file()); print(files)",
            ]
        )

    command = mock_run.call_args.args[0]
    assert command[0].lower().endswith("python.exe") or command[0] == "python"
