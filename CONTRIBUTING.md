# Contributing to Agentheim Code

Thank you for your interest in contributing! This document will help you get started.

## Development Setup

### Prerequisites

- Python 3.12+
- Node.js 22+
- Rust (latest stable, for Tauri desktop builds)
- Visual Studio Build Tools with C++ workload (Windows, for Tauri)

### Repository Structure

This project lives in a monorepo-adjacent setup. The main `agentheim` dependency is expected to be checked out adjacent to this repository:

```
workspace/
├── agentheim/          # https://github.com/0langa/agentheim
└── agentheim-code/     # this repository
```

### Install

```powershell
cd agentheim-code

# Install the shared agentheim dependency
pip install -e ../agentheim

# Install this package in editable mode with dev tools
pip install -e .[dev]

# Install frontend dependencies
npm --prefix apps/web install
npm --prefix apps/desktop install
```

## Running Tests

### Python

```powershell
# Run all Python tests with coverage
pytest --cov

# Linting and formatting (product-owned code only)
ruff check src/agentheim_code src/memory src/tools/shell tests/
ruff format --check src/agentheim_code src/memory src/tools/shell tests/

# Type checking (product-owned code only)
mypy src/agentheim_code src/memory src/tools/shell --follow-imports=skip
```

### Frontend

```powershell
cd apps/web

# Unit tests
npm run test

# Type check and build
npm run build
```

### Desktop (Rust)

```powershell
cd apps/desktop/src-tauri

cargo test
```

## Task Runner

A `justfile` is provided for common tasks:

```powershell
just test      # Run all tests (Python + web + Rust)
just test-py   # Python tests only
just test-web  # Frontend tests only
just test-rust # Rust tests only
just lint      # Lint and type-check product code
just fix       # Auto-fix lint/format issues
just build-web
just build-desktop
```

## Code Style

- **Python:** We use `ruff` for linting and formatting, and `mypy` for type checking.
- **TypeScript:** Follow the existing `tsconfig.json` strict settings.
- **Rust:** Standard `cargo fmt` and `cargo clippy`.

## Pull Request Process

1. Create a feature branch: `git checkout -b feat/your-feature-name`
2. Make your changes with tests
3. Ensure all linters and tests pass
4. Open a PR against `main`

## Commit Messages

Use clear, descriptive commit messages. We loosely follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add user configuration file support
fix: handle port collisions in serve_web()
docs: update API reference
```

## Questions?

Open an issue or reach out to the maintainers.
