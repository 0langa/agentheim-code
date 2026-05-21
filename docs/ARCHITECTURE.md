# Architecture

Agentheim Code is a focused product shell around the shared Agentheim Coder
runtime.

```text
Agentheim Code CLI / Desktop App
  -> local FastAPI backend
  -> agentheim_coder_core runtime
  -> agentheim_core config, providers, tools, policy, runs
```

Agentheim Full remains the superset platform. Agentheim Code depends on the
shared package boundaries and does not copy coder runtime behavior.

## Boundaries

- `agentheim_code`: focused product CLI, app launcher, and local backend wrapper.
- `agentheim_coder_core`: shared coder sessions, commands, models, runtime, and
  event contracts.
- `agentheim_core`: shared provider profiles, policy, tools, readiness, and run
  views.
- `apps/web`: premium React frontend.
- `apps/desktop`: Tauri shell.

## Persistence

Coder sessions stay under `.ai-team/runs/<session-id>/` for compatibility with
Agentheim Full.

