class AIteamError(Exception):
    """Base application error."""


class ConfigError(AIteamError):
    """Raised when configuration is missing or invalid."""


class ProviderError(AIteamError):
    """Raised when provider operations fail."""

    def __init__(self, message: str, *, http_status: int | None = None) -> None:
        super().__init__(message)
        self.http_status = http_status


class RepoInspectionError(AIteamError):
    """Raised when repository inspection fails."""


class ToolSafetyError(AIteamError):
    """Raised when a tool violates safety policy."""


class PlanningError(AIteamError):
    """Raised when planning fails."""


class ExecutionError(AIteamError):
    """Raised when apply-mode execution fails."""


class PatchApplicationError(AIteamError):
    """Raised when a generated patch cannot be applied safely."""


class VerificationError(AIteamError):
    """Raised when verification cannot complete."""


class ResumeError(AIteamError):
    """Raised when run ledger resume/report operations fail."""


class IntegrationError(AIteamError):
    """Raised when optional integrations are requested but unavailable."""
