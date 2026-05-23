# Release Checklist

Use this file as a release template. Do not leave old verification numbers in
place. Replace every placeholder with fresh command output for the release you
are preparing.

## Scope And Intent

- current repo version: `1.5.0`
- primary packaged target: Windows NSIS installer
- Python wheel remains part of the release surface
- no tag, push, or hosted release creation unless explicitly requested

## Canonical Verification Commands

Run these fresh:

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
powershell -ExecutionPolicy Bypass -File scripts/release.ps1 -Version 1.0.0
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
- provider wizard can test and save a provider
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

Fill this section for the actual release:

- date:
- branch:
- version:
- `ruff check`:
- `ruff format --check`:
- `mypy`:
- `pytest`:
- `npm --prefix apps/web run test -- --run`:
- `npm --prefix apps/web run build`:
- `npm --prefix apps/web run e2e`:
- `cargo test`:
- `python -m build --wheel`:
- `scripts/package-beta.ps1`:
- `scripts/release.ps1 -Version <version>`:
- manual browser smoke:
- packaged desktop smoke:

## Distribution Notes

- Windows is the primary packaged desktop target today
- macOS/Linux are currently best served by the Python package plus browser mode
- updates are manual
- unsigned Windows installers may trigger reputation warnings
