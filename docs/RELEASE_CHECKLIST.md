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

## Windows Packaging

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

Release automation script:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/release.ps1 -Version 1.0.0
```

It performs:

- web build
- desktop build
- wheel build
- installer copy into `dist/`
- checksum generation
- release notes generation

## Last Verified For 1.0.0

Date: 2026-05-23

- `ruff check src/agentheim_code src/memory src/tools/shell tests/`: passed
- `ruff format --check src/agentheim_code src/memory src/tools/shell tests/`: passed
- `mypy src/agentheim_code src/memory src/tools/shell --follow-imports=skip`: passed
- `pytest --cov --cov-report=term-missing --cov-fail-under=80 -m "not integration"`: 225 passed, 3 deselected, 82.55% coverage
- `npm --prefix apps/web run test -- --run`: 39 passed
- `npm --prefix apps/web run build`: passed
- `npm --prefix apps/web run e2e`: 2 passed
- `cd apps/desktop/src-tauri; cargo test`: 1 passed
- `powershell -ExecutionPolicy Bypass -File scripts/package-beta.ps1 -PythonExe python`: passed with clean wheel smoke
- `powershell -ExecutionPolicy Bypass -File scripts/release.ps1 -Version 1.0.0`: passed with wheel, Windows installer copy, checksums, and release notes
- Browser visual smoke: passed for the main workbench surface

## CI Expectations

- Python job uses the non-integration pytest coverage gate.
- Web job runs unit tests, build, and Playwright smoke.
- `desktop-rust` uploads `agentheim-code-windows-installer` and wheel artifacts with checksums.

## Manual Checks

- onboarding appears on fresh config
- existing configured user lands in app
- `@` context picker can add and remove files
- context previews show token estimates and rejections
- stop cancels the backend session
- structured errors show codes and recovery actions
- approvals are readable and actionable in the GUI
- diff viewer shows before/after with copy
- terminal panel shows collapsible output with copy
- workspace explorer shows file tree with changed badges
- command palette executes new session, settings, approvals, files, terminal, retry, stop
- session search filters by status and mode
- dark, light, high-contrast themes are usable
- keyboard flow covers new session, settings, send, modal close, approvals
- `agentheim-code app --workspace .` launches packaged shell with local backend
- `agentheim-code diagnostics` produces a redacted bundle
- docs match actual CLI and UI labels

## Distribution

- Windows is the primary packaging target for 1.0.
- macOS/Linux are supported via pip install.
- App updates are manual: `pip install --upgrade agentheim-code`.
- Unsigned builds may trigger Windows reputation warnings.
