# Future Improvements

This file is now a verified backlog from a code-and-doc audit on `2026-05-23`.
It replaces an older speculative report that mixed real gaps with claims that
were already implemented.

## Already Implemented Or Previously Misreported

These items should not be tracked as missing anymore:

- onboarding config API exists
- Ollama local detection exists
- session resume endpoint exists
- file preview endpoint exists and performs workspace-bound path checks
- context validation endpoint exists
- bounded context bundling exists
- structured errors exist
- request ids exist on backend responses and client requests
- request size limits exist on context-heavy and message endpoints
- graceful backend lifespan hooks exist
- cancellation cleanup is better than simple session flagging
- diagnostics bundle generation exists
- provider health persistence exists
- a first-party OCI GenAI adapter exists; the older vendored bridge has been removed
- Typer shell completion support exists
- dark, light, and high-contrast themes exist
- keyboard shortcuts exist for command palette, settings, new session, and send
- modal focus trapping exists
- chat uses `aria-live`
- the Tauri config already has a CSP
- CI already uploads a Windows NSIS installer artifact

## Confirmed Improvement Opportunities

### Backend And Runtime

- propagate request ids deeper into shared runtime logs and run artifacts
- make token estimation smarter than a fixed chars-per-token heuristic
- expand structured error coverage for provider, network, and filesystem failures
- consider provider circuit breaker or fallback behavior
- unify or better abstract the current split between UI config and shared provider profile storage

### Frontend

- split `App.tsx` state into more maintainable slices
- virtualize or incrementally load the files panel for large workspaces
- replace the naive line diff algorithm
- render ANSI terminal output cleanly
- add request retry/backoff for safe API calls
- make command palette execution fully honest: either support more commands or hide them
- improve approval presentation for file edits
- improve file-panel scaling beyond the current 500-item cap

### Desktop And CI

- add Rust build cache in CI
- cache Playwright browsers in CI
- decide on a Windows signing path
- consider window-state persistence if the desktop shell becomes a heavier daily-use surface
- keep Windows-first packaging strong before adding more desktop distribution targets

### Docs And Process

- generate TypeScript API types from FastAPI/OpenAPI
- add ADRs for major architecture choices
- keep release checklist result blocks fresh instead of preserving stale numbers
- add visual regression checks only after the UI surface is more stable

## Better Alternatives To The Old Report

The earlier version of this file proposed many large, generic platform upgrades
at once. Better next steps for this repository are:

1. Fix observability and runtime correctness before adding more product surface.
2. Improve the existing workbench panels before adding new platform integrations.
3. Prefer measured, low-dependency additions over big framework jumps.

Examples:

- request ids before full OpenTelemetry
- `jsdiff`-class improvements before a full custom diff framework
- file-list scaling before adding an IDE plugin system
- API type generation before a larger frontend state-management rewrite

## Priority Order

### P1

- file panel scaling
- more honest command palette behavior
- deeper request-id propagation into logs and diagnostics

### P2

- smarter token estimation
- richer diff rendering
- ANSI terminal rendering
- config-surface cleanup
- CI caching
- OCI provider parity and broader provider regression coverage

### P3

- signed Windows builds
- window-state persistence
- model-quality benchmark suites
- deeper plugin or IDE integrations
