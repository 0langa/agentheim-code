# Contributing to Agentheim Code

Thank you for your interest in contributing. This document covers developer
setup, checks, and repository boundaries.

## Development Setup

### Prerequisites

- Python 3.12+
- Node.js 22+
- Rust latest stable, for Tauri desktop builds
- Visual Studio Build Tools with C++ workload on Windows, for Tauri

### Repository Structure

Agentheim Code is the focused product repository. The tracked product surface is
`src/agentheim_code`, `src/memory`, `src/tools/shell`, `apps/web`, and
`apps/desktop`. Some local checkouts may contain ignored sibling Agentheim
packages under `src/`; treat those as development/runtime dependencies unless a
task explicitly targets them.

### Install

```powershell
cd agentheim-code
pip install -e .[dev]
npm --prefix apps/web install
npm --prefix apps/desktop install
```

## Running Checks

### Python

```powershell
# Non-integration tests with the CI coverage gate
pytest --cov --cov-report=term-missing --cov-fail-under=80 -m "not integration"

# Linting and formatting for product-owned code
ruff check src/agentheim_code src/memory src/tools/shell tests/
ruff format --check src/agentheim_code src/memory src/tools/shell tests/

# Type checking for product-owned code
mypy src/agentheim_code src/memory src/tools/shell --follow-imports=skip
```

### Frontend

```powershell
npm --prefix apps/web run test -- --run
npm --prefix apps/web run build
```

### Desktop

```powershell
cd apps/desktop/src-tauri && cargo test
```

## Task Runner

A `justfile` is provided for common tasks:

```powershell
just test
just test-py
just test-web
just test-rust
just lint
just fix
just build-web
just build-desktop
```

## Code Style

- Python: `ruff` for linting/formatting and `mypy` for type checking.
- TypeScript: follow the existing `tsconfig.json` strict settings.
- Rust: use standard `cargo fmt` and `cargo clippy`.

## Pull Request Process

1. Create a feature branch.
2. Make focused changes with tests when behavior changes.
3. Run the relevant checks.
4. Open a pull request against `main`.

## Commit Messages

Use clear, descriptive commit messages. Conventional Commit style is welcome:

```text
feat: add user configuration file support
fix: handle port collisions in serve_web
docs: update API reference
```

## Questions

Open an issue or reach out to the maintainers.
