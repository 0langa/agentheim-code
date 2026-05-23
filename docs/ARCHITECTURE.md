# Architecture

Agentheim Code is a focused product shell around the shared Agentheim Coder
runtime.

```text
Agentheim Code CLI / Desktop App
  -> local FastAPI backend
  -> agentheim_coder_core runtime
  -> agentheim_core config, providers, tools, policy, runs
```

Agentheim Full remains the superset platform. Agentheim Code carries the shared
package boundaries inside this repo for now, so it installs and runs without a
sibling Agentheim Full checkout.

## Boundaries

- `agentheim_code`: focused product CLI, app launcher, and local backend wrapper.
- `agentheim_coder_core`: coder sessions, commands, models, runtime, and event
  contracts.
- `agentheim_core`: provider profiles, policy, tools, readiness, and run views.
- `apps/web`: React frontend.
- `apps/desktop`: Tauri shell.

## Repository Scope

This checkout may contain broader Agentheim packages from a sibling editable
install, but they are not owned by this repository. The tracked Agentheim Code
surface is `src/agentheim_code`, `src/memory`, `src/tools/shell`, `apps/web`,
and `apps/desktop`. Ignored local packages such as `src/core`, `src/config`,
`src/providers`, and `src/workflows` are runtime dependencies for development,
not product-owned files to modify as part of Agentheim Code changes.

## Persistence

Coder sessions stay under `.ai-team/runs/<session-id>/` for compatibility with
Agentheim Full.
