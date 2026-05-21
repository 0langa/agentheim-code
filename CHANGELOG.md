# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.0] - 2026-05-21

### Added
- Initial release of Agentheim Code
- Typer-based CLI with `app`, `coder`, `models`, `doctor`, `runs`, `version`, and `completions` commands
- FastAPI backend serving local-only Agentheim Coder runtime
- Tauri v2 desktop shell with React/TypeScript frontend
- Web fallback via Uvicorn when Tauri is unavailable
- Command palette with keyboard shortcuts (`Ctrl+K`, `Ctrl+P`)
- Session management (create, resume, list)
- Mode selection: ask, plan, code, review, fix, docs, test
- Azure OpenAI provider support via `agentheim` shared runtime
- Policy-gated tool approvals for risky actions
- User configuration file (`config.toml`) with platform-aware paths
- Structured logging throughout Python backend
- Workspace input validation
- Port collision handling with automatic fallback
- Subprocess timeout for Tauri launcher
- Restrictive Content Security Policy for desktop app
- Comprehensive test suite (Python ≥82% coverage, frontend Vitest, Rust cargo test)
- CI/CD pipeline with lint, type check, test, and coverage gates
- Developer tooling: ruff, mypy, pytest-cov
