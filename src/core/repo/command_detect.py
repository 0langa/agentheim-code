from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class DetectedCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    command: list[str] = Field(min_length=1)
    working_dir: str = "."
    risk_level: str = Field(pattern="^(safe|install|destructive|deploy)$")
    reason: str = Field(min_length=1)


def detect_commands(repo_root: Path, relative_paths: set[Path]) -> list[DetectedCommand]:
    commands: list[DetectedCommand] = []
    path_strings = {path.as_posix() for path in relative_paths}

    if any(path.endswith(".sln") or path.endswith(".csproj") for path in path_strings):
        commands.append(
            DetectedCommand(
                name="dotnet-build",
                command=["dotnet", "build"],
                risk_level="safe",
                reason="Detected .NET solution/project files.",
            )
        )
        if any("test" in path.lower() and path.endswith(".csproj") for path in path_strings):
            commands.append(
                DetectedCommand(
                    name="dotnet-test",
                    command=["dotnet", "test"],
                    risk_level="safe",
                    reason="Detected .NET test project.",
                )
            )

    package_json_paths = [
        repo_root / path for path in relative_paths if path.name == "package.json"
    ]
    for package_json in package_json_paths:
        try:
            package_data = json.loads(package_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            package_data = {}
        scripts = package_data.get("scripts", {}) if isinstance(package_data, dict) else {}
        working_dir = str(package_json.parent.relative_to(repo_root)).replace("\\", "/") or "."
        if "build" in scripts:
            commands.append(
                DetectedCommand(
                    name=f"npm-build:{working_dir}",
                    command=["npm", "run", "build"],
                    working_dir=working_dir,
                    risk_level="safe",
                    reason="Detected npm build script.",
                )
            )
        if "test" in scripts:
            commands.append(
                DetectedCommand(
                    name=f"npm-test:{working_dir}",
                    command=["npm", "test"],
                    working_dir=working_dir,
                    risk_level="safe",
                    reason="Detected npm test script.",
                )
            )
        commands.append(
            DetectedCommand(
                name=f"npm-install:{working_dir}",
                command=["npm", "install"],
                working_dir=working_dir,
                risk_level="install",
                reason="Node project detected; install is manual only.",
            )
        )

    python_roots = set()
    for path in relative_paths:
        if path.name in {"pyproject.toml", "requirements.txt"}:
            python_roots.add(str(path.parent).replace("\\", "/") or ".")
    for working_dir in sorted(python_roots):
        if any(
            path.startswith(f"{working_dir}/tests/")
            or (working_dir == "." and path.startswith("tests/"))
            or "test" in Path(path).name.lower()
            for path in path_strings
        ):
            commands.append(
                DetectedCommand(
                    name=f"pytest:{working_dir}",
                    command=["python", "-m", "pytest"],
                    working_dir=working_dir,
                    risk_level="safe",
                    reason="Python test files detected.",
                )
            )

    if "Cargo.toml" in path_strings:
        commands.append(
            DetectedCommand(
                name="cargo-test",
                command=["cargo", "test"],
                risk_level="safe",
                reason="Rust manifest detected.",
            )
        )

    if "go.mod" in path_strings:
        commands.append(
            DetectedCommand(
                name="go-test",
                command=["go", "test", "./..."],
                risk_level="safe",
                reason="Go module detected.",
            )
        )

    return commands
