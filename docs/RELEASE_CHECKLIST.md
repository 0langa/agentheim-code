# Release Checklist

- `python -m pytest -q`
- `ruff check src/agentheim_code src/memory src/tools/shell tests`
- `ruff format --check src/agentheim_code src/memory src/tools/shell tests`
- `mypy src/agentheim_code src/memory src/tools/shell --follow-imports=skip`
- `npm --prefix apps/web run build`
- `npm --prefix apps/web run test -- --run`
- `cd apps/desktop/src-tauri && cargo test`
- `python -m build --wheel`
- `npm --prefix apps/desktop run build`
- Windows desktop builds require Visual Studio Build Tools with the C++ workload
  so Rust can find `link.exe`.
- clean wheel install smoke for `agentheim-code --help`, `agentheim-code models --json`,
  and backend app import
- launch `agentheim-code app --web`
- verify no unapproved palette hex values
- verify docs match CLI help
