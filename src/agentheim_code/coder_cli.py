from __future__ import annotations

import json
import threading
import webbrowser
from pathlib import Path
from typing import Any, cast

import typer
from rich.console import Console
from rich.table import Table

from agentheim_code.backend import create_app as create_web_app
from workflows.coder.runtime import (
    approve_request,
    cancel_session,
    create_session,
    get_session,
    get_session_view,
    list_file_tree,
    list_model_options,
    list_session_views,
    list_sessions,
    post_message,
    update_session_model,
)

coder_app = typer.Typer(help="Persistent local coding sessions.", invoke_without_command=True)
console = Console()


def _wait_for_web_server(port: int) -> bool:
    import time
    import urllib.error
    import urllib.request

    deadline = time.monotonic() + 15.0
    url = f"http://127.0.0.1:{port}/api/health"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=0.5) as response:
                return bool(response.status < 500)
        except (OSError, urllib.error.URLError):
            time.sleep(0.2)
    return False


def _open_coder_browser_when_ready(port: int, url: str) -> None:
    if _wait_for_web_server(port):
        webbrowser.open(url)


def _serve_coder_ui(workspace: Path, port: int, open_browser: bool) -> None:
    import uvicorn

    workspace = workspace.resolve()
    url = f"http://127.0.0.1:{port}/coder"
    if open_browser:
        thread = threading.Thread(
            target=_open_coder_browser_when_ready,
            args=(port, url),
            daemon=True,
        )
        thread.start()
    console.print(f"Agentheim Code UI: {url}")
    app = create_web_app(workspace)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


def _render_session(session: Any) -> None:
    console.print(f"session id: {session.session_id}")
    console.print(f"workspace: {session.workspace_root}")
    console.print(f"trust mode: {session.trust_mode}")
    console.print(f"status: {session.status}")
    if session.current_assistant_message:
        console.print(f"assistant: {session.current_assistant_message}")
    if session.pending_approval:
        console.print(
            f"approval pending: {session.pending_approval.request_id} ({session.pending_approval.tool_id})"
        )


def _render_view(view: Any) -> None:
    _render_session(view.session)
    if view.diffs:
        table = Table(title="Diffs")
        table.add_column("Path")
        table.add_column("Status")
        for diff in view.diffs:
            table.add_row(diff.path, diff.status)
        console.print(table)
    if view.command_results:
        table = Table(title="Commands")
        table.add_column("Command")
        table.add_column("Exit")
        for result in view.command_results:
            table.add_row(
                " ".join(result.command), "" if result.exit_code is None else str(result.exit_code)
            )
        console.print(table)


def _render_slash_help() -> None:
    console.print(
        "Slash commands: /new, /resume <id>, /sessions, /status, /diff, /files, /approve <id>, /deny <id>, /cancel, /open, /model <provider> <model>, /provider <id>, /profile <name>, /models, /help, exit"
    )


def _render_models(options: dict[str, object]) -> None:
    if not options.get("configured"):
        console.print(str(options.get("error", "No provider profiles configured.")))
        return
    profiles = cast(list[dict[str, Any]], options.get("profiles", []))
    for profile in profiles:
        table = Table(title=f"Coder Models: {profile['name']}")
        table.add_column("role")
        table.add_column("provider")
        table.add_column("model")
        for model in cast(list[dict[str, Any]], profile.get("models", [])):
            table.add_row(
                str(model.get("role", "")),
                str(model.get("provider", "")),
                str(model.get("model", "")),
            )
        console.print(table)


def _interactive_loop(workspace: Path, session: Any) -> None:
    console.print("Interactive coder session. Type `exit` to leave.")
    current = session
    while True:
        entered = typer.prompt("coder", prompt_suffix="> ", default="", show_default=False).strip()
        if entered.lower() in {"exit", "quit"}:
            break
        if not entered:
            continue
        if entered.startswith("/"):
            parts = entered.split()
            command = parts[0].lower()
            if command == "/help":
                _render_slash_help()
            elif command == "/status":
                _render_view(get_session_view(workspace.resolve(), current.session_id))
            elif command == "/sessions":
                for view in list_session_views(workspace.resolve()):
                    console.print(f"{view.session.session_id} {view.session.status}")
            elif command == "/resume" and len(parts) > 1:
                current = get_session(workspace.resolve(), parts[1])
                _render_view(get_session_view(workspace.resolve(), current.session_id))
            elif command == "/new":
                current = create_session(workspace.resolve(), trust_mode=current.trust_mode.value)
                _render_session(current)
            elif command == "/diff":
                for diff in get_session_view(workspace.resolve(), current.session_id).diffs:
                    console.print(f"{diff.path}: {len(diff.before)} -> {len(diff.after)} chars")
            elif command == "/files":
                for item in list_file_tree(workspace.resolve())[:50]:
                    console.print(f"{item['type']}: {item['path']}")
            elif command == "/approve" and len(parts) > 1:
                current = approve_request(
                    workspace.resolve(), current.session_id, parts[1], grant=True
                )
                _render_view(get_session_view(workspace.resolve(), current.session_id))
            elif command == "/deny" and len(parts) > 1:
                current = approve_request(
                    workspace.resolve(), current.session_id, parts[1], grant=False
                )
                _render_view(get_session_view(workspace.resolve(), current.session_id))
            elif command == "/cancel":
                current = cancel_session(workspace.resolve(), current.session_id)
                _render_view(get_session_view(workspace.resolve(), current.session_id))
            elif command == "/open":
                webbrowser.open("http://127.0.0.1:8765/coder")
                console.print("Opened http://127.0.0.1:8765/coder")
            elif command == "/models":
                _render_models(list_model_options())
            elif command == "/model" and len(parts) > 2:
                current = update_session_model(
                    workspace.resolve(), current.session_id, provider=parts[1], model=parts[2]
                )
                console.print(
                    f"provider: {current.model_selection.provider} model: {current.model_selection.model}"
                )
            elif command == "/provider" and len(parts) > 1:
                current = update_session_model(
                    workspace.resolve(), current.session_id, provider=parts[1]
                )
                console.print(f"provider: {current.model_selection.provider}")
            elif command == "/profile" and len(parts) > 1:
                current = update_session_model(
                    workspace.resolve(), current.session_id, profile=parts[1]
                )
                console.print(f"profile: {current.model_selection.profile}")
            else:
                _render_slash_help()
            continue
        current = post_message(workspace.resolve(), current.session_id, entered)
        _render_session(current)
        if current.pending_approval:
            decision = typer.confirm("Grant the pending approval?", default=False)
            if decision:
                current = approve_request(
                    workspace.resolve(),
                    current.session_id,
                    current.pending_approval.request_id,
                    grant=True,
                )
            else:
                current = approve_request(
                    workspace.resolve(),
                    current.session_id,
                    current.pending_approval.request_id,
                    grant=False,
                )
            _render_session(current)


@coder_app.callback()
def coder_root(
    ctx: typer.Context,
    workspace: Path = typer.Option(
        Path.cwd(), "--workspace", help="Workspace directory for the coder session."
    ),
    prompt: str | None = typer.Option(
        None, "--prompt", help="Optional first prompt for a new coder session."
    ),
    trust_mode: str = typer.Option(
        "ask", "--trust-mode", help="Trust mode: read_only, ask, workspace."
    ),
    mode: str = typer.Option(
        "code", "--mode", help="Coder mode: ask, plan, code, review, fix, docs, test."
    ),
    profile: str | None = typer.Option(
        None, "--profile", help="Provider profile for this coder session."
    ),
    provider: str | None = typer.Option(
        None, "--provider", help="Provider id for this coder session."
    ),
    model: str | None = typer.Option(None, "--model", help="Model id for this coder session."),
    as_json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON output."),
) -> None:
    if ctx.invoked_subcommand is not None:
        return
    session = create_session(
        workspace.resolve(),
        trust_mode=trust_mode,
        mode=mode,
        profile=profile,
        provider=provider,
        model=model,
    )
    if prompt:
        session = post_message(workspace.resolve(), session.session_id, prompt)
    if as_json:
        console.print_json(
            json.dumps(
                get_session_view(workspace.resolve(), session.session_id).model_dump(mode="json")
            )
        )
        return
    _render_session(session)
    if not prompt:
        _interactive_loop(workspace.resolve(), session)


@coder_app.command("ui")
def coder_ui(
    workspace: Path = typer.Option(
        Path.cwd(), "--workspace", help="Workspace directory to serve in the coder UI."
    ),
    port: int = typer.Option(8765, "--port", help="Port for the local coder UI."),
    no_browser: bool = typer.Option(
        False, "--no-browser", help="Start the coder UI without opening a browser."
    ),
    as_json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON output."),
) -> None:
    url = f"http://127.0.0.1:{port}/coder"
    if as_json:
        console.print_json(json.dumps({"url": url, "workspace": str(workspace.resolve())}))
        return
    _serve_coder_ui(workspace.resolve(), port, open_browser=not no_browser)


@coder_app.command("list")
def coder_list(
    workspace: Path = typer.Option(
        Path.cwd(), "--workspace", help="Workspace directory to inspect."
    ),
    as_json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON output."),
) -> None:
    sessions = list_sessions(workspace.resolve())
    if as_json:
        views = list_session_views(workspace.resolve())
        console.print_json(json.dumps([view.model_dump(mode="json") for view in views]))
        return
    table = Table(title="Coder Sessions")
    table.add_column("Session")
    table.add_column("Status")
    table.add_column("Trust")
    for session in sessions:
        table.add_row(session.session_id, str(session.status), str(session.trust_mode))
    console.print(table)


@coder_app.command("models")
def coder_models(
    as_json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON output."),
) -> None:
    options = list_model_options()
    if as_json:
        console.print_json(json.dumps(options))
        return
    _render_models(options)


@coder_app.command("resume")
def coder_resume(
    session_id: str,
    workspace: Path = typer.Option(
        Path.cwd(), "--workspace", help="Workspace directory for the session."
    ),
    prompt: str | None = typer.Option(None, "--prompt", help="Optional follow-up prompt."),
    approve: str | None = typer.Option(
        None, "--approve", help="Grant a pending approval request by id."
    ),
    grant: str | None = typer.Option(
        None, "--grant", help="Grant a pending approval request by id."
    ),
    deny: str | None = typer.Option(None, "--deny", help="Deny a pending approval request by id."),
    as_json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON output."),
) -> None:
    grant_id = grant or approve
    if grant_id and deny:
        raise typer.BadParameter("Use only one of --grant or --deny.")
    if grant_id:
        session = approve_request(workspace.resolve(), session_id, grant_id, grant=True)
    elif deny:
        session = approve_request(workspace.resolve(), session_id, deny, grant=False)
    elif prompt:
        session = post_message(workspace.resolve(), session_id, prompt)
    else:
        session = get_session(workspace.resolve(), session_id)
    if as_json:
        console.print_json(
            json.dumps(
                get_session_view(workspace.resolve(), session.session_id).model_dump(mode="json")
            )
        )
        return
    _render_view(get_session_view(workspace.resolve(), session.session_id))
    if not any([grant_id, deny, prompt]):
        _interactive_loop(workspace.resolve(), session)
