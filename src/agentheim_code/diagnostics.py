"""Security/support diagnostics bundle for Agentheim Code.

Gathers config, logs, provider health, and system info while redacting secrets.
"""

from __future__ import annotations

import json
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agentheim_code import __version__
from agentheim_code.provider_health import load_health
from agentheim_code.structured_errors import redact_text


def _redacted_config() -> dict[str, Any]:
    from agentheim_code.config import load_config

    try:
        cfg = load_config()
    except Exception:
        return {"error": "Could not load config"}
    # Redact any string values that look like secrets
    return _deep_redact(cfg)


def _deep_redact(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _deep_redact(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_deep_redact(item) for item in obj]
    if isinstance(obj, str):
        return redact_text(obj)
    return obj


def _system_info() -> dict[str, Any]:
    return {
        "platform": platform.system(),
        "platform_release": platform.release(),
        "architecture": platform.machine(),
        "python_version": sys.version,
        "app_version": __version__,
        "timestamp": datetime.now(tz=UTC).isoformat(),
    }


def _log_paths() -> dict[str, str]:
    from platformdirs import user_log_dir

    log_dir = Path(user_log_dir("agentheim", "Agentheim"))
    paths: dict[str, str] = {}
    if log_dir.exists():
        for f in sorted(log_dir.iterdir()):
            if f.is_file():
                paths[f.name] = str(f)
    return paths


def generate_diagnostics_bundle() -> dict[str, Any]:
    return {
        "system": _system_info(),
        "config": _redacted_config(),
        "provider_health": {k: v.to_dict() for k, v in load_health().items()},
        "log_paths": _log_paths(),
    }


def write_diagnostics_bundle(out_path: Path) -> None:
    bundle = generate_diagnostics_bundle()
    out_path.write_text(json.dumps(bundle, indent=2), encoding="utf-8")
