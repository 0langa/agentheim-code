# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [2.0.0] - 2026-05-26

### Added
- Paged workspace browser endpoint for incremental file loading in the web workbench
- Reproducible docs screenshot pipeline via `npm --prefix apps/web run docs:screenshots`
- Dedicated Providers & Models management workspace with profile import/export, draft account testing, secret rotation, discovery, and manual fallback flows
- Draft provider-account test route for unsaved account verification before save
- Focused provider-management backend, frontend, and Playwright coverage

### Changed
- The workbench file explorer now loads files from the backend in pages instead of browsing one capped client-side list
- Frontend request helpers now preserve `x-request-id` when custom headers are added
- Command palette support now includes Runs, Timeline, and Usage navigation
- Session and session-view frontend types now align more closely with generated OpenAPI contracts
- User-facing docs now include stable workbench screenshots and frozen `New session` terminology
- Onboarding provider setup now reuses the same provider-management surface instead of a separate legacy form path
- Provider capability/discovery metadata is now stricter about manual-only and hybrid providers

### Fixed
- Session list state now stays in sync more reliably when the active session changes status
- Generated API contract is consumed more directly for config, command, provider-detection, and file-browser types
- Workspace file search now ignores stale out-of-order page responses instead of letting older results overwrite newer searches
- Full Playwright coverage now includes files paging/preview and usage-plus-runs-filter flows
- Draft provider tests now exercise the current unsaved account state instead of only persisted account ids
- Provider secret rotation is now wired through the main UI instead of being silently ignored

## [1.9.0] - 2026-05-24

### Added
- Diagnostics bundle now includes redacted config, provider health, and recent session summaries
- CLI support commands for diagnostics export, provider connection testing, config export/import, and version checks
- Broader Playwright smoke coverage for keyboard flow, onboarding, provider wizard, and streaming session behavior
- Relative-time display helpers for inspector and terminal surfaces

### Changed
- Runtime request IDs now propagate deeper into run artifacts, cancellation paths, and diagnostics surfaces
- Session cancel/resume behavior is more explicit and resilient in the coder runtime
- Workspace explorer now batches large file lists client-side while preserving the backend safety cap
- Approval, diff, terminal, and inspector panels have been refined for daily-use review flows
- Release automation and release docs were relabeled to the verified `1.9.0` baseline instead of the premature `2.0.0` claim

### Fixed
- Playwright smoke mocks now preserve realistic session/view state through onboarding, provider creation, and streaming flows
- Version drift across Python, web, desktop, Tauri, tests, and release docs has been reconciled to `1.9.0`
- Removed a debug-only Playwright spec that did not belong in the baseline

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
- ADR-0001 documenting the intentional config surface split (UI config vs provider profiles)
- ADR-0002 documenting the OpenAPI-to-TypeScript generation approach
- CI caching for Rust/cargo (`Swatinem/rust-cache@v2`) and Playwright browsers
- First-party OCI GenAI provider adapter with focused provider tests

### Changed
- `backend.py` wired with request ID middleware, lifespan, and size limit enforcement
- `backend.py` now reports the source-tree/package version consistently through `/api/health`
- `desktop.py` improved graceful shutdown with safer subprocess termination
- `workflows/coder/runtime.py` improved cancellation cleanup with suppressed lock-file errors
- `App.tsx` deduplicates commands by ID to prevent palette duplicates
- `api.ts` sends `x-request-id` header on every request
- Version-synced Python, web, desktop, and Tauri surfaces to `1.5.0`
- `RELEASE_CHECKLIST.md` updated with current verification commands and CI expectations
- `PRODUCT_ROADMAP.md` updated to reflect completed workstreams
- wheel builds now clear stale `build/` Python output before packaging

### Fixed
- Command palette no longer shows duplicate "settings" command from backend
- Terminal output no longer renders raw ANSI escape codes
- Diff viewer produces cleaner add/remove/same line output
- Readiness guidance no longer points to nonexistent inherited `agentheim` commands
- plain wheel builds no longer include deleted vendored/runtime files from stale build output

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
