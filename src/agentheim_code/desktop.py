from __future__ import annotations

import logging
import os
import secrets
import socket
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

import uvicorn

from agentheim_code.backend import create_app

logger = logging.getLogger("agentheim_code.desktop")

_DEFAULT_PORT = 8765
_BROWSER_OPEN_DELAY = 1.0


class DesktopLaunchError(RuntimeError):
    """Raised when the production desktop shell cannot be launched."""


def _find_desktop_dir() -> Path | None:
    """Locate the Tauri desktop app directory using multiple strategies."""
    env_dir = os.environ.get("AGENTHEIM_CODE_DESKTOP_DIR")
    if env_dir:
        desktop_dir = Path(env_dir).resolve()
        if (desktop_dir / "package.json").exists():
            return desktop_dir

    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "src").is_dir() and (parent / "apps" / "desktop" / "package.json").is_file():
            return parent / "apps" / "desktop"

    pkg_dir = current.parent
    candidate = pkg_dir.parents[1] / "apps" / "desktop"
    if (candidate / "package.json").exists():
        return candidate

    return None


def _desktop_binary_names() -> list[str]:
    if sys.platform.startswith("win"):
        return ["agentheim-code.exe", "Agentheim Code.exe"]
    if sys.platform == "darwin":
        return [
            "Agentheim Code.app/Contents/MacOS/Agentheim Code",
            "agentheim-code",
        ]
    return ["agentheim-code", "Agentheim Code"]


def _find_desktop_binary() -> Path | None:
    """Locate a packaged Tauri binary without falling back to source dev mode."""
    env_binary = os.environ.get("AGENTHEIM_CODE_DESKTOP_BINARY")
    if env_binary:
        candidate = Path(env_binary).resolve()
        if candidate.exists():
            return candidate

    current = Path(__file__).resolve()
    search_roots = [
        current.parent / "desktop",
        current.parents[2] / "apps" / "desktop" / "src-tauri" / "target" / "release",
    ]
    for root in search_roots:
        for name in _desktop_binary_names():
            candidate = root / name
            if candidate.exists():
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
    """Run the local fallback web app in-process."""
    workspace_path = Path(workspace).resolve()
    resolved_port = _find_free_port(port)
    if resolved_port != port:
        logger.warning(
            "Port %s is in use. Using port %s instead.",
            port,
            resolved_port,
        )

    url = f"http://127.0.0.1:{resolved_port}/coder"
    if open_browser:
        threading.Timer(
            _BROWSER_OPEN_DELAY,
            lambda: webbrowser.open(url),
        ).start()

    # Change into the workspace so that relative paths like "." resolve
    # to the intended directory rather than the process cwd.
    original_cwd = os.getcwd()
    try:
        os.chdir(workspace_path)
        uvicorn.run(
            create_app(workspace_path),  # type: ignore[arg-type]
            host="127.0.0.1",
            port=resolved_port,
            log_level="warning",
        )
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt; shutting down.")
    finally:
        os.chdir(original_cwd)


def _start_backend_subprocess(workspace_path: Path, port: int) -> subprocess.Popen[bytes]:
    """Start the FastAPI backend in a dedicated subprocess."""
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "agentheim_code._serve",
            str(workspace_path),
            str(port),
        ],
        cwd=workspace_path,
    )
    logger.info(
        "Backend started on http://127.0.0.1:%s (pid %s)",
        port,
        proc.pid,
    )
    return proc


def _stop_backend(proc: subprocess.Popen[bytes]) -> None:
    """Terminate the backend subprocess gracefully."""
    if proc.poll() is not None:
        logger.info("Backend (pid %s) already exited.", proc.pid)
        return
    logger.info("Stopping backend (pid %s)...", proc.pid)
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        logger.warning("Backend did not exit gracefully; killing.")
        proc.kill()
        proc.wait()


def launch_desktop(
    workspace: str | Path = ".",
    port: int = _DEFAULT_PORT,
    web_fallback: bool = False,
    dev: bool = False,
) -> None:
    """Launch the production desktop app, dev shell, or web fallback."""
    if web_fallback:
        serve_web(workspace, port=port, open_browser=True)
        return

    workspace_path = Path(workspace).resolve()
    if not workspace_path.exists():
        raise DesktopLaunchError(f"Workspace does not exist: {workspace_path}")
    if not workspace_path.is_dir():
        raise DesktopLaunchError(f"Workspace is not a directory: {workspace_path}")

    # Verify Python backend can start before launching the shell
    try:
        import fastapi  # noqa: F401
        import uvicorn  # noqa: F401
    except ImportError as exc:
        raise DesktopLaunchError(
            "Python backend dependencies are missing. Install with: pip install agentheim-code"
        ) from exc

    resolved_port = _find_free_port(port)
    if resolved_port != port:
        logger.warning(
            "Port %s is in use. Using port %s instead.",
            port,
            resolved_port,
        )

    env = {
        **os.environ.copy(),
        "AGENTHEIM_CODE_WORKSPACE": str(workspace_path),
        "AGENTHEIM_CODE_BACKEND_PORT": str(resolved_port),
        "AGENTHEIM_CODE_BACKEND_URL": f"http://127.0.0.1:{resolved_port}",
    }

    launch_nonce = secrets.token_urlsafe(32)
    env["AGENTHEIM_CODE_LAUNCH_NONCE"] = launch_nonce

    if dev:
        desktop_dir = _find_desktop_dir()
        if desktop_dir is None or not (desktop_dir / "package.json").exists():
            raise DesktopLaunchError(
                "Tauri desktop source was not found. Use `agentheim-code app --web` "
                "for the browser UI, or run --dev from a source checkout."
            )
        command = ["npm", "run", "tauri", "--", "dev"]
        cwd = desktop_dir
    else:
        binary = _find_desktop_binary()
        if binary is None:
            raise DesktopLaunchError(
                "Packaged Agentheim Code desktop binary was not found. Build it with "
                "`npm --prefix apps/desktop run build`, set AGENTHEIM_CODE_DESKTOP_BINARY, "
                "or run `agentheim-code app --web` for the browser fallback."
            )
        command = [str(binary)]
        cwd = workspace_path

    backend_proc: subprocess.Popen[bytes] | None = _start_backend_subprocess(
        workspace_path,
        resolved_port,
    )
    try:
        subprocess.run(command, cwd=cwd, check=True, env=env)
    except FileNotFoundError as exc:
        raise DesktopLaunchError(f"Desktop command is unavailable: {command[0]}") from exc
    except subprocess.CalledProcessError as exc:
        raise DesktopLaunchError(
            f"Desktop command failed with exit code {exc.returncode}."
        ) from exc
    finally:
        if backend_proc is not None:
            _stop_backend(backend_proc)
