from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from core.public_api import inspect_repository
from workflows.coder.models import CoderMode, CoderSession, TrustMode, canonical_mode

SAFE_COMMANDS = ("python", "pytest", "git", "npm", "node", "pip", "poetry", "cargo", "go", "dotnet")
CODING_VERIFICATION_KEYWORDS = (
    "app",
    "application",
    "build",
    "create",
    "fix",
    "from scratch",
    "from the ground up",
    "empty workspace",
    "implement",
    "make",
    "project",
    "refactor",
    "scaffold",
    "test",
    "write code",
)


def _planner_command_guidance(os_name: str | None = None) -> str:
    current_os = os_name or os.name
    allowlist = ", ".join(SAFE_COMMANDS)
    if current_os == "nt":
        return (
            "Current OS is Windows and run_command only allows these executable roots: "
            f"{allowlist}. "
            "Use argv command arrays only. "
            "Do not use sh, bash, cmd, powershell, shell pipelines, or Unix utilities like test, sed, find, ls, cat, grep, or tr. "
            "For file checks or smoke checks, prefer python -c one-liners or framework-native commands that start with an allowed executable."
        )
    return (
        "run_command only allows these executable roots: "
        f"{allowlist}. "
        "Use argv command arrays only and keep verification local."
    )


def _workspace_scan_summary(workspace_root: Path) -> tuple[dict[str, Any], bool]:
    scan = inspect_repository(workspace_root)
    summary = {
        "repo_name": scan.repo_name,
        "languages": scan.languages,
        "manifests": scan.manifests,
        "warnings": scan.warnings,
        "file_count": len(scan.files),
        "git_available": scan.git.is_git_repo,
    }
    return summary, scan.git.is_git_repo


def _requires_coding_verification(prompt: str) -> bool:
    lowered = prompt.lower()
    return any(keyword in lowered for keyword in CODING_VERIFICATION_KEYWORDS)


def _session_has_coding_context(session: CoderSession, prompt: str) -> bool:
    if _requires_coding_verification(prompt):
        return True
    return any(
        message.role == "user" and _requires_coding_verification(message.content)
        for message in session.transcript
    )


def _mode_allows_noop_plan(mode: CoderMode) -> bool:
    return canonical_mode(mode) in {CoderMode.ASK, CoderMode.REVIEW}


def _mode_planner_guidance(mode: CoderMode) -> str:
    normalized = canonical_mode(mode)
    if normalized == CoderMode.ASK:
        return (
            "Ask mode: default to a direct conversational answer. "
            "When the user asks about the current workspace, repo health, or file contents, inspect first instead of guessing. "
            "Only include actions when the user clearly needs real inspection or edits. "
            "assistant_message should read like a natural chat reply, not a tool status log."
        )
    if normalized == CoderMode.REVIEW:
        return (
            "Review mode: produce a conversational review response with findings first, then supporting detail. "
            "Read-only inspection is allowed when it is needed to review honestly. "
            "Do not pretend to edit code unless the user explicitly asks for changes."
        )
    return (
        "Code mode: behave like a real coding partner. "
        "assistant_message should summarize what you changed, what you verified, and any remaining issue in natural language."
    )


def _prompt_explicitly_requests_workspace_action(prompt: str) -> bool:
    lowered = prompt.lower()
    markers = (
        "workspace",
        "repo",
        "repository",
        "codebase",
        "folder",
        "directory",
        "file",
        "files",
        "diff",
        "patch",
        "open ",
        "read ",
        "inspect ",
        "search ",
        "look through",
        "run ",
        "execute ",
        "edit ",
        "change ",
        "update ",
        "write ",
        "create ",
        "delete ",
        "rename ",
        "refactor ",
        "implement ",
        "build ",
        "in this workspace",
        "in the workspace",
        "in this repo",
        "in the repo",
    )
    return any(marker in lowered for marker in markers)


def _trust_mode_planner_guidance(trust_mode: TrustMode) -> str:
    if trust_mode == TrustMode.READ_ONLY:
        return (
            "Read-only trust mode allows listing files, reading files, and other safe inspection without asking for extra permission. "
            "Do not ask the user for permission before using read-only actions that are already allowed."
        )
    if trust_mode == TrustMode.ASK:
        return (
            "Ask trust mode still allows read-only inspection immediately. "
            "Only pause when an action truly needs approval under policy."
        )
    return (
        "Workspace trust mode allows routine workspace reads and normal edits under policy. "
        "Do not ask for permission for ordinary local inspection."
    )


def _normalized_prompt_text(prompt: str) -> str:
    return re.sub(r"[^a-z0-9\s]+", " ", prompt.lower()).strip()


def _prompt_is_workspace_action_affirmation(prompt: str) -> bool:
    normalized = " ".join(_normalized_prompt_text(prompt).split())
    if not normalized:
        return False
    exact_matches = {
        "yes",
        "yes please",
        "yes confirmed",
        "go ahead",
        "do that now",
        "please do that now",
        "yes please do that now",
        "can you do so now",
        "can you do that now",
        "how about now",
        "okay you should be able to do so now",
        "are you able to read files in the codespace now",
    }
    if normalized in exact_matches:
        return True
    return any(
        phrase in normalized
        for phrase in (
            "go check",
            "check it now",
            "inspect now",
            "read the files now",
            "review the workspace now",
            "smoke test now",
        )
    )


def _assistant_requested_workspace_action(session: CoderSession) -> bool:
    markers = (
        "inspect the workspace",
        "inspect the files",
        "inspect the workspace files",
        "read files",
        "review the file layout",
        "run a smoke test",
        "check the workspace",
        "check the layout",
        "identify the entry point",
        "verify whether the workspace is healthy",
        "file inspection",
    )
    for message in reversed(session.transcript[-6:]):
        if message.role != "assistant":
            continue
        lowered = message.content.lower()
        if any(marker in lowered for marker in markers):
            return True
    return False


def _workspace_action_requested(session: CoderSession, prompt: str) -> bool:
    if _prompt_explicitly_requests_workspace_action(prompt):
        return True
    return _prompt_is_workspace_action_affirmation(
        prompt
    ) and _assistant_requested_workspace_action(session)


def _allow_noop_plan(session: CoderSession, prompt: str) -> bool:
    normalized_mode = canonical_mode(session.mode)
    if _mode_allows_noop_plan(normalized_mode):
        return True
    if normalized_mode != CoderMode.CODE:
        return False
    if _workspace_action_requested(session, prompt):
        return False
    return not _session_has_coding_context(session, prompt)


def _assistant_message_reads_like_future_intent(message: str) -> bool:
    normalized = " ".join(_normalized_prompt_text(message).split())
    if normalized.startswith(
        (
            "i will ",
            "ill ",
            "i ll ",
            "let me ",
            "next i will ",
            "first i will ",
            "i can ",
        )
    ):
        return True
    return any(
        marker in normalized
        for marker in (
            " verifying ",
            " checking ",
            " running ",
        )
    )


def _normalize_completed_assistant_message(message: str) -> str:
    def _replace(match: re.Match[str], replacement: str) -> str:
        token = match.group(0)
        if token[:1].isupper():
            return replacement.capitalize()
        return replacement

    normalized = re.sub(
        r"\bverifying\b",
        lambda match: _replace(match, "verified"),
        message,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(
        r"\bchecking\b",
        lambda match: _replace(match, "checked"),
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(
        r"\brunning\b",
        lambda match: _replace(match, "ran"),
        normalized,
        flags=re.IGNORECASE,
    )
    return normalized
