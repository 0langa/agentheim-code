# Privacy and Security

## Core Assumptions

- Agentheim Code is local-first.
- The backend is meant to stay on the local machine.
- Provider credentials should not appear in normal UI responses or diagnostics output.

## Local Backend

- the backend binds to `127.0.0.1`
- the local API is unauthenticated
- HTTP CORS and WebSocket origin checks allow `localhost`, `127.0.0.1`, and Tauri origins

This means the backend should not be exposed to an untrusted network.

## Provider Secrets

- provider setup uses the shared compatibility secret-store abstraction when possible
- provider profile APIs return redacted summaries rather than raw secrets
- diagnostics redact common secret patterns before writing JSON output

## Context And File Data

When file context is enabled for a turn:

- selected file contents are read locally
- invalid paths are rejected before provider execution
- accepted previews are embedded into the prompt sent to the selected model

Do not attach files that contain secrets unless you intend to send that content
to the configured provider.

## Policy And Approvals

- risky tool actions are mediated by the runtime policy layer
- approvals are surfaced in the session view and UI inspector
- trust mode changes how aggressively the runtime pauses for approval

Current trust modes:

- `read_only`
- `ask`
- `workspace`

## Desktop Shell

- the packaged shell receives the backend URL through `AGENTHEIM_CODE_BACKEND_URL`
- the launcher starts the backend subprocess locally
- the launcher attempts to terminate the backend when the shell exits

The Tauri config currently includes a Content Security Policy in
`apps/desktop/src-tauri/tauri.conf.json`.

## Diagnostics

`agentheim-code diagnostics` writes a redacted JSON bundle with:

- system info
- redacted UI config
- provider health summaries
- discovered log paths

The diagnostics bundle is meant for local inspection or deliberate support
sharing, not automatic upload.

## Telemetry And Updates

- no telemetry pipeline is documented or implemented in the audited product surface
- no auto-updater is configured
- updates are manual
