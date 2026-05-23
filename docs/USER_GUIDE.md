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

## Trust

New UI sessions default to `ask`. Use the composer trust selector or CLI
`--trust-mode` to choose `read_only`, `ask`, or `workspace`.

## Inspectors

The right inspector keeps secondary surfaces out of the main chat:

- `timeline`: session events and activity.
- `runs`: sessions plus changed-file summaries.
- `terminal`: command results for the active session.
- `usage`: token and estimated cost summary for the active session.
- `settings`: mode, trust, provider/model, and available commands.
