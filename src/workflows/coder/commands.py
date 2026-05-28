"""Shared command metadata for Coder CLI, API, docs, and UI."""

from __future__ import annotations

from typing import TypedDict


class CoderCommand(TypedDict):
    id: str
    label: str
    cli: str
    surface: str


CODER_COMMANDS: list[CoderCommand] = [
    {"id": "new", "label": "New Session", "cli": "/new", "surface": "session"},
    {"id": "resume", "label": "Resume Session", "cli": "/resume <id>", "surface": "session"},
    {"id": "sessions", "label": "List Sessions", "cli": "/sessions", "surface": "session"},
    {"id": "status", "label": "Session Status", "cli": "/status", "surface": "session"},
    {"id": "diff", "label": "Open Diff", "cli": "/diff", "surface": "inspector"},
    {"id": "files", "label": "Open Files", "cli": "/files", "surface": "inspector"},
    {"id": "approve", "label": "Approve Request", "cli": "/approve <id>", "surface": "approval"},
    {"id": "deny", "label": "Deny Request", "cli": "/deny <id>", "surface": "approval"},
    {"id": "cancel", "label": "Cancel Turn", "cli": "/cancel", "surface": "session"},
    {"id": "open", "label": "Open UI", "cli": "/open", "surface": "ui"},
    {
        "id": "model",
        "label": "Switch Model",
        "cli": "/model <provider> <model>",
        "surface": "model",
    },
    {"id": "provider", "label": "Switch Provider", "cli": "/provider <id>", "surface": "model"},
    {"id": "profile", "label": "Switch Profile", "cli": "/profile <name>", "surface": "model"},
    {"id": "models", "label": "List Models", "cli": "/models", "surface": "model"},
    {"id": "trust", "label": "Change Trust Mode", "cli": "--trust-mode", "surface": "settings"},
    {"id": "runs", "label": "Open Runs", "cli": "agentheim-code runs", "surface": "drawer"},
    {"id": "settings", "label": "Open Settings", "cli": "Ctrl+K settings", "surface": "drawer"},
]


def command_ids() -> list[str]:
    return [item["cli"].split()[0] for item in CODER_COMMANDS]


def command_registry() -> list[CoderCommand]:
    return CODER_COMMANDS.copy()
