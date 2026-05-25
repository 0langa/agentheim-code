# User Guide

## Choose A Launch Mode

### Browser workbench

Works from a normal Python install:

```powershell
agentheim-code app --workspace . --web
```

### Packaged desktop shell

Use this only when you have a built or installed Tauri binary:

```powershell
agentheim-code app --workspace .
```

### Source-tree dev shell

```powershell
agentheim-code app --workspace . --dev
```

## First Run

Fresh UI config opens onboarding automatically.

1. Choose the workspace.
2. If Ollama is running, review the detected local endpoint.
3. Or open the provider wizard and add a profile manually.
4. Start the first session.

Skipping onboarding only dismisses the dialog. Settings still exposes provider
setup later.

## Main Layout

- Left rail: new session plus shortcuts for timeline, runs, files, terminal, approvals, command palette, usage, and settings
- Center: top bar, chat transcript, composer
- Right inspector: the currently selected panel

## Sessions

Create a session from:

- the rail `New session` button
- the top bar `New` button
- `Ctrl/Cmd+Shift+N`

The active session view keeps:

- transcript
- timeline events
- approvals
- terminal results
- diffs
- usage

## Composer

The composer controls each turn.

- Modes: `ask`, `plan`, `code`, `review`, `fix`, `docs`, `test`
- Trust modes: `ask`, `read_only`, `workspace`
- Profile and model selectors: choose explicit values or keep `Auto`
- Send: `Ctrl/Cmd+Enter`
- Stop: available while streaming
- Retry: available after a completed turn

## File Context

Type `@` in the prompt to search workspace files.

Current flow:

1. Type `@partial-name`
2. Pick one or more files from the inline match list
3. Review context previews and token estimates
4. Remove any file that should not be included

Files are validated before provider execution. The current validation rejects:

- missing paths
- directories
- files under `.git` or `.ai-team`
- binary files
- files larger than the current bundle limit
- paths outside the workspace

Accepted files are embedded into the runtime prompt as bounded file-content
blocks.

## Inspector Panels

### Timeline

Shows session events as they arrive.

### Runs

Lists sessions and supports a simple text filter over:

- session id
- status
- mode

### Files

Shows the current workspace tree with:

- incremental backend loading
- simple substring search
- changed-file badges
- preview
- copy path
- attach to context

Large workspaces now load in backend pages instead of one capped client-side
list. Use `Load next 100` to keep browsing without locking the panel.

### Terminal

Shows command results with:

- exit status badge
- collapse/expand
- copy command
- copy stdout
- copy stderr
- ANSI escape codes are stripped for clean rendering

### Approvals

Risky actions automatically push the inspector to Approvals when pending items
exist.

Each approval shows:

- tool id
- action kind
- risk level
- status
- target
- reason

Shell approvals also show the command. File approvals show pending content when
available.

### Usage

Shows aggregated token and cost data when the provider returns usage metadata.

### Settings

The current Settings panel includes:

- theme selector
- active session mode/trust/model summary
- configured provider profiles
- command list

## Keyboard Shortcuts

- `Ctrl/Cmd+K` or `Ctrl/Cmd+P`: open command palette
- `Ctrl/Cmd+,`: open Settings
- `Ctrl/Cmd+Shift+N`: new session
- `Ctrl/Cmd+Enter`: send prompt
- `Escape`: close the command palette or modal

The command palette only shows actions that the workbench can execute directly.
Unsupported CLI-only commands are hidden rather than displayed as non-functional
items.

The current supported palette actions include navigation for Runs, Timeline,
Files, Terminal, Usage, Settings, approvals, retry, stop, and new session.

## CLI Flow

Terminal-first work is still supported:

```powershell
agentheim-code doctor
agentheim-code models
agentheim-code coder --workspace .
agentheim-code coder --workspace . --prompt "Review src/auth.py"
```

## Recovery And Diagnostics

When a run fails, the app may surface a structured error with:

- error code
- message
- technical detail
- recovery action

For deeper inspection, open Timeline, Terminal, Approvals, and Diffs.

Generate a redacted support bundle with:

```powershell
agentheim-code diagnostics --out agentheim-diagnostics.json
```
