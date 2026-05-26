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

Current response normalization also gives the frontend stable display fields:

- transcript entries expose `timestamp`
- events expose `type`, `timestamp`, and optional `payload`
- command results expose computed `status` and `timestamp`
- diffs expose `timestamp`

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

Returns the legacy bounded workspace file snapshot used by older clients.
Current implementation returns the first page-like slice of the workspace tree.

### `GET /api/coder/files/browser?q=...&offset=0&limit=100`

Returns the paged workspace browser payload used by the current workbench.

Response fields:

- `items`
- `next_offset`
- `has_more`
- `query`

This route:

- supports flat substring filtering with `q`
- excludes `.git` and `.ai-team`
- bounds `limit` to `1..200`
- allows the frontend to incrementally load more results instead of fetching one capped list

### `GET /api/coder/files/search?q=...&limit=50`

Returns matching file entries. Current implementation:

- filters against the workspace file tree
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

### `GET /api/coder/models`

Returns the current provider/model selection payload used by the workbench.
Current implementation includes:

- `configured`
- `default_profile`
- `profiles`
- per-model `health` summaries when persisted health data exists
- per-model `recommendations` metadata for planner suitability and cost support

### `GET /api/coder/commands`

Returns the built-in command registry exposed to the frontend command palette.
The palette still executes only the frontend-supported subset directly.

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

## Providers (Legacy)

These endpoints remain for backward compatibility. New integrations should prefer
the `/api/provider-management/*` routes below.

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

## Provider Management

The `/api/provider-management/*` namespace replaces the legacy provider routes
with full CRUD for profiles, accounts, and model bindings.

Onboarding now reuses the same provider-management stack through a guided
wrapper in the frontend rather than maintaining a separate provider form path.

### Profiles

#### `GET /api/provider-management/profiles`

Lists all profiles with redacted accounts and bindings.

#### `POST /api/provider-management/profiles`

Creates a profile. Body:

```json
{
  "name": "work",
  "set_as_default": false
}
```

#### `GET /api/provider-management/profiles/{name}`

Returns a single profile.

#### `PATCH /api/provider-management/profiles/{name}`

Renames or updates profile metadata.

#### `DELETE /api/provider-management/profiles/{name}`

Deletes the profile and its secrets.

#### `POST /api/provider-management/profiles/{name}/duplicate`

Duplicates the profile under a new name.

#### `POST /api/provider-management/profiles/{name}/set-default`

Sets the profile as the document-wide default.

#### `GET /api/provider-management/profiles/{name}/export`

Exports the profile as a portable JSON document (secrets redacted).

#### `POST /api/provider-management/profiles/import`

Imports a previously exported profile JSON document. Validates provider refs and
deduplicates entries.

### Accounts

#### `POST /api/provider-management/profiles/{name}/accounts`

Adds a provider account to the profile. Body:

```json
{
  "id": "openai",
  "kind": "openai_v1",
  "endpoint": "https://api.openai.com/v1",
  "auth_mode": "bearer",
  "timeout_seconds": 60,
  "headers": {},
  "metadata": {
    "template": "openai_v1"
  }
}
```

Add or rotate credentials through the dedicated secret routes. Secrets are
stored through the shared secret store; the API never returns raw secrets.

#### `PATCH /api/provider-management/profiles/{name}/accounts/{account_id}`

Updates an existing account. Partial updates are supported.

#### `DELETE /api/provider-management/profiles/{name}/accounts/{account_id}`

Removes the account. Use `?cascade=true` to also remove dependent model bindings.

#### `POST /api/provider-management/profiles/{name}/accounts/{account_id}/test`

Runs a live connection test against the provider.

#### `POST /api/provider-management/accounts/test-draft`

Runs a live connection test against an unsaved account payload from the editor.
This is the route used when the UI tests a draft account before it has been
saved to a profile.

Body:

```json
{
  "account": {
    "id": "openai-cloud",
    "kind": "openai_compatible",
    "endpoint": "https://api.openai.com/v1",
    "auth_mode": "bearer",
    "timeout_seconds": 60,
    "headers": {},
    "metadata": {
      "template": "openai_compatible"
    }
  },
  "secret_value": "sk-...",
  "profile_name": "default",
  "existing_account_id": "openai-cloud"
}
```

`existing_account_id` is optional and lets the backend reuse a stored secret
reference when the user is editing an existing account but leaves the secret
blank.

#### `POST /api/provider-management/profiles/{name}/accounts/{account_id}/rotate-secret`

Rotates a stored secret. Body:

```json
{
  "secret_name": "api_key",
  "secret_value": "sk-new-..."
}
```

#### `POST /api/provider-management/profiles/{name}/accounts/{account_id}/discover-models`

Triggers remote model discovery for supported providers. Returns:

```json
{
  "ok": true,
  "supported": true,
  "discovery_mode": "remote_list",
  "models": [{"id": "gpt-4o", "display_name": "GPT-4o", ...}]
}
```

For unsupported providers `supported` is `false` and `models` is empty.
The UI surfaces this as an explicit manual-entry fallback instead of pretending
discovery succeeded.

#### `GET /api/provider-management/profiles/{name}/accounts/{account_id}/discovered-models`

Re-runs discovery without persisting; useful for UI refresh.

### Models

#### `POST /api/provider-management/profiles/{name}/models`

Adds a model binding. The normal user-facing role is `planner`. Body:

```json
{
  "id": "planner",
  "role": "planner",
  "provider": "openai",
  "model": "gpt-4o-mini",
  "display_name": "Planner",
  "capabilities": ["text", "json", "streaming"],
  "enabled": true,
  "is_default": true
}
```

#### `PATCH /api/provider-management/profiles/{name}/models/{binding_id}`

Updates a model binding.

#### `DELETE /api/provider-management/profiles/{name}/models/{binding_id}`

Removes the binding.

#### `POST /api/provider-management/profiles/{name}/models/{binding_id}/set-default`

Sets this binding as the default coding model for the profile.

#### `POST /api/provider-management/profiles/{name}/models/{binding_id}/assign-role`

Compatibility endpoint for internal role reassignment. The user-facing product
only configures `planner` through the main UI.

#### `POST /api/provider-management/profiles/{name}/models/import-discovered`

Bulk-imports models from a prior discovery result. Body:

```json
{
  "account_id": "openai",
  "models": ["gpt-4o", "gpt-4o-mini"]
}
```

### Templates

#### `GET /api/provider-management/templates`

Lists all templates with capability metadata.

#### `GET /api/provider-management/templates/{template_id}`

Returns a single template with its capability metadata attached.

## WebSocket

### `WS /api/coder/sessions/{session_id}/events`

Returns session event snapshots. The main assistant response path is still the
SSE message stream, not the WebSocket.
