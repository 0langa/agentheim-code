# Privacy and Security

- Local-first by default.
- Backend binds to `127.0.0.1`.
- The local API is unauthenticated in this pass. It should only be reachable
  from the local machine.
- HTTP CORS and WebSocket origin checks allow localhost/127.0.0.1 and Tauri app
  origins, but they are defense-in-depth rather than authentication.
- Tool calls go through Agentheim policy checks.
- Medium/high risk actions require approval unless trust mode allows them.
- Secrets stay in the shared provider secret store and are not written to run
  artifacts, UI payloads, or CLI JSON.
- Network access is disabled for coder tools unless explicitly allowed by
  policy.
- Desktop production launch starts the backend on `127.0.0.1` and passes the
  backend URL to the Tauri shell through environment variables.
