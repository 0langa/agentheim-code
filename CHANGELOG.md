# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

No unreleased changes.

## [1.0.0] - 2026-05-23

### Added
- Bounded context bundle validation, previews, token estimates, and runtime context blocks
- Backend cancellation, structured run errors, and session resume sanity checks
- Workspace explorer, diff review, richer terminal output, session filters, and executable command palette actions
- Provider bake-off reporting, provider health state, model recommendation metadata, and improved provider failure diagnostics
- Release automation, diagnostics bundle generation, privacy/security documentation, and manual update guidance
- 1.0 release readiness polish, diagnostics coverage, and release script hardening

### Fixed
- Diagnostics bundle typing and redaction test coverage
- JavaScript package-lock version drift before the 1.0 release sync
- Release script artifact selection so stale installers are not packaged

### Changed
- Bumped all Python, web, desktop, and Tauri package versions to `1.0.0`
- Refreshed README, user guide, API reference, release checklist, and roadmap around the 1.0 workbench experience
- Expanded Python tests to 225 non-integration tests with 82.55% coverage
- Expanded frontend tests to 39 Vitest tests plus Playwright smoke coverage

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
