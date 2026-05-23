"""Security/support diagnostics bundle for Agentheim Code.

Gathers config, logs, provider health, and system info while redacting secrets.
"""

from __future__ import annotations

import json
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

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
    return cast(dict[str, Any], _deep_redact(cfg))


def _deep_redact(obj: Any) -> object:
    if isinstance(obj, dict):
        return {k: _deep_redact(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_deep_redact(item) for item in obj]
    if isinstance(obj, str):
        return redact_text(obj)
    return cast(object, obj)


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


def _recent_sessions(workspace_root: Path | None = None) -> list[dict[str, Any]]:
    from workflows.coder.runtime import list_sessions

    try:
        root = workspace_root or Path(".")
        sessions = list_sessions(root)
    except Exception:
        return []
    recent: list[dict[str, Any]] = []
    for session in sessions[:5]:
        recent.append(
            {
                "session_id": session.session_id,
                "status": session.status.value
                if hasattr(session.status, "value")
                else str(session.status),
                "mode": session.mode.value if hasattr(session.mode, "value") else str(session.mode),
                "trust_mode": session.trust_mode.value
                if hasattr(session.trust_mode, "value")
                else str(session.trust_mode),
                "updated_at": session.updated_at,
                "last_failure_reason": session.last_failure_reason,
                "repair_attempts": session.repair_attempts,
            }
        )
    return recent


def generate_diagnostics_bundle(workspace_root: Path | None = None) -> dict[str, Any]:
    from config.config import load_profiles_document

    bundle: dict[str, Any] = {
        "system": _system_info(),
        "config": _redacted_config(),
        "provider_health": {k: v.to_dict() for k, v in load_health().items()},
        "log_paths": _log_paths(),
        "recent_sessions": _recent_sessions(workspace_root),
    }
    try:
        doc = load_profiles_document()
        bundle["provider_summary"] = {
            "configured": True,
            "default_profile": doc.default_profile,
            "profile_count": len(doc.profiles),
        }
    except Exception as exc:
        bundle["provider_summary"] = {"configured": False, "error": str(exc)}
    if workspace_root:
        bundle["workspace"] = str(workspace_root)
    return bundle


def write_diagnostics_bundle(out_path: Path) -> None:
    bundle = generate_diagnostics_bundle()
    out_path.write_text(json.dumps(bundle, indent=2), encoding="utf-8")
