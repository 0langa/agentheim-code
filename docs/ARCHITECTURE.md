# Architecture

Agentheim Code is a standalone local product shell around shared runtime
modules that live in this repository.

```text
CLI / Browser / Tauri shell
  -> local FastAPI backend
  -> coder runtime and session storage
  -> provider/profile/config/tool layers
```

## Repository Map

### Product-facing layers

- `src/agentheim_code`
  Product CLI, app launcher, FastAPI backend, onboarding/config APIs,
  diagnostics, provider wizard, context bundle adapter, packaged web assets.
- `apps/web`
  React/Vite workbench UI.
- `apps/desktop`
  Tauri shell that reads the backend URL from the launcher environment.

### Shared runtime layers used directly by this product

- `src/agentheim_coder_core`
  Coder command and runtime contracts.
- `src/agentheim_core`
  Readiness, run views, and shared model selection helpers.
- `src/core`
  Policies, runs, approvals, tools, schemas, and runtime infrastructure.
- `src/config`
  Shared provider/profile storage and template registry.
- `src/providers`
  Provider adapters and usage extraction.
- `src/workflows`
  Session runtime, persistence, and command execution.

Most product work starts in `src/agentheim_code`, `apps/web`, and
`apps/desktop`, but real behavior changes often require coordinated edits in
the shared runtime modules above.

## Launch Modes

### Browser fallback

`agentheim-code app --web`

- starts the FastAPI backend locally
- serves the built frontend
- opens the browser workbench at `/coder`

### Packaged desktop shell

`agentheim-code app`

- requires a built or installed Tauri binary
- starts the backend in a subprocess
- passes `AGENTHEIM_CODE_BACKEND_URL` into the shell

### Source-tree dev shell

`agentheim-code app --dev`

- expects a full checkout with Node, Rust, and Tauri dependencies
- runs the Tauri development workflow against the source web app

## Data And Config Locations

### Session data

- `.ai-team/runs/<session-id>/`

### UI config

Stored by `src/agentheim_code/config.py` in a platform-specific `config.toml`.

- Windows: `%APPDATA%\\Agentheim Code\\config.toml`
- macOS: `~/Library/Application Support/Agentheim Code/config.toml`
- Linux: `~/.config/agentheim-code/config.toml`

This file stores **UI preferences and onboarding state only**:

- `core.default_workspace`
- `core.default_port`
- `ui.theme`
- `onboarding.complete`
- `onboarding.dismissed`

Provider profiles and secrets are intentionally kept out of this file.
See `docs/adr/0001-config-surface-and-storage.md` for the boundary rationale.

### Provider profiles

Stored by `src/config/config.py` in `providers.json`.

- default location: `platformdirs.user_config_dir("agentheim")`
- this path uses the historical "agentheim" app name for backward compatibility
  with existing profiles; new installs use the same path so profiles are preserved
- secrets are stored in the OS keyring or an encrypted vault, never in the JSON document

### Provider health

Stored as `provider-health.json` in the same config directory as provider profiles.

## Frontend/Backend Contract

The web app talks only to the local backend under `/api`.

Main surfaces:

- onboarding and UI config
- session creation and session views
- streaming messages through SSE
- file search and preview
- provider templates, profiles, tests, and health
- approvals, diffs, terminal results, usage, and runs

The Tauri shell does not implement business logic. It only hosts the web app
and exposes the backend URL through a small command in `apps/desktop/src-tauri/src/main.rs`.
