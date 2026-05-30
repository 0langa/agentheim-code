from __future__ import annotations

import difflib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from core.errors import PatchApplicationError


class AppliedFileChange(BaseModel):
    model_config = ConfigDict(frozen=True)

    path: str
    change_type: str
    diff: str
    before_text: str
    after_text: str


class PatchApplyResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    applied: bool
    file_changes: list[AppliedFileChange] = Field(default_factory=list)
    diff_text: str = ""
    errors: list[str] = Field(default_factory=list)


class PatchApplier:
    def __init__(
        self,
        repo_root: str | Path,
        forbidden_paths: list[str] | None = None,
        max_diff_lines: int = 1200,
        scope_override: bool = False,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.forbidden_paths = {
            self._normalize_relative(Path(item)) for item in (forbidden_paths or [])
        }
        self.max_diff_lines = max_diff_lines
        self.scope_override = scope_override

    def validate_relative_path(self, relative_path: str) -> Path:
        normalized_input = self._normalize_input_path(relative_path)
        candidate = (self.repo_root / normalized_input).resolve()
        try:
            candidate.relative_to(self.repo_root)
        except ValueError as exc:
            raise PatchApplicationError(f"Patch path escapes repo root: {relative_path}") from exc
        relative = self._normalize_relative(candidate.relative_to(self.repo_root))
        if relative in self.forbidden_paths:
            raise PatchApplicationError(f"Patch touches forbidden file: {relative}")
        return candidate

    def apply_changes(
        self, file_changes: list[dict[str, Any]], allowed_files: list[str] | None = None
    ) -> PatchApplyResult:
        errors: list[str] = []
        applied_changes: list[AppliedFileChange] = []
        allowed_set = {
            self._normalize_relative(Path(self._normalize_input_path(item)))
            for item in (allowed_files or [])
        }

        for file_change in file_changes:
            relative_path = file_change["path"]
            normalized = self._normalize_relative(Path(self._normalize_input_path(relative_path)))
            if allowed_set and normalized not in allowed_set:
                errors.append(f"Change touches file outside work order scope: {normalized}")
                continue

            try:
                target = self.validate_relative_path(relative_path)
            except PatchApplicationError as exc:
                errors.append(str(exc))
                continue

            before_text = target.read_text(encoding="utf-8") if target.exists() else ""
            after_text = self._render_after_text(before_text, file_change)
            diff = self._build_diff(normalized, before_text, after_text)
            diff_line_count = len(diff.splitlines())
            if diff_line_count > self.max_diff_lines and not self.scope_override:
                errors.append(
                    f"Patch for {normalized} exceeds max diff lines ({diff_line_count}>{self.max_diff_lines})"
                )
                continue

            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(after_text, encoding="utf-8")
            applied_changes.append(
                AppliedFileChange(
                    path=normalized,
                    change_type=file_change["change_type"],
                    diff=diff,
                    before_text=before_text,
                    after_text=after_text,
                )
            )

        combined_diff = "\n".join(change.diff for change in applied_changes if change.diff)
        return PatchApplyResult(
            applied=not errors, file_changes=applied_changes, diff_text=combined_diff, errors=errors
        )

    def rollback(self, applied_changes: list[AppliedFileChange]) -> None:
        for change in reversed(applied_changes):
            target = self.validate_relative_path(change.path)
            if change.change_type == "create" and not change.before_text:
                if target.exists():
                    target.unlink()
                continue
            target.write_text(change.before_text, encoding="utf-8")

    def _render_after_text(self, before_text: str, file_change: dict[str, Any]) -> str:
        change_type = file_change.get("change_type", "update")
        if change_type == "delete":
            return ""
        old_string = file_change.get("old_string")
        new_string = file_change.get("new_string")
        if old_string is not None and new_string is not None:
            if old_string not in before_text:
                raise PatchApplicationError(
                    f"old_string not found in file: {file_change.get('path', '?')!r}"
                )
            return before_text.replace(old_string, new_string, 1)
        patch = file_change.get("patch", "")
        if patch:
            return str(patch)
        return str(file_change.get("after_text", before_text))

    @staticmethod
    def _normalize_relative(path: Path) -> str:
        return path.as_posix()

    @staticmethod
    def _normalize_input_path(path: str) -> str:
        return path.replace("\\", "/")

    @staticmethod
    def _build_diff(relative_path: str, before_text: str, after_text: str) -> str:
        before_lines = before_text.splitlines(keepends=True)
        after_lines = after_text.splitlines(keepends=True)
        return "".join(
            difflib.unified_diff(
                before_lines,
                after_lines,
                fromfile=f"a/{relative_path}",
                tofile=f"b/{relative_path}",
                lineterm="",
            )
        )
