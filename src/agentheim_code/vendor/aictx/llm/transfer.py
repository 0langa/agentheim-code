"""Model-transfer safety preflight."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from agentheim_code.vendor.aictx.config import AictxConfig
from agentheim_code.vendor.aictx.errors import ConfigError, SafetyError, SecretScanError, TokenBudgetExceededError
from agentheim_code.vendor.aictx.models.inventory import FileEntry, RepositoryInventory

RUNTIME_BLOCKED_PREFIXES = (
    ".git/",
    ".ai-team/runs/",
    ".ai-team/cache/",
    ".ai-team/tmp/",
    ".aictx/runs/",
    ".aictx/cache/",
    ".aictx/tmp/",
    "build/",
    "dist/",
    "node_modules/",
)
MAX_OUTPUT_PACKS = 6
OUTPUT_TOKENS_PER_PACK = 4096


@dataclass(frozen=True)
class TransferFile:
    """File approved for provider prompt use."""

    path: str
    size_bytes: int
    estimated_tokens: int
    reason: str


@dataclass(frozen=True)
class ModelTransferPlan:
    """Validated file set and budget estimates for model transfer."""

    provider: str
    model: str
    allow_ai: bool
    selected_files: list[TransferFile]
    estimated_input_tokens: int
    estimated_output_tokens: int
    max_input_tokens_per_run: int
    max_output_tokens_per_run: int
    max_files_per_run: int
    max_file_bytes: int

    def to_dict(self) -> dict[str, object]:
        """Return JSON-serializable metadata without prompt content."""
        return {
            "provider": self.provider,
            "model": self.model,
            "allow_ai": self.allow_ai,
            "selected_files": [asdict(file) for file in self.selected_files],
            "estimated_input_tokens": self.estimated_input_tokens,
            "estimated_output_tokens": self.estimated_output_tokens,
            "max_input_tokens_per_run": self.max_input_tokens_per_run,
            "max_output_tokens_per_run": self.max_output_tokens_per_run,
            "max_files_per_run": self.max_files_per_run,
            "max_file_bytes": self.max_file_bytes,
        }


def prepare_model_transfer(
    repo_root: Path,
    inventory: RepositoryInventory,
    selected_files: list[str],
    reason_per_selected_file: dict[str, str],
    config: AictxConfig,
    allow_ai: bool,
) -> ModelTransferPlan:
    """Validate selected files before any provider can receive repository content."""
    if inventory.secrets:
        raise SecretScanError("High-confidence secrets detected; refusing model transfer.")
    if config.llm.provider != "dry_run" and not allow_ai:
        raise ConfigError(f"Provider '{config.llm.provider}' requires explicit --allow-ai.")
    if len(selected_files) > config.limits.max_files_per_run:
        raise TokenBudgetExceededError("Planned context exceeds configured max_files_per_run.")

    entries = {entry.path: entry for entry in inventory.files}
    transfer_files: list[TransferFile] = []
    for path in selected_files:
        entry = entries.get(path)
        if entry is None:
            raise SafetyError(f"Selected file is not present in inventory: {path}")
        _validate_transfer_file(path, entry, config)
        estimated_tokens = _estimate_file_tokens(repo_root / path)
        transfer_files.append(
            TransferFile(
                path=path,
                size_bytes=entry.size_bytes,
                estimated_tokens=estimated_tokens,
                reason=reason_per_selected_file.get(path, "selected"),
            )
        )

    estimated_input_tokens = sum(file.estimated_tokens for file in transfer_files)
    estimated_output_tokens = _estimate_output_tokens(transfer_files)
    if estimated_input_tokens > config.limits.max_input_tokens_per_run:
        raise TokenBudgetExceededError(
            "Planned context exceeds configured max_input_tokens_per_run."
        )
    if estimated_output_tokens > config.limits.max_output_tokens_per_run:
        raise TokenBudgetExceededError(
            "Planned context exceeds configured max_output_tokens_per_run."
        )

    return ModelTransferPlan(
        provider=config.llm.provider,
        model=config.llm.model,
        allow_ai=allow_ai,
        selected_files=transfer_files,
        estimated_input_tokens=estimated_input_tokens,
        estimated_output_tokens=estimated_output_tokens,
        max_input_tokens_per_run=config.limits.max_input_tokens_per_run,
        max_output_tokens_per_run=config.limits.max_output_tokens_per_run,
        max_files_per_run=config.limits.max_files_per_run,
        max_file_bytes=config.limits.max_file_bytes,
    )


def _validate_transfer_file(path: str, entry: FileEntry, config: AictxConfig) -> None:
    if _is_unsafe_relative_path(path):
        raise SafetyError(f"Selected file path is not repo-relative and safe: {path}")
    if path.startswith(RUNTIME_BLOCKED_PREFIXES) or path == ".git":
        raise SafetyError(f"Selected file is a blocked runtime/build artifact: {path}")
    if entry.is_ignored:
        raise SafetyError(f"Selected file is ignored: {path}")
    if entry.is_binary:
        raise SafetyError(f"Selected file is binary: {path}")
    if entry.is_generated:
        raise SafetyError(f"Selected file is generated runtime context: {path}")
    if entry.size_bytes > config.limits.max_file_bytes:
        raise TokenBudgetExceededError("Selected file exceeds configured max_file_bytes.")
    if entry.sha256 == "skipped":
        raise SafetyError(f"Selected file was not hashed and cannot be transferred: {path}")


def _is_unsafe_relative_path(path: str) -> bool:
    parts = Path(path).parts
    return not path or path.startswith(("/", "\\")) or ".." in parts or ":" in parts[0]


def _estimate_file_tokens(path: Path) -> int:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise SafetyError(f"Could not read selected file for token estimate: {path}") from exc
    if not text:
        return 0
    return max(len(text) // 4, 1)


def _estimate_output_tokens(files: list[TransferFile]) -> int:
    if not files:
        return 0
    return min(MAX_OUTPUT_PACKS, max(1, len(files))) * OUTPUT_TOKENS_PER_PACK
