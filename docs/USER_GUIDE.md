# User Guide

## Start App

Desktop shell:

```powershell
agentheim-code app --workspace .
```

Browser fallback:

```powershell
agentheim-code app --workspace . --web
```

## First Run

Fresh configs open onboarding automatically.

1. Pick workspace.
2. Accept detected Ollama, or open provider wizard.
3. Save provider if needed.
4. Start first session.

Skipping onboarding is allowed. The setup path remains available in Settings.

## Main Layout

- Left rail: new session, inspector shortcuts, command palette.
- Center: top bar, chat transcript, composer.
- Right inspector: timeline, runs, terminal, approvals, usage, settings.

## Sessions

Create a session with:

- rail `New session`
- top bar `New`
- command palette
- `Ctrl+Shift+N`

Sessions keep transcript, approvals, terminal output, diffs, and usage together.

## Composer

Use the composer to control each turn:

- Mode: `ask`, `plan`, `code`, `review`, `fix`, `docs`, `test`
- Trust: `read_only`, `ask`, `workspace`
- Provider/model: choose explicit profile/model or keep auto
- Prompt send: `Ctrl+Enter`

## File Context

Type `@` in the composer to search files from the current workspace.

- pick one or more files
- review chips before send
- remove chips if scope is wrong

Context is sent as explicit bounded file-content blocks in the prompt payload.
Files are validated before use. Missing files, ignored files, binary files,
oversized files, and paths outside the workspace are rejected before the model
call. Accepted files show a preview and rough token estimate.

## Files, Diffs, And Terminal

Use the right inspector as the workbench surface:

- Files: search workspace files, preview content, copy paths, and attach files
  to context.
- Runs: filter sessions by id, status, or mode and resume prior work.
- Terminal: expand command output, copy commands, stdout, or stderr.
- Diffs: review changed files from the run inspector and copy patches.

## Approvals

When a risky action pauses:

- open the Approvals inspector automatically
- read action kind, risk, reason, and target
- grant or deny in place

Trust guidance:

- `read_only`: safest, no edits
- `ask`: recommended default
- `workspace`: faster when you trust the session

## Providers

The provider wizard supports local and cloud setups.

- Ollama auto-detection checks `http://localhost:11434/v1`
- cloud/API providers use the wizard form
- test connection before save

## Keyboard Shortcuts

- `Ctrl+K` or `Ctrl+P`: command palette
- `Ctrl+,`: open Settings
- `Ctrl+Shift+N`: new session
- `Ctrl+Enter`: send prompt
- `Escape`: close palette or modal

## CLI Flow

Terminal-first use remains available:

```powershell
agentheim-code doctor
agentheim-code models
agentheim-code coder --workspace .
agentheim-code coder --workspace . --prompt "Review src/auth.py"
```

## Recovery And Diagnostics

If a run fails, the app shows a structured error with a code and recovery
action. Open Timeline, Terminal, Approvals, and Diffs to inspect what happened.

Generate a redacted support bundle:

```powershell
agentheim-code diagnostics --out agentheim-diagnostics.json
```

Update manually:

```powershell
pip install --upgrade agentheim-code
```
