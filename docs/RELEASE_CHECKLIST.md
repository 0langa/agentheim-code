# Release Checklist

## Required Verification

Run fresh before claiming release readiness:

```powershell
ruff check src/agentheim_code src/memory src/tools/shell tests/
ruff format --check src/agentheim_code src/memory src/tools/shell tests/
mypy src/agentheim_code src/memory src/tools/shell --follow-imports=skip
pytest --cov --cov-report=term-missing --cov-fail-under=80 -m "not integration"
npm --prefix apps/web run test -- --run
npm --prefix apps/web run build
npm --prefix apps/web run e2e
cd apps/desktop/src-tauri; cargo test
python -m build --wheel
npm --prefix apps/desktop run build
```

## Windows Beta Packaging

Preferred local packager:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/package-beta.ps1
```

It performs:

- web build
- Windows Tauri build
- wheel build
- clean wheel smoke in a temporary venv
- NSIS installer artifact lookup

## CI Expectations

- Python job uses the non-integration pytest coverage gate.
- Web job runs unit tests, build, and Playwright smoke.
- `desktop-rust` uploads `agentheim-code-windows-installer`.

## Manual Checks

- onboarding appears on fresh config
- existing configured user lands in app
- `@` context picker can add and remove files
- approvals are readable and actionable in the GUI
- dark, light, high-contrast themes are usable
- keyboard flow covers new session, settings, send, modal close, approvals
- `agentheim-code app --workspace .` launches packaged shell with local backend
- docs match actual CLI and UI labels

## Beta Notes

- Windows is primary packaging target for `0.5.0`.
- App updates are manual. No auto-updater is bundled.
- Unsigned beta builds may trigger Windows reputation warnings.
