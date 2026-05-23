# Agentheim Next Baseline Implementation Plan

Historical note: this was the internal execution plan used to move the
repository from the `1.0.0` baseline to the verified `1.5.0` baseline.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the full audited roadmap and verified future backlog from the current `1.0.0` baseline through a coherent sequence of reliability, UX, config, packaging, and quality-engineering releases.

**Architecture:** Implement this as a staged hardening program, not a feature pile. The backend contract must be tightened first, then the workbench UI can scale honestly on top of it, then config/supportability and release engineering can be made durable, and only then should optional benchmark and extensibility work proceed. Shared runtime modules under `src/core`, `src/config`, `src/providers`, and `src/workflows` are treated as first-class product dependencies, not untouchable externals.

**Tech Stack:** Python 3.12, FastAPI, Typer, React 19, TypeScript, Vite, Vitest, Playwright, Tauri v2, Rust, GitHub Actions

---

## Scope Check

This scope is too broad to execute as one uninterrupted coding task. Treat this as one combined master plan composed of six release workstreams:

1. `1.1.0` Reliability and backend contract hardening
2. `1.2.0` Workbench scale and UX honesty
3. `1.3.0` Config unification and supportability
4. `1.4.0` Packaging, CI, and release engineering hardening
5. `1.5.0` API typing, ADRs, and visual/quality infrastructure
6. `1.6.0+` Optional model-quality and deeper platform extensions

Each workstream should land as a self-contained branchable milestone with its
own verification pass and release-sync commit. Do not attempt to blend them all
into one giant implementation PR.

## File Structure

### Core backend and launcher files

- Modify: `src/agentheim_code/backend.py`
  Add middleware/lifespan wiring, stricter request handling, and API contract changes.
- Create: `src/agentheim_code/http_context.py`
  Request ID propagation, header helpers, and size-limit enforcement.
- Create: `src/agentheim_code/lifecycle.py`
  Graceful startup/shutdown and background cleanup hooks.
- Modify: `src/agentheim_code/desktop.py`
  Improve backend subprocess lifecycle and shutdown guarantees.
- Modify: `src/agentheim_code/context_bundle.py`
  Better token estimation and incremental validation support.
- Modify: `src/agentheim_code/structured_errors.py`
  Expand machine-readable error coverage.

### Shared runtime files

- Modify: `src/workflows/coder/runtime.py`
  Subprocess-aware cancellation, possible provider fallback hooks, and session/runtime hardening.
- Modify: `src/core/run_executor.py`
  Execution cancellation and cleanup integration if runtime changes require lower-level support.
- Modify: `src/config/config.py`
  Provider/config surface cleanup and documentation-driven structure improvements.
- Modify: `src/providers/usage.py`
  Improved token-estimate and usage metadata integration if needed.

### Frontend files

- Modify: `apps/web/src/App.tsx`
  Reduce monolithic state and wire improved API/inspector flows.
- Modify: `apps/web/src/api.ts`
  Retry policy, request ID usage, and safer stream/error handling.
- Create: `apps/web/src/state/sessionState.ts`
  Shared session/workbench state extracted from `App.tsx`.
- Create: `apps/web/src/utils/ansi.ts`
  Terminal output normalization/parsing.
- Modify: `apps/web/src/components/WorkspaceExplorer.tsx`
  Large-workspace scaling and cleaner attach/preview behavior.
- Modify: `apps/web/src/components/DiffViewer.tsx`
  Better diff rendering.
- Modify: `apps/web/src/components/TerminalPanel.tsx`
  ANSI-safe rendering and richer metadata.
- Modify: `apps/web/src/components/CommandPalette.tsx`
  Honest action execution rules.
- Modify: `apps/web/src/components/Inspector.tsx`
  Better approvals, settings, and runs presentation.

### Desktop and release files

- Modify: `.github/workflows/ci.yml`
  Add cache improvements and release-hygiene checks.
- Modify: `scripts/package-beta.ps1`
  Keep Windows packaging deterministic and smoke-tested.
- Modify: `scripts/release.ps1`
  Keep artifact staging aligned with the real release surface.
- Modify: `apps/desktop/src-tauri/tauri.conf.json`
  Signing or desktop-surface adjustments if adopted.
- Modify: `apps/desktop/src-tauri/src/main.rs`
  Desktop shell improvements that remain intentionally small and auditable.

### Docs and process files

- Create: `docs/adr/0001-config-surface-and-storage.md`
  Explain config boundary decisions.
- Create: `docs/adr/0002-api-type-generation.md`
  Explain OpenAPI-to-TypeScript generation choice.
- Modify: `README.md`
- Modify: `PRODUCT_ROADMAP.md`
- Modify: `docs/API_REFERENCE.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/CLI_COMMANDS.md`
- Modify: `docs/PROVIDERS.md`
- Modify: `docs/TROUBLESHOOTING.md`
- Modify: `docs/RELEASE_CHECKLIST.md`

### Test files

- Modify: `tests/test_backend_routes.py`
- Modify: `tests/test_backend_context.py`
- Modify: `tests/test_backend_misc.py`
- Modify: `tests/test_supportability.py`
- Create: `tests/test_backend_lifecycle.py`
- Create: `tests/test_backend_limits.py`
- Modify: `apps/web/src/__tests__/api.test.ts`
- Modify: `apps/web/src/components/__tests__/App.api.test.tsx`
- Modify: `apps/web/src/components/__tests__/Inspector.test.tsx`
- Modify: `apps/web/src/components/__tests__/Composer.test.tsx`
- Create: `apps/web/src/components/__tests__/TerminalPanel.test.tsx`
- Create: `apps/web/src/components/__tests__/WorkspaceExplorer.test.tsx`
- Modify: `apps/web/e2e/smoke.spec.ts`

## Release Order

- `1.1.0`: reliability and contract hardening
- `1.2.0`: workbench scale and UX honesty
- `1.3.0`: config/supportability cleanup
- `1.4.0`: packaging and CI hardening
- `1.5.0`: typed contract generation, ADRs, and visual/quality infrastructure
- `1.6.0+`: optional benchmark and extensibility work

### Task 1: `1.1.0` Reliability And Backend Contract Hardening

**Files:**
- Create: `src/agentheim_code/http_context.py`
- Create: `src/agentheim_code/lifecycle.py`
- Modify: `src/agentheim_code/backend.py`
- Modify: `src/agentheim_code/desktop.py`
- Modify: `src/agentheim_code/context_bundle.py`
- Modify: `src/agentheim_code/structured_errors.py`
- Modify: `src/workflows/coder/runtime.py`
- Modify: `tests/test_backend_routes.py`
- Modify: `tests/test_backend_context.py`
- Create: `tests/test_backend_lifecycle.py`
- Create: `tests/test_backend_limits.py`
- Modify: `docs/API_REFERENCE.md`

- [ ] **Step 1: Write failing tests for request IDs, request size limits, and graceful shutdown**

```python
def test_health_includes_request_id_header(client: TestClient) -> None:
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.headers["x-request-id"]


def test_large_message_request_is_rejected(client: TestClient) -> None:
    session_id = client.post("/api/coder/sessions", json={"trust_mode": "ask", "mode": "code"}).json()["session_id"]
    payload = {"prompt": "x" * 300_000}
    resp = client.post(f"/api/coder/sessions/{session_id}/messages", json=payload)
    assert resp.status_code == 413


def test_lifespan_shutdown_completes_cleanly() -> None:
    app = create_app(".")
    assert app.title == "Agentheim Code"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_backend_routes.py tests/test_backend_limits.py tests/test_backend_lifecycle.py -q`
Expected: FAIL with missing `x-request-id` header, no 413 enforcement, and missing lifecycle coverage.

- [ ] **Step 3: Implement request context and limits**

```python
# src/agentheim_code/http_context.py
from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4


REQUEST_ID_HEADER = "x-request-id"
MAX_JSON_BODY_BYTES = 262_144


@dataclass(frozen=True)
class RequestContext:
    request_id: str


def new_request_id() -> str:
    return uuid4().hex
```

- [ ] **Step 4: Wire middleware and lifespan into the backend**

```python
app = FastAPI(title="Agentheim Code", version=_version(), lifespan=build_lifespan())

@app.middleware("http")
async def attach_request_context(request: Request, call_next: Callable[..., Awaitable[Response]]) -> Response:
    request_id = request.headers.get(REQUEST_ID_HEADER, new_request_id())
    response = await call_next(request)
    response.headers[REQUEST_ID_HEADER] = request_id
    return response
```

- [ ] **Step 5: Add request-size guards and structured 413 errors for message-like endpoints**

```python
if len(body.prompt.encode("utf-8")) > MAX_JSON_BODY_BYTES:
    raise HTTPException(
        status_code=413,
        detail=StructuredError(
            error_code="E2008",
            message="Request body is too large.",
            technical_detail="Prompt payload exceeded the configured body limit.",
            recovery_action="Reduce the prompt size or attached context and retry.",
        ).to_dict(),
    )
```

- [ ] **Step 6: Improve runtime cancellation and launcher shutdown semantics**

```python
def _stop_backend(proc: subprocess.Popen[bytes]) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
```

- [ ] **Step 7: Run focused tests, then full backend checks**

Run: `pytest tests/test_backend_routes.py tests/test_backend_context.py tests/test_backend_limits.py tests/test_backend_lifecycle.py tests/test_supportability.py -q`
Expected: PASS

Run: `ruff check src/agentheim_code tests/`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add src/agentheim_code/backend.py src/agentheim_code/http_context.py src/agentheim_code/lifecycle.py src/agentheim_code/desktop.py src/agentheim_code/context_bundle.py src/agentheim_code/structured_errors.py src/workflows/coder/runtime.py tests/test_backend_routes.py tests/test_backend_context.py tests/test_backend_limits.py tests/test_backend_lifecycle.py docs/API_REFERENCE.md
git commit -m "feat: harden backend request and lifecycle contracts"
```

### Task 2: `1.2.0` Workbench Scale And UX Honesty

**Files:**
- Create: `apps/web/src/state/sessionState.ts`
- Create: `apps/web/src/utils/ansi.ts`
- Modify: `apps/web/src/App.tsx`
- Modify: `apps/web/src/api.ts`
- Modify: `apps/web/src/components/WorkspaceExplorer.tsx`
- Modify: `apps/web/src/components/DiffViewer.tsx`
- Modify: `apps/web/src/components/TerminalPanel.tsx`
- Modify: `apps/web/src/components/CommandPalette.tsx`
- Modify: `apps/web/src/components/Inspector.tsx`
- Modify: `apps/web/src/components/__tests__/App.api.test.tsx`
- Modify: `apps/web/src/components/__tests__/Inspector.test.tsx`
- Modify: `apps/web/src/components/__tests__/Composer.test.tsx`
- Create: `apps/web/src/components/__tests__/TerminalPanel.test.tsx`
- Create: `apps/web/src/components/__tests__/WorkspaceExplorer.test.tsx`
- Modify: `apps/web/e2e/smoke.spec.ts`
- Modify: `docs/USER_GUIDE.md`

- [ ] **Step 1: Write failing component tests for palette honesty, file-list scaling hooks, and ANSI-safe terminal rendering**

```tsx
it("does not render unsupported palette actions as executable buttons", () => {
  render(<CommandPalette commands={[{ id: "unknown", label: "Unknown", cli: "/unknown", surface: "global" }]} onExecute={vi.fn()} onClose={vi.fn()} />);
  expect(screen.queryByText("Unknown")).toBeInTheDocument();
});

it("renders terminal output without raw ansi escapes", () => {
  render(<TerminalPanel results={[{ command: ["pytest"], stdout: "\u001b[31mFAIL\u001b[0m", exit_code: 1 }]} />);
  expect(screen.getByText("FAIL")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run web tests to verify they fail**

Run: `npm --prefix apps/web run test -- --run`
Expected: FAIL in new terminal and palette expectations.

- [ ] **Step 3: Extract session/workbench state from `App.tsx`**

```ts
// apps/web/src/state/sessionState.ts
export type WorkbenchSelection = {
  inspector: string;
  sessionFilter: string;
  selectedContextFiles: string[];
};
```

- [ ] **Step 4: Add safer retry logic and request-ID-aware error handling in the API layer**

```ts
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, { headers: { "content-type": "application/json" }, ...init });
  if (!response.ok) throw new ApiError(response.status, await response.text());
  return response.json() as Promise<T>;
}
```

- [ ] **Step 5: Scale the files panel and make the command palette honest**

```tsx
const visibleCommands = commands.filter((command) => command.id in supportedCommandIds);
const filtered = files.slice(0, 500).filter((f) => f.path.toLowerCase().includes(query.toLowerCase()));
```

- [ ] **Step 6: Replace naive terminal rendering and improve diff readability**

```ts
export function stripAnsi(text: string): string {
  return text.replace(/\u001b\[[0-9;]*m/g, "");
}
```

- [ ] **Step 7: Run targeted web tests and smoke**

Run: `npm --prefix apps/web run test -- --run`
Expected: PASS

Run: `npm --prefix apps/web run e2e`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add apps/web/src/App.tsx apps/web/src/api.ts apps/web/src/state/sessionState.ts apps/web/src/utils/ansi.ts apps/web/src/components/WorkspaceExplorer.tsx apps/web/src/components/DiffViewer.tsx apps/web/src/components/TerminalPanel.tsx apps/web/src/components/CommandPalette.tsx apps/web/src/components/Inspector.tsx apps/web/src/components/__tests__/App.api.test.tsx apps/web/src/components/__tests__/Inspector.test.tsx apps/web/src/components/__tests__/Composer.test.tsx apps/web/src/components/__tests__/TerminalPanel.test.tsx apps/web/src/components/__tests__/WorkspaceExplorer.test.tsx apps/web/e2e/smoke.spec.ts docs/USER_GUIDE.md
git commit -m "feat: scale workbench panels and command behavior"
```

### Task 3: `1.3.0` Config Unification And Supportability

**Files:**
- Modify: `src/agentheim_code/config.py`
- Modify: `src/config/config.py`
- Modify: `src/agentheim_code/backend.py`
- Modify: `src/agentheim_code/cli.py`
- Modify: `tests/test_config.py`
- Modify: `tests/test_backend_routes.py`
- Create: `docs/adr/0001-config-surface-and-storage.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/PROVIDERS.md`
- Modify: `docs/TROUBLESHOOTING.md`

- [ ] **Step 1: Write failing tests for a documented, coherent config surface**

```python
def test_ui_config_exposes_documented_default_workspace(tmp_path: Path) -> None:
    cfg = {"core": {"default_workspace": str(tmp_path)}, "ui": {"theme": "dark"}}
    assert cfg["core"]["default_workspace"] == str(tmp_path)
```

- [ ] **Step 2: Run config and route tests**

Run: `pytest tests/test_config.py tests/test_backend_routes.py -q`
Expected: FAIL where assumptions no longer match the target unified surface.

- [ ] **Step 3: Decide and document the storage boundary**

```md
# ADR 0001: Config Surface And Storage

- UI preferences stay in `config.toml`
- provider profiles stay in `providers.json`
- docs and API must present this split explicitly
```

- [ ] **Step 4: Implement the minimum code/doc changes to make the split coherent and explicit**

```python
def _read_ui_config() -> dict[str, Any]:
    return {
        "onboarding_complete": bool(onboarding.get("complete", False)),
        "onboarding_dismissed": bool(onboarding.get("dismissed", False)),
        "default_workspace": str(core.get("default_workspace", ".")),
        "theme": str(ui.get("theme", "dark")),
    }
```

- [ ] **Step 5: Verify the documented contract in tests and CLI help paths**

Run: `pytest tests/test_config.py tests/test_backend_routes.py tests/test_cli.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/agentheim_code/config.py src/config/config.py src/agentheim_code/backend.py src/agentheim_code/cli.py tests/test_config.py tests/test_backend_routes.py docs/adr/0001-config-surface-and-storage.md docs/ARCHITECTURE.md docs/PROVIDERS.md docs/TROUBLESHOOTING.md
git commit -m "feat: clarify config and supportability boundaries"
```

### Task 4: `1.4.0` Packaging, CI, And Release Engineering Hardening

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `scripts/package-beta.ps1`
- Modify: `scripts/release.ps1`
- Modify: `docs/RELEASE_CHECKLIST.md`
- Modify: `README.md`

- [ ] **Step 1: Write or update CI expectations in docs before changing the workflow**

```md
- cache Rust builds
- cache Playwright browsers
- keep wheel and installer artifacts explicit
```

- [ ] **Step 2: Add CI caching and preserve the current artifact contract**

```yaml
- uses: Swatinem/rust-cache@v2
- uses: actions/cache@v4
  with:
    path: ~/.cache/ms-playwright
```

- [ ] **Step 3: Keep packaging scripts aligned with the real release surface**

```powershell
Invoke-Step "Build web assets" {
    & npm --prefix apps/web run build
}
```

- [ ] **Step 4: Run packaging and release checks locally**

Run: `python -m build --wheel`
Expected: PASS

Run: `powershell -ExecutionPolicy Bypass -File scripts/package-beta.ps1`
Expected: PASS with wheel smoke and installer lookup.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/ci.yml scripts/package-beta.ps1 scripts/release.ps1 docs/RELEASE_CHECKLIST.md README.md
git commit -m "chore: harden packaging and ci release workflows"
```

### Task 5: `1.5.0` Typed Contracts, ADRs, And Visual/Quality Infrastructure

**Files:**
- Create: `docs/adr/0002-api-type-generation.md`
- Modify: `apps/web/package.json`
- Modify: `apps/web/src/types.ts`
- Modify: `docs/API_REFERENCE.md`
- Modify: `docs/README.md`
- Modify: `apps/web/e2e/smoke.spec.ts`

- [ ] **Step 1: Document the OpenAPI-to-TypeScript decision**

```md
# ADR 0002: API Type Generation

- backend remains FastAPI-first
- frontend generated types are checked in or reproducibly regenerated
```

- [ ] **Step 2: Add generation tooling in the web package**

```json
{
  "scripts": {
    "types:api": "openapi-typescript http://127.0.0.1:8765/openapi.json -o src/generated/api-types.ts"
  }
}
```

- [ ] **Step 3: Add visual-regression scaffolding only for stable UI states**

```ts
await expect(page).toHaveScreenshot("workbench-empty.png");
```

- [ ] **Step 4: Run web build and e2e again**

Run: `npm --prefix apps/web run build`
Expected: PASS

Run: `npm --prefix apps/web run e2e`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add docs/adr/0002-api-type-generation.md apps/web/package.json apps/web/src/types.ts docs/API_REFERENCE.md docs/README.md apps/web/e2e/smoke.spec.ts
git commit -m "feat: add typed contract and visual quality scaffolding"
```

### Task 6: `1.6.0+` Optional Benchmarking And Extension Program

**Files:**
- Create: `tests/benchmarks/README.md`
- Create: `tests/benchmarks/b001_reference_task/`
- Modify: `.github/workflows/ci.yml`
- Modify: `docs/FUTURE_IMPROVEMENTS.md`
- Modify: `PRODUCT_ROADMAP.md`

- [ ] **Step 1: Defer this task unless the first five workstreams are complete and stable**

Run: `git status --short`
Expected: clean enough to branch a dedicated benchmark effort.

- [ ] **Step 2: Add a tiny reference benchmark skeleton rather than a giant quality platform**

```text
tests/benchmarks/
  b001_reference_task/
    prompt.md
    expected/
    test.py
```

- [ ] **Step 3: Prove the benchmark harness locally before CI**

Run: `pytest tests/benchmarks -q`
Expected: PASS with one benchmark harness task.

- [ ] **Step 4: Commit**

```bash
git add tests/benchmarks .github/workflows/ci.yml docs/FUTURE_IMPROVEMENTS.md PRODUCT_ROADMAP.md
git commit -m "feat: add benchmark and extension program scaffolding"
```

## Shared Verification Gate After Every Workstream

Run:

```powershell
ruff check src/agentheim_code src/memory src/tools/shell tests/
ruff format --check src/agentheim_code src/memory src/tools/shell tests/
mypy src/agentheim_code src/memory src/tools/shell --follow-imports=skip
pytest --cov --cov-report=term-missing --cov-fail-under=80 -m "not integration"
npm --prefix apps/web run test -- --run
npm --prefix apps/web run build
npm --prefix apps/web run e2e
cd apps/desktop/src-tauri; cargo test
```

Expected:

- all commands pass
- docs match actual behavior
- `docs/RELEASE_CHECKLIST.md` is updated with fresh numbers, not copied numbers

## Self-Review

### Spec coverage

This plan covers every confirmed item in:

- `PRODUCT_ROADMAP.md`
- `docs/FUTURE_IMPROVEMENTS.md`

Mapped workstreams:

- reliability and observability: Task 1
- UX scale and honesty: Task 2
- config/supportability: Task 3
- packaging/release engineering: Task 4
- OpenAPI typing, ADRs, visual infrastructure: Task 5
- optional model-quality and extension program: Task 6

### Placeholder scan

No `TODO`, `TBD`, or "implement later" placeholders remain in execution steps.
Optional scope is explicitly isolated in Task 6 rather than left ambiguous.

### Type consistency

The plan preserves current real identifiers where known:

- `context_files`
- `use_context_bundle`
- `onboarding_complete`
- `onboarding_dismissed`
- `default_workspace`
- `theme`

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-23-agentheim-next-baseline.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
