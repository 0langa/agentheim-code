# Agentheim Code

**Agentheim Code is the focused coding-agent product built from Agentheim.**

It keeps the Coder runtime, provider setup, policy-gated tools, approvals, diffs,
terminal output, run artifacts, and local-first privacy model while leaving the
broader automation presets in Agentheim Full.

## Install

Developer install from this checkout:

```powershell
cd agentheim-code
pip install -e ".[dev]"
npm --prefix apps/web install
npm --prefix apps/desktop install
```

## Quick Start

```powershell
agentheim-code doctor
agentheim-code models
agentheim-code coder --workspace .
agentheim-code app --workspace .
```

`agentheim-code` is standalone. It carries the coder runtime it needs inside this
repo and stores coder artifacts under `.ai-team/runs/<session-id>/`.

## App Launch Modes

- `agentheim-code app` launches the packaged Tauri desktop binary. If no binary
  is installed or discoverable, it fails with build and fallback instructions.
- `agentheim-code app --web` starts the local FastAPI/browser UI fallback.
- `agentheim-code app --dev` runs source-tree Tauri dev mode and requires Node,
  Rust, and the repository checkout.

## CLI Commands

| Command | Description |
|---------|-------------|
| `app` | Launch the desktop or web app |
| `coder` | Persistent local coding sessions |
| `models` | List configured provider profiles and models |
| `doctor` | Check local readiness |
| `runs` | List recent run artifacts |
| `version` | Show installed version |
| `completions` | Generate shell completion scripts |

## Development

### Python

```powershell
# Run tests with coverage
pytest --cov

# Lint and format product-owned code
ruff check src/agentheim_code src/memory src/tools/shell tests/
ruff format src/agentheim_code src/memory src/tools/shell tests/

# Type check
mypy src/agentheim_code src/memory src/tools/shell --follow-imports=skip
```

### Frontend

```powershell
cd apps/web
npm run dev      # Start Vite dev server
npm run build    # Type-check and build
npm run test     # Run Vitest suite
```

### Desktop

```powershell
cd apps/desktop
npm run build    # Build web assets + Tauri bundle
```

## Product Boundary

- Use **Agentheim Code** for daily coding-agent work.
- Use **Agentheim Full** for presets, research, document chat, marketplace,
  federation, monitoring, multimodal, and non-coder automation workflows.

The premium desktop app lives under `apps/desktop` and uses a Tauri shell with a
React/TypeScript frontend. The Python backend stays local-only and binds to
`127.0.0.1`.
