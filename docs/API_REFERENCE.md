# API Reference

Agentheim Code exposes a local FastAPI backend for the desktop shell, web
fallback, and tests. It binds to `127.0.0.1` and is unauthenticated in this pass.
Do not expose this port on a public interface.

Allowed browser origins are localhost/127.0.0.1 and Tauri app origins. The
origin check is hygiene, not a replacement for API auth.

## Routes

- `GET /api/health`: backend version and workspace.
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
- `GET /api/coder/files`: workspace file tree.
- `GET /api/coder/runs`: run artifact list.
- `GET /api/coder/models`: provider profiles and model options.
- `GET /api/coder/commands`: command registry metadata.
- `GET /api/providers/templates`: provider setup templates.
- `GET /api/providers/profiles`: configured provider profile summary without secrets.

## WebSocket

- `WS /api/coder/sessions/{id}/events`: event replay/snapshot stream for a
  session. Disconnects are handled without leaking background tasks.
