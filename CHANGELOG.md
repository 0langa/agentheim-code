# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Desktop launcher with subprocess backend lifecycle and graceful teardown
- Free-port detection with automatic fallback when the default port is in use
- Packaged binary discovery with `AGENTHEIM_CODE_DESKTOP_BINARY` override
- Web UI provider profile and planner model selectors in the Composer
- Session model sync via PATCH `/api/coder/sessions/{id}/model`
- Universal coder runtime with verification detection and automatic repair loops
- Base64 file write support for robust binary content handling
- Windows shell executable resolution for shims like `npm.cmd`
- Token-budget tuning and compact fallback for Gemini/OCI providers
- `src/memory/` package with working-memory tier
- `src/tools/shell/` package with sandboxed shell execution
- Vendored `aictx` scanner, verifier, and context pipeline under `src/agentheim_code/vendor/`
- Pre-commit configuration for automated lint checks
- `justfile` task runner for common dev workflows

### Changed
- Expanded Python test suite to 59 tests covering CLI, desktop, backend, coder runtime, shell sandbox, and serve entry point
- Expanded frontend tests to 21 Vitest component tests
- Scoped lint/type-check to product-owned code only (`src/agentheim_code`, `src/memory`, `src/tools/shell`)

## [0.1.0] - 2026-05-21

### Added
- Initial release of Agentheim Code
- Typer-based CLI with `app`, `coder`, `models`, `doctor`, `runs`, `version`, and `completions` commands
- FastAPI backend serving local-only Agentheim Coder runtime
- Tauri v2 desktop shell with React/TypeScript frontend
- Explicit web fallback via `agentheim-code app --web`
- Command palette with keyboard shortcuts (`Ctrl+K`, `Ctrl+P`)
- Session management (create, resume, list)
- Mode selection: ask, plan, code, review, fix, docs, test
- Provider support through standalone shared-runtime code inside Agentheim Code
- Policy-gated tool approvals for risky actions
- User configuration file (`config.toml`) with platform-aware paths
- Structured logging throughout Python backend
- Workspace input validation
- Port collision handling with automatic fallback
- Production desktop launch fails fast when the packaged binary is missing
- Restrictive Content Security Policy for desktop app
- Comprehensive test suite (Python ≥82% coverage, frontend Vitest, Rust cargo test)
- CI/CD pipeline with lint, type check, test, and coverage gates
- Developer tooling: ruff, mypy, pytest-cov
