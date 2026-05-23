# API Reference

Agentheim Code exposes a local FastAPI backend for the desktop shell, web
fallback, and tests. It binds to `127.0.0.1` and is unauthenticated in this pass.
Do not expose this port on a public interface.

Allowed browser origins are localhost/127.0.0.1 and Tauri app origins. The
origin check is hygiene, not a replacement for API auth.

## Routes

### Health & Workspace

- `GET /api/health`: backend version and workspace.
- `GET /api/config`: UI config for onboarding, default workspace, and theme.
- `PATCH /api/config`: partial config update. Valid themes are `dark`, `light`,
  and `high_contrast`.
- `GET /api/onboarding/local-providers`: local provider detection. Currently
  reports Ollama at `http://localhost:11434/v1`.
- `POST /api/onboarding/complete`: mark onboarding complete and optionally store
  `default_workspace`.

### Coder Sessions

- `GET /api/coder/sessions`: list sessions.
- `POST /api/coder/sessions`: create a session. Body supports `trust_mode`,
  `mode`, `profile`, `provider`, and `model`.
- `GET /api/coder/sessions/{id}`: session metadata.
- `GET /api/coder/sessions/{id}/view`: full UI/API session view.
- `POST /api/coder/sessions/{id}/messages`: run a user turn. Body supports
  `prompt` and optional `context_files`.
- `POST /api/coder/sessions/{id}/messages/stream`: run a user turn and stream
  Server-Sent Events. Emits `start`, `activity`, `token`, `done`, and `error`
  events. Body supports `prompt` and optional `context_files`.
- `POST /api/coder/sessions/{id}/queue`: queue a prompt.
- `POST /api/coder/sessions/{id}/cancel`: cancel active work.
- `PATCH /api/coder/sessions/{id}/model`: update per-session model selection.
- `PATCH /api/coder/sessions/{id}/mode`: update session mode.
- `POST /api/coder/sessions/{id}/approvals/{request_id}/grant`: approve a tool request.
- `POST /api/coder/sessions/{id}/approvals/{request_id}/deny`: deny a tool request.
  Session views include pending approval display fields: `params`, `target`,
  and `action_kind`.
- `GET /api/coder/sessions/{id}/diff`: changed-file summaries.
- `GET /api/coder/files/search?q=...&limit=50`: fuzzy file context search.

### Usage Tracking

- `GET /api/coder/sessions/{id}/usage`: aggregated token usage and estimated cost
  for a session. Returns:
  ```json
  {
    "session_id": "...",
    "input_tokens": 150,
    "output_tokens": 75,
    "total_tokens": 225,
    "estimated_cost_usd": 0.000150,
    "calls": 3,
    "breakdown": [
      {
        "sequence": 1,
        "timestamp": "2026-05-21T12:00:00Z",
        "model": "gpt-4o-mini",
        "provider": "openai_v1",
        "input_tokens": 50,
        "output_tokens": 25,
        "total_tokens": 75,
        "estimated_cost_usd": 0.000050
      }
    ]
  }
  ```
  If no usage data is available, `estimated_cost_usd` will be `null`.

### Workspace & Commands

- `GET /api/coder/files`: workspace file tree.
- `GET /api/coder/runs`: run artifact list.
- `GET /api/coder/models`: provider profiles and model options.
- `GET /api/coder/commands`: command registry metadata.

### Provider Setup

- `GET /api/providers/templates`: provider setup templates.
- `GET /api/providers/wizard-templates`: templates with wizard field schemas.
- `GET /api/providers/profiles`: configured provider profile summary without secrets.
- `POST /api/providers/profiles`: create a new provider profile.
- `DELETE /api/providers/profiles/{name}`: delete a provider profile.
- `POST /api/providers/test`: test a provider connection with live inference.
  Body: `{"provider_kind": "...", "fields": {"api_key": "...", "endpoint": "..."}, "model_id": "..."}`.
  Returns `{"ok": true, "latency_ms": 123, "model": "...", "usage": {...}}`
  or `{"ok": false, "error": "..."}`.

## WebSocket

- `WS /api/coder/sessions/{id}/events`: event replay/snapshot stream for a
  session. Disconnects are handled without leaking background tasks.

The WebSocket remains for session event snapshots. Chat response delivery should
use the streaming message endpoint.
