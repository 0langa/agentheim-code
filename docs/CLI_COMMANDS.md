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

The `coder` subcommand exposes the shared Agentheim Coder terminal client,
including `/new`, `/resume`, `/sessions`, `/status`, `/diff`, `/files`,
`/approve`, `/deny`, `/cancel`, `/open`, `/model`, `/provider`, `/profile`, and
`/models`.

Useful noninteractive forms:

```powershell
agentheim-code coder --workspace . --prompt "Write tests for the parser"
agentheim-code coder --workspace . --prompt "Review this repo" --json
agentheim-code coder --workspace . --profile default --provider openai --model gpt-4.1
agentheim-code coder resume <session-id> --workspace .
agentheim-code coder resume <session-id> --workspace . --approve <request-id>
agentheim-code coder ui --workspace . --port 8765
```

The UI command palette is backed by the same command registry as the CLI slash
commands.
