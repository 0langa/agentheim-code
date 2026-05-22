# Providers

Agentheim Code uses standalone provider/profile code copied into this product.
It can read the same profile format and secret references as Agentheim Full, but
does not depend on Agentheim Full being installed.

Typical checks:

```powershell
agentheim-code doctor
agentheim-code models
```

Session-local overrides:

```powershell
agentheim-code coder --workspace . --profile default --provider openai --model gpt-4.1
```

In the app, use the model pill near the composer.

Provider secrets should be stored through the configured secret store or
environment variables. They should not be committed, printed in CLI JSON, or
written into `.ai-team/runs`.
