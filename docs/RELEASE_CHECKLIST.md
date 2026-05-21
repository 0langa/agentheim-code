# Release Checklist

- `python -m pytest -q`
- `python -m build`
- `npm --prefix apps/web run build`
- `npm --prefix apps/desktop run build`
- Windows desktop builds require Visual Studio Build Tools with the C++ workload
  so Rust can find `link.exe`.
- clean install smoke for `agentheim-code --help`
- launch `agentheim-code app --web`
- verify no unapproved palette hex values
- verify docs match CLI help
