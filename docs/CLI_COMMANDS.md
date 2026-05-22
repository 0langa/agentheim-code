# CLI Commands

```powershell
agentheim-code app --workspace .        # packaged desktop app
agentheim-code app --workspace . --web  # browser fallback
agentheim-code app --workspace . --dev  # source-tree Tauri dev mode
agentheim-code coder --workspace .
agentheim-code coder models
agentheim-code models
agentheim-code doctor
agentheim-code runs --workspace .
```

The `coder` subcommand exposes the shared Agentheim Coder terminal client.
Available slash commands inside an interactive session:

- `/new` — start a new session
- `/resume <id>` — resume a different session
- `/sessions` — list all sessions
- `/status` — show current session status
- `/diff` — show changed files
- `/files` — list workspace files
- `/approve <id>` — grant a pending approval
- `/deny <id>` — deny a pending approval
- `/cancel` — cancel active work
- `/open` — open the coder UI in a browser
- `/model <provider> <model>` — set provider and model
- `/provider <id>` — set provider
- `/profile <name>` — set profile
- `/models` — list available models
- `/help` — show this list
- `exit` or `quit` — leave the session

Useful noninteractive forms:

```powershell
# Non-interactive one-shot
agentheim-code coder --workspace . --prompt "Write tests for the parser"
agentheim-code coder --workspace . --prompt "Review this repo" --json
agentheim-code coder --workspace . --profile default --provider openai --model gpt-4.1

# Resume and manage sessions
agentheim-code coder resume <session-id> --workspace .
agentheim-code coder resume <session-id> --workspace . --approve <request-id>
agentheim-code coder resume <session-id> --workspace . --prompt "Continue"

# Launch the coder UI
agentheim-code coder ui --workspace . --port 8765

# List sessions or models
agentheim-code coder list --workspace .
agentheim-code coder models
```

The UI command palette is backed by the same command registry as the CLI slash
commands.
