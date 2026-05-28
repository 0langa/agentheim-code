# Contributing to Agentheim Code

This document covers setup, repository shape, verification, and doc-maintenance
rules for the current codebase.

## Prerequisites

- Python 3.12+
- Node.js 22+
- Rust stable for Tauri builds
- Visual Studio Build Tools with the C++ workload on Windows for Tauri packaging

## Install

```powershell
pip install -e .[dev]
npm --prefix apps/web install
npm --prefix apps/desktop install
```

## Repository Shape

### Product-first surfaces

- `src/agentheim_code`
- `apps/web`
- `apps/desktop`

### Shared runtime surfaces used directly by the product

- `src/core`
- `src/config`
- `src/providers`
- `src/workflows`
- `src/agentheim_core`
- `src/agentheim_coder_core`

Do not assume only `src/agentheim_code` matters for behavior changes. Many real
product fixes require coordinated runtime edits.

## Canonical Verification Commands

```powershell
ruff check src/agentheim_code src/workflows/coder src/config src/memory src/tools/shell tests/
ruff format --check src/agentheim_code src/workflows/coder src/config src/memory src/tools/shell tests/
mypy src/agentheim_code src/workflows/coder src/config src/memory src/tools/shell --follow-imports=skip
pytest --cov --cov-report=term-missing --cov-fail-under=80 -m "not integration"
npm --prefix apps/web run test -- --run
npm --prefix apps/web run build
npm --prefix apps/web run e2e
cd apps/desktop/src-tauri; cargo test
```

Use the release checklist in [docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md)
for packaging and release verification.

## Convenience Task Runner

The `justfile` is for convenience, not the canonical release gate. Use it when
helpful, but treat the commands above as source of truth.

Examples:

```powershell
just lint
just test
just build-web
just build-desktop
just package-beta
```

## Docs Maintenance Rules

When you change behavior, update the relevant docs in the same branch:

- [README.md](README.md)
- [docs/README.md](docs/README.md)
- [docs/USER_GUIDE.md](docs/USER_GUIDE.md)
- [docs/API_REFERENCE.md](docs/API_REFERENCE.md)
- [docs/CLI_COMMANDS.md](docs/CLI_COMMANDS.md)
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)
- [docs/PROVIDERS.md](docs/PROVIDERS.md)
- [docs/PRIVACY_SECURITY.md](docs/PRIVACY_SECURITY.md)
- [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md)

Keep docs:

- grounded in current code
- specific about which mode is supported
- honest about limits
- free of stale verification counts unless freshly rerun

## Pull Request Guidance

1. Create a feature branch.
2. Keep changes focused.
3. Add or update tests when behavior changes.
4. Run the relevant checks.
5. Update docs for any user-visible or operator-visible changes.

## Commit Messages

Conventional Commit style is welcome:

```text
feat: add provider health badges
fix: reject file previews outside workspace
docs: align install guidance with browser fallback
```
