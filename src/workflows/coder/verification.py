"""Project verification profile detection and structured verification steps.

Scans the workspace for common project types and returns a VerificationProfile
with appropriate lint / typecheck / test / build steps.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from workflows.coder.models import (
    RepairContext,
    RepairContextKind,
    VerificationProfile,
    VerificationStep,
    VerificationStepKind,
)


def _detect_verification_profiles(workspace_root: str | Path) -> list[VerificationProfile]:
    """Auto-detect verification profiles based on project files."""
    workspace = Path(workspace_root)
    profiles: list[VerificationProfile] = []

    # Python projects
    if (workspace / "pyproject.toml").exists() or (workspace / "setup.py").exists():
        steps: list[VerificationStep] = []
        if (workspace / "pyproject.toml").exists():
            content = (workspace / "pyproject.toml").read_text(encoding="utf-8", errors="ignore")
            if "[tool.ruff]" in content or "[tool.ruff.lint]" in content:
                steps.append(
                    VerificationStep(
                        kind=VerificationStepKind.LINT,
                        command=["ruff", "check", "."],
                        description="Run Ruff linter",
                    )
                )
            if "[tool.mypy]" in content or "mypy" in content:
                steps.append(
                    VerificationStep(
                        kind=VerificationStepKind.TYPECHECK,
                        command=["mypy", "."],
                        description="Run MyPy type checker",
                    )
                )
        if (
            (workspace / "pytest.ini").exists()
            or (workspace / "setup.cfg").exists()
            or (workspace / "tests").is_dir()
            or list(workspace.glob("test_*.py"))
        ):
            steps.append(
                VerificationStep(
                    kind=VerificationStepKind.TEST,
                    command=["pytest", "-x", "-q"],
                    description="Run pytest",
                )
            )
        profiles.append(VerificationProfile(name="python", detected=True, steps=steps))

    # Node.js projects
    if (workspace / "package.json").exists():
        pkg = _read_json_safe(workspace / "package.json")
        scripts = pkg.get("scripts", {}) if isinstance(pkg, dict) else {}
        node_steps: list[VerificationStep] = []
        if "test" in scripts:
            node_steps.append(
                VerificationStep(
                    kind=VerificationStepKind.TEST,
                    command=["npm", "test"],
                    description="Run npm test",
                )
            )
        if "lint" in scripts:
            node_steps.append(
                VerificationStep(
                    kind=VerificationStepKind.LINT,
                    command=["npm", "run", "lint"],
                    description="Run npm lint",
                )
            )
        if "build" in scripts:
            node_steps.append(
                VerificationStep(
                    kind=VerificationStepKind.BUILD,
                    command=["npm", "run", "build"],
                    description="Run npm build",
                )
            )
        if "typecheck" in scripts:
            node_steps.append(
                VerificationStep(
                    kind=VerificationStepKind.TYPECHECK,
                    command=["npm", "run", "typecheck"],
                    description="Run npm typecheck",
                )
            )
        profiles.append(VerificationProfile(name="node", detected=True, steps=node_steps))

    # Rust projects
    if (workspace / "Cargo.toml").exists():
        profiles.append(
            VerificationProfile(
                name="rust",
                detected=True,
                steps=[
                    VerificationStep(
                        kind=VerificationStepKind.TEST,
                        command=["cargo", "test"],
                        description="Run cargo test",
                    ),
                    VerificationStep(
                        kind=VerificationStepKind.BUILD,
                        command=["cargo", "build"],
                        description="Run cargo build",
                    ),
                    VerificationStep(
                        kind=VerificationStepKind.LINT,
                        command=["cargo", "clippy", "--", "-D", "warnings"],
                        description="Run cargo clippy",
                        required=False,
                    ),
                ],
            )
        )

    # Go projects
    if (workspace / "go.mod").exists():
        profiles.append(
            VerificationProfile(
                name="go",
                detected=True,
                steps=[
                    VerificationStep(
                        kind=VerificationStepKind.TEST,
                        command=["go", "test", "./..."],
                        description="Run go test",
                    ),
                    VerificationStep(
                        kind=VerificationStepKind.BUILD,
                        command=["go", "build", "./..."],
                        description="Run go build",
                    ),
                ],
            )
        )

    # .NET projects
    if list(workspace.glob("*.csproj")) or list(workspace.glob("*.sln")):
        profiles.append(
            VerificationProfile(
                name="dotnet",
                detected=True,
                steps=[
                    VerificationStep(
                        kind=VerificationStepKind.TEST,
                        command=["dotnet", "test"],
                        description="Run dotnet test",
                    ),
                    VerificationStep(
                        kind=VerificationStepKind.BUILD,
                        command=["dotnet", "build"],
                        description="Run dotnet build",
                    ),
                ],
            )
        )

    return profiles


def _read_json_safe(path: Path) -> Any:
    import json

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _classify_repair_context(
    command: list[str],
    exit_code: int | None,
    stdout: str,
    stderr: str,
) -> RepairContext:
    """Classify a failed command result into a structured repair context."""
    combined = f"{stdout}\n{stderr}"
    combined_lower = combined.lower()

    # Permission denial
    if exit_code == 126 or exit_code == 127:
        return RepairContext(
            kind=RepairContextKind.PERMISSION_DENIED,
            command=command,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            message="Command not found or permission denied.",
        )
    if "permission denied" in combined_lower or "access is denied" in combined_lower:
        return RepairContext(
            kind=RepairContextKind.PERMISSION_DENIED,
            command=command,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            message="Permission denied during command execution.",
        )

    # Timeout
    if exit_code == 124 or "timeout" in combined_lower:
        return RepairContext(
            kind=RepairContextKind.TIMEOUT,
            command=command,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            message="Command timed out.",
        )

    # Environment / config failure
    if (
        "not found" in combined_lower
        and "module" in combined_lower
        or "package" in combined_lower
        or "cannot find" in combined_lower
    ):
        return RepairContext(
            kind=RepairContextKind.ENV_CONFIG_FAILURE,
            command=command,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            message="Missing dependency or module not found.",
        )
    if "environment" in combined_lower and "not set" in combined_lower:
        return RepairContext(
            kind=RepairContextKind.ENV_CONFIG_FAILURE,
            command=command,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            message="Environment variable or config missing.",
        )

    # Test failure
    if any(kw in combined_lower for kw in ("failed", "failure", "assert", "test")) and any(
        kw in combined_lower for kw in ("pytest", "unittest", "test", "spec")
    ):
        return RepairContext(
            kind=RepairContextKind.TEST_FAILURE,
            command=command,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            message="One or more tests failed.",
        )

    # Lint / type failure
    if any(kw in combined_lower for kw in ("error", "warning", "lint", "type")) and any(
        kw in combined_lower
        for kw in (
            "ruff",
            "flake8",
            "pylint",
            "eslint",
            "clippy",
            "mypy",
            "pyright",
            "tsc",
        )
    ):
        return RepairContext(
            kind=RepairContextKind.LINT_TYPE_FAILURE,
            command=command,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            message="Lint or type check failed.",
        )

    return RepairContext(
        kind=RepairContextKind.UNKNOWN,
        command=command,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        message="Command failed with an unrecognized error.",
    )
