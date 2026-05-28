"""Shared error catalog for user-facing errors across CLI, API, and Web UI.

Maps exceptions to stable categories with machine codes, human messages,
exit codes, HTTP status codes, and next actions. This is the user-facing
layer; runtime retry strategy continues to live in core.error_classification.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from core.errors import (
    AIteamError,
    ConfigError,
    ExecutionError,
    IntegrationError,
    PatchApplicationError,
    PlanningError,
    ProviderError,
    RepoInspectionError,
    ResumeError,
    ToolSafetyError,
    VerificationError,
)


class ErrorCatalogEntry(BaseModel):
    """A stable, user-facing error category."""

    category: str
    machine_code: str
    human_message: str
    exit_code: int
    http_status: int
    next_actions: list[str]


# ------------------------------------------------------------------
# Canonical catalog entries
# ------------------------------------------------------------------

CATALOG: dict[str, ErrorCatalogEntry] = {
    "validation_error": ErrorCatalogEntry(
        category="validation_error",
        machine_code="E1001",
        human_message="The input you provided is invalid or incomplete.",
        exit_code=2,
        http_status=400,
        next_actions=[
            "Check the command arguments or request body.",
            "Run the command with --help to see valid options.",
        ],
    ),
    "configuration_error": ErrorCatalogEntry(
        category="configuration_error",
        machine_code="E1002",
        human_message="Agentheim Code is not configured correctly for this operation.",
        exit_code=3,
        http_status=400,
        next_actions=[
            "Run 'agentheim-code doctor' to diagnose the issue.",
            "Review your provider profile and secret store.",
        ],
    ),
    "auth_error": ErrorCatalogEntry(
        category="auth_error",
        machine_code="E1003",
        human_message="Authentication failed. Your API key or credentials are missing, invalid, or expired.",
        exit_code=4,
        http_status=401,
        next_actions=[
            "Check that your API key is set in the secret store.",
            "Run 'agentheim-code doctor' to verify provider authentication.",
        ],
    ),
    "provider_error": ErrorCatalogEntry(
        category="provider_error",
        machine_code="E1004",
        human_message="The AI provider returned an error or is temporarily unreachable.",
        exit_code=5,
        http_status=503,
        next_actions=[
            "Wait a moment and retry the operation.",
            "Run 'agentheim-code doctor' to check provider connectivity.",
            "Switch to a different provider if the issue persists.",
        ],
    ),
    "policy_block": ErrorCatalogEntry(
        category="policy_block",
        machine_code="E1005",
        human_message="This action was blocked by a safety or policy rule.",
        exit_code=6,
        http_status=409,
        next_actions=[
            "Review the policy justification and adjust your request.",
            "If you believe this is a mistake, run with --no-confirm after reviewing risks.",
        ],
    ),
    "integration_unavailable": ErrorCatalogEntry(
        category="integration_unavailable",
        machine_code="E1006",
        human_message="An optional integration or dependency is not installed or not reachable.",
        exit_code=7,
        http_status=503,
        next_actions=[
            "Install the missing integration or dependency.",
            "Run 'agentheim-code doctor' to check optional integrations.",
        ],
    ),
    "not_found": ErrorCatalogEntry(
        category="not_found",
        machine_code="E1007",
        human_message="The requested run, preset, or resource could not be found.",
        exit_code=8,
        http_status=404,
        next_actions=[
            "Check the run ID or preset name for typos.",
            "Run 'agentheim-code runs' to see available runs.",
        ],
    ),
    "run_failed": ErrorCatalogEntry(
        category="run_failed",
        machine_code="E1008",
        human_message="The run failed during execution, planning, or verification.",
        exit_code=9,
        http_status=500,
        next_actions=[
            "Check the run report for details.",
            "Run 'agentheim-code runs inspect <run-id>' or resume from the relevant workflow surface.",
        ],
    ),
    "unexpected_error": ErrorCatalogEntry(
        category="unexpected_error",
        machine_code="E1009",
        human_message="An unexpected error occurred. This is likely a bug.",
        exit_code=1,
        http_status=500,
        next_actions=[
            "Check the logs for a traceback.",
            "Report the issue with the machine code and steps to reproduce.",
        ],
    ),
}


def catalog_entry_for(exc: BaseException) -> ErrorCatalogEntry:
    """Map an exception to its canonical catalog entry."""

    # Validation
    if isinstance(exc, (ValueError, TypeError)):
        return CATALOG["validation_error"]

    # Auth (check ProviderError sub-messages first)
    if isinstance(exc, PermissionError):
        return CATALOG["auth_error"]

    if isinstance(exc, ProviderError):
        msg = str(exc).lower()
        auth_keywords = ("auth", "api key", "credential", "unauthorized", "401")
        perm_keywords = ("permission denied", "forbidden", "access denied", "403")
        if any(k in msg for k in auth_keywords + perm_keywords):
            return CATALOG["auth_error"]
        return CATALOG["provider_error"]

    # Configuration
    if isinstance(
        exc, (ConfigError, KeyError, ImportError, ModuleNotFoundError, FileNotFoundError)
    ):
        return CATALOG["configuration_error"]

    # Policy
    if isinstance(exc, ToolSafetyError):
        return CATALOG["policy_block"]

    # Integration
    if isinstance(exc, IntegrationError):
        return CATALOG["integration_unavailable"]

    # Not found / resume
    if isinstance(exc, ResumeError):
        if "not found" in str(exc).lower():
            return CATALOG["not_found"]
        return CATALOG["run_failed"]

    # Run failure
    if isinstance(
        exc,
        (
            ExecutionError,
            PlanningError,
            PatchApplicationError,
            VerificationError,
            RepoInspectionError,
        ),
    ):
        return CATALOG["run_failed"]

    # AIteamError base catch-all
    if isinstance(exc, AIteamError):
        return CATALOG["unexpected_error"]

    # Everything else
    return CATALOG["unexpected_error"]


def format_api_response(entry: ErrorCatalogEntry, exc: BaseException) -> dict[str, Any]:
    """Build a JSON-safe error response that merges catalog metadata with
    the existing error_summary shape for backward compatibility."""
    from core.error_classification import error_summary

    summary = error_summary(exc)
    return {
        **summary,
        "machine_code": entry.machine_code,
        "exit_code": entry.exit_code,
        "next_actions": entry.next_actions,
        "human_message": entry.human_message,
    }


def format_cli_message(entry: ErrorCatalogEntry, exc: BaseException | None = None) -> str:
    """Build a plain-text error message suitable for CLI output."""
    lines = [f"Error ({entry.machine_code}): {entry.human_message}"]
    if exc is not None and str(exc):
        lines.append(f"  {exc}")
    for action in entry.next_actions:
        lines.append(f"  → {action}")
    return "\n".join(lines)
