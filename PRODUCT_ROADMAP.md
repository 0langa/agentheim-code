# Product Roadmap

Updated: 2026-05-28

This roadmap describes the current audited baseline and the next useful product
moves from here. It intentionally avoids stale phase-complete language and old
verification counts.

## Current Baseline

The repository version is currently `2.0.0`. This is the verified product
baseline after completing the audited `1.5.0` through `2.0.0` workstreams.

Confirmed product shape:

- local FastAPI backend
- browser workbench and optional Tauri shell
- onboarding with Ollama auto-detection
- provider and model management workspace with draft testing, secret rotation, import/export, and discovery/manual fallback flows
- session creation, resume, cancel, approvals, diffs, terminal results, and usage
- bounded file-context validation with previews and token estimates
- structured errors and diagnostics bundle generation
- Windows packaging scripts and CI artifact upload
- request IDs and size limits on backend endpoints
- graceful startup/shutdown hooks
- request-id propagation into runtime artifacts and diagnostics surfaces
- session cancel/resume hardening in the coder runtime
- improved diff rendering (LCS-style line diff)
- ANSI-safe terminal output
- honest command palette (unsupported commands hidden)
- incremental workspace explorer backed by paged server-side file browsing
- OpenAPI-to-TypeScript type generation pipeline
- broader Playwright smoke coverage for onboarding, provider, and streaming flows
- CI caching for Rust/cargo and Playwright browsers
- first-party OCI GenAI provider adapter with the legacy vendored bridge removed
- Python non-integration coverage gate enforced at 80% (typically ~81%)

## Verified `2.0.0` Baseline

The current baseline now includes:

- broader frontend consumption of generated OpenAPI types
- paged backend file browsing replacing the old capped client snapshot flow
- stronger session-list synchronization while active runs change state
- more complete command-palette execution for runs, timeline, and usage navigation
- broader e2e and smoke coverage around the updated workbench behavior
- stable mock-backed screenshots and user-doc polish for the current workbench surface

## What Is Working Well

- The local workbench flow exists end to end.
- The backend/API surface is broader and more mature than older docs implied.
- The product can run entirely from a Python install in browser mode.
- The Windows packaging path is present and scriptable.
- The provider layer is less inherited than before; dead vendored OCI code has been removed.

## Current Constraints

- The packaged desktop shell is not part of the Python wheel. `agentheim-code app`
  requires a built or installed Tauri binary.
- UI config and provider profile storage are intentionally split across different config systems.
- The files panel is still a flat browser rather than a fully virtualized tree.
- The diff viewer is intentionally simple and line-based.
- The command palette only directly executes a built-in subset of actions.
- Release automation is Windows-first and local-artifact oriented.

## Near-Term Priorities

### 1. Post-2.0 Contract Discipline

- broaden generated API type adoption across remaining session/view-heavy frontend surfaces
- freeze terminology across CLI, UI, API docs, and release notes
- keep the code-vs-doc truth audit strict after the `2.0.0` release

### 2. Premium Finish

- expand Playwright coverage from smoke into fuller release-grade flows
- add stable screenshots and final user-facing polish
- keep keyboard, onboarding, provider, approval, and streaming flows trustworthy

### 3. Release Sign-Off (Completed for 2.0.0)

- ✅ `docs/RELEASE_CHECKLIST.md` refreshed with fresh verification output
- ✅ browser, desktop, wheel, and installer smoke rerun from a clean tree
- ✅ release state signed off when docs and artifacts matched shipped truth

### 4. Provider And Runtime Hardening (In Progress)

- deepen request-id correlation across remaining shared logs and diagnostics
- expand structured provider/network/filesystem error coverage
- improve approval preview quality for file edits
- keep provider discovery claims strictly aligned with real implementation
- harden chat flow, session controls, resume flow, and workspace inspection
- self-heal stale provider default profiles
- repair desktop provider flow and session messaging

## Completed Workstreams

- ✅ OpenAPI-to-TypeScript type generation pipeline

## Longer-Term Opportunities

- native file watching instead of purely pull-based refresh flows
- richer provider fallback and circuit-breaker behavior
- stable visual regression checks once the UI surface is intentionally frozen
- optional benchmark suites for model-output quality
- smarter token estimation than the current fixed heuristic
- virtualized tree browsing only if the paged flat browser stops being enough

## Release Discipline

For any future release branch:

- update version numbers intentionally
- record fresh verification output in `docs/RELEASE_CHECKLIST.md`
- keep docs aligned with the actual CLI, UI, and backend surface
- do not tag, push, or publish unless explicitly requested
