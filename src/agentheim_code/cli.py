from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from agentheim_core.readiness import build_readiness_state
from agentheim_coder_core.runtime import list_model_options
from interfaces.cli.coder_commands import coder_app
from core.run_view import list_run_views

from agentheim_code.desktop import launch_desktop


app = typer.Typer(help="Agentheim Code: focused local coding-agent client.", no_args_is_help=True)
app.add_typer(coder_app, name="coder", help="Persistent local coding sessions.")
console = Console()


@app.command("app")
def app_cmd(
    workspace: Path = typer.Option(Path.cwd(), "--workspace", help="Workspace directory for the app."),
    port: int = typer.Option(8765, "--port", help="Local backend port."),
    web: bool = typer.Option(False, "--web", help="Use browser fallback instead of the Tauri shell."),
) -> None:
    """Launch the Agentheim Code desktop app."""
    launch_desktop(workspace=workspace, port=port, web_fallback=web)


@app.command("models")
def models(as_json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON.")) -> None:
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
            table.add_row(str(model.get("role", "")), str(model.get("provider", "")), str(model.get("model", "")))
        console.print(table)


@app.command("doctor")
def doctor(as_json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON.")) -> None:
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
    workspace: Path = typer.Option(Path.cwd(), "--workspace", help="Workspace directory to inspect."),
    as_json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """List recent coder-compatible run artifacts."""
    views = list_run_views(workspace.resolve())
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


def main() -> None:
    app()


if __name__ == "__main__":
    main()

