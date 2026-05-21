from __future__ import annotations

import logging
import os
import platform
from pathlib import Path

logger = logging.getLogger("agentheim_code.config")


def _config_dir() -> Path:
    """Return the platform-appropriate configuration directory."""
    system = platform.system()
    if system == "Windows":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return base / "Agentheim Code"
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "Agentheim Code"
    return Path.home() / ".config" / "agentheim-code"


def _config_file() -> Path:
    return _config_dir() / "config.toml"


def load_config() -> dict:
    """Load user configuration from disk.

    Returns an empty dict if the config file does not exist.
    """
    config_path = _config_file()
    if not config_path.exists():
        return {}
    try:
        import tomllib

        with config_path.open("rb") as fh:
            return tomllib.load(fh)
    except Exception:
        logger.warning("Failed to load config from %s", config_path)
        return {}


def save_config(config: dict) -> None:
    """Save user configuration to disk."""
    config_path = _config_file()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import tomli_w

        with config_path.open("wb") as fh:
            tomli_w.dump(config, fh)
    except ImportError:
        logger.warning("tomli_w not installed; cannot save config")
    except Exception:
        logger.warning("Failed to save config to %s", config_path)


def ensure_default_config() -> Path:
    """Create the config file with defaults if it doesn't exist."""
    config_path = _config_file()
    if not config_path.exists():
        config_path.parent.mkdir(parents=True, exist_ok=True)
        default = b"""[core]
default_workspace = "."
default_port = 8765

[ui]
theme = "dark"
"""
        config_path.write_bytes(default)
        logger.info("Created default config at %s", config_path)
    return config_path
