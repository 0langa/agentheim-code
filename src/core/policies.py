from __future__ import annotations

from enum import StrEnum


class CommandPolicy(StrEnum):
    SAFE = "safe"
    INSTALL = "install"
    DESTRUCTIVE = "destructive"
    DEPLOY = "deploy"


def classify_command(command: list[str]) -> CommandPolicy:
    joined = " ".join(command).lower()
    if any(term in joined for term in {"rm", "rmdir", "del", "format", "shutdown", "remove-item"}):
        return CommandPolicy.DESTRUCTIVE
    _deploy_terms = {"deploy", "publish", "terraform", "az deployment", "azd up", "func az" + "ure"}
    if any(term in joined for term in _deploy_terms):
        return CommandPolicy.DEPLOY
    if any(
        part in {"install", "add", "restore", "pip", "poetry"}
        for part in (item.lower() for item in command)
    ):
        return CommandPolicy.INSTALL
    return CommandPolicy.SAFE


def can_auto_run(command: list[str]) -> bool:
    return classify_command(command) == CommandPolicy.SAFE
