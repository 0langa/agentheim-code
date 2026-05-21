# Providers

Agentheim Code uses the same provider profiles and secret storage as Agentheim
Full.

Typical setup remains:

```powershell
agentheim setup
agentheim-code doctor
agentheim-code models
```

Session-local overrides:

```powershell
agentheim-code coder --workspace . --profile default --provider openai --model gpt-4.1
```

In the app, use the model pill near the composer.

