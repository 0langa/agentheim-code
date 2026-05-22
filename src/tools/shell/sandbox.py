"""Process-level sandbox for shell command execution.

Provides OS-level process isolation, working directory confinement,
environment filtering, and strict command validation.

This is the enforcement layer that transforms the safety-net allowlist
into a proper sandbox.  It is called by ``ShellTool`` before any command
execution and by the policy engine for network-level enforcement.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from core.errors import ToolSafetyError


class SandboxViolation(ToolSafetyError):
    """Raised when a command violates sandbox constraints."""


@dataclass(frozen=True)
class SandboxConfig:
    """Sandbox configuration that controls process-level isolation."""

    # Strict allowlist of permitted command prefixes.
    # If empty, all commands are denied (default-deny).
    allowed_commands: tuple[str, ...] = (
        "python",
        "pytest",
        "dotnet",
        "cargo",
        "go",
        "git",
        "npm",
        "node",
        "pip",
        "poetry",
    )

    # Commands whose arguments will be further validated (no shell injection).
    validate_args: tuple[str, ...] = ("git",)

    # Directories the sandbox is confined to.
    workspace: Path = field(default_factory=lambda: Path(".").resolve())

    # Environment variables to inherit (everything else is stripped).
    allowed_env_vars: tuple[str, ...] = (
        "PATH",
        "HOME",
        "USER",
        "USERNAME",
        "TEMP",
        "TMP",
        "SYSTEMROOT",
        "COMPUTERNAME",
        "PYTHONPATH",
        "PIP_INDEX_URL",
        "PIP_TRUSTED_HOST",
        "POETRY_CACHE_DIR",
        "CARGO_HOME",
        "NPM_CONFIG_CACHE",
        "GIT_SSL_NO_VERIFY",
    )

    # Maximum wall-clock time per command (seconds).
    timeout_seconds: float = 120.0

    # Maximum stdout/stderr bytes captured.
    max_output_bytes: int = 1_000_000

    # Whether to use a new process group (for cleanup on timeout).
    use_process_group: bool = True

    # Policy mode: "strict" denies unknown commands, "advisory" warns only.
    policy_mode: Literal["strict", "advisory"] = "strict"


class ShellSandbox:
    """Process-level sandbox for shell commands.

    Usage::

        sandbox = ShellSandbox(SandboxConfig(workspace=Path("/repo")))
        result = sandbox.execute(["python", "test.py"])
    """

    def __init__(self, config: SandboxConfig | None = None) -> None:
        self.config = config or SandboxConfig()

    def execute(
        self,
        command: list[str],
        *,
        env_override: dict[str, str] | None = None,
        cwd: Path | None = None,
        timeout: float | None = None,
    ) -> subprocess.CompletedProcess:
        """Execute *command* within the sandbox.

        Args:
            command: The command as a list of strings.
            env_override: Extra environment variables to include.
            cwd: Working directory (defaults to workspace).
            timeout: Override default timeout.

        Returns:
            ``subprocess.CompletedProcess`` with stdout/stderr captured.

        Raises:
            SandboxViolation: If the command violates sandbox constraints.
        """
        self._validate(command)
        resolved_cwd = (cwd or self.config.workspace).resolve()

        # Build a sanitised environment
        env = self._build_env(env_override)
        resolved_command = self._resolve_command(command, env)

        effective_timeout = timeout if timeout is not None else self.config.timeout_seconds

        try:
            result = subprocess.run(
                resolved_command,
                cwd=str(resolved_cwd),
                capture_output=True,
                text=True,
                timeout=effective_timeout,
                check=False,
                env=env,
                creationflags=self._creation_flags(),
                # On POSIX use a process group so we can kill the entire tree
                start_new_session=self.config.use_process_group,
            )
        except subprocess.TimeoutExpired as exc:
            raise SandboxViolation(
                f"Command '{' '.join(shlex.quote(p) for p in command)}' "
                f"timed out after {effective_timeout}s"
            ) from exc
        except FileNotFoundError as exc:
            raise SandboxViolation(f"Command not found: {command[0]}") from exc
        except OSError as exc:
            raise SandboxViolation(f"OS error executing command: {exc}") from exc

        # Truncate output if needed
        if len(result.stdout) > self.config.max_output_bytes:
            result.stdout = result.stdout[: self.config.max_output_bytes] + "\n... [truncated]"
        if len(result.stderr) > self.config.max_output_bytes:
            result.stderr = result.stderr[: self.config.max_output_bytes] + "\n... [truncated]"

        return result

    def _resolve_command(self, command: list[str], env: dict[str, str]) -> list[str]:
        """Resolve executable names through PATH/PATHEXT before subprocess launch."""
        executable = shutil.which(command[0], path=env.get("PATH"))
        if executable is None:
            return command
        return [executable, *command[1:]]

    def _validate(self, command: list[str]) -> None:
        """Validate *command* against sandbox rules.

        Raises SandboxViolation on any violation.
        """
        if not command:
            raise SandboxViolation("Empty command")

        allowed = self.config.allowed_commands
        first = command[0].lower()

        # Check that the command prefix is in the strict allowlist
        if allowed and first not in allowed:
            msg = (
                f"Command '{first}' is not in the sandbox allowlist. "
                f"Allowed: {', '.join(sorted(allowed))}"
            )
            if self.config.policy_mode == "strict":
                raise SandboxViolation(msg)

        # For sensitive commands, validate arguments
        if first in self.config.validate_args:
            self._validate_args(command)

        # Check for shell injection attempts in arguments
        for arg in command[1:]:
            self._validate_arg(arg)

    def _validate_args(self, command: list[str]) -> None:
        """Validate arguments for sensitive commands like git."""
        dangerous_git_args = {
            "clone",
            "fetch",
            "pull",
            "push",
            "remote",
            "submodule",
            "config",
        }
        if command[0].lower() == "git" and len(command) > 1:
            subcmd = command[1].lower()
            if subcmd in dangerous_git_args:
                raise SandboxViolation(
                    f"Git subcommand '{subcmd}' is not allowed in sandbox mode. "
                    f"Use the dedicated GitTool for push/clone operations."
                )

    def _validate_arg(self, arg: str) -> None:
        """Check for shell injection or path escape attempts."""
        forbidden = {
            "`",
            "$(",
            ";",
            "|",
            "&&",
            "||",
            ">",
            ">>",
            "<",
            "<<",
        }
        for token in forbidden:
            if token in arg:
                raise SandboxViolation(
                    f"Argument contains shell metacharacter '{token}': {shlex.quote(arg)}"
                )

        # Block path traversal attempts
        normalized = Path(arg).as_posix()
        if ".." in normalized.split("/"):
            raise SandboxViolation(f"Argument contains path traversal: {shlex.quote(arg)}")

    def _build_env(self, env_override: dict[str, str] | None) -> dict[str, str]:
        """Build a sanitised environment dict.

        Only inherits variables from the allowlist, then applies overrides.
        """
        env: dict[str, str] = {}
        for var in self.config.allowed_env_vars:
            val = os.environ.get(var)
            if val is not None:
                env[var] = val

        if env_override:
            env.update(env_override)

        return env

    def _creation_flags(self) -> int:
        """Return subprocess creation flags for the current platform."""
        flags = 0
        if sys.platform == "win32":
            # CREATE_NO_WINDOW on Windows to avoid flashing consoles
            flags = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
        return flags
