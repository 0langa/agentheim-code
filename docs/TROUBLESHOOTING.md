# Troubleshooting

## No provider configured

Run:

```powershell
agentheim-code doctor
agentheim-code models
```

## Provider connection test fails

Use the built-in provider test to diagnose connectivity before saving a profile:

```powershell
agentheim-code provider-test openai_v1 --api-key "sk-..." --endpoint "https://api.openai.com/v1" --model "gpt-4o-mini"
```

Common causes:

- **Invalid API key** — verify the key has not expired and has sufficient quota.
- **Wrong endpoint** — ensure the base URL ends with `/v1` for OpenAI-compatible endpoints.
- **Model not found** — the model ID must match what the provider expects (e.g. `gpt-4o-mini`, not `gpt-4o`).
- **Network / firewall** — the backend must be able to reach the endpoint directly.

If the test returns `ok: true` but shows a **usage warning**, the provider works
but does not return token usage metadata. Cost tracking will be unavailable for
that provider.

## Custom endpoint not working

When using the **Custom Endpoint** (openai_compatible) template:

1. Verify the endpoint URL is reachable from the machine running Agentheim Code.
2. Ensure the endpoint implements the OpenAI chat completions API (`/v1/chat/completions`).
3. Check that the model name matches what the custom server expects.

## Desktop app does not launch

`agentheim-code app` expects a packaged Tauri binary. Build it or use the web
fallback:

```powershell
npm --prefix apps/desktop run build
agentheim-code app --workspace . --web
```

For source development, use:

```powershell
agentheim-code app --workspace . --dev
```

You can also point production launch at a known binary:

```powershell
$env:AGENTHEIM_CODE_DESKTOP_BINARY="C:\path\to\agentheim-code.exe"
agentheim-code app --workspace .
```

## Web assets missing

The backend first looks for packaged assets under `src/agentheim_code/web`. From
a checkout, run:

```powershell
npm --prefix apps/web run build
```

## Tauri build fails with `link.exe not found`

Install Visual Studio Build Tools with the **Desktop development with C++**
workload, then rerun:

```powershell
npm --prefix apps/desktop run build
```

## Session is already running

Another turn owns the session lock. Wait for it to finish, cancel from the UI,
or resume a different session.

## Provider failure

Run `agentheim-code models --json` to inspect configured profiles without
printing secrets. Then retry with an explicit profile/provider/model:

```powershell
agentheim-code coder --workspace . --profile default --provider <provider-id> --model <model-id>
```

## Usage/cost shows "—" instead of a dollar amount

This means the provider did not return token usage metadata, or the model is not
in the pricing registry. Cost tracking requires:

1. The provider to return `usage` in its response (OpenAI, Anthropic, Gemini, etc.)
2. The model to have a known rate in `src/agentheim_code/pricing.json`

You can still see raw token counts even when cost estimation is unavailable.
