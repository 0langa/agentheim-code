# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [1.5.0] - 2026-05-23

### Added
- Request context propagation with `x-request-id` header and UUID4 request IDs
- Request body size limits (256KB cap) on message and streaming endpoints with structured `E_REQUEST_TOO_LARGE` errors
- Graceful startup/shutdown lifespan hooks for the FastAPI backend
- LCS-style line diff algorithm replacing naive greedy diff in `DiffViewer`
- ANSI escape code stripping utility for safe terminal output rendering
- Workspace explorer capped at 500 files to prevent UI lock on large repositories
- Honest command palette that hides unsupported backend commands
- OpenAPI-to-TypeScript type generation script and generated `apps/web/src/generated/api-types.ts`
- Visual regression scaffolding in Playwright smoke tests with baseline screenshot capture
- ADR-0001 documenting the intentional config surface split (UI config vs provider profiles)
- ADR-0002 documenting the OpenAPI-to-TypeScript generation approach
- CI caching for Rust/cargo (`Swatinem/rust-cache@v2`) and Playwright browsers

### Changed
- `backend.py` wired with request ID middleware, lifespan, and size limit enforcement
- `desktop.py` improved graceful shutdown with safer subprocess termination
- `workflows/coder/runtime.py` improved cancellation cleanup with suppressed lock-file errors
- `App.tsx` deduplicates commands by ID to prevent palette duplicates
- `api.ts` sends `x-request-id` header on every request
- `RELEASE_CHECKLIST.md` updated with current verification commands and CI expectations
- `PRODUCT_ROADMAP.md` updated to reflect completed workstreams

### Fixed
- Command palette no longer shows duplicate "settings" command from backend
- Terminal output no longer renders raw ANSI escape codes
- Diff viewer produces cleaner add/remove/same line output

## [1.0.0] - 2026-05-23

### Added
- Bounded context bundle validation, previews, token estimates, and runtime context blocks
- Backend cancellation, structured run errors, and session resume paths
- Workspace explorer, terminal panel, diff review, usage panel, and approvals inspector
- Provider bake-off reporting, provider health state, and model metadata
- Release automation, diagnostics generation, and Windows packaging support

### Fixed
- Diagnostics bundle redaction coverage
- Release script artifact selection so stale installers are not packaged

### Changed
- Bumped all Python, web, desktop, and Tauri package versions to `1.0.0`
- Expanded the workbench documentation around the 1.0 surface

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

## [1.0.0] - 2026-05-23

### Added
- Bounded context bundle validation, previews, token estimates, and runtime context blocks
- Backend cancellation, structured run errors, and session resume paths
- Workspace explorer, terminal panel, diff review, usage panel, and approvals inspector
- Provider bake-off reporting, provider health state, and model metadata
- Release automation, diagnostics generation, and Windows packaging support

### Fixed
- Diagnostics bundle redaction coverage
- Release script artifact selection so stale installers are not packaged

### Changed
- Bumped all Python, web, desktop, and Tauri package versions to `1.0.0`
- Expanded the workbench documentation around the 1.0 surface

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
