# Troubleshooting

## Onboarding Did Not Appear

Check config state:

```powershell
agentheim-code doctor
```

If you previously skipped onboarding, open Settings and add a provider there.

## Ollama Was Not Detected

Verify Ollama is running locally:

```powershell
curl http://localhost:11434/api/tags
```

If that fails:

- start Ollama
- verify port `11434` is not blocked
- add a provider manually with the wizard

## Provider Test Failed

Common causes:

- invalid API key
- wrong base URL
- wrong model ID
- firewall or proxy blocking outbound calls

CLI retry:

```powershell
agentheim-code provider-test openai_v1 --api-key "sk-..." --endpoint "https://api.openai.com/v1" --model "gpt-4o-mini"
```

## Desktop Shell Opens But Cannot Reach Backend

Use the managed launcher:

```powershell
agentheim-code app --workspace .
```

This starts the local backend subprocess and passes its URL to the desktop shell.

Browser fallback remains available:

```powershell
agentheim-code app --workspace . --web
```

## Web Assets Missing

Rebuild packaged frontend assets:

```powershell
npm --prefix apps/web run build
```

## Windows Desktop Build Fails

Install Visual Studio Build Tools with the `Desktop development with C++`
workload, then retry:

```powershell
npm --prefix apps/desktop run build
```

## Installer Artifact Not Found After CI Build

The Windows workflow uploads:

- `agentheim-code-windows-installer`

Artifact source path:

- `apps/desktop/src-tauri/target/release/bundle/nsis/*.exe`

## Prompt Send Does Nothing

Check:

- active session exists
- prompt is not empty
- provider is configured
- approvals are not blocking required work

If a turn is stuck, stop it and retry from the composer.

## Usage Or Cost Is Blank

Likely causes:

- provider did not return token usage metadata
- model is missing from pricing registry

The session can still run without cost data.
