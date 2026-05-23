# Privacy and Security

## Principles

- Local-first by default.
- No cloud sync requirement.
- Secrets never leak to run artifacts, UI payloads, or CLI JSON.

## Network

- Backend binds to `127.0.0.1` only.
- The local API is unauthenticated; it should only be reachable from the local machine.
- HTTP CORS and WebSocket origin checks allow `localhost`/`127.0.0.1` and Tauri app origins.
- Network access is disabled for coder tools unless explicitly allowed by policy.

## Data Handling

- Tool calls go through Agentheim policy checks.
- Medium/high risk actions require approval unless trust mode allows them.
- Secrets stay in the shared provider secret store (OS keyring or encrypted vault).
- Diagnostics bundle command redacts secrets before writing to disk.

## Desktop Lifecycle

- Desktop production launch starts the backend on `127.0.0.1` and passes the backend URL to the Tauri shell through environment variables.
- Backend subprocess is terminated when the desktop shell exits.
- If Python dependencies are missing, the launcher shows a clear fallback message.

## Updates

- No auto-updater in 1.0.
- Manual update via `pip install --upgrade agentheim-code`.
- Version check is best-effort and privacy-safe (no telemetry).
