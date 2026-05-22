from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from agentheim_code import __version__
from agentheim_code.coder_cli import coder_app
from agentheim_code.config import ensure_default_config, load_config
from agentheim_code.desktop import DesktopLaunchError, launch_desktop
from agentheim_coder_core.runtime import list_model_options
from agentheim_core.readiness import build_readiness_state
from core.run_view import list_run_views

app = typer.Typer(
    help="Agentheim Code: focused local coding-agent client.",
    no_args_is_help=True,
)
app.add_typer(coder_app, name="coder", help="Persistent local coding sessions.")
console = Console()


def _resolve_workspace(path: Path) -> Path:
    """Resolve and validate a workspace path."""
    resolved = path.resolve()
    if not resolved.exists():
        raise typer.BadParameter(f"Workspace does not exist: {resolved}")
    if not resolved.is_dir():
        raise typer.BadParameter(f"Workspace must be a directory: {resolved}")
    return resolved


def _config_workspace() -> Path:
    cfg = load_config()
    return Path(cfg.get("core", {}).get("default_workspace", "."))


def _config_port() -> int:
    cfg = load_config()
    return int(cfg.get("core", {}).get("default_port", 8765))


@app.command("version")
def version_cmd() -> None:
    """Show the installed version."""
    console.print(f"agentheim-code, version {__version__}")


@app.command("app")
def app_cmd(
    workspace: Path | None = typer.Option(
        None, "--workspace", help="Workspace directory for the app."
    ),
    port: int | None = typer.Option(None, "--port", help="Local backend port."),
    web: bool = typer.Option(
        False, "--web", help="Use browser fallback instead of the Tauri shell."
    ),
    dev: bool = typer.Option(
        False, "--dev", help="Run source-tree Tauri dev mode. Requires Node, Rust, and checkout."
    ),
) -> None:
    """Launch the Agentheim Code desktop app."""
    if web and dev:
        raise typer.BadParameter("Use only one of --web or --dev.")
    workspace_path = _resolve_workspace(workspace or _config_workspace())
    resolved_port = port if port is not None else _config_port()
    try:
        launch_desktop(workspace=workspace_path, port=resolved_port, web_fallback=web, dev=dev)
    except DesktopLaunchError as exc:
        console.print(f"[red]Desktop launch failed:[/red] {exc}")
        raise typer.Exit(1) from exc


@app.command("models")
def models(
    as_json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """List configured provider profiles and models."""
    payload = list_model_options()
    if as_json:
        console.print_json(json.dumps(payload))
        return
    if not payload.get("configured"):
        console.print(str(payload.get("error", "No provider profiles configured.")))
        return
    for profile in payload.get("profiles", []):
        table = Table(title=f"Models: {profile['name']}")
        table.add_column("role")
        table.add_column("provider")
        table.add_column("model")
        for model in profile.get("models", []):
            table.add_row(
                str(model.get("role", "")),
                str(model.get("provider", "")),
                str(model.get("model", "")),
            )
        console.print(table)


@app.command("doctor")
def doctor(
    as_json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """Check local readiness for coding-agent work."""
    readiness = build_readiness_state(skip_connectivity=True, check_optional_integrations=False)
    payload = readiness.model_dump(mode="json")
    if as_json:
        console.print_json(json.dumps(payload))
        return
    console.print(f"status: {readiness.status}")
    console.print(f"profile: {readiness.profile_name or 'none'}")
    console.print(f"providers: {len(readiness.configured_providers)}")


@app.command("runs")
def runs(
    workspace: Path | None = typer.Option(
        None, "--workspace", help="Workspace directory to inspect."
    ),
    as_json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """List recent coder-compatible run artifacts."""
    workspace_path = _resolve_workspace(workspace or _config_workspace())
    views = list_run_views(workspace_path)
    if as_json:
        console.print_json(json.dumps([view.model_dump(mode="json") for view in views]))
        return
    table = Table(title="Agentheim Code Runs")
    table.add_column("run")
    table.add_column("workflow")
    table.add_column("status")
    for view in views:
        table.add_row(view.run_id, view.workflow_id or "", view.status)
    console.print(table)


@app.command("completions")
def completions(
    shell: str = typer.Argument(..., help="Shell: bash, zsh, fish, powershell"),
) -> None:
    """Generate shell completion script."""
    import typer.completion

    typer.completion.completion_init()
    script = typer.completion.get_completion_script(
        prog_name="agentheim-code",
        complete_var="_AGENTHEIM_CODE_COMPLETE",
        shell=shell,
    )
    console.print(script)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )
    logging.getLogger("boto3").setLevel(logging.WARNING)
    logging.getLogger("botocore").setLevel(logging.WARNING)
    ensure_default_config()
    app()


if __name__ == "__main__":
    main()
