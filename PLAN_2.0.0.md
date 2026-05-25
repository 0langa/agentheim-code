# Agentheim Code 2.0.0 Plan

Completed: 2026-05-26

Updated: 2026-05-24

This file is the historical execution plan from the verified `1.9.0` baseline
to the shipped `2.0.0` release. It is retained as the implementation record
for the final rc hardening and release-truth-sync pass.

## Starting Point

Current proven baseline:

- local FastAPI backend with request ids, size limits, structured errors, and graceful lifespan hooks
- browser workbench plus optional Tauri shell
- first-run onboarding with Ollama auto-detection
- session creation, resume, cancel, approvals, diffs, terminal output, usage, and file-context validation
- first-party OCI adapter and trimmed inherited vendor surface
- Windows NSIS packaging path with clean wheel smoke
- Python non-integration coverage at `92%`
- broadened Playwright smoke coverage for onboarding, provider, and streaming flows

## 2.0.0 Product Goal

Ship Agentheim Code as a genuinely standalone, premium-feel coding workbench
that:

- behaves consistently across browser and packaged desktop modes
- has no misleading inherited surfaces
- scales to larger real-world repositories
- is observable and supportable when things go wrong
- is releaseable with confidence, not ceremony

## Guardrails

- Prefer targeted hardening over platform sprawl.
- Do not add major new product surfaces until the current ones are stable.
- Remove inherited compatibility code when it is not part of the shipped UX.
- Keep Windows-first distribution strong before expanding installer targets.
- Every release must update docs, generated assets, and verification records together.

## Release Map

### Completed: `1.6.0` Runtime Correctness And Observability

Primary goal: make failures diagnosable and long-running work more trustworthy.

Deliverables:

- propagate request ids into shared runtime logs, run artifacts, and structured error payloads more consistently
- add explicit runtime cancellation tracking for subprocess-backed actions and pending approvals
- improve structured error mapping for provider/network/filesystem failures
- add safe retry/backoff for idempotent frontend API fetches
- tighten diagnostics so request ids, relevant paths, and provider-state hints are easier to correlate

Key code areas:

- `src/agentheim_code/backend.py`
- `src/agentheim_code/structured_errors.py`
- `src/agentheim_code/diagnostics.py`
- `src/workflows/coder/runtime.py`
- `src/core/run_view.py`
- `apps/web/src/api.ts`

Acceptance:

- failed runs are easier to map from UI -> logs -> session artifacts
- cancel/stop behavior is materially more reliable for active turns
- common provider failures surface specific recovery guidance instead of generic fallback text

### Completed: `1.7.0` Workbench Scale And UX Polish

Primary goal: keep the workbench fast and high-signal on larger repositories and longer sessions.

Deliverables:

- replace the current 500-item file cap with incremental loading or virtualization
- improve diff presentation with chunking, better unchanged-context handling, and large-diff fallbacks
- improve approval previews for file edits and shell commands
- improve terminal UX with better grouping, timestamps, and copy affordances
- expand keyboard-first flows and focus handling across inspectors and modals
- make command palette behavior exhaustive for supported actions and explicit for unsupported ones

Key code areas:

- `apps/web/src/App.tsx`
- `apps/web/src/components/WorkspaceExplorer.tsx`
- `apps/web/src/components/DiffViewer.tsx`
- `apps/web/src/components/TerminalPanel.tsx`
- `apps/web/src/components/Inspector.tsx`
- `apps/web/e2e/`

Acceptance:

- large repositories remain responsive without hiding too much useful context
- diffs and approvals feel trustworthy enough for daily use
- keyboard-only operation covers the core workbench flow cleanly

### Completed: `1.8.0` Standalone Product Boundary Cleanup

Primary goal: remove the last confusing inheritance seams and own the product boundary end to end.

Deliverables:

- inventory every remaining compatibility path rooted in old Agentheim naming or storage
- migrate UI-visible config, docs, and support flows to Agentheim Code naming consistently
- decide whether provider profile storage should remain in the compatibility root or move to an Agentheim Code-owned path with migration
- remove dead compatibility packages/modules that are not on a real execution path
- audit CLI/help/readiness/support text for any stale or partial guidance

Key code areas:

- `src/config/config.py`
- `src/interfaces/`
- `src/agentheim_core/`
- `src/core/public_api.py`
- `docs/ARCHITECTURE.md`
- `docs/PRIVACY_SECURITY.md`
- `docs/TROUBLESHOOTING.md`

Acceptance:

- no user-facing command/help text references nonexistent inherited flows
- storage decisions are documented with a migration story if changed
- dead compatibility code is removed rather than tolerated

### Completed: `1.9.0` Distribution, Install, And Trust Hardening

Primary goal: make install/update/support feel like a product, not a dev environment.

Deliverables:

- define and implement Windows signing strategy
- add installer smoke verification that proves the packaged shell launches against the packaged backend path, not just source checkout
- improve release automation around artifact naming, retention, and verification
- document clean install, upgrade, rollback, and diagnostics-share flows
- consider settings export/import for safer user migration and support

Key code areas:

- `scripts/package-beta.ps1`
- `scripts/release.ps1`
- `.github/workflows/ci.yml`
- `apps/desktop/src-tauri/`
- `docs/RELEASE_CHECKLIST.md`
- `README.md`

Acceptance:

- installer artifacts are trustworthy and easier to support
- release verification includes an installed-app smoke, not just a build smoke
- upgrade guidance is explicit and tested

### Phase 5: `2.0.0-rc1` Contract Freeze And Premium Finish

Primary goal: stabilize the product contract and refine the surface users actually feel.

Deliverables:

- freeze core API/UI terminology and remove avoidable churn
- consume generated OpenAPI types more broadly in the frontend
- expand Playwright coverage to key session, onboarding, provider, and approval flows
- add curated screenshots once the UI surface is stable
- tighten docs so install, first run, provider setup, approvals, and recovery are all reproducible from docs alone
- run a final inherited-surface audit before the release candidate

Key code areas:

- `apps/web/src/generated/api-types.ts`
- `apps/web/src/types.ts`
- `apps/web/e2e/`
- `docs/README.md`
- `docs/USER_GUIDE.md`
- `docs/API_REFERENCE.md`
- `docs/TROUBLESHOOTING.md`

Acceptance:

- docs, UI labels, and API contracts say the same thing
- release-candidate regressions are caught by e2e, not by user discovery
- screenshots and documentation are generated from the actual stable product

### Phase 6: `2.0.0` Release

Primary goal: ship a disciplined, supportable, standalone major version.

Exit criteria:

- all phases above are complete or explicitly deferred with documented rationale
- version sync is complete across Python, web, desktop, and Tauri
- final wheel and installer artifacts are built from a clean tree
- docs and changelog reflect the shipped truth
- no open blocker remains in runtime correctness, install path, or supportability

## Cross-Cutting Workstreams

These run through every phase:

### 1. Verification Discipline

- keep the canonical verification wall green on every release branch
- update `docs/RELEASE_CHECKLIST.md` only with fresh output
- treat browser smoke and packaged-shell smoke as first-class release gates

### 2. Product-Honesty Audits

- remove or hide any surface that is not actually supported
- prefer deleting dead compatibility code over documenting it forever
- keep CLI, UI, and docs language aligned

### 3. Documentation Sync

Every phase updates as needed:

- `README.md`
- `PRODUCT_ROADMAP.md`
- `docs/README.md`
- `docs/ARCHITECTURE.md`
- `docs/API_REFERENCE.md`
- `docs/USER_GUIDE.md`
- `docs/TROUBLESHOOTING.md`
- `docs/PRIVACY_SECURITY.md`
- `docs/RELEASE_CHECKLIST.md`
- `CHANGELOG.md`

## Recommended Commit Boundaries

For each phase:

1. failing/regression tests
2. implementation
3. docs + generated artifacts + release-sync

Do not collapse a whole phase into one giant commit if the review surface becomes opaque.

## Canonical Verification Wall

Run this on every release-sync branch before sign-off:

```powershell
ruff check src/agentheim_code src/memory src/tools/shell tests/
ruff format --check src/agentheim_code src/memory src/tools/shell tests/
mypy src/agentheim_code src/memory src/tools/shell --follow-imports=skip
pytest --cov --cov-report=term-missing --cov-fail-under=80 -m "not integration"
npm --prefix apps/web run test -- --run
npm --prefix apps/web run build
npm --prefix apps/web run e2e
cd apps/desktop/src-tauri; cargo test
python -m build --wheel
powershell -ExecutionPolicy Bypass -File scripts/package-beta.ps1
```

## Explicit Non-Goals Before 2.0.0

- macOS/Linux installer parity
- cloud-hosted multi-user backend deployment
- plugin marketplace or IDE extension ecosystem
- large new provider families without product need
- heavy framework rewrites that do not reduce real maintenance cost

## First Recommended Next Step

Start with `2.0.0-rc1` and keep it disciplined:

- finish the code-vs-doc truth pass
- stabilize and broaden release-grade Playwright coverage
- freeze product terminology and release metadata
- only then decide whether `2.0.0` is honestly earned
