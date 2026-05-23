# ADR 0001: Config Surface And Storage

## Status

Accepted

## Context

Agentheim Code stores two categories of configuration:

1. **UI preferences and onboarding state** — theme, default workspace, default port,
   onboarding completion flags.
2. **Provider profiles and secrets** — provider endpoints, model bindings, API keys,
   and secret references.

These two categories have different consumers, lifecycles, and security requirements.
Merging them into a single file would complicate secret handling and make the UI
config harder to evolve independently.

## Decision

Keep the split explicit and document it in code, API contracts, and user-facing docs.

- **UI config** lives in `config.toml` managed by `src/agentheim_code/config.py`.
  - Storage: platform-specific user config dir
    - Windows: `%APPDATA%\Agentheim Code\config.toml`
    - macOS: `~/Library/Application Support/Agentheim Code/config.toml`
    - Linux: `~/.config/agentheim-code/config.toml`
  - Exposed via `GET/PATCH /api/config`
  - Keys: `core.default_workspace`, `core.default_port`, `ui.theme`,
    `onboarding.complete`, `onboarding.dismissed`

- **Provider profiles** live in `providers.json` managed by `src/config/config.py`.
  - Storage: `platformdirs.user_config_dir("agentheim") / "providers.json"`
  - Secrets are stored in the OS keyring or an encrypted file vault, never in the
    JSON document itself (only `secret_ref` pointers).
  - Exposed via `/api/providers/*`

## Consequences

- The backend `/api/config` endpoint never returns provider secrets or profile data.
- The CLI `agentheim-code app` reads workspace and port defaults from UI config.
- Provider setup flows always use the shared `src/config/config.py` layer.
- Both systems can evolve independently: UI config can add theme variants without
  touching provider schema, and provider schema can add new auth modes without
  affecting UI config parsing.
