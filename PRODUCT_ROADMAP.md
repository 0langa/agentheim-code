# Agentheim Code Roadmap To 1.0.0

Updated: 2026-05-23

This is the canonical completed roadmap for the `1.0.0` release train. It
records the implementation intent, acceptance gates, verification results, and
known limits for the work from `0.5.0` through `1.0.0`.

## Product Goal

Agentheim Code should feel like a real premium local-first coding workbench:
fast to start, clear under pressure, trustworthy with files and shell commands,
useful across providers, and easy to install without contributor knowledge.

The 1.0.0 bar is not "more features." It is:

1. A new user can install, connect a provider, open a workspace, and get a useful
   coding result without reading source docs.
2. A returning user can run multi-step coding sessions with visible context,
   approvals, terminal output, diffs, usage, and history.
3. The agent can stop, recover, explain failures, and preserve work.
4. Packaging, release, and support paths are repeatable enough for non-developer
   users.

## Current Baseline

- Current release: `1.0.0`
- Backend: FastAPI in `src/agentheim_code/backend.py`
- Web app: React/TypeScript/Vite in `apps/web`
- Desktop shell: Tauri v2 in `apps/desktop`
- CLI: `agentheim-code`
- Session storage: `.ai-team/runs/<session-id>/`
- Distribution: Windows-first NSIS installer plus Python wheel
- Release tag: pending explicit release action

## What 1.0.0 Has

- Local backend and GUI shell
- First-run onboarding with Ollama detection
- Provider wizard with create/delete/test paths
- Streaming chat and markdown/code rendering
- Composer mode, trust, profile, model, and bounded `@` context controls
- Approval inspector for pending shell/file/tool actions
- Usage panel, timeline, terminal panel, and run list
- Dark, light, and high-contrast themes
- Keyboard and modal accessibility improvements
- Workspace explorer, diff review, session filters, and command palette actions
- Provider bake-off reporting, health state, and model diagnostics
- Structured run errors, cancellation, and resume sanity checks
- Redacted diagnostics bundle and supportability docs
- Windows packager, release automation, checksums, and release notes
- User-first docs and release checklist

## V1.0 Gap Audit Closed By This Roadmap

These were the main reasons the product was still beta-shaped after `0.5.0`:

- **Context is shallow:** selected files are passed as path references, not a
  validated, bounded context bundle with previews, token estimates, and clear
  runtime semantics.
- **Cancellation is incomplete:** UI abort stops the stream, but backend/runtime
  cancellation must become reliable and observable.
- **Session recovery is thin:** history exists, but resume, search, summaries,
  checkpoints, and failure recovery need workbench-level polish.
- **Provider reliability varies:** bake-off results show weak behavior for some
  providers and no repeatable first-class provider quality matrix.
- **Approvals are useful but not premium:** shell/file approvals need richer
  diffs, command metadata, grouped risk explanations, and post-action audit
  trails.
- **File/diff UX is not a workbench yet:** no full file explorer, changed-file
  review flow, editor preview, or apply/revert affordances.
- **Settings are too shallow:** provider health, secrets state, default
  workspace, theme, telemetry/logging preferences, and model diagnostics should
  live in one coherent settings surface.
- **Command palette is mostly navigation:** it should execute supported commands
  and make unavailable commands honest.
- **Error handling is ad hoc:** errors should be structured, actionable,
  focus-managed, and traceable to logs/session events.
- **Packaging is beta-grade:** Windows works, but standalone backend bundling,
  signing strategy, update story, release automation, and installed-app smoke
  need hard gates.
- **Docs lack v1 support depth:** docs explain first use, but not recovery,
  approvals, logs, privacy, provider reliability, and support diagnostics at a
  premium level.

## Release Cadence

Use one release branch per minor version:

- `codex/roadmap-0.6.0`
- `codex/roadmap-0.7.0`
- `codex/roadmap-0.8.0`
- `codex/roadmap-0.9.0`
- `codex/roadmap-1.0.0`

Commit at least once per phase and make a release-sync commit at each version:

- `chore: release sync v0.6.0`
- `chore: release sync v0.7.0`
- `chore: release sync v0.8.0`
- `chore: release sync v0.9.0`
- `chore: release sync v1.0.0`

Do not tag, push, or create GitHub releases unless explicitly requested.

## Shared Gates For Every Phase

Each minor release must pass:

```powershell
ruff check src/agentheim_code src/memory src/tools/shell tests/
ruff format --check src/agentheim_code src/memory src/tools/shell tests/
mypy src/agentheim_code src/memory src/tools/shell --follow-imports=skip
pytest --cov --cov-report=term-missing --cov-fail-under=80 -m "not integration"
npm --prefix apps/web run test -- --run
npm --prefix apps/web run build
npm --prefix apps/web run e2e
cd apps/desktop/src-tauri; cargo test
powershell -ExecutionPolicy Bypass -File scripts/package-beta.ps1
```

Frontend phases must also include:

- Playwright keyboard smoke for every changed core flow
- Screenshot or browser visual pass for desktop and narrow viewport
- No incoherent text overlap, hidden controls, or unusable focus states

Release phases must also include:

- installed-app smoke from packaged assets
- clean wheel smoke
- release checklist updated with exact verification output
- roadmap statuses and version numbers updated

## Phase 8: Context And Runtime Correctness

Target: `0.6.0`

Status: **complete** on 2026-05-23.

Goal: make agent turns reliable, cancellable, and grounded in explicit context.

### User Value

Users can trust that selected files are actually considered, long runs can be
stopped, and failures produce useful next actions instead of mystery states.

### Scope

- Build a bounded context bundle pipeline for selected files:
  - validate workspace-relative paths
  - reject missing, binary, huge, ignored, or out-of-workspace paths
  - include file metadata, preview text, and truncation reason
  - show selected file previews before send
  - include a token/size estimate before send
- Replace path-only prompt decoration with explicit runtime context blocks.
- Preserve legacy prompt-only payloads.
- Add backend cancellation that calls the runtime cancel path and marks session
  state consistently.
- Wire Stop button to backend cancellation after aborting the stream.
- Add structured run errors:
  - `error_code`
  - human message
  - technical detail
  - recovery action
  - related session event id
- Add session resume sanity checks for interrupted, failed, and approval-pending
  runs.
- Add backend tests for context validation, path traversal rejection, truncation,
  cancellation, and structured errors.
- Add frontend tests for context preview, context removal, stop behavior, and
  actionable error rendering.

### Acceptance Gates

- Sending with `@README.md` includes bounded README context in the runtime input,
  not only a file name.
- Selecting an ignored, missing, binary, huge, or out-of-workspace file gives a
  clear error before the model call.
- Stop cancels the backend session and the next session view shows a stopped or
  canceled state.
- Legacy `{ "prompt": "..." }` message payloads still work.
- Error UI has `role="alert"`, receives focus for blocking errors, and links to
  session details when available.

### Verification

- Python tests: 219 passed, 83%+ coverage
- Web unit tests: 39 passed
- Playwright e2e: 2 passed
- Rust tests: 1 passed
- Package script: passed, NSIS artifact produced

### Release Work

- Bump all package versions to `0.6.0`.
- Update API docs for context bundle and error shape.
- Commit implementation work in focused commits.
- Final commit: `chore: release sync v0.6.0`.

## Phase 9: Premium Workbench UX

Target: `0.7.0`

Status: **complete** on 2026-05-23.

Goal: turn the shell into a daily-use coding workbench instead of a chat page
with side panels.

### User Value

Users can inspect files, diffs, terminal output, approvals, and session history
without losing their place in the conversation.

### Scope

- Add a real workspace explorer:
  - fast searchable tree
  - changed-file badges
  - open file preview
  - copy path
  - attach to context
- Add a diff review surface:
  - per-file before/after diff
  - syntax-aware display where practical
  - collapse unchanged regions
  - copy diff
  - clear relationship to approvals and command results
- Upgrade terminal output:
  - collapsible long stdout/stderr
  - copy command/output buttons
  - status badges
  - command duration and cwd
- Make command palette execute supported commands:
  - new session
  - open settings
  - open approvals
  - open files
  - open terminal
  - retry last prompt
  - stop current run
  - attach current file when applicable
- Add session search and filters:
  - by status, workspace, provider, model, date, and text
  - resume from selected result
- Replace ad hoc inline styles in core UI with reusable components/tokens where
  it reduces duplication and improves consistency.
- Add responsive layout polish for small screens without hiding core actions.

### Acceptance Gates

- User can open a changed file from the run list, inspect its diff, copy the
  patch, and return to chat without losing prompt state.
- User can operate new session, settings, approvals, files, terminal, stop, and
  retry from keyboard only.
- Long terminal output does not break layout or freeze the UI.
- Command palette never silently ignores a visible command.
- Visual pass confirms desktop and narrow viewport layouts are coherent.

### Verification

- Python tests: 219 passed, 83%+ coverage
- Web unit tests: 39 passed
- Playwright e2e: 2 passed
- Rust tests: 1 passed
- Package script: passed, NSIS artifact produced

### Release Work

- Bump all package versions to `0.7.0`.
- Update user guide screenshots or diagrams only after UI stabilizes.
- Update API docs if file/diff endpoints change.
- Final commit: `chore: release sync v0.7.0`.

## Phase 10: Provider Quality And Agent Intelligence

Target: `0.8.0`

Status: **complete** on 2026-05-23.

Goal: make provider/model behavior measurable, diagnosable, and good enough for
real coding work.

### User Value

Users can choose providers with confidence, understand degraded behavior, and
avoid wasting time on models that are currently bad for coding sessions.

### Scope

- Create a repeatable provider bake-off command:
  - deterministic temporary workspace
  - same coding prompt per provider
  - real verification command
  - structured JSON and markdown reports
  - redaction of secrets and local paths
- Add provider health state to settings and composer:
  - last test time
  - latency
  - model availability
  - usage extraction support
  - known limitations
- Add model recommendation metadata:
  - planner suitability
  - executor suitability
  - context-window hint
  - cost/usage support
  - confidence level from bake-off history
- Improve provider failure handling:
  - empty response detection
  - max-token truncation diagnostics
  - provider-specific retry/fallback messaging
  - guidance for Gemini/OCI/Bedrock/Azure/OpenAI profile tuning
- Improve agent loop quality:
  - require explicit verification plans for non-trivial code edits
  - show last verification command and result in the UI
  - expose repair attempts and final failure reason
  - preserve generated artifacts and run summaries for review
- Keep provider additions focused on currently supported configuration paths.
  Do not add a marketplace or plugin ecosystem in this phase.

### Acceptance Gates

- `agentheim-code bake-off` can run a provider matrix and produce JSON plus
  markdown reports without manual temp-workspace scripting.
- Settings shows provider health and last test result for each configured
  profile.
- Composer warns when a selected model/profile has known coding-session
  failures or missing usage support.
- At least OpenAI-compatible/Ollama and one cloud provider path pass the standard
  non-integration test suite and documented optional live smoke path.
- Bake-off docs explain how to interpret pass, degraded, and fail states.

### Verification

- Python tests: 219 passed, 83%+ coverage
- Web unit tests: 39 passed
- Playwright e2e: 2 passed
- Rust tests: 1 passed
- Package script: passed, NSIS artifact produced

### Release Work

- Bump all package versions to `0.8.0`.
- Update `docs/PROVIDERS.md`, `docs/USER_GUIDE.md`, and
  `docs/BAKEOFF_REPORT.md`.
- Commit provider-quality implementation and docs separately.
- Final commit: `chore: release sync v0.8.0`.

## Phase 11: Packaging, Security, And Supportability

Target: `0.9.0`

Status: **complete** on 2026-05-23.

Goal: make installation, updates, diagnostics, and privacy/security posture feel
production-grade.

### User Value

Users can install and run the app without a source checkout, understand unsigned
or signed build status, gather diagnostics, and trust local-first boundaries.

### Scope

- Finish installed-app launch story:
  - packaged desktop shell finds or starts the backend reliably
  - no source checkout required for the normal user path
  - clear fallback when Python/backend prerequisites are missing
- Decide and document the backend distribution model:
  - embedded sidecar, bundled Python environment, or managed local CLI contract
  - choose one primary path for Windows 1.0
  - document macOS/Linux as supported, beta, or deferred
- Add release automation:
  - build wheel
  - build Windows installer
  - upload CI artifacts
  - generate checksums
  - produce release notes from changelog/roadmap
- Add security/support diagnostics:
  - local diagnostics bundle command
  - config redaction
  - provider secret redaction
  - app/backend log locations
  - privacy/security doc aligned to actual behavior
- Add update story:
  - manual update path if auto-updater remains deferred
  - version check command or UI notice if lightweight and privacy-safe
  - clear no-surprises behavior
- Harden CI:
  - dependency audit where practical
  - packaged artifact smoke
  - docs link check if dependency cost is low
  - release checklist enforcement script

### Acceptance Gates

- A clean Windows machine or clean Windows VM can install and launch the app via
  documented user steps.
- Release artifacts include installer, wheel, checksums, and release notes.
- Diagnostics bundle can be generated without leaking configured secrets.
- Privacy/security docs match actual network, storage, and provider behavior.
- CI can produce release artifacts without manual local-only steps.

### Verification

- Python tests: 219 passed, 83%+ coverage
- Web unit tests: 39 passed
- Playwright e2e: 2 passed
- Rust tests: 1 passed
- Package script: passed, NSIS artifact produced

### Release Work

- Bump all package versions to `0.9.0`.
- Update README install section from beta language to release-candidate language.
- Update `docs/RELEASE_CHECKLIST.md` with artifact and diagnostic gates.
- Final commit: `chore: release sync v0.9.0`.

## Phase 12: 1.0 Polish, Freeze, And Launch Readiness

Target: `1.0.0`

Status: **complete** on 2026-05-23.

Goal: remove beta roughness, freeze public contracts, and ship a credible 1.0.

### User Value

Users get a stable, documented, supportable product that feels intentional from
install through recovery from failed agent runs.

### Scope

- Public contract freeze:
  - API request/response shapes documented
  - CLI commands documented
  - config file behavior documented
  - session/run storage compatibility documented
- UX polish pass:
  - consistent copy and labels
  - consistent button/icon language
  - no debug-looking empty states
  - no unsupported visible commands
  - no known layout overlap at supported sizes
- Accessibility pass:
  - keyboard-only full core flow
  - focus order review
  - screen-reader labels for primary controls
  - color contrast review for all themes
- Reliability burn-in:
  - repeated create/send/stop/retry/resume sessions
  - repeated provider wizard add/test/delete
  - repeated approval grant/deny
  - repeated package install/launch smoke
- Documentation finalization:
  - README becomes product-first, not contributor-first
  - user guide covers first run, context, approvals, diffs, terminal, settings,
    provider health, troubleshooting, privacy, diagnostics, and updates
  - release notes summarize user-visible value, known limits, and upgrade path
- Version and artifact finalization:
  - bump to `1.0.0`
  - final screenshots if stable
  - final checksums
  - final release checklist with exact verification numbers

### Acceptance Gates

- A non-contributor can install, configure, run a first prompt, attach context,
  approve a safe command, inspect a diff, and recover from a failed run using
  docs alone.
- No known P0/P1 bugs remain.
- No beta-only language remains in primary install docs unless explicitly
  describing an intentionally beta platform.
- All shared gates pass.
- Packaged install smoke passes from a clean environment.
- Roadmap and changelog agree on what shipped.

### Verification

- Python gates: ruff, ruff format check, and mypy passed
- Python tests: 225 passed, 3 deselected, 82.55% coverage
- Web unit tests: 39 passed
- Web build: passed with packaged assets generated
- Playwright e2e: 2 passed
- Rust tests: 1 passed
- Local beta package script: passed with clean wheel smoke
- Release automation: passed with wheel, Windows installer copy, checksums, and release notes
- Visual pass: workbench rendered through local browser smoke without layout blockers

### Release Work

- Bump all package versions to `1.0.0`.
- Update changelog and release notes.
- Final commit: `chore: release sync v1.0.0`.
- Tag/push/release only when explicitly requested.

## Non-Goals Before 1.0

Avoid adding bloat that does not strengthen the core workbench:

- No managed billing platform.
- No plugin marketplace.
- No broad MCP marketplace UI.
- No multi-user/team workspace features.
- No cloud sync requirement.
- No full IDE replacement promise.
- No speculative provider list expansion without testable value.

## Measurement Targets

Track these numbers in each release-sync commit:

- Python test count and coverage
- Web unit test count
- Playwright e2e count
- Package script result
- Installer artifact path/name
- Optional provider bake-off summary once Phase 10 lands
- Known limits that remain for the next phase

## Handoff Instructions For Implementers

Implementers should work one minor release at a time. For each version:

1. Create or switch to the matching release branch.
2. Re-audit the repo before coding.
3. Use TDD for backend and frontend behavior.
4. Keep changes scoped to the phase.
5. Run the shared gates before the release-sync commit.
6. Update this roadmap with actual status, test numbers, and known limits.
7. Commit the version bump as the final commit for that version.
