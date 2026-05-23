# API Reference

Agentheim Code exposes a local FastAPI backend on `127.0.0.1`.

- web fallback calls it directly
- desktop shell reaches it through the local launcher contract
- it is not designed for public exposure

## Health And UI Config

- `GET /api/health`
  Returns backend status, version, and workspace.
- `GET /api/config`
  Returns onboarding state, default workspace, and theme.
- `PATCH /api/config`
  Accepts partial config updates.
  Valid theme values: `dark`, `light`, `high_contrast`.
- `GET /api/onboarding/local-providers`
  Returns detected local providers. Current auto-detection target: Ollama.
- `POST /api/onboarding/complete`
  Marks onboarding complete and can persist `default_workspace`.

## Sessions

- `GET /api/coder/sessions`
- `POST /api/coder/sessions`
  Body supports `workspace_root`, `trust_mode`, `mode`, `profile`, `provider`,
  `model`.
- `GET /api/coder/sessions/{id}`
- `GET /api/coder/sessions/{id}/view`
- `PATCH /api/coder/sessions/{id}/mode`
- `PATCH /api/coder/sessions/{id}/model`
- `POST /api/coder/sessions/{id}/cancel`
- `POST /api/coder/sessions/{id}/queue`

## Messages

- `POST /api/coder/sessions/{id}/messages`
- `POST /api/coder/sessions/{id}/messages/stream`

Message bodies accept:

```json
{
  "prompt": "Review auth flow",
  "context_files": ["src/auth.py", "tests/test_auth.py"]
}
```

`context_files` is optional. Legacy prompt-only payloads still work.

Streaming endpoint emits SSE events:

- `start`
- `activity`
- `token`
- `done`
- `error`

## Files, Runs, Usage

- `GET /api/coder/files`
- `GET /api/coder/files/search?q=...&limit=50`
- `GET /api/coder/runs`
- `GET /api/coder/sessions/{id}/diff`
- `GET /api/coder/sessions/{id}/usage`

## Approvals

- `POST /api/coder/sessions/{id}/approvals/{request_id}/grant`
- `POST /api/coder/sessions/{id}/approvals/{request_id}/deny`

Session views enrich pending approvals with:

- `params`
- `target`
- `action_kind`

## Provider Setup

- `GET /api/providers/templates`
- `GET /api/providers/wizard-templates`
- `GET /api/providers/profiles`
- `POST /api/providers/profiles`
- `DELETE /api/providers/profiles/{name}`
- `POST /api/providers/test`

## WebSocket

- `WS /api/coder/sessions/{id}/events`

WebSocket is kept for session-event snapshots. Assistant response delivery uses
the streaming message endpoint.
