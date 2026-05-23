# Release Checklist

- `python -m pytest -q`
- `python -m pytest tests/ -m "not integration" --cov=src/agentheim_code --cov=src/memory --cov=src/tools/shell --cov-fail-under=80`
- `ruff check src/agentheim_code src/memory src/tools/shell tests`
- `ruff format --check src/agentheim_code src/memory src/tools/shell tests`
- `mypy src/agentheim_code src/memory src/tools/shell --follow-imports=skip`
- `npm --prefix apps/web run build`
- `npm --prefix apps/web run test -- --run`
- `npm --prefix apps/web run e2e`
- `cd apps/desktop/src-tauri && cargo test`
- `python -m build --wheel`
- `npm --prefix apps/desktop run build`
- Windows desktop builds require Visual Studio Build Tools with the C++ workload
  so Rust can find `link.exe`.
- clean wheel install smoke for `agentheim-code --help`, `agentheim-code models --json`,
  `agentheim-code provider-test`, and backend app import
- launch `agentheim-code app --web`
- verify no unapproved palette hex values
- verify docs match CLI help
