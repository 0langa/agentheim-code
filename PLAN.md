# Agentheim Code — Concrete Implementation Plan

> ⚠️ **OWNER NOTE — DO NOT PUSH:** The repository owner has 2FA enabled and will not be available to confirm pushes. **Do NOT push any branches or commits to GitHub while executing this plan.** Work locally on feature branches only. Push only when the owner is present to approve 2FA.

> **Objective:** Transform the current v0.1.0 prototype into a hardened, production-ready local coding-agent product.  
> **Approach:** Hand this document to an agent (or yourself) and execute phase by phase. Each phase has explicit deliverables, files to touch, and success criteria.

---

## Phase 0: Foundation Hardening (Do First — Blocks Everything Else)

**Goal:** Fix critical bugs and safety issues before any feature work.

### P0.1 Fix fragile path resolution in `desktop.py`
**File:** `src/agentheim_code/desktop.py`  
**Problem:** `Path(__file__).resolve().parents[3]` breaks if the package moves.  
**Implementation:**
- Replace `parents[3]` traversal with `importlib.resources.files("agentheim_code")` or a build-time constant.
- If using `importlib.resources`, handle both editable installs and wheel installs.
- Fallback gracefully if the desktop app source is not found (it already falls back to web, but the detection logic should be robust).

**Success criteria:** `launch_desktop()` works when:
- Run from source (`pip install -e .`)
- Run from a built wheel (`pip install agentheim_code-0.1.0-py3-none-any.whl`)
- The source tree is renamed or moved

### P0.2 Add subprocess timeout for Tauri launch
**File:** `src/agentheim_code/desktop.py`  
**Problem:** `subprocess.run(["npm", "run", "tauri", "--", "dev"], ...)` hangs forever if Tauri stalls.  
**Implementation:**
- Add `timeout=120` to the `subprocess.run()` call.
- Catch `subprocess.TimeoutExpired` and print a clear error, then fall back to web.

**Success criteria:** If `npm run tauri -- dev` hangs for >2 minutes, the process is killed and the web fallback launches automatically.

### P0.3 Handle port collisions in `serve_web()`
**File:** `src/agentheim_code/desktop.py`  
**Problem:** `uvicorn.run()` crashes with a stack trace if the port is already in use.  
**Implementation:**
- Before calling `uvicorn.run()`, attempt to bind a socket to `("127.0.0.1", port)`.
- If `OSError` (address in use), print `"Port {port} is in use. Trying {port+1}..."` and increment until a free port is found.
- Pass the resolved port to `uvicorn.run()` and update the browser-open URL.

**Success criteria:** Running two `agentheim-code app` instances simultaneously launches two working web UIs on different ports.

### P0.4 Define a restrictive CSP in Tauri config
**File:** `apps/desktop/src-tauri/tauri.conf.json`  
**Problem:** `"security": { "csp": null }` disables all content security policy.  
**Implementation:**
```json
"security": {
  "csp": "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self' http://127.0.0.1:*"
}
```
(Adjust `connect-src` if the frontend needs to call other local APIs.)

**Success criteria:** Tauri build succeeds and the desktop app loads without CSP violations in devtools.

### P0.5 Validate workspace input at CLI layer
**File:** `src/agentheim_code/cli.py`, `src/agentheim_code/backend.py`, `src/agentheim_code/desktop.py`  
**Problem:** `workspace` is accepted as `str | Path` but never validated.  
**Implementation:**
- Add a small helper `_resolve_workspace(path)` that:
  1. Converts to `Path`
  2. Calls `.resolve()`
  3. Checks `.exists()` → if not, raise `typer.BadParameter("Workspace does not exist: {path}")`
  4. Checks `.is_dir()` → if not, raise `typer.BadParameter("Workspace must be a directory: {path}")`
- Use this helper in `app_cmd()`, `create_app()`, and `launch_desktop()`.

**Success criteria:**
```bash
agentheim-code app --workspace /nonexistent
# → Error: Workspace does not exist: /nonexistent

agentheim-code app --workspace /some/file.txt
# → Error: Workspace must be a directory: /some/file.txt
```

---

## Phase 1: Developer Experience & CI Hardening

**Goal:** Make the project maintainable and catch regressions automatically.

### P1.1 Add Python dev tooling
**Files:** `pyproject.toml`  
**Implementation:**
Add to `[project.optional-dependencies]`:
```toml
dev = [
  "pytest>=9.0.3,<10.0.0",
  "pytest-cov>=6.0.0,<7.0.0",
  "ruff>=0.9.0,<1.0.0",
  "mypy>=1.14.0,<2.0.0",
]
```
Add `[tool.ruff]` config:
```toml
[tool.ruff]
target-version = "py312"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "W", "UP", "B", "C4", "SIM"]
ignore = ["E501"]

[tool.ruff.lint.pydocstyle]
convention = "google"

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
```
Add `[tool.mypy]` config:
```toml
[tool.mypy]
python_version = "3.12"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
```
Add `[tool.coverage.run]` config:
```toml
[tool.coverage.run]
source = ["src/agentheim_code"]
omit = ["*/tests/*"]

[tool.coverage.report]
fail_under = 70
skip_covered = false
```

**Success criteria:**
```bash
pip install -e .[dev]
ruff check src/ tests/
ruff format --check src/ tests/
mypy src/
pytest --cov
```
All commands run without config errors.

### P1.2 Fix all ruff/mypy violations in existing code
**Files:** `src/agentheim_code/*.py`, `tests/*.py`  
**Implementation:**
- Run `ruff check --fix src/ tests/`
- Run `ruff format src/ tests/`
- Run `mypy src/` and fix every reported error (add missing type hints, fix import issues).
- Add `__all__` to `__init__.py`.

**Success criteria:** `ruff check src/ tests/` exits 0. `mypy src/` exits 0.

### P1.3 Expand test coverage to all Python modules
**Files:** `tests/test_cli.py`, `tests/test_desktop.py`, `tests/test_backend.py`  
**Implementation:**
- `test_cli.py`: Add tests for:
  - `doctor` command (table and JSON output)
  - `runs` command (table and JSON output)
  - `app` command (mock `launch_desktop` to avoid actually starting servers)
  - `models` table-render path when providers are configured
  - `models` error path when no providers are configured
- `test_desktop.py`: Add tests for:
  - `serve_web()` with mocked `uvicorn.run`
  - `launch_desktop()` with `web_fallback=True`
  - `launch_desktop()` when `package.json` is missing (fallback)
  - `launch_desktop()` subprocess timeout scenario
  - Port collision resolution logic
- `test_backend.py`: Add tests for:
  - `create_app()` with valid workspace
  - `create_app()` with invalid workspace (raises error after P0.5)

**Success criteria:** `pytest --cov` reports ≥70% coverage. All tests pass.

### P1.4 Commit lock files for reproducible builds
**Files:** New `uv.lock` or `package-lock.json` / `Cargo.lock`  
**Implementation:**
- If using `uv`: run `uv lock` and commit `uv.lock`.
- If using `npm`: ensure `package-lock.json` in both `apps/web` and `apps/desktop` is committed.
- `Cargo.lock` in `apps/desktop/src-tauri/` is already committed — good.
- Document the lock strategy in `CONTRIBUTING.md` (see P4.6).

**Success criteria:** A fresh clone can reproduce the exact dependency tree via the lock file.

### P1.5 Harden CI pipeline
**File:** `.github/workflows/ci.yml`  
**Implementation:**
Replace the current minimal CI with a matrix:

```yaml
name: CI
on:
  push:
    branches: [main]
  pull_request:

jobs:
  python:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.12", "3.13"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - name: Cache pip
        uses: actions/cache@v4
        with:
          path: ~/.cache/pip
          key: ${{ runner.os }}-pip-${{ hashFiles('pyproject.toml') }}
      - name: Install agentheim dependency
        run: |
          git clone https://github.com/0langa/agentheim ../agentheim
          pip install -e ../agentheim
      - name: Install project
        run: pip install -e .[dev]
      - name: Lint
        run: ruff check src/ tests/
      - name: Format check
        run: ruff format --check src/ tests/
      - name: Type check
        run: mypy src/
      - name: Test with coverage
        run: pytest --cov --cov-report=xml --cov-fail-under=70
      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          files: ./coverage.xml

  web:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "22"
      - uses: actions/cache@v4
        with:
          path: ~/.npm
          key: ${{ runner.os }}-npm-${{ hashFiles('apps/web/package-lock.json') }}
      - name: Build web
        run: |
          npm --prefix apps/web ci
          npm --prefix apps/web run build

  desktop-rust:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: dtolnay/rust-action@stable
      - uses: actions/setup-node@v4
        with:
          node-version: "22"
      - name: Build web assets
        run: |
          npm --prefix apps/web ci
          npm --prefix apps/web run build
      - name: Build Tauri
        run: npm --prefix apps/desktop run tauri build
        env:
          CI: true
```

**Success criteria:** CI passes on the PR that introduces these changes.

---

## Phase 2: Frontend Architecture & Quality

**Goal:** Decompose the monolithic React app into maintainable components and make the UI actually functional.

### P2.1 Extract an API client module
**New file:** `apps/web/src/api.ts`  
**Implementation:**
```typescript
const API_BASE = "/api";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "content-type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    throw new ApiError(response.status, await response.text());
  }
  return response.json() as Promise<T>;
}
```
- Replace all raw `fetch` calls in `main.tsx` with `api<T>(...)`.  
- Add request/response logging in dev mode.

**Success criteria:** `main.tsx` imports from `./api` and contains no raw `fetch` calls.

### P2.2 Decompose `main.tsx` into components
**New files:**
- `apps/web/src/components/Rail.tsx`
- `apps/web/src/components/TopBar.tsx`
- `apps/web/src/components/Chat.tsx`
- `apps/web/src/components/Composer.tsx`
- `apps/web/src/components/Inspector.tsx`
- `apps/web/src/components/CommandPalette.tsx`
- `apps/web/src/hooks/useSessions.ts`
- `apps/web/src/hooks/useCommands.ts`

**Implementation:**
- Move each UI section into its own component.
- Extract custom hooks for data fetching (`useSessions`, `useCommands`) that handle:
  - Loading states
  - Error states
  - Refetching
- Keep `App.tsx` (rename from `main.tsx`) as the composition root.

**Success criteria:** No component file exceeds 100 lines. `App.tsx` only composes children and holds shared state.

### P2.3 Add loading, error, and empty states
**Files:** All new component files  
**Implementation:**
- Every async data fetch shows a loading indicator (spinner or skeleton).
- Every async action (send prompt, create session) disables its button while in-flight.
- API errors surface in the UI (toast or inline error banner), not just `console.error`.
- Add an `ErrorBoundary` component that catches React errors and shows a friendly "Something went wrong" screen with a reload button.

**Success criteria:**
- Throttling network to "Slow 3G" in DevTools shows loading states.
- Blocking `/api/coder/sessions` in DevTools shows an error message in the UI.

### P2.4 Make the command palette functional
**File:** `apps/web/src/components/CommandPalette.tsx`  
**Implementation:**
- Add local state for the search query.
- Filter `commands` by `label` and `cli` against the query.
- Execute the selected command when clicked or when Enter is pressed:
  - If the command maps to a UI action (e.g., "New session"), call the appropriate handler prop.
  - If the command maps to a CLI-only action, show a toast: "Run in terminal: {cli}".
- Add `aria-expanded`, focus trapping, and `Escape` to close.

**Success criteria:** Typing "new" filters to the new-session command. Pressing Enter creates a session. Clicking a command executes it.

### P2.5 Move build-time deps to `devDependencies`
**File:** `apps/web/package.json`  
**Implementation:**
Move these from `dependencies` to `devDependencies`:
- `@vitejs/plugin-react`
- `vite`
- `typescript`

Leave only runtime deps in `dependencies`:
- `react`
- `react-dom`
- `lucide-react`

**Success criteria:** `npm --prefix apps/web install --production` only installs 3 packages (+ peers).

### P2.6 Add frontend type-checking and linting to CI
**File:** `.github/workflows/ci.yml` (web job)  
**Implementation:**
Add steps to the `web` job:
```yaml
- name: Type check
  run: npm --prefix apps/web run build  # tsc is already part of build
- name: Lint (optional)
  run: npx --prefix apps/web eslint src/ || true
```
(If adding ESLint, install `eslint`, `@eslint/js`, `typescript-eslint` as dev deps and create a minimal `eslint.config.js`.)

**Success criteria:** CI fails if the TypeScript build fails.

---

## Phase 3: Testing & Security

**Goal:** Verify the frontend and backend behave correctly, and catch vulnerabilities early.

### P3.1 Add Vitest + React Testing Library for frontend unit tests
**Files:** `apps/web/package.json`, new `apps/web/src/components/*.test.tsx`  
**Implementation:**
```bash
cd apps/web
npm install -D vitest @testing-library/react @testing-library/jest-dom jsdom
```
Add to `package.json` scripts:
```json
"test": "vitest run",
"test:watch": "vitest"
```
Create `vitest.config.ts`:
```typescript
import { defineConfig } from "vitest/config";
export default defineConfig({
  test: {
    environment: "jsdom",
    globals: true,
  },
});
```
Write at least these tests:
- `CommandPalette.test.tsx`: renders, filters commands, calls `onSelect`.
- `Composer.test.tsx`: textarea accepts input, send button calls `onSend`.
- `Chat.test.tsx`: renders empty state, renders active session.

**Success criteria:** `npm --prefix apps/web run test` passes with ≥3 component tests.

### P3.2 Add Playwright E2E smoke test
**Files:** New `e2e/` directory or `apps/web/e2e/`  
**Implementation:**
```bash
npm install -D @playwright/test
npx playwright install
```
Create `apps/web/e2e/smoke.spec.ts`:
```typescript
import { test, expect } from "@playwright/test";

test("page loads and shows Coder Hub", async ({ page }) => {
  await page.goto("http://127.0.0.1:5173/coder");
  await expect(page.locator("h1")).toContainText("Coder Hub");
});
```
Add a CI job that starts the backend and runs the E2E test.

**Success criteria:** One E2E test runs successfully in CI.

### P3.3 Add Rust tests for Tauri shell
**File:** `apps/desktop/src-tauri/src/main.rs`  
**Implementation:**
Add a simple unit test:
```rust
#[cfg(test)]
mod tests {
    #[test]
    fn it_compiles() {
        assert_eq!(2 + 2, 4);
    }
}
```
Add `cargo test` to CI.

**Success criteria:** `cargo test` in `apps/desktop/src-tauri` passes.

### P3.4 Add dependency security scanning to CI
**File:** `.github/workflows/ci.yml`  
**Implementation:**
Add a new job:
```yaml
  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install pip-audit
      - run: pip-audit --desc --requirement <(pip install -e . && pip freeze)
      - uses: actions/setup-node@v4
        with: { node-version: "22" }
      - run: npm --prefix apps/web audit --audit-level moderate
```

**Success criteria:** CI reports known vulnerabilities (if any) without failing the build.

---

## Phase 4: Polish, Features & Documentation

**Goal:** Ship a product that feels complete and is easy for others to contribute to.

### P4.1 Add `--version` CLI flag and shell completions
**File:** `src/agentheim_code/cli.py`  
**Implementation:**
- Add `version` parameter to the `typer.Typer()` constructor:
  ```python
  app = typer.Typer(
      help="Agentheim Code: focused local coding-agent client.",
      no_args_is_help=True,
      version=__version__,
  )
  ```
- Add a new command or script to generate shell completions:
  ```python
  @app.command("completions")
  def completions(shell: str = typer.Argument(..., help="Shell: bash, zsh, fish, powershell")) -> None:
      import typer.completion
      typer.completion.install_callback(app, shell)
  ```
  (Or use `typer`’s built-in completion generation.)

**Success criteria:**
```bash
agentheim-code --version
# → agentheim-code, version 0.1.0

agentheim-code completions bash
# → valid bash completion script
```

### P4.2 Add user configuration file support
**New file:** `src/agentheim_code/config.py`  
**Implementation:**
- Use `platformdirs` or `pathlib` to resolve a config directory:
  - Windows: `%APPDATA%/Agentheim Code/config.toml`
  - macOS: `~/Library/Application Support/Agentheim Code/config.toml`
  - Linux: `~/.config/agentheim-code/config.toml`
- Support settings:
  ```toml
  [core]
  default_workspace = "."
  default_port = 8765
  
  [ui]
  theme = "dark"  # placeholder for future light mode
  ```
- Load this config in `cli.py` and use values as defaults for CLI options.
- Create the file with defaults on first run if it doesn't exist.

**Success criteria:** After first run, the config file exists. Editing `default_port` changes the default for `agentheim-code app`.

### P4.3 Render actual chat message history
**Files:** `apps/web/src/components/Chat.tsx`, `apps/web/src/api.ts`  
**Implementation:**
- Extend the `SessionView` type to include `messages: Message[]`.
- Update `Chat.tsx` to map over `messages` and render them with sender labels (user / assistant) and timestamps.
- Add a scroll-to-bottom effect when new messages arrive.
- Style message bubbles differently for user vs assistant.

**Success criteria:** Sending a prompt shows both the user message and the assistant response in the chat panel.

### P4.4 Make mode buttons functional
**File:** `apps/web/src/components/Composer.tsx`  
**Implementation:**
- Track the selected mode in `App.tsx` state.
- Pass `selectedMode` and `onModeChange` to `Composer`.
- Highlight the active mode button.
- When creating a session or sending a prompt, include the selected mode in the API payload.

**Success criteria:** Clicking "review" highlights it. Creating a session POSTs `mode: "review"`.

### P4.5 Add structured logging to Python backend
**File:** `src/agentheim_code/cli.py`, `src/agentheim_code/backend.py`, `src/agentheim_code/desktop.py`  
**Implementation:**
- Use Python’s standard `logging` module (or `structlog` if you want structured JSON logs).
- Configure a basic config in `cli.py`:
  ```python
  import logging
  logging.basicConfig(
      level=logging.INFO,
      format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
  )
  ```
- Replace the single `print(..., file=sys.stderr)` in `desktop.py` with `logging.getLogger("agentheim_code.desktop").warning("Tauri dev shell unavailable; starting web fallback.")`.
- Add log lines for:
  - Server start/stop
  - Session creation
  - CLI command invocation

**Success criteria:** Running `agentheim-code app` shows timestamped log lines. No `print()` statements remain in production code.

### P4.6 Write `CONTRIBUTING.md` and `CHANGELOG.md`
**New files:** `CONTRIBUTING.md`, `CHANGELOG.md`  
**Implementation:**
- `CONTRIBUTING.md`:
  - Development setup (install `agentheim` adjacently, `pip install -e .[dev]`)
  - How to run tests (`pytest`, `npm run test`, `cargo test`)
  - How to run linters (`ruff`, `mypy`)
  - Branch naming and PR process
- `CHANGELOG.md`:
  - Start with `## [0.1.0] - 2026-05-21` and list the initial feature set.
  - Use Keep a Changelog format.

**Success criteria:** A new contributor can set up the project in <10 minutes using only `CONTRIBUTING.md`.

### P4.7 Generate API documentation
**New file:** `docs/API_INTERNAL.md` or use a doc generator  
**Implementation:**
- Add module-level docstrings to `backend.py` and `desktop.py`.
- Ensure every public function has a Google-style docstring.
- Optionally, set up `mkdocs` + `mkdocstrings` to auto-generate docs from docstrings.

**Success criteria:** All public Python symbols have docstrings. `mkdocs serve` (if used) renders them.

---

## Execution Order Summary

| Phase | Tasks | Est. Time |
|-------|-------|-----------|
| **P0** | Critical fixes (path, timeout, port, CSP, validation) | 2–3 hrs |
| **P1** | Tooling, linting, type checking, tests, CI, lock files | 4–6 hrs |
| **P2** | Frontend decomposition, API client, functional palette, loading states | 6–8 hrs |
| **P3** | Frontend tests, E2E, Rust tests, security audit CI | 4–6 hrs |
| **P4** | Version flag, config file, chat history, mode buttons, logging, docs | 6–8 hrs |

**Total estimate:** ~22–31 hours of focused development.

---

## Immediate Next Steps (If You Hand This Off Now)

1. **Create a feature branch:** `git checkout -b feat/hardening`
2. **Start Phase 0.** Open `src/agentheim_code/desktop.py` and fix the three issues there (path, timeout, port).
3. **Commit after each P0 task** with clear messages.
4. **Open a PR when P0+P1 are done.** This is the "foundation" PR.
5. **Open a second PR for P2+P3** (frontend architecture + testing).
6. **Open a third PR for P4** (features + docs).

---

## Definition of Done

- [ ] `ruff check src/ tests/` → exit 0
- [ ] `mypy src/` → exit 0
- [ ] `pytest --cov` → ≥70% coverage, all pass
- [ ] `npm --prefix apps/web run test` → ≥3 tests pass
- [ ] `cargo test` in `apps/desktop/src-tauri` → pass
- [ ] `npm --prefix apps/desktop run build` → produces a `.exe`
- [ ] CI is green on all jobs (Python matrix, web build, desktop Rust, security audit)
- [ ] `CONTRIBUTING.md` and `CHANGELOG.md` exist
- [ ] No `print()` in production Python code
- [ ] Command palette is functional
- [ ] Chat renders message history
- [ ] Mode buttons change the session mode

---

*End of plan. Execute at will.*
