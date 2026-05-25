# Troubleshooting

## Onboarding Did Not Appear

Onboarding currently shows only when both are true:

- `onboarding_complete` is false
- `onboarding_dismissed` is false
- no configured provider profiles are available in the model options response

If you already skipped it, use Settings to add a provider.

## `agentheim-code app` Fails Immediately

`agentheim-code app` expects a packaged or locally built Tauri binary.

If you only installed the Python package, use browser mode instead:

```powershell
agentheim-code app --workspace . --web
```

If you do want the desktop shell, build it locally:

```powershell
npm --prefix apps/web install
npm --prefix apps/desktop install
npm --prefix apps/desktop run build
```

## Ollama Was Not Detected

Verify Ollama directly:

```powershell
curl http://localhost:11434/api/tags
```

If that fails:

- start Ollama
- confirm port `11434` is available
- add a provider manually from **Providers & Models**

## Provider Test Failed

Common causes:

- invalid API key
- wrong base URL
- wrong model id
- provider-specific auth mismatch
- network, proxy, or firewall issues

Retry from the CLI:

```powershell
agentheim-code provider-test openai_v1 --api-key "sk-..." --endpoint "https://api.openai.com/v1" --model "gpt-4o-mini"
```

## Browser UI Loads But Looks Empty Or Broken

Rebuild the frontend bundle:

```powershell
npm --prefix apps/web run build
```

Then relaunch `agentheim-code app --web`.

## Prompt Send Does Nothing

Check:

- a session is active
- the prompt is not empty
- a provider profile is configured
- an earlier turn is not still running

If a turn looks stuck, use `Stop`, then refresh the session view by selecting
the session again.

## File Context Was Rejected

Current context validation rejects:

- missing files
- directories
- files in `.git`
- files in `.ai-team`
- binary files
- oversized files
- paths outside the workspace

Use the context preview area to see which file failed and why.

## File Preview Fails

The preview endpoint only serves files inside the current workspace.

Failures usually mean:

- the file does not exist anymore
- the path was outside the workspace
- the file could not be read as text

## Desktop Shell Cannot Reach The Backend

Use the managed launcher rather than opening the Tauri binary manually:

```powershell
agentheim-code app --workspace .
```

This starts the backend subprocess and passes the backend URL through
`AGENTHEIM_CODE_BACKEND_URL`.

Browser fallback is always the simplest recovery path:

```powershell
agentheim-code app --workspace . --web
```

## Windows Desktop Build Fails

Install Visual Studio Build Tools with the `Desktop development with C++`
workload, then retry:

```powershell
npm --prefix apps/desktop run build
```

## CI Installer Artifact Is Missing

Current CI uploads:

- `agentheim-code-windows-installer`
- `agentheim-code-wheel`

The installer is expected under:

- `apps/desktop/src-tauri/target/release/bundle/nsis/*.exe`

## Usage Or Cost Is Blank

Likely causes:

- the provider did not return token usage metadata
- the model is not priced in the local pricing registry

The session can still run without cost data.

## Need A Support Bundle

Generate a redacted diagnostics bundle:

```powershell
agentheim-code diagnostics --out agentheim-diagnostics.json
```

## Config Path Confusion

UI preferences and provider profiles use different files:

- UI config (theme, workspace, onboarding): `config.toml` managed by
  `src/agentheim_code/config.py`
- Provider profiles: `providers.json` managed by `src/config/config.py` in the
  shared compatibility config area

See `docs/adr/0001-config-surface-and-storage.md` for the full boundary.
