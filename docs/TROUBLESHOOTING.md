# Troubleshooting

## No provider configured

Run:

```powershell
agentheim setup
agentheim-code doctor
```

## Desktop app does not launch

Use the web fallback:

```powershell
agentheim-code app --workspace . --web
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
