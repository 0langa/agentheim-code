# Privacy and Security

- Local-first by default.
- Backend binds to `127.0.0.1`.
- Tool calls go through Agentheim policy checks.
- Medium/high risk actions require approval unless trust mode allows them.
- Secrets stay in the shared provider secret store and are not written to run
  artifacts, UI payloads, or CLI JSON.
- Network access is disabled for coder tools unless explicitly allowed by
  policy.

