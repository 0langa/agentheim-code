"""Project classification without LLM calls."""

from __future__ import annotations

from pathlib import Path


class ProjectClassification:
    """Deterministic classification of a repository."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root
        self.primary_language = "unknown"
        self.project_type = "unknown"
        self.build_system = "unknown"
        self.test_system = "unknown"
        self.package_system = "unknown"
        self.app_type = "unknown"
        self.docs_layout = "unknown"
        self.ci_layout = "unknown"
        self._classify()

    def _has(self, pattern: str) -> bool:
        return any(self.repo_root.rglob(pattern))

    def _classify(self) -> None:
        has_pyproject = self._has("pyproject.toml")
        has_package_json = self._has("package.json")
        has_cargo = self._has("Cargo.toml")
        has_go = self._has("go.mod")
        has_sln = self._has("*.sln")
        has_csproj = self._has("*.csproj")
        has_xaml = self._has("*.xaml")
        has_readme = (self.repo_root / "README.md").exists()
        docs_dir = (self.repo_root / "docs").is_dir()
        root_md_files = list(self.repo_root.glob("*.md"))

        if has_pyproject:
            self.primary_language = "python"
            self.build_system = "setuptools/flit/hatch"
            self.package_system = "pip/uv"
            if self._has("src/**/cli.py") or self._has("**/cli.py"):
                self.project_type = "python_cli"
                self.app_type = "cli"
            else:
                self.project_type = "python_project"
                self.app_type = "library_or_app"
            if self._has("pytest.ini") or self._has("tests/**"):
                self.test_system = "pytest"
            elif self._has("unittest"):
                self.test_system = "unittest"
        elif has_sln or has_csproj or has_xaml:
            self.primary_language = "csharp"
            self.project_type = "dotnet_desktop" if has_xaml else "dotnet"
            self.build_system = "msbuild/dotnet"
            self.app_type = "desktop" if has_xaml else "app_or_library"
            self.test_system = "xunit/nunit/mstest"
        elif has_package_json:
            self.primary_language = "javascript"
            self.project_type = "node_app"
            self.build_system = "npm/yarn/pnpm"
            self.app_type = "web_or_cli"
        elif has_cargo:
            self.primary_language = "rust"
            self.project_type = "rust_app"
            self.build_system = "cargo"
        elif has_go:
            self.primary_language = "go"
            self.project_type = "go_app"
            self.build_system = "go_modules"
        elif has_readme and (docs_dir or len(root_md_files) > 2):
            self.primary_language = "mixed_or_docs"
            self.project_type = "docs_heavy"

        if self._has(".github/workflows/*.yml"):
            self.ci_layout = "github_actions"

        if docs_dir:
            self.docs_layout = "docs_folder"
        elif has_readme:
            self.docs_layout = "readme_only"

    def as_dict(self) -> dict[str, str]:
        return {
            "primary_language": self.primary_language,
            "project_type": self.project_type,
            "build_system": self.build_system,
            "test_system": self.test_system,
            "package_system": self.package_system,
            "app_type": self.app_type,
            "docs_layout": self.docs_layout,
            "ci_layout": self.ci_layout,
        }


def classify_project(repo_root: Path) -> dict[str, str]:
    """Classify *repo_root* using deterministic heuristics."""
    return ProjectClassification(repo_root).as_dict()
