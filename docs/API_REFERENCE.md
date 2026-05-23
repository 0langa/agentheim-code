# API Reference

Agentheim Code exposes a local FastAPI backend on `127.0.0.1`.

- browser mode calls it directly
- the Tauri shell resolves it through a launcher-provided backend URL
- it is local-only and not meant for public internet exposure

## Conventions

- base path: `/api`
- many coder endpoints accept optional `workspace_root`
- every response includes `x-request-id`
- structured failures may return:

```json
{
  "error_code": "E2003",
  "message": "Some selected context files could not be used.",
  "technical_detail": "...",
  "recovery_action": "...",
  "related_event_id": ""
}
```

## Request Limits

The backend enforces a maximum JSON body size of **256 KB** (`262,144` bytes).
Endpoints that accept large payloads return `413` when the limit is exceeded:

- `POST /api/coder/sessions/{session_id}/messages`
- `POST /api/coder/sessions/{session_id}/messages/stream`
- `POST /api/coder/sessions/{session_id}/queue`

Oversized requests receive structured error `E2008`.

## Request IDs

All responses include the header `x-request-id`. Clients may supply their own
value in the request header; otherwise the backend generates a UUID4 hex value.
Request IDs are also attached to structured error detail payloads when available.

## OpenAPI Schema

The backend serves its own OpenAPI document at:

```
GET /openapi.json
```

This can be used to regenerate TypeScript API types for the frontend:

```powershell
npm --prefix apps/web run types:api
```

See `docs/adr/0002-api-type-generation.md` for the generation decision.

## Health And UI Config

### `GET /api/health`

Returns:

- `status`
- `version`
- `workspace`

### `GET /api/config`

Returns UI config:

- `onboarding_complete`
- `onboarding_dismissed`
- `default_workspace`
- `theme`

### `PATCH /api/config`

Accepts partial updates for:

- `onboarding_complete`
- `onboarding_dismissed`
- `default_workspace`
- `theme`

Current valid themes:

- `dark`
- `light`
- `high_contrast`

### `GET /api/onboarding/local-providers`

Returns detected local providers. The current implementation only auto-detects
Ollama by probing `http://localhost:11434/api/tags` and exposes the app-facing
endpoint as `http://localhost:11434/v1`.

### `POST /api/onboarding/complete`

Marks onboarding complete and can also persist `default_workspace`.

## Sessions

### `GET /api/coder/sessions`

Lists sessions for the selected workspace.

### `POST /api/coder/sessions`

Request body:

```json
{
  "workspace_root": ".",
  "trust_mode": "ask",
  "mode": "code",
  "profile": "default",
  "provider": "openai",
  "model": "gpt-4.1"
}
```

All fields except `trust_mode` and `mode` are optional.

### `GET /api/coder/sessions/{session_id}`

Returns the raw session record.

### `GET /api/coder/sessions/{session_id}/view`

Returns the session plus derived UI data such as:

- `events`
- `approvals`
- `diffs`
- `command_results`
- `queued_prompts`
- `available_commands`

### `PATCH /api/coder/sessions/{session_id}/mode`

Body:

```json
{ "mode": "review" }
```

### `PATCH /api/coder/sessions/{session_id}/model`

Body:

```json
{
  "profile": "default",
  "provider": "openai",
  "model": "gpt-4.1"
}
```

Each field is optional.

### `POST /api/coder/sessions/{session_id}/cancel`

Cancels the active turn and returns the updated session.

### `POST /api/coder/sessions/{session_id}/resume`

Attempts to move a blocked or resumable session back to idle. Running or
invalid sessions return a structured conflict error.

### `POST /api/coder/sessions/{session_id}/queue`

Body:

```json
{ "prompt": "Continue after approval" }
```

## Messages And Streaming

### `POST /api/coder/sessions/{session_id}/messages`

### `POST /api/coder/sessions/{session_id}/messages/stream`

Message body:

```json
{
  "prompt": "Review auth flow",
  "context_files": ["src/auth.py", "tests/test_auth.py"],
  "use_context_bundle": true
}
```

Notes:

- `prompt` is required
- `context_files` is optional
- `use_context_bundle` defaults to `true`
- legacy prompt-only payloads still work

When context bundling is enabled, accepted files are read and embedded into an
explicit `<context_files>` prompt block. Invalid selections return structured
context errors before provider execution starts.

### Streaming SSE events

The stream endpoint emits:

- `start`
- `activity`
- `token`
- `done`
- `error`

The frontend currently parses these events manually in `apps/web/src/api.ts`.

## Files, Context, Runs, Diffs, Usage

### `GET /api/coder/files`

Returns the workspace file tree.

### `GET /api/coder/files/search?q=...&limit=50`

Returns matching file entries. Current implementation:

- filters against the existing file tree
- returns files only
- excludes `.git` and `.ai-team`
- bounds `limit` to `1..200`

### `GET /api/coder/files/preview?path=...`

Returns UTF-8 text content for a workspace file.

Current protections:

- rejects empty paths
- rejects `..`
- rejects paths outside the workspace

### `POST /api/coder/sessions/{session_id}/context/validate`

Body:

```json
{
  "paths": ["src/app.py", "README.md"]
}
```

Returns:

- `session_id`
- `items`
- `errors`
- `total_token_estimate`

Each item includes:

- `path`
- `status`
- `size`
- `preview`
- `truncation_reason`
- `token_estimate`

### `GET /api/coder/runs`

Lists run views for the workspace.

### `GET /api/coder/sessions/{session_id}/diff`

Returns per-file before/after diff payloads from the session view.

### `GET /api/coder/sessions/{session_id}/usage`

Returns aggregated token and cost data for the session when provider metadata is
available.

## Approvals

### `POST /api/coder/sessions/{session_id}/approvals/{request_id}/grant`

### `POST /api/coder/sessions/{session_id}/approvals/{request_id}/deny`

Session views enrich approval entries with frontend display fields derived from
pending params:

- `params`
- `target`
- `action_kind`

## Providers

### `GET /api/providers/templates`

Returns provider templates from the shared registry, including experimental
templates.

### `GET /api/providers/wizard-templates`

Returns provider templates augmented with wizard field definitions.

### `GET /api/providers/profiles`

Returns configured profiles plus:

- `configured`
- `default_profile`
- `profiles`

### `GET /api/providers/health`

Returns persisted provider health summaries from `provider-health.json`.

### `POST /api/providers/profiles`

Creates or updates a profile. Current body shape:

```json
{
  "name": "default",
  "provider_kind": "openai_v1",
  "provider_id": "openai",
  "model_id": "gpt-4o-mini",
  "fields": {
    "api_key": "sk-...",
    "endpoint": "https://api.openai.com/v1"
  },
  "set_as_default": true
}
```

### `DELETE /api/providers/profiles/{name}`

Deletes a provider profile and its stored secrets when possible.

### `POST /api/providers/test`

Tests a provider with a real inference call using the supplied fields.

## WebSocket

### `WS /api/coder/sessions/{session_id}/events`

Returns session event snapshots. The main assistant response path is still the
SSE message stream, not the WebSocket.
