# Agentheim Code Phased Plan

Updated: 2026-05-23

This is the canonical product plan. It replaces the separate audit/report file
and keeps current-state facts, priorities, release targets, and gates in one
place.

## Goal

Make Agentheim Code a fast, legible, safe GUI-first coding assistant while
preserving the local-first BYOK architecture.

First-session success is the priority:

1. User opens the app.
2. User chooses or detects a provider.
3. User opens a workspace.
4. User sends a prompt.
5. Response streams visibly.
6. Code renders clearly.
7. Risky actions have understandable approvals.

## Current Baseline

### Product Shape

- Python package: `agentheim-code`
- Version: `0.1.0`
- Python requirement: `>=3.12`
- CLI entrypoint: `agentheim-code`
- Backend: FastAPI in `src/agentheim_code/backend.py`
- Web app: React/TypeScript/Vite in `apps/web`
- Desktop shell: Tauri v2 in `apps/desktop`
- Packaged web assets: `src/agentheim_code/web`
- Session/run storage: `.ai-team/runs/<session-id>/`

### Owned Repository Surface

Tracked Agentheim Code surface:

- `src/agentheim_code`
- `src/memory`
- `src/tools/shell`
- `apps/web`
- `apps/desktop`
- `docs`
- root project docs/config

This checkout can also contain ignored sibling Agentheim packages, such as
`src/core`, `src/config`, `src/providers`, and `src/workflows`. Treat those as
development/runtime dependencies unless a task explicitly targets them.

### Already Present

- Local FastAPI backend
- CLI entrypoint and desktop/web launch modes
- React/Tauri shell
- Provider wizard templates
- Provider profile create/delete/test flow
- Model/profile selectors in the composer
- Session list/view/message APIs
- Approval APIs
- File tree API
- Usage aggregation endpoint and panel
- Shell sandbox and policy-gated tools
- CI for Python, web build/tests, and Windows Tauri build

### Main Gaps

- Token streaming
- Markdown/code rendering
- First-run onboarding
- `@` file context
- Richer visual approvals
- Light/high-contrast themes
- Consumer installer flow
- End-user docs

### Current Verification

Last verified on 2026-05-23:

- `pytest --cov --cov-report=term-missing --cov-fail-under=80 -m "not integration"`: 190 passed, 3 deselected, 83.12% coverage
- `npm --prefix apps/web test -- --run --reporter=dot`: 21 passed
- `npm --prefix apps/web run build`: passed

Known test noise:

- Python provider-wizard tests emit third-party OCI/urllib3 deprecation warnings.

## Phase 0: Truth And Baseline Cleanup

Status: complete on 2026-05-23.

Deliverable: repo facts and quality gates are consistent.

Completed:

- Coverage threshold is 80 in both `pyproject.toml` and CI.
- Inspector test waits for async provider state and no longer emits a React
  `act(...)` warning.
- Separate report content is folded into this canonical phased plan.
- `docs/ARCHITECTURE.md` documents tracked Agentheim Code scope vs ignored
  sibling packages.

Gate:

- Normal local verification is green without threshold contradictions.

## Phase 1: Streaming And Chat Legibility

Status: complete on 2026-05-23.

Deliverable: chat feels alive and code-heavy output is readable.

Backend:

- Added a streaming message endpoint alongside existing
  `POST /api/coder/sessions/{id}/messages`.
- Kept existing non-streaming endpoint working during migration.
- Chose SSE over `fetch` for assistant delivery while retaining WebSocket for
  event snapshots.
- Added cancellation behavior through `AbortController`.
- Added tests for stream lifecycle and frontend stream consumption.

Frontend:

- Added streaming chat state.
- Render partial assistant output while generation runs.
- Added stop/retry controls.
- Added markdown rendering with strict component mapping.
- Added syntax highlighting for code blocks.
- Added copy buttons for code blocks.
- Kept transcript auto-scroll predictable.

Gate:

- User sees incremental streamed output, can stop or retry generation, and code
  blocks render with highlighting and copy controls.

Note:

- The tracked backend/frontend SSE transport is complete. Runtime/provider code
  currently exposes final assistant content and activity updates; provider-level
  token callbacks can further improve granularity later inside the shared runtime.

Release target: v0.2.0.

## Phase 2: First-Run Onboarding

Deliverable: a new user can reach a working chat session without reading docs.

Flow:

1. Welcome
2. Workspace selection
3. Provider path selection
4. Provider verification
5. Start first session

Provider paths:

- Local model: detect common local endpoints such as Ollama.
- API key: route into existing provider wizard with sensible defaults.
- Expert setup: expose provider/model/profile details directly.
- Skip for later: allowed, but leaves a clear next action.

Implementation notes:

- Reuse existing provider wizard APIs.
- Do not duplicate provider form logic.
- Store onboarding completion in local config.
- Provide empty states that point to the next useful action.

Gate:

- Fresh config opens to onboarding, configured users go directly to app, and at
  least one provider path can be completed end to end.

Release target: v0.3.0.

## Phase 3: Context Selection

Deliverable: users can explicitly scope prompts to files without typing paths
manually.

Frontend:

- Add `@` trigger in composer.
- Show fuzzy file picker from workspace file tree.
- Insert removable context chips.
- Support drag/drop files into composer if feasible.
- Make selected context visible before send.

Backend:

- Extend file tree/search API if current file list is too heavy.
- Add payload shape for selected context.
- Preserve compatibility with plain-text prompts.

Gate:

- User can type `@`, choose a file, send prompt, and see selected context
  attached to the turn.

Release target: v0.3.0.

## Phase 4: Approval UX And Trust

Deliverable: safety model becomes visible and understandable.

UI:

- Add approval queue surface.
- Show pending action type, command/path, risk level, and reason.
- For file writes, show diff preview.
- For shell commands, show exact command and working directory.
- Provide clear grant/deny controls.
- Keep terminal output linked to the action that produced it.

Trust modes:

- Keep exact internal names: `read_only`, `ask`, `workspace`.
- Add short human descriptions in UI.
- Make current trust mode visible in the composer and approval panel.

Gate:

- Pending approvals are hard to miss and can be handled entirely from the GUI.

Release target: v0.4.0.

## Phase 5: Themes And Accessibility

Deliverable: app is usable across light/dark/high-contrast preferences and
stronger keyboard/screen-reader paths.

- Add theme tokens for dark, light, and high contrast.
- Add theme selector in settings.
- Improve visible focus states.
- Make chat updates announce correctly with appropriate ARIA behavior.
- Review modal keyboard behavior.
- Add automated accessibility checks where practical.
- Manually verify common keyboard-only flows.

Gate:

- Core flows work with keyboard only, focus is visible, and all three themes are
  usable.

Release target: v0.4.0.

## Phase 6: Distribution

Deliverable: repeatable consumer install path.

Installer:

- Decide backend bundling approach.
- Produce repeatable Windows installer from CI.
- Add macOS and Linux packaging plans after Windows path is stable.
- Keep unsigned beta expectations explicit if signing is not ready.

Updates:

- Defer auto-updater until installer is stable.
- When added, require signed update metadata and documented release flow.

Gate:

- A user can install and launch without a source checkout on the target
  platform.

Release target: v0.5.0.

## Phase 7: End-User Docs

Deliverable: docs match the GUI-first product.

- Rewrite README for users first, developers second.
- Add first-run screenshots after onboarding stabilizes.
- Update `docs/PROVIDERS.md` around provider wizard flows.
- Keep developer commands in `CONTRIBUTING.md` and `docs/RELEASE_CHECKLIST.md`.

Gate:

- A non-contributor can install, configure, and run the app using docs alone.

Release target: v0.5.0.

## Deferred Platform Work

Defer until first-session experience is strong:

- Semantic indexing
- MCP marketplace or plugin ecosystem
- Advanced usage dashboards
- Rich terminal emulator
- Full file explorer/editor surface
- Managed API-key billing model

These may become important, but they should not outrank streaming, onboarding,
context selection, approvals, accessibility, and installability.

## Working Principles

- Preserve local-first behavior.
- Reuse existing provider wizard and backend contracts.
- Keep old APIs during migrations until tests cover the new path.
- Prioritize first-session success over broad platform features.
- Avoid market/legal claims unless backed by current sources.
- Avoid precise competitor/product claims unless re-verified at the time of use.
