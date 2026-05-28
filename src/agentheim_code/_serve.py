"""CLI helper to run the Agentheim Code backend in a subprocess.

Used by desktop.py so the backend can have its own working directory
without affecting the parent process.
"""

import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import uvicorn

from agentheim_code.backend import create_app


def _parse_args(argv: list[str]) -> tuple[Path, int]:
    if len(argv) != 3:
        raise SystemExit("Usage: python -m agentheim_code._serve <workspace> <port>")
    workspace = Path(argv[1]).resolve()
    if not workspace.exists():
        raise SystemExit(f"Workspace does not exist: {workspace}")
    if not workspace.is_dir():
        raise SystemExit(f"Workspace must be a directory: {workspace}")
    try:
        port = int(argv[2])
    except ValueError as exc:
        raise SystemExit(f"Port must be an integer: {argv[2]}") from exc
    if port < 1 or port > 65535:
        raise SystemExit(f"Port must be between 1 and 65535: {port}")
    return workspace, port


def main(argv: list[str] | None = None) -> None:
    workspace, port = _parse_args(argv or sys.argv)
    app = create_app(workspace)
    nonce = os.environ.get("AGENTHEIM_CODE_LAUNCH_NONCE")
    if nonce:
        app.state.launch_nonce = nonce
        app.state.launch_nonce_expires = datetime.now(UTC) + timedelta(seconds=30)
    uvicorn.run(
        app,  # type: ignore[arg-type]
        host="127.0.0.1",
        port=port,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
