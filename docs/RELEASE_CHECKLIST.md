# Release Checklist

Use this file as a release template. Do not leave old verification numbers in
place. Replace every placeholder with fresh command output for the release you
are preparing.

## Scope And Intent

- current repo version: `2.0.0`
- primary packaged target: Windows NSIS installer
- Python wheel remains part of the release surface
- no tag, push, or hosted release creation unless explicitly requested

## Canonical Verification Commands

Run these fresh:

```powershell
ruff check src/agentheim_code src/workflows/coder src/config src/memory src/tools/shell tests/
ruff format --check src/agentheim_code src/workflows/coder src/config src/memory src/tools/shell tests/
mypy src/agentheim_code src/workflows/coder src/config src/memory src/tools/shell --follow-imports=skip
pytest --cov --cov-report=term-missing --cov-fail-under=80 -m "not integration"
npm --prefix apps/web run test -- --run
npm --prefix apps/web run build
npm --prefix apps/web run e2e
cd apps/desktop/src-tauri; cargo test
python -m build --wheel
```

## Packaging Commands

### Preferred local packaging pass

```powershell
powershell -ExecutionPolicy Bypass -File scripts/package-beta.ps1
```

This currently performs:

- clean prior build artifacts
- web build
- Windows desktop build
- wheel build
- clean-wheel smoke test in a temporary virtual environment
- NSIS installer lookup

### Local release artifact staging

```powershell
powershell -ExecutionPolicy Bypass -File scripts/release.ps1 -Version 2.0.0
```

This script is Windows-only and currently stages local artifacts only. It does
not create tags, publish to PyPI, or push to GitHub.

## CI Expectations

- Python job runs lint, format, mypy, non-integration pytest coverage, and wheel build
- Web job runs unit tests, build, and Playwright smoke
- CI caches:
  - pip dependencies via `actions/cache@v4` on `~/.cache/pip`
  - npm dependencies via `actions/cache@v4` on `~/.npm`
  - Playwright browsers via `actions/cache@v4` on `~/.cache/ms-playwright`
  - Rust/cargo dependencies via `Swatinem/rust-cache@v2`
- `desktop-rust` uploads:
  - `agentheim-code-windows-installer`
  - `agentheim-code-wheel`

## Manual Product Checks

- fresh config shows onboarding
- existing configured user lands in the main workbench
- Ollama detection path is visible when Ollama is running
- provider management workspace can test, save, discover, and import providers
- draft provider test works before save
- provider secret rotation works from the workspace
- provider profile export/import works from the workspace
- unsupported discovery paths show a clear manual-entry fallback
- `@` context search can add and remove files
- context preview shows token estimates and rejected files
- stop cancels an active run
- structured errors are readable in the alert area
- approvals are readable and actionable
- diff copy works
- terminal output expand/collapse and copy work
- files panel preview/copy/attach work
- runs filter works by session id, status, or mode
- dark, light, and high-contrast themes all apply correctly
- keyboard flow covers command palette, settings, new session, send, and modal close
- browser mode launches from a Python-only install
- packaged desktop shell launches only from an installed or built binary
- diagnostics bundle is generated and redacted
- docs match actual CLI commands and UI labels

## Release Record

_Last verified: 2026-05-28_

- branch: `main`
- version: `2.0.0`
- `ruff check`: All checks passed
- `ruff format --check`: 99 files already formatted
- `mypy`: Success, no issues found in 36 source files
- `pytest`: 346 passed, 3 deselected, 81.57% coverage (coverage gate is 80%)
- `npm --prefix apps/web run test -- --run`: 14 test files, 95 tests passed
- `npm --prefix apps/web run build`: passed
- `npm --prefix apps/web run e2e`: 10 passed (chromium)
- `cargo test`: 2 passed in `apps/desktop/src-tauri/src/main.rs`
- `python -m build --wheel`: passed; built `agentheim_code-2.0.0-py3-none-any.whl`
- `scripts/package-beta.ps1`: not run in this baseline cleanup
- manual browser smoke: not run in this baseline cleanup
- built desktop shell smoke: not run in this baseline cleanup
- provider-management live smoke: not run in this baseline cleanup; mocked Playwright provider-management lifecycle passed
- wheel contents smoke: not run in this baseline cleanup

### Unverified / Deferred
- `scripts/package-beta.ps1`
- manual browser smoke
- built desktop shell smoke
- provider-management live smoke
- wheel contents smoke
- `scripts/release.ps1` local staging flow

## Windows Signing Strategy

Agentheim Code installers are currently unsigned. To sign future releases:

1. Obtain a Windows code-signing certificate (OV or EV)
2. Export certificate thumbprint and set `TAURI_SIGNING_PRIVATE_KEY` / `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` env vars
3. Tauri v2 will sign the NSIS installer automatically during `npm run tauri build`
4. Document the signed thumbprint in release notes so users can verify

Until signing is configured, the installer is built unsigned and Windows SmartScreen may show a reputation warning. Users can verify integrity via the SHA256 checksum published with each release.

## Distribution Notes

- Windows is the primary packaged desktop target today
- macOS/Linux are currently best served by the Python package plus browser mode
- updates are manual: `pip install --upgrade agentheim-code` or reinstall the Windows installer
- unsigned Windows installers may trigger reputation warnings; verify with SHA256 checksums
- settings can be migrated between installs with `agentheim-code config export` and `agentheim-code config import`
