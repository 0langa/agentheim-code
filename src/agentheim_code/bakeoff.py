from __future__ import annotations

import json
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from rich.console import Console
from rich.table import Table

from workflows.coder.runtime import (
    create_session,
    get_session_view,
    post_message,
)

console = Console()

_BAKEOFF_PROMPT = (
    "Write a Python file called hello.py that prints 'Hello, Agentheim!' when run. "
    "Write a second file called test_hello.py with a pytest test that checks the output. "
    "Run pytest to verify both files work. Keep the solution minimal."
)

_DEFAULT_TIMEOUT = 300.0


@dataclass
class BakeOffResult:
    profile: str
    provider: str
    model: str
    passed: bool
    files_created: list[str] = field(default_factory=list)
    verification_exit: int | None = None
    verification_output: str = ""
    error: str = ""
    duration: float = 0.0


def _run_single_bakeoff(
    workspace: Path,
    profile: str,
    provider: str,
    model: str,
    timeout: float = _DEFAULT_TIMEOUT,
) -> BakeOffResult:
    result = BakeOffResult(
        profile=profile,
        provider=provider,
        model=model,
        passed=False,
    )
    start = time.monotonic()
    try:
        session = create_session(
            workspace,
            trust_mode="workspace",
            mode="code",
            profile=profile,
            provider=provider,
            model=model,
        )
        session = post_message(workspace, session.session_id, _BAKEOFF_PROMPT)

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            view = get_session_view(workspace, session.session_id)
            if view.session.status in ("completed", "failed", "cancelled"):
                break
            time.sleep(1.0)

        view = get_session_view(workspace, session.session_id)
        result.files_created = [diff.path for diff in view.diffs]

        if view.command_results:
            last_result = view.command_results[-1]
            result.verification_exit = last_result.exit_code
            result.verification_output = " ".join(last_result.command)

        expected_files = {"hello.py", "test_hello.py"}
        created = set(result.files_created)
        has_files = expected_files.issubset(created)
        verification_ok = result.verification_exit == 0

        result.passed = has_files and verification_ok
        if not has_files:
            result.error = f"Missing files: {expected_files - created}"
        elif not verification_ok:
            result.error = f"Verification failed (exit {result.verification_exit})"
    except Exception as exc:
        result.error = str(exc)
    finally:
        result.duration = time.monotonic() - start
    return result


def run_bakeoff(
    models_payload: dict[str, Any],
    workspace: Path | None = None,
    profile_filter: str | None = None,
    provider_filter: str | None = None,
    model_filter: str | None = None,
    timeout: float = _DEFAULT_TIMEOUT,
) -> list[BakeOffResult]:
    if not models_payload.get("configured"):
        return []

    base_workspace = workspace or Path(tempfile.mkdtemp(prefix="agentheim-bakeoff-"))
    base_workspace.mkdir(parents=True, exist_ok=True)

    targets: list[tuple[str, str, str]] = []
    for profile in cast(list[dict[str, Any]], models_payload.get("profiles", [])):
        profile_name = profile["name"]
        if profile_filter and profile_name != profile_filter:
            continue
        for model_info in cast(list[dict[str, Any]], profile.get("models", [])):
            provider_id = str(model_info.get("provider", ""))
            model_id = str(model_info.get("model", ""))
            if provider_filter and provider_id != provider_filter:
                continue
            if model_filter and model_id != model_filter:
                continue
            targets.append((profile_name, provider_id, model_id))

    results: list[BakeOffResult] = []
    for idx, (profile_name, provider_id, model_id) in enumerate(targets, 1):
        run_workspace = base_workspace / f"run-{idx}"
        run_workspace.mkdir(parents=True, exist_ok=True)
        console.print(f"[{idx}/{len(targets)}] Testing {profile_name}/{provider_id}/{model_id} ...")
        result = _run_single_bakeoff(
            run_workspace,
            profile=profile_name,
            provider=provider_id,
            model=model_id,
            timeout=timeout,
        )
        results.append(result)
        status = "[green]PASS[/green]" if result.passed else "[red]FAIL[/red]"
        console.print(f"  {status} ({result.duration:.1f}s)")

    if workspace is None:
        shutil.rmtree(base_workspace, ignore_errors=True)

    return results


def render_bakeoff_table(results: list[BakeOffResult]) -> None:
    if not results:
        console.print("No provider profiles configured.")
        return

    table = Table(title="Agentheim Code Bake-Off Results")
    table.add_column("Profile")
    table.add_column("Provider")
    table.add_column("Model")
    table.add_column("Result")
    table.add_column("Duration")
    table.add_column("Error")

    for result in results:
        status = "[green]PASS[/green]" if result.passed else "[red]FAIL[/red]"
        table.add_row(
            result.profile,
            result.provider,
            result.model,
            status,
            f"{result.duration:.1f}s",
            result.error,
        )
    console.print(table)


def render_bakeoff_json(results: list[BakeOffResult]) -> None:
    payload = [
        {
            "profile": r.profile,
            "provider": r.provider,
            "model": r.model,
            "passed": r.passed,
            "files_created": r.files_created,
            "verification_exit": r.verification_exit,
            "verification_output": r.verification_output,
            "error": r.error,
            "duration": round(r.duration, 2),
        }
        for r in results
    ]
    console.print_json(json.dumps(payload))
