# Troubleshooting

## No provider configured

Run:

```powershell
agentheim-code doctor
agentheim-code models
```

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
