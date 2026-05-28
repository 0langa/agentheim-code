"""AST-based Python script intent inspection.

Inspects Python files to determine their high-level intent for policy
classification (e.g. read-only, networked, eval).
"""

from __future__ import annotations

import ast
from pathlib import Path


class _IntentVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.networked = False
        self.eval_like = False

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        name = _resolve_expr_name(node.func)
        if name:
            if name in {"eval", "exec", "compile"}:
                self.eval_like = True
            if name in {
                "requests.get",
                "requests.post",
                "requests.put",
                "requests.delete",
                "requests.head",
                "requests.patch",
                "urllib.request.urlopen",
                "http.client.HTTPConnection",
                "http.client.HTTPSConnection",
                "socket.socket",
                "socket.create_connection",
                "ftplib.FTP",
                "smtplib.SMTP",
                "subprocess.run",
                "subprocess.call",
                "subprocess.Popen",
                "os.system",
                "os.popen",
                "os.execve",
                "os.execv",
            }:
                self.networked = True
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
        for alias in node.names:
            mod = alias.name
            if mod in {"requests", "ftplib", "smtplib", "http.client", "urllib.request"}:
                self.networked = True
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        if node.module in {
            "requests",
            "ftplib",
            "smtplib",
            "http.client",
            "urllib.request",
        }:
            self.networked = True
        self.generic_visit(node)


def _resolve_expr_name(node: ast.expr) -> str | None:
    """Best-effort resolution of a call target to a dotted name."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parts: list[str] = []
        current: ast.expr = node
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
        return ".".join(reversed(parts))
    return None


def inspect_python_script(path: str | Path) -> str | None:
    """Return the inferred intent of a Python script by static analysis.

    Returns one of ``"read_only"``, ``"networked"``, ``"eval"`` or ``None``
    when the file cannot be read or parsed.
    """
    try:
        with open(path, encoding="utf-8", errors="ignore") as fh:
            source = fh.read()
    except OSError:
        return None

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    except RecursionError:
        return None

    visitor = _IntentVisitor()
    try:
        visitor.visit(tree)
    except Exception:
        return None

    if visitor.networked:
        return "networked"
    if visitor.eval_like:
        return "eval"
    return "read_only"
