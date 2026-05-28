"""Filesystem tool implementing ToolProtocol.

Operations: read, write, list, stat with path confinement.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from core.errors import ToolSafetyError
from core.path_security import safe_open_nofollow, safe_workspace_file_path
from core.tool_protocol import (
    BaseTool,
    ParamSchema,
    ReturnSchema,
    RiskLevel,
    ToolContext,
    ToolResult,
    ToolSchema,
)


class FilesystemTool(BaseTool):
    """Filesystem operations with path confinement."""

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        schema = ToolSchema(
            description="Read, write, list, and stat files within the workspace.",
            parameters={
                "operation": ParamSchema(
                    type="string",
                    description="Operation: read, write, list, stat, copy",
                    enum=["read", "write", "list", "stat", "copy"],
                    required=True,
                ),
                "path": ParamSchema(
                    type="string", description="Relative path within workspace", required=True
                ),
                "content": ParamSchema(
                    type="string", description="Content for write operation", required=False
                ),
                "destination": ParamSchema(
                    type="string", description="Destination path for copy operation", required=False
                ),
            },
            returns=ReturnSchema(type="any", description="Operation result"),
        )
        super().__init__("filesystem", schema, RiskLevel.NONE)

    def _resolve(self, raw_path: str, context: ToolContext) -> Path:
        """Resolve and validate a path against workspace boundaries."""
        try:
            target = safe_workspace_file_path(self.repo_root, raw_path)
        except ValueError as exc:
            raise ToolSafetyError(str(exc)) from exc

        # Enforce context boundaries (denied/allowed paths from policy)
        if not context.path_allowed(target):
            raise ToolSafetyError(f"Path outside allowed boundaries: {raw_path}")

        return target

    def invoke(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        valid, err = self.validate_params(params)
        if not valid:
            return ToolResult(success=False, error=err)

        operation = params.get("operation")
        raw_path = params.get("path", ".")

        try:
            target = self._resolve(raw_path, context)
        except ToolSafetyError as exc:
            return ToolResult(success=False, error=str(exc))

        if operation == "read":
            return self._read(target, context)
        if operation == "write":
            return self._write(target, params.get("content", ""), context)
        if operation == "list":
            return self._list(target)
        if operation == "stat":
            return self._stat(target)
        if operation == "copy":
            raw_dest = params.get("destination", "")
            return self._copy(target, raw_dest, context)

        return ToolResult(success=False, error=f"Unknown operation: {operation}")

    def _read(self, target: Path, context: ToolContext) -> ToolResult:
        if not target.exists():
            return ToolResult(success=False, error=f"File not found: {target}")
        if target.is_dir():
            return ToolResult(success=False, error=f"Path is a directory: {target}")
        size = target.stat().st_size
        if size > context.max_file_size:
            return ToolResult(
                success=False, error=f"File too large ({size} > {context.max_file_size})"
            )
        try:
            fd = safe_open_nofollow(target, os.O_RDONLY)
            try:
                fh = os.fdopen(fd, "r", encoding="utf-8", errors="ignore")
            except Exception:
                os.close(fd)
                raise
            with fh:
                data = fh.read()
                return ToolResult(success=True, data=data, metadata={"size": size})
        except OSError as exc:
            return ToolResult(success=False, error=str(exc))

    def _write(self, target: Path, content: str, context: ToolContext) -> ToolResult:
        # Write is MEDIUM risk — policy engine should have already checked
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            fd = safe_open_nofollow(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
            try:
                fh = os.fdopen(fd, "w", encoding="utf-8")
            except Exception:
                os.close(fd)
                raise
            with fh:
                fh.write(content)
                return ToolResult(
                    success=True,
                    data=str(target.relative_to(self.repo_root)),
                    metadata={"bytes_written": len(content.encode("utf-8"))},
                )
        except OSError as exc:
            return ToolResult(success=False, error=str(exc))

    def _list(self, target: Path) -> ToolResult:
        if not target.exists():
            return ToolResult(success=False, error=f"Path not found: {target}")
        if not target.is_dir():
            return ToolResult(success=False, error=f"Path is not a directory: {target}")
        try:
            entries = sorted(item.name for item in target.iterdir())
            return ToolResult(success=True, data=entries)
        except OSError as exc:
            return ToolResult(success=False, error=str(exc))

    def _stat(self, target: Path) -> ToolResult:
        if not target.exists():
            return ToolResult(success=False, error=f"Path not found: {target}")
        try:
            st = target.stat()
            return ToolResult(
                success=True,
                data={
                    "size": st.st_size,
                    "modified": st.st_mtime,
                    "is_file": target.is_file(),
                    "is_dir": target.is_dir(),
                },
            )
        except OSError as exc:
            return ToolResult(success=False, error=str(exc))

    def _copy(self, source: Path, raw_dest: str, context: ToolContext) -> ToolResult:
        if not source.exists():
            return ToolResult(success=False, error=f"Source not found: {source}")
        try:
            dest = self._resolve(raw_dest, context)
        except ToolSafetyError as exc:
            return ToolResult(success=False, error=str(exc))
        if dest.exists():
            return ToolResult(success=False, error=f"Destination already exists: {dest}")
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            if source.is_dir():
                shutil.copytree(source, dest)
            else:
                shutil.copy2(source, dest)
            return ToolResult(
                success=True,
                data=str(dest.relative_to(self.repo_root)),
                metadata={
                    "source": str(source.relative_to(self.repo_root)),
                    "is_dir": source.is_dir(),
                },
            )
        except OSError as exc:
            return ToolResult(success=False, error=str(exc))
