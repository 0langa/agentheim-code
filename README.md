# Agentheim Code

Agentheim Code is a local-first coding assistant with a FastAPI backend, React
web UI, and Tauri desktop shell. It is built for one fast path:

1. Open app.
2. Choose workspace.
3. Connect provider.
4. Send prompt.
5. Review streamed output and approvals.

## Install

### Windows beta path

Current beta packaging is Windows-first and produces:

- a Python wheel for the local backend and CLI
- an NSIS desktop-shell installer artifact from Tauri

Build both locally:

```powershell
pip install -e ".[dev]"
npm --prefix apps/web install
npm --prefix apps/desktop install
powershell -ExecutionPolicy Bypass -File scripts/package-beta.ps1
```

Quick beta launch from this checkout:

```powershell
agentheim-code app --workspace .
```

### Web fallback

If you want browser-only UI instead of the desktop shell:

```powershell
agentheim-code app --workspace . --web
```

## First Run

On a fresh config, Agentheim Code opens onboarding first.

1. Choose workspace.
2. Let it auto-detect local Ollama if available.
3. Or open the provider wizard and add an API provider.
4. Start first session.

If you skip onboarding, the app stays usable and keeps provider setup available
 from Settings.

## Provider Setup

- Local auto-detection currently targets Ollama at `http://localhost:11434/v1`.
- Cloud/API providers use the existing provider wizard.
- You can test a provider before saving it.

CLI check:

```powershell
agentheim-code doctor
agentheim-code models
```

## First Prompt

In the composer:

- choose mode: `ask`, `plan`, `code`, `review`, `fix`, `docs`, `test`
- choose trust: `read_only`, `ask`, or `workspace`
- optionally attach file context with `@`
- send with `Ctrl+Enter`

Responses stream live. Code blocks render with syntax highlighting and copy
actions.

## Approvals

Risky actions stay visible in the Approvals inspector.

- Shell approvals show exact command and working directory.
- File approvals show target path and pending content preview.
- Grant or deny without leaving the main UI.

Trust modes:

- `read_only`: inspect only
- `ask`: pause for risky actions
- `workspace`: allow workspace edits under policy

## Docs

- [User guide](docs/USER_GUIDE.md)
- [Provider setup](docs/PROVIDERS.md)
- [API reference](docs/API_REFERENCE.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Release checklist](docs/RELEASE_CHECKLIST.md)
- [Product roadmap](PRODUCT_ROADMAP.md)

## Development

```powershell
ruff check src/agentheim_code src/memory src/tools/shell tests/
ruff format --check src/agentheim_code src/memory src/tools/shell tests/
mypy src/agentheim_code src/memory src/tools/shell --follow-imports=skip
pytest --cov --cov-report=term-missing --cov-fail-under=80 -m "not integration"
npm --prefix apps/web run test -- --run
npm --prefix apps/web run build
npm --prefix apps/web run e2e
cd apps/desktop/src-tauri; cargo test
```
