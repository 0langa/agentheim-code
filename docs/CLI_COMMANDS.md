# CLI Commands

The installed entry point is `agentheim-code`.

Typer also provides:

- `agentheim-code --install-completion`
- `agentheim-code --show-completion`

The project also keeps a manual completion script command:

```powershell
agentheim-code completions powershell
```

## Top-Level Commands

### App Launch

```powershell
agentheim-code app --workspace .                # packaged desktop shell, requires a built/installed binary
agentheim-code app --workspace . --web          # browser fallback
agentheim-code app --workspace . --dev          # source-tree Tauri dev mode
agentheim-code app --workspace . --port 9999    # non-default backend port
```

### Readiness And Inventory

```powershell
agentheim-code version
agentheim-code doctor
agentheim-code doctor --json
agentheim-code models
agentheim-code models --json
agentheim-code runs --workspace .
agentheim-code runs --workspace . --json
agentheim-code version-check
```

### Support And Provider Checks

```powershell
agentheim-code diagnostics --out agentheim-diagnostics.json
agentheim-code provider-test openai_v1 --api-key "sk-..." --endpoint "https://api.openai.com/v1" --model "gpt-4o-mini"
agentheim-code provider-test aws_bedrock --api-key "..." --region us-east-1 --model "amazon.nova-pro-v1:0"
agentheim-code config export --path agentheim-code-config.json
agentheim-code config import --path agentheim-code-config.json
```

### Provider Comparison

```powershell
agentheim-code bake-off --workspace . --json
agentheim-code bake-off --workspace . --profile default --provider openai --model gpt-4o-mini --timeout 300 --report-dir ./reports
```

## `coder` Subcommand

The `coder` subcommand exposes the shared terminal-first session flow.

```powershell
agentheim-code coder --workspace .
agentheim-code coder --workspace . --prompt "Review the auth flow"
agentheim-code coder --workspace . --json
agentheim-code coder --workspace . --profile default --provider openai --model gpt-4.1
agentheim-code coder --workspace . --trust-mode ask     # read_only | ask | workspace
agentheim-code coder --workspace . --mode code           # ask | code | review
```

### `coder` Subcommands

```powershell
agentheim-code coder ui --workspace . --port 8765
agentheim-code coder ui --workspace . --port 8765 --no-browser
agentheim-code coder ui --workspace . --port 8765 --json
agentheim-code coder list --workspace .
agentheim-code coder list --workspace . --json
agentheim-code coder models
agentheim-code coder resume <session-id> --workspace .
```

### `coder resume` examples

```powershell
agentheim-code coder resume <session-id> --workspace . --prompt "Continue"
agentheim-code coder resume <session-id> --workspace . --approve <request-id>
agentheim-code coder resume <session-id> --workspace . --grant <request-id>
agentheim-code coder resume <session-id> --workspace . --deny <request-id>
agentheim-code coder resume <session-id> --workspace . --json
```

## Interactive Slash Commands

Inside an interactive `agentheim-code coder` session:

- `/new` starts a new session
- `/resume <id>` switches to another session
- `/sessions` lists sessions
- `/status` shows the current session view
- `/diff` shows changed files
- `/files` lists workspace files
- `/approve <id>` grants a pending approval
- `/deny <id>` denies a pending approval
- `/cancel` cancels active work
- `/open` opens the browser workbench
- `/model <provider> <model>` sets provider and model
- `/provider <id>` sets provider
- `/profile <name>` sets profile
- `/models` lists available models
- `/help` prints slash-command help
- `exit` or `quit` leaves the session

## Notes

- `agentheim-code app` is not the same as `agentheim-code app --web`.
- The packaged desktop shell is optional. The browser workbench is the lowest
  friction path from source or wheel install.
- The UI command palette overlaps with the coder command registry, but today it
  directly executes only the built-in navigation and retry/stop actions exposed
  by the frontend.
- `agentheim-code --version` and `agentheim-code -v` print the version and exit
  immediately without entering the Typer CLI.
- During an interactive `coder` session, if the assistant produces a pending
  approval, the REPL automatically prompts `Grant the pending approval?`
  inline before continuing.
