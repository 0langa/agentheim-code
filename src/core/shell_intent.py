"""Shell command intent classification.

Maps argv-based shell commands to intent categories so policy and risk
assessment can reason about what the command is trying to do, not only
which binary is invoked.
"""

from __future__ import annotations

from enum import Enum
from typing import Any


class ShellIntent(Enum):
    """High-level intent of a shell command."""

    READ_ONLY = "read_only"
    BUILD_TEST = "build_test"
    PACKAGE = "package"
    EVAL = "eval"
    NETWORKED = "networked"
    UNKNOWN = "unknown"


def classify_shell_intent(command: Any) -> ShellIntent:
    """Classify the intent of *command* (a list of strings).

    Returns ``ShellIntent.UNKNOWN`` for empty or unrecognised commands.
    Dangerous patterns (e.g. ``python -c``) are classified as ``EVAL``
    even though the executable itself is harmless.
    """
    if not isinstance(command, list) or not command:
        return ShellIntent.UNKNOWN

    parts = [str(part) for part in command]
    head = parts[0].lower()

    # Networked commands
    if head in {"curl", "wget", "ssh", "scp", "ftp", "nc", "telnet", "netcat"}:
        return ShellIntent.NETWORKED
    if head == "git" and len(parts) > 1 and parts[1].lower() in {"clone", "fetch", "pull", "push"}:
        return ShellIntent.NETWORKED
    if head == "npm" and len(parts) > 1 and parts[1].lower() == "publish":
        return ShellIntent.NETWORKED

    # Package / dependency mutation
    if head in {"pip", "poetry", "conda", "gem", "bundle"}:
        return ShellIntent.PACKAGE
    if (
        head == "npm"
        and len(parts) > 1
        and parts[1].lower() in {"install", "ci", "update", "add", "remove", "uninstall"}
    ):
        return ShellIntent.PACKAGE
    if (
        head == "cargo"
        and len(parts) > 1
        and parts[1].lower() in {"add", "remove", "install", "update"}
    ):
        return ShellIntent.PACKAGE
    if head == "go" and len(parts) > 1 and parts[1].lower() in {"get", "mod", "install"}:
        return ShellIntent.PACKAGE
    if head == "python" and len(parts) >= 3 and parts[1].lower() == "-m":
        mod = parts[2].lower()
        if mod in {"pip", "poetry", "ensurepip", "venv", "virtualenv"}:
            return ShellIntent.PACKAGE

    # Build / test
    if head == "pytest":
        return ShellIntent.BUILD_TEST
    if head == "npm" and len(parts) > 1 and parts[1].lower() in {"test", "run", "build", "lint"}:
        return ShellIntent.BUILD_TEST
    if head == "dotnet" and len(parts) > 1 and parts[1].lower() in {"build", "test", "publish"}:
        return ShellIntent.BUILD_TEST
    if (
        head == "cargo"
        and len(parts) > 1
        and parts[1].lower() in {"build", "test", "check", "clippy"}
    ):
        return ShellIntent.BUILD_TEST
    if head == "go" and len(parts) > 1 and parts[1].lower() in {"build", "test", "vet"}:
        return ShellIntent.BUILD_TEST
    if head == "python" and len(parts) >= 3 and parts[1].lower() == "-m":
        mod = parts[2].lower()
        if mod == "pytest":
            return ShellIntent.BUILD_TEST

    # Arbitrary interpreter evaluation
    if head in {"python", "node", "ruby", "perl"}:
        if head == "python" and len(parts) >= 2 and parts[1].lower() in {"-c", "-m"}:
            # -m pytest / -m pip handled above
            if (
                parts[1].lower() == "-m"
                and len(parts) >= 3
                and parts[2].lower()
                in {
                    "pytest",
                    "pip",
                    "poetry",
                    "ensurepip",
                    "venv",
                    "virtualenv",
                }
            ):
                pass
            else:
                return ShellIntent.EVAL
        if head == "node" and len(parts) >= 2 and parts[1].lower() == "-e":
            return ShellIntent.EVAL

    # Read-only inspection
    if head in {
        "dir",
        "type",
        "cat",
        "ls",
        "rg",
        "grep",
        "find",
        "head",
        "tail",
        "wc",
        "file",
        "stat",
        "tree",
    }:
        return ShellIntent.READ_ONLY
    if (
        head == "git"
        and len(parts) > 1
        and parts[1].lower() in {"status", "diff", "log", "show", "branch", "blame"}
    ):
        return ShellIntent.READ_ONLY

    return ShellIntent.UNKNOWN
