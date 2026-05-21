# User Guide

## Daily Flow

```powershell
agentheim-code doctor
agentheim-code models
agentheim-code app --workspace .
```

Use the app for most work. Use the CLI when scripting or when you want terminal
mode:

```powershell
agentheim-code coder --workspace .
agentheim-code coder --workspace . --prompt "Review the auth module"
agentheim-code coder resume <session-id> --workspace .
```

## Modes

Coder supports `ask`, `plan`, `code`, `review`, `fix`, `docs`, and `test`. The
UI mode chips and CLI mode/slash commands use the same runtime contract.

