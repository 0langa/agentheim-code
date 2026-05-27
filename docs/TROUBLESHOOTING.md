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

If the turn is blocked on approval, the chat now shows an inline assistant
message plus an `Open approvals` action. Use that instead of waiting for the
right panel to switch automatically.

## `Failed to fetch` Or Backend Unreachable

The workbench now rewrites raw browser `Failed to fetch` errors into a product
message, but the root cause is still usually one of these:

- the local backend never started
- the desktop shell lost its backend subprocess
- the previous session is pointing at a stale local server

Try:

- fully close and reopen the app
- relaunch with `agentheim-code app --workspace . --web`
- or, for desktop mode, relaunch with `agentheim-code app --workspace .`

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

## Provider Permission Denied / Forbidden

The provider rejected the request with a 403 or permission-denied response.

- Verify the API key has access to the requested model
- Check provider dashboard for usage limits or access restrictions
- Run `agentheim-code doctor` to verify provider connectivity

## Provider Authentication Failed

The provider rejected the credentials (401 or auth-related error).

- Check that the API key is set in the secret store and has not expired
- Verify the `auth_mode` matches the provider template (bearer, api_key, x_api_key, etc.)
- Run `agentheim-code provider-test <kind> --api-key ...` to test live

## Provider Rate Limit Or Temporary Outage

The provider returned a rate-limit, quota, or temporary-unavailable error.

- Wait briefly and retry
- Check provider status page for known outages
- Switch to a different provider or model if the issue persists
- Run `agentheim-code doctor` to check provider connectivity

## Provider Endpoint / Model Mismatch

The provider returned a model-not-found, deployment-not-found, or bad-request error.

- Verify the model ID is valid for the selected provider
- Check that the endpoint URL is correct
- Run `agentheim-code provider-test <kind> --model <model-id>` to test

## Tool Call Blocked

A tool invocation was blocked by the policy engine.

- Review the policy justification in the approval panel
- Check the current trust mode (`read_only`, `ask`, or `workspace`)
- For path-related blocks, confirm the file is inside the workspace and not in `.git`
- For command-related blocks, confirm the command prefix is in the safe allowlist

## Recovering From A Failed Run

A session turn failed and the session is in `failed` or `blocked` state.

- Read the structured error message and machine code in the session timeline
- Check the terminal panel for command exit codes and output
- Use `agentheim-code coder resume <session-id>` to reset the session to idle
- Send a simpler or more specific follow-up prompt

## Run Fails Mid-Execution

A turn starts but fails partway through action execution.

- Check if the failure was caused by a blocked approval — grant or deny it, then resume
- Check the diff panel for partially applied changes
- Check the terminal panel for failed verification commands
- If stuck, cancel the session and start a new turn

## Configuration Issues

Agentheim Code is not configured correctly for the requested operation.

- Run `agentheim-code doctor` to diagnose readiness
- Verify provider profiles exist with `agentheim-code models`
- Check UI config and provider profiles are in their correct locations (see **Config Path Confusion** above)
- Export and inspect config with `agentheim-code config export --path check.json`

## Request Too Large

The prompt or attached context exceeded the 256KB request body limit (`E2008`).

- Reduce the prompt length
- Remove large attached context files
- Split the request into smaller turns

## Error Code Quick Reference

| Code | Meaning | Recovery |
|------|---------|----------|
| `E1001` | Validation error | Check arguments or request body |
| `E1002` | Configuration error | Run `agentheim-code doctor` |
| `E1003` | Authentication failed | Check API key and secret store |
| `E1004` | Provider error | Retry or switch provider |
| `E1005` | Policy block | Review trust mode and approval |
| `E1006` | Integration unavailable | Install missing dependency |
| `E1007` | Not found | Check IDs and run list |
| `E1008` | Run failed | Check timeline and retry |
| `E1009` | Unexpected error | Check logs and report |
| `E2001` | Session not found | Create or select a valid session |
| `E2002` | Session locked | Wait or cancel current turn |
| `E2003` | Context validation failed | Review rejected context files |
| `E2004` | Cancellation failed | Refresh and retry |
| `E2005` | Provider returned error | Check settings and retry |
| `E2006` | Unexpected runtime error | Simplify prompt and retry |
| `E2007` | Resume invalid state | Wait for completion or create new session |
| `E2008` | Request too large | Reduce prompt or context size |
| `E2009` | Network error | Check connection and retry |
| `E2010` | Filesystem error | Check disk space and permissions |
| `E2099` | Unknown error | Check timeline and retry |
