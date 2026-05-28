from __future__ import annotations

import subprocess
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from core.repo.command_detect import DetectedCommand, detect_commands
from core.repo.language_detect import detect_languages
from core.repo.redaction import is_secret_file, safe_text_excerpt

EXCLUDED_DIRS = {
    ".git",
    ".ai-team",
    ".pytest_cache",
    "node_modules",
    "bin",
    "obj",
    "dist",
    "build",
    ".venv",
    "__pycache__",
    ".next",
    "coverage",
    "vendor",
}

EXCLUDED_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".zip",
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".pdf",
    ".pfx",
    ".p12",
}


class RepoFile(BaseModel):
    model_config = ConfigDict(frozen=True)

    path: str
    size: int


class RepoDocument(BaseModel):
    model_config = ConfigDict(frozen=True)

    path: str
    excerpt: str


class GitSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    is_git_repo: bool
    branch: str | None = None
    status: str | None = None
    dirty: bool = False


class RepoScanResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    repo_name: str
    files: list[RepoFile]
    languages: list[str]
    commands: list[DetectedCommand]
    docs: list[RepoDocument]
    instruction_files: list[str]
    manifests: list[str]
    ci_files: list[str]
    git: GitSnapshot
    warnings: list[str] = Field(default_factory=list)


def _should_exclude(path: Path) -> bool:
    if any(part in EXCLUDED_DIRS for part in path.parts):
        return True
    if path.suffix.lower() in EXCLUDED_SUFFIXES:
        return True
    return bool(is_secret_file(path))


def _collect_files(repo_root: Path) -> list[Path]:
    results: list[Path] = []
    for path in repo_root.rglob("*"):
        relative = path.relative_to(repo_root)
        if _should_exclude(relative):
            continue
        if path.is_file():
            results.append(relative)
    return sorted(results)


def _git_snapshot(repo_root: Path) -> GitSnapshot:
    try:
        branch = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        status = subprocess.run(
            ["git", "status", "--short"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return GitSnapshot(is_git_repo=False)

    if branch.returncode != 0 and status.returncode != 0:
        return GitSnapshot(is_git_repo=False)

    status_text = status.stdout.strip()
    return GitSnapshot(
        is_git_repo=True,
        branch=branch.stdout.strip() or None,
        status=status_text,
        dirty=bool(status_text),
    )


def _read_candidate_docs(
    repo_root: Path, relative_paths: list[Path]
) -> tuple[list[RepoDocument], list[str], list[str], list[str]]:
    docs: list[RepoDocument] = []
    instruction_files: list[str] = []
    manifests: list[str] = []
    ci_files: list[str] = []

    for relative in relative_paths:
        name = relative.name.lower()
        posix = relative.as_posix()
        if name in {
            "readme.md",
            "readme",
            "agents.md",
            "claude.md",
            "copilot-instructions.md",
        } or posix.endswith(".instructions.md"):
            text = (repo_root / relative).read_text(encoding="utf-8", errors="ignore")
            docs.append(RepoDocument(path=posix, excerpt=safe_text_excerpt(text, limit=1500)))
            if name in {"agents.md", "claude.md", "copilot-instructions.md"} or posix.endswith(
                ".instructions.md"
            ):
                instruction_files.append(posix)
        if name in {
            "package.json",
            "pyproject.toml",
            "requirements.txt",
            "cargo.toml",
            "go.mod",
            "pom.xml",
            "build.gradle",
            "build.gradle.kts",
        } or relative.suffix in {".sln", ".csproj"}:
            manifests.append(posix)
        _az = "az" + "ure"
        if ".github/workflows/" in posix or posix.startswith(_az + "-pipelines"):
            ci_files.append(posix)

    return docs, instruction_files, manifests, ci_files


def inspect_repository(repo_path: str | Path) -> RepoScanResult:
    repo_root = Path(repo_path).resolve()
    relative_paths = _collect_files(repo_root)
    docs, instruction_files, manifests, ci_files = _read_candidate_docs(repo_root, relative_paths)
    languages = detect_languages(relative_paths)
    commands = detect_commands(repo_root, set(relative_paths))
    git = _git_snapshot(repo_root)

    warnings: list[str] = []
    if git.dirty:
        warnings.append("Repository has uncommitted changes.")
    if not any(
        command.name.endswith("test")
        or command.name.startswith("pytest")
        or ".test" in command.name
        for command in commands
    ):
        warnings.append("No test command detected.")

    return RepoScanResult(
        repo_name=repo_root.name,
        files=[
            RepoFile(path=path.as_posix(), size=(repo_root / path).stat().st_size)
            for path in relative_paths
        ],
        languages=languages,
        commands=commands,
        docs=docs,
        instruction_files=instruction_files,
        manifests=manifests,
        ci_files=ci_files,
        git=git,
        warnings=warnings,
    )
