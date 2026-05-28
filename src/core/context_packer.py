"""Context bundle and manifest generation.

Scans a repository, summarizes files, redacts secrets, and packs the result
into a human-readable markdown bundle plus a machine-readable JSON manifest.
Respects a configurable token budget using a simple char-to-token heuristic.
"""

from __future__ import annotations

import json
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.redaction import redact_text
from core.repo.scanner import inspect_repository
from core.tool_protocol import ToolRegistry

warnings.warn(
    "ContextPacker is deprecated. Use AICtx via ContextOps instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Excluded directories and file patterns (extends scanner exclusions)
ADDITIONAL_EXCLUDES = {
    ".git",
    ".ai-team",
    ".pytest_cache",
    "node_modules",
    "__pycache__",
    ".venv",
    "dist",
    "build",
    "coverage",
    ".next",
    "vendor",
    "bin",
    "obj",
}

BINARY_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".zip",
    ".tar",
    ".gz",
    ".bz2",
    ".7z",
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".bin",
    ".pdf",
    ".doc",
    ".docx",
    ".ppt",
    ".pptx",
    ".mp3",
    ".mp4",
    ".wav",
    ".avi",
    ".mov",
}

DEFAULT_CHARS_PER_TOKEN = 4
DEFAULT_MAX_TOKENS = 128_000  # ~128k context window (generous default)


@dataclass
class FileEntry:
    path: str
    size: int
    language: str | None = None
    summary: str = ""
    included: bool = False


@dataclass
class ContextManifest:
    repo_name: str = ""
    repo_root: str = ""
    total_files: int = 0
    included_files: int = 0
    excluded_files: int = 0
    total_tokens_estimate: int = 0
    included_tokens_estimate: int = 0
    max_tokens: int = 0
    files: list[FileEntry] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo_name": self.repo_name,
            "repo_root": self.repo_root,
            "total_files": self.total_files,
            "included_files": self.included_files,
            "excluded_files": self.excluded_files,
            "total_tokens_estimate": self.total_tokens_estimate,
            "included_tokens_estimate": self.included_tokens_estimate,
            "max_tokens": self.max_tokens,
            "files": [
                {
                    "path": f.path,
                    "size": f.size,
                    "language": f.language,
                    "summary": f.summary,
                    "included": f.included,
                }
                for f in self.files
            ],
        }


class ContextPacker:
    """Pack repository context into a bundle and manifest."""

    def __init__(
        self,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        chars_per_token: int = DEFAULT_CHARS_PER_TOKEN,
    ) -> None:
        self.max_tokens = max_tokens
        self.chars_per_token = chars_per_token
        self.max_chars = max_tokens * chars_per_token

    def pack(
        self,
        repo_root: Path,
        run_config: dict[str, Any] | None = None,
        tool_registry: ToolRegistry | None = None,
    ) -> tuple[str, ContextManifest]:
        """Generate context bundle and manifest for a repository.

        Returns:
            (bundle_md: str, manifest: ContextManifest)
        """
        repo_root = repo_root.resolve()
        scan = inspect_repository(repo_root)

        manifest = ContextManifest(
            repo_name=scan.repo_name,
            repo_root=str(repo_root),
            max_tokens=self.max_tokens,
        )

        # Collect candidate files
        candidates: list[Path] = []
        for path in repo_root.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(repo_root).as_posix()
            if self._should_exclude(path, rel):
                continue
            candidates.append(path)

        # Sort by relevance: smaller files first, then docs/readmes, then code
        candidates.sort(key=lambda p: self._relevance_score(p, repo_root))

        # Build bundle incrementally within budget
        bundle_lines: list[str] = [
            f"# Context Bundle: {scan.repo_name}",
            "",
            f"**Repo root:** `{repo_root}`  ",
            f"**Max tokens:** {self.max_tokens}  ",
            f"**Files scanned:** {len(candidates)}  ",
            "",
        ]

        # Add config section if provided
        if run_config:
            bundle_lines.extend(
                [
                    "## Run Configuration",
                    "",
                    "```json",
                    json.dumps(run_config, indent=2, sort_keys=True),
                    "```",
                    "",
                ]
            )

        # Add tools section if provided
        if tool_registry is not None:
            bundle_lines.extend(
                [
                    "## Available Tools",
                    "",
                ]
            )
            for tool_id in sorted(tool_registry.list_tools()):
                tool = tool_registry.get(tool_id)
                bundle_lines.append(f"- `{tool_id}` — {tool.schema.description}")
            bundle_lines.append("")

        bundle_lines.extend(
            [
                "## Files",
                "",
            ]
        )

        current_chars = sum(len(line) for line in bundle_lines)
        included_count = 0
        included_chars = 0

        for path in candidates:
            rel = path.relative_to(repo_root).as_posix()
            try:
                raw_text = path.read_text(encoding="utf-8", errors="replace")
            except (OSError, UnicodeDecodeError):
                continue

            size = len(raw_text)
            tokens_est = size // self.chars_per_token
            manifest.total_files += 1
            manifest.total_tokens_estimate += tokens_est

            # Skip if adding this file would exceed budget
            file_header = f"### `{rel}`\n\n"
            file_block = file_header + raw_text + "\n\n"
            if current_chars + len(file_block) > self.max_chars:
                entry = FileEntry(
                    path=rel,
                    size=size,
                    language=self._detect_language(path),
                    summary=f"excluded (would exceed {self.max_tokens} token budget)",
                    included=False,
                )
                manifest.files.append(entry)
                manifest.excluded_files += 1
                continue

            # Include file
            redacted = redact_text(raw_text)
            bundle_lines.append(file_header)
            bundle_lines.append("```")
            bundle_lines.append(redacted)
            bundle_lines.append("```")
            bundle_lines.append("")

            current_chars += len(file_header) + len(redacted) + 20  # rough estimate for fences
            included_count += 1
            included_chars += size

            entry = FileEntry(
                path=rel,
                size=size,
                language=self._detect_language(path),
                summary=f"included ({tokens_est} tokens estimated)",
                included=True,
            )
            manifest.files.append(entry)

        manifest.included_files = included_count
        manifest.included_tokens_estimate = included_chars // self.chars_per_token

        bundle_md = "\n".join(bundle_lines)
        return bundle_md, manifest

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _should_exclude(path: Path, rel_path: str) -> bool:
        parts = Path(rel_path).parts
        if any(part in ADDITIONAL_EXCLUDES for part in parts):
            return True
        return path.suffix.lower() in BINARY_SUFFIXES

    @staticmethod
    def _relevance_score(path: Path, repo_root: Path) -> tuple[int, int]:
        """Return a sort key: lower = more relevant (included first)."""
        name = path.name.lower()
        size = path.stat().st_size

        # Prioritize docs and config
        if name in ("readme.md", "readme.rst", "readme.txt", "readme"):
            return (0, size)
        if name in ("pyproject.toml", "setup.py", "setup.cfg", "package.json", "dockerfile"):
            return (1, size)
        if path.suffix in (".md", ".rst", ".txt", ".yaml", ".yml", ".json", ".toml"):
            return (2, size)
        # Code files
        if path.suffix in (".py", ".js", ".ts", ".rs", ".go", ".java", ".c", ".cpp", ".h"):
            return (3, size)
        return (4, size)

    @staticmethod
    def _detect_language(path: Path) -> str | None:
        mapping = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".jsx": "javascript",
            ".rs": "rust",
            ".go": "go",
            ".java": "java",
            ".c": "c",
            ".cpp": "cpp",
            ".h": "c",
            ".hpp": "cpp",
            ".md": "markdown",
            ".rst": "rst",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".json": "json",
            ".toml": "toml",
            ".sh": "shell",
            ".ps1": "powershell",
            ".html": "html",
            ".css": "css",
            ".sql": "sql",
        }
        return mapping.get(path.suffix.lower())
