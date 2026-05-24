# Product Roadmap

Updated: 2026-05-24

This roadmap describes the current audited baseline and the next useful product
moves from here. It intentionally avoids stale phase-complete language and old
verification counts.

For the full forward implementation program, see [PLAN_2.0.0.md](PLAN_2.0.0.md).

## Current Baseline

The repository version is currently `1.9.0`. This is the verified product
baseline after completing the audited `1.6.0` through `1.9.0` workstreams.

Confirmed product shape:

- local FastAPI backend
- browser workbench and optional Tauri shell
- onboarding with Ollama auto-detection
- provider wizard with test/create/delete flows
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
- workspace explorer capped at 500 files with incremental client-side batching
- OpenAPI-to-TypeScript type generation pipeline
- broader Playwright smoke coverage for onboarding, provider, and streaming flows
- CI caching for Rust/cargo and Playwright browsers
- first-party OCI GenAI provider adapter with the legacy vendored bridge removed
- Python non-integration coverage gate proven at 90%+

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
- The files panel loads the file tree and filters client-side.
- The diff viewer is intentionally simple and line-based.
- The command palette only directly executes a built-in subset of actions.
- Release automation is Windows-first and local-artifact oriented.

## Near-Term Priorities

### 1. 2.0.0-rc1 Contract Freeze

- broaden generated API type adoption across the frontend
- freeze terminology across CLI, UI, API docs, and release notes
- tighten the code-vs-doc truth audit before any `2.0.0` claim

### 2. Premium Finish

- expand Playwright coverage from smoke into release-grade flows
- add stable screenshots and final user-facing polish
- keep keyboard, onboarding, provider, approval, and streaming flows trustworthy

### 3. Release Sign-Off

- refresh `docs/RELEASE_CHECKLIST.md` with fresh verification output only
- rerun browser, desktop, wheel, and installer smoke from a clean tree
- sign off the release state only when docs and artifacts match the shipped truth

## Longer-Term Opportunities

- native file watching instead of purely pull-based refresh flows
- richer provider fallback and circuit-breaker behavior
- ✅ OpenAPI-to-TypeScript type generation pipeline
- stable visual regression checks once the UI surface is intentionally frozen
- optional benchmark suites for model-output quality

## Release Discipline

For any future release branch:

- update version numbers intentionally
- record fresh verification output in `docs/RELEASE_CHECKLIST.md`
- keep docs aligned with the actual CLI, UI, and backend surface
- do not tag, push, or publish unless explicitly requested
