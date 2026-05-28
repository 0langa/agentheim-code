from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path


def detect_languages(relative_paths: Iterable[Path]) -> list[str]:
    path_set = {path.as_posix() for path in relative_paths}
    languages: list[str] = []

    if any(path.endswith(".sln") or path.endswith(".csproj") for path in path_set):
        languages.append("dotnet-csharp")
    if (
        "package.json" in path_set
        or "tsconfig.json" in path_set
        or any(path.endswith("package.json") for path in path_set)
    ):
        languages.append("node-typescript")
    if (
        "pyproject.toml" in path_set
        or "requirements.txt" in path_set
        or any(path.endswith(".py") for path in path_set)
    ):
        languages.append("python")
    if "Cargo.toml" in path_set or any(path.endswith("Cargo.toml") for path in path_set):
        languages.append("rust")
    if "go.mod" in path_set or any(path.endswith("go.mod") for path in path_set):
        languages.append("go")
    if any(
        path.endswith(name)
        for name in ("pom.xml", "build.gradle", "build.gradle.kts")
        for path in path_set
    ):
        languages.append("java-kotlin")

    return languages
