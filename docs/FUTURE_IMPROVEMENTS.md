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
- OpenAPI-to-TypeScript generation exists and is consumed directly for config, command, provider-detection, and file-browser surfaces
- provider health persistence exists
- a first-party OCI GenAI adapter exists; the older vendored bridge has been removed
- a paged backend file browser exists; the old 500-item client cap is gone
- the command palette now directly supports runs, timeline, files, terminal, usage, settings, retry, stop, approvals, and new-session flows
- Typer shell completion support exists
- dark, light, and high-contrast themes exist
- keyboard shortcuts exist for command palette, settings, new session, and send
- modal focus trapping exists
- chat uses `aria-live`
- the Tauri config already has a CSP
- CI already uploads a Windows NSIS installer artifact

## Confirmed Improvement Opportunities

### Backend And Runtime

- finish request-id correlation across remaining shared core/provider logging paths
- make token estimation smarter than a fixed chars-per-token heuristic
- expand structured error coverage for provider, network, and filesystem failures
- consider provider circuit breaker or fallback behavior
- unify or better abstract the current split between UI config and shared provider profile storage

### Frontend

- split `App.tsx` state into more maintainable slices
- graduate the flat paged files browser into a virtualized tree view if larger repositories demand it
- move beyond the current line-based diff viewer only if richer structured diffs materially improve review quality
- preserve useful terminal formatting if runtime output starts relying on more than ANSI stripping
- keep the command palette exhaustive for the supported workbench surface as new actions are added
- improve approval presentation for file edits

### Desktop And CI

- add Rust build cache in CI
- cache Playwright browsers in CI
- decide on a Windows signing path
- consider window-state persistence if the desktop shell becomes a heavier daily-use surface
- keep Windows-first packaging strong before adding more desktop distribution targets

### Docs And Process

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
- tree-virtualization only if the paged flat browser stops being enough
- `jsdiff`-class improvements before a full custom diff framework
- request/type surface cleanup before a larger frontend state-management rewrite

## Priority Order

### P1

- config-surface cleanup
- deeper request-id correlation across shared logs and diagnostics
- approval preview quality

### P2

- smarter token estimation
- richer diff presentation where line-based review becomes limiting
- stronger file-browser ergonomics for very large repos
- CI caching
- OCI provider parity and broader provider regression coverage

### P3

- signed Windows builds
- window-state persistence
- model-quality benchmark suites
- deeper plugin or IDE integrations
