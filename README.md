# Agentheim Code

Agentheim Code is the focused local-first coding-agent product built from
Agentheim. It keeps the coder runtime, provider setup, policy-gated tools,
approvals, diffs, terminal output, run artifacts, and BYOK privacy model in a
desktop/web app shell.

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

## Documentation

- [Product plan](PRODUCT_ROADMAP.md): current state, phases, gates, and release targets.
- [User guide](docs/USER_GUIDE.md): daily app and CLI flow.
- [CLI commands](docs/CLI_COMMANDS.md): command and slash-command reference.
- [Provider setup](docs/PROVIDERS.md): provider templates, custom endpoints, and testing.
- [Architecture](docs/ARCHITECTURE.md): product boundaries and runtime shape.
- [API reference](docs/API_REFERENCE.md): local FastAPI routes.
- [Privacy and security](docs/PRIVACY_SECURITY.md): local API, secrets, and tool policy.
- [Troubleshooting](docs/TROUBLESHOOTING.md): common setup/runtime issues.
- [Contributing](CONTRIBUTING.md): developer setup and checks.

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
# Run non-integration tests with the CI coverage gate
pytest --cov --cov-report=term-missing --cov-fail-under=80 -m "not integration"

# Lint and format product-owned code
ruff check src/agentheim_code src/memory src/tools/shell tests/
ruff format src/agentheim_code src/memory src/tools/shell tests/

# Type check
mypy src/agentheim_code src/memory src/tools/shell --follow-imports=skip
```

### Frontend

```powershell
npm --prefix apps/web run dev             # Start Vite dev server
npm --prefix apps/web run build           # Type-check and build
npm --prefix apps/web run test -- --run   # Run Vitest suite
```

### Desktop

```powershell
npm --prefix apps/desktop run build       # Build web assets + Tauri bundle
```

## Product Boundary

- Use **Agentheim Code** for daily coding-agent work.
- Use **Agentheim Full** for presets, research, document chat, marketplace,
  federation, monitoring, multimodal, and non-coder automation workflows.

The desktop app lives under `apps/desktop` and uses a Tauri shell with a
React/TypeScript frontend. The Python backend stays local-only and binds to
`127.0.0.1`.
