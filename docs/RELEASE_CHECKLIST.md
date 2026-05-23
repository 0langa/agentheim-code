# Release Checklist

## Required Checks

- `pytest --cov --cov-report=term-missing --cov-fail-under=80 -m "not integration"`
- `ruff check src/agentheim_code src/memory src/tools/shell tests/`
- `ruff format --check src/agentheim_code src/memory src/tools/shell tests/`
- `mypy src/agentheim_code src/memory src/tools/shell --follow-imports=skip`
- `npm --prefix apps/web run test -- --run`
- `npm --prefix apps/web run build`
- `npm --prefix apps/web run e2e`
- `cd apps/desktop/src-tauri && cargo test`
- `python -m build --wheel`
- `npm --prefix apps/desktop run build`

## Manual Checks

- Windows desktop builds require Visual Studio Build Tools with the C++ workload
  so Rust can find `link.exe`.
- Clean wheel install smoke:
  - `agentheim-code --help`
  - `agentheim-code models --json`
  - `agentheim-code provider-test`
  - backend app import
- Launch `agentheim-code app --web`.
- Verify no unapproved palette hex values.
- Verify docs match CLI help.
