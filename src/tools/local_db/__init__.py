"""Local DB tool implementing ToolProtocol.

Read-only SQLite database inspection and querying with workspace path confinement.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from core.errors import ToolSafetyError
from core.tool_protocol import (
    BaseTool,
    ParamSchema,
    ReturnSchema,
    RiskLevel,
    ToolContext,
    ToolResult,
    ToolSchema,
)


class LocalDBTool(BaseTool):
    """Read-only SQLite database operations within the workspace."""

    # SQL statements allowed in read-only mode
    READ_ONLY_PREFIXES = ("select", "pragma", "explain", "with")
    # Dangerous keywords that are never allowed
    DANGEROUS_KEYWORDS = (
        "insert",
        "update",
        "delete",
        "drop",
        "create",
        "alter",
        "replace",
        "attach",
        "detach",
        "vacuum",
    )

    def __init__(self, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        schema = ToolSchema(
            description="Query local SQLite databases within the workspace.",
            parameters={
                "operation": ParamSchema(
                    type="string",
                    description="Operation to perform",
                    enum=["query", "list_tables", "describe"],
                    required=True,
                ),
                "db_path": ParamSchema(
                    type="string",
                    description="Relative path to SQLite database file",
                    required=True,
                ),
                "sql": ParamSchema(
                    type="string",
                    description="SQL query (required for query operation)",
                    required=False,
                ),
                "table_name": ParamSchema(
                    type="string",
                    description="Table name (required for describe operation)",
                    required=False,
                ),
                "limit": ParamSchema(
                    type="integer",
                    description="Max rows to return for query",
                    default=1000,
                    required=False,
                ),
            },
            returns=ReturnSchema(type="object", description="Operation result"),
        )
        super().__init__("local_db", schema, RiskLevel.MEDIUM)

    def invoke(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        valid, err = self.validate_params(params)
        if not valid:
            return ToolResult(success=False, error=err)

        operation = params.get("operation")
        raw_db_path = params.get("db_path", "")

        try:
            db_path = self._resolve_db_path(raw_db_path, context)
        except ToolSafetyError as exc:
            return ToolResult(success=False, error=str(exc))

        if not db_path.exists():
            return ToolResult(success=False, error=f"Database not found: {raw_db_path}")

        try:
            if operation == "query":
                sql = params.get("sql", "")
                limit = params.get("limit", 1000)
                return self._query(db_path, sql, limit)
            if operation == "list_tables":
                return self._list_tables(db_path)
            if operation == "describe":
                table_name = params.get("table_name", "")
                return self._describe(db_path, table_name)
        except sqlite3.Error as exc:
            return ToolResult(success=False, error=f"SQLite error: {exc}")
        except OSError as exc:
            return ToolResult(success=False, error=str(exc))

        return ToolResult(success=False, error=f"Unknown operation: {operation}")

    def _resolve_db_path(self, raw_path: str, context: ToolContext) -> Path:
        """Resolve and validate a database path against workspace boundaries."""
        target = (self.repo_root / raw_path).resolve()

        # Prevent directory traversal outside repo
        try:
            target.relative_to(self.repo_root)
        except ValueError as exc:
            raise ToolSafetyError(f"Database path escapes workspace: {raw_path}") from exc

        # Prevent symlink escape
        if target.is_symlink():
            real = target.resolve()
            try:
                real.relative_to(self.repo_root)
            except ValueError as exc:
                raise ToolSafetyError(f"Symlink escapes workspace: {raw_path}") from exc

        # Enforce context boundaries
        if not context.path_allowed(target):
            raise ToolSafetyError(f"Database path outside allowed boundaries: {raw_path}")

        return target

    def _sanitize_sql(self, sql: str) -> tuple[bool, str]:
        """Validate SQL is read-only and safe."""
        stripped = sql.strip()
        if not stripped:
            return False, "SQL query cannot be empty."

        first_token = stripped.split()[0].lower()

        if first_token not in self.READ_ONLY_PREFIXES:
            return (
                False,
                f"SQL must start with a read-only statement (got '{first_token}'). Allowed: {self.READ_ONLY_PREFIXES}",
            )

        lower_sql = stripped.lower()
        for keyword in self.DANGEROUS_KEYWORDS:
            if keyword in lower_sql:
                return False, f"SQL contains disallowed keyword: '{keyword}'"

        return True, ""

    def _query(self, db_path: Path, sql: str, limit: int) -> ToolResult:
        safe, err = self._sanitize_sql(sql)
        if not safe:
            return ToolResult(success=False, error=err)

        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(sql)
            rows = cursor.fetchmany(limit)
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            results = [dict(zip(columns, row, strict=False)) for row in rows]
            row_count = len(results)
            has_more = cursor.fetchone() is not None

        return ToolResult(
            success=True,
            data={"columns": columns, "rows": results, "row_count": row_count},
            metadata={"limit": limit, "has_more": has_more},
        )

    def _list_tables(self, db_path: Path) -> ToolResult:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
            cursor = conn.execute(
                "SELECT name, type FROM sqlite_master WHERE type IN ('table', 'view') ORDER BY name"
            )
            rows = cursor.fetchall()
            tables = [{"name": r[0], "type": r[1]} for r in rows]

        return ToolResult(
            success=True,
            data=tables,
            metadata={"count": len(tables)},
        )

    def _describe(self, db_path: Path, table_name: str) -> ToolResult:
        if not table_name:
            return ToolResult(
                success=False, error="Parameter 'table_name' is required for describe."
            )

        # Validate table name to prevent injection
        if not table_name.replace("_", "").replace(" ", "").isalnum():
            return ToolResult(success=False, error="Invalid table name.")

        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
            # Table info
            cursor = conn.execute(f'PRAGMA table_info("{table_name}")')
            columns = cursor.fetchall()
            schema = [
                {
                    "cid": r[0],
                    "name": r[1],
                    "type": r[2],
                    "notnull": bool(r[3]),
                    "default_value": r[4],
                    "pk": bool(r[5]),
                }
                for r in columns
            ]

            # Row count
            cursor = conn.execute(f'SELECT COUNT(*) FROM "{table_name}"')
            row_count = cursor.fetchone()[0]

            # Indexes
            cursor = conn.execute(
                "SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name=?",
                (table_name,),
            )
            indexes = [{"name": r[0], "sql": r[1]} for r in cursor.fetchall()]

        return ToolResult(
            success=True,
            data={
                "table_name": table_name,
                "columns": schema,
                "row_count": row_count,
                "indexes": indexes,
            },
            metadata={"column_count": len(schema), "index_count": len(indexes)},
        )
