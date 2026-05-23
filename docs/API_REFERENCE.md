# API Reference

Agentheim Code exposes a local FastAPI backend for the desktop shell, web
fallback, and tests. It binds to `127.0.0.1` and is unauthenticated in this pass.
Do not expose this port on a public interface.

Allowed browser origins are localhost/127.0.0.1 and Tauri app origins. The
origin check is hygiene, not a replacement for API auth.

## Routes

### Health & Workspace

- `GET /api/health`: backend version and workspace.

### Coder Sessions

- `GET /api/coder/sessions`: list sessions.
- `POST /api/coder/sessions`: create a session. Body supports `trust_mode`,
  `mode`, `profile`, `provider`, and `model`.
- `GET /api/coder/sessions/{id}`: session metadata.
- `GET /api/coder/sessions/{id}/view`: full UI/API session view.
- `POST /api/coder/sessions/{id}/messages`: run a user turn.
- `POST /api/coder/sessions/{id}/queue`: queue a prompt.
- `POST /api/coder/sessions/{id}/cancel`: cancel active work.
- `PATCH /api/coder/sessions/{id}/model`: update per-session model selection.
- `PATCH /api/coder/sessions/{id}/mode`: update session mode.
- `POST /api/coder/sessions/{id}/approvals/{request_id}/grant`: approve a tool request.
- `POST /api/coder/sessions/{id}/approvals/{request_id}/deny`: deny a tool request.
- `GET /api/coder/sessions/{id}/diff`: changed-file summaries.

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
