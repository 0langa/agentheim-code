from __future__ import annotations

import logging
import os
import socket
import subprocess
import threading
import webbrowser
from pathlib import Path

import uvicorn

from agentheim_code.backend import create_app

logger = logging.getLogger("agentheim_code.desktop")

_DEFAULT_PORT = 8765
_TAURI_TIMEOUT_SECONDS = 120
_BROWSER_OPEN_DELAY = 1.0


def _find_desktop_dir() -> Path | None:
    """Locate the Tauri desktop app directory using multiple strategies."""
    # Strategy 1: Environment override
    env_dir = os.environ.get("AGENTHEIM_CODE_DESKTOP_DIR")
    if env_dir:
        desktop_dir = Path(env_dir).resolve()
        if (desktop_dir / "package.json").exists():
            return desktop_dir

    # Strategy 2: Resolve relative to this source file.
    # Walk up until we find a directory containing both src/ and apps/.
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "src").is_dir() and (parent / "apps" / "desktop" / "package.json").is_file():
            return parent / "apps" / "desktop"

    # Strategy 3: Check adjacent to the installed package (editable installs).
    pkg_dir = current.parent
    candidate = pkg_dir.parents[1] / "apps" / "desktop"
    if (candidate / "package.json").exists():
        return candidate

    return None


def _find_free_port(start: int = _DEFAULT_PORT, host: str = "127.0.0.1") -> int:
    """Return the first available port starting from *start*."""
    port = start
    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind((host, port))
                return port
            except OSError:
                pass
        port += 1


def serve_web(
    workspace: str | Path = ".",
    port: int = _DEFAULT_PORT,
    open_browser: bool = True,
) -> None:
    """Run the local fallback web app."""
    workspace_path = Path(workspace).resolve()
    resolved_port = _find_free_port(port)
    if resolved_port != port:
        logger.warning("Port %s is in use. Using port %s instead.", port, resolved_port)

    url = f"http://127.0.0.1:{resolved_port}/coder"
    if open_browser:
        threading.Timer(_BROWSER_OPEN_DELAY, lambda: webbrowser.open(url)).start()

    uvicorn.run(
        create_app(workspace_path),  # type: ignore[arg-type]
        host="127.0.0.1",
        port=resolved_port,
        log_level="warning",
    )


def launch_desktop(
    workspace: str | Path = ".",
    port: int = _DEFAULT_PORT,
    web_fallback: bool = False,
) -> None:
    """Launch the Tauri desktop app when available, otherwise run web fallback."""
    if web_fallback:
        serve_web(workspace, port=port, open_browser=True)
        return

    desktop_dir = _find_desktop_dir()
    if desktop_dir is None or not (desktop_dir / "package.json").exists():
        logger.info("Tauri desktop source not found; starting web fallback.")
        serve_web(workspace, port=port, open_browser=True)
        return

    env = {
        **os.environ.copy(),
        "AGENTHEIM_CODE_WORKSPACE": str(Path(workspace).resolve()),
        "AGENTHEIM_CODE_BACKEND_PORT": str(port),
    }
    try:
        subprocess.run(
            ["npm", "run", "tauri", "--", "dev"],
            cwd=desktop_dir,
            check=True,
            env=env,
            timeout=_TAURI_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        logger.warning(
            "Tauri dev shell did not start within %ss; starting web fallback.",
            _TAURI_TIMEOUT_SECONDS,
        )
        serve_web(workspace, port=port, open_browser=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        logger.warning("Tauri dev shell unavailable; starting web fallback.")
        serve_web(workspace, port=port, open_browser=True)
