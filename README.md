# Agentheim Code

**Agentheim Code is the focused coding-agent product built from Agentheim.**

It keeps the Coder runtime, provider setup, policy-gated tools, approvals, diffs,
terminal output, run artifacts, and local-first privacy model while leaving the
broader automation presets in Agentheim Full.

## Install

Developer install from adjacent checkouts:

```powershell
cd agentheim-code
pip install -e ..\agentheim
pip install -e .
```

## Quick Start

```powershell
agentheim-code doctor
agentheim-code models
agentheim-code coder --workspace .
agentheim-code app --workspace .
```

`agentheim-code` uses the same provider profiles and `.ai-team/runs/<session-id>/`
artifacts as Agentheim Full, so coder sessions remain portable between products.

## Product Boundary

- Use **Agentheim Code** for daily coding-agent work.
- Use **Agentheim Full** for presets, research, document chat, marketplace,
  federation, monitoring, multimodal, and non-coder automation workflows.

The premium desktop app lives under `apps/desktop` and uses a Tauri shell with a
React/TypeScript frontend. The Python backend stays local-only and binds to
`127.0.0.1`.

