from __future__ import annotations

import subprocess
import sys
import threading
import webbrowser
import os
from pathlib import Path

import uvicorn

from agentheim_code.backend import create_app


def serve_web(workspace: str | Path = ".", port: int = 8765, open_browser: bool = True) -> None:
    """Run the local fallback web app."""
    workspace_path = Path(workspace).resolve()
    url = f"http://127.0.0.1:{port}/coder"
    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    uvicorn.run(create_app(workspace_path), host="127.0.0.1", port=port, log_level="warning")


def launch_desktop(workspace: str | Path = ".", port: int = 8765, web_fallback: bool = False) -> None:
    """Launch the Tauri desktop app when available, otherwise run web fallback."""
    if web_fallback:
        serve_web(workspace, port=port, open_browser=True)
        return

    repo_root = Path(__file__).resolve().parents[3]
    desktop_dir = repo_root / "apps" / "desktop"
    if not (desktop_dir / "package.json").exists():
        serve_web(workspace, port=port, open_browser=True)
        return

    env = {
        **os.environ.copy(),
        "AGENTHEIM_CODE_WORKSPACE": str(Path(workspace).resolve()),
        "AGENTHEIM_CODE_BACKEND_PORT": str(port),
    }
    try:
        subprocess.run(["npm", "run", "tauri", "--", "dev"], cwd=desktop_dir, check=True, env=env)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("Tauri dev shell unavailable; starting web fallback.", file=sys.stderr)
        serve_web(workspace, port=port, open_browser=True)
