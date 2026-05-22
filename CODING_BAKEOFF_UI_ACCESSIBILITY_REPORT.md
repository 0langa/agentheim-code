# Agentheim Code Bake-Off And UX Hardening Report

Date: 2026-05-22

## Scope

Ran real empty-workspace coding tests against the configured profiles and hardened runtime/UI behavior found during the test pass. The test prompt allowed any language, framework, architecture, or file layout. The only universal requirements were: create a local-first personal sprint planner, persist data, include meaningful domain logic, include tests or smoke checks, document usage, and run a real local verification command.

Artifacts are under:

`C:\Users\juliu\AppData\Local\Temp\agentheim-code-universal-bakeoff-20260522-231704`

## Provider Results

| Profile | Model | Result | Verification |
| --- | --- | --- | --- |
| `azure-real` | `gpt-4.1` | Pass | Built a Python sprint planner. Initial tests failed twice; runtime repaired and reran `python test_sprint_planner.py` successfully. |
| `aws-bedrock` | `eu.amazon.nova-lite-v1:0` | Pass after runtime hardening | Initial app/test mismatches failed repeatedly; repair now reruns the original unittest command and completed only after exit code `0`. |
| `google-adc` | `gemini-2.5-flash` | Not production-pass yet | Vertex credentials work, but large structured plans still produce empty/truncated/missing-content plans. Runtime schema, base64, and per-file fill improved this, but final runs still failed before a green verification. |
| `oci-genai` | `google.gemini-2.5-flash` | Not production-pass yet | OCI credentials work for simple JSON calls, but coder planning returns empty/truncated completions for this task even with compact fallback. Needs OCI-specific planner strategy or a stronger model/profile. |

## Runtime Fixes Implemented

- Removed static-web-app assumptions from coder planning.
- Added universal coding verification detection instead of hard-coded `index.html/styles.css/app.js`.
- Required non-trivial coding plans to include local verification.
- Added automatic repair for failed verification commands across any language/framework.
- Increased repair attempts from 2 to 4.
- Ensured repair reruns the original failed command before marking a session complete.
- Added `content_base64` support for robust file writes.
- Added tolerant provider action alias parsing for `type`, `file_path`, and string commands.
- Added Gemini/OCI token-budget tuning and compact fallback attempts.
- Added invalid `write_file` detection so empty file plans are rejected before execution.
- Fixed Windows shell executable resolution for shims like `npm.cmd`.
- Reduced noisy AWS/botocore logs in CLI JSON flows.

## UI And Provider UX Fixes Implemented

- Composer now exposes provider profile and planner model selectors.
- New sessions include selected profile/model without requiring CLI-only setup.
- Selecting an existing session syncs mode, trust, profile, and model controls.
- Changing profile/model for an active session calls the existing session model API and refreshes the full session view.
- Composer keeps keyboard send behavior: `Ctrl/Cmd+Enter` sends, `Shift+Enter` remains multiline.
- Web tests and production build pass after the UI changes.

## Remaining UX And Accessibility Work

- Provider setup still needs a guided add/edit flow, not only selection of configured profiles.
- Settings inspector should show provider health, auth mode, model capabilities, and setup actions in one place.
- Model picker should show actual resolved model after `Auto` and warn when a profile has known bake-off failures.
- Command palette should execute more commands directly instead of logging unsupported commands.
- Error lane should use a reusable component with `role="alert"` and focus management.
- Long terminal output should be virtualized/collapsible and expose copy buttons.
- Inspector panels should have clearer empty states and keyboard shortcuts for panel switching.
- The UI should surface provider test status and last verification command result near the model selector.

## Provider-Specific Next Steps

- `google-adc`: try a smaller/faster model profile or a planner mode that separates file manifest generation from file content generation by default.
- `oci-genai`: add an OCI-specific compact planner adapter or use a stronger model if available; current endpoint returns `finish_reason=max_tokens` with empty content on several planner prompts.
- All providers: add a repeatable provider bake-off command so future changes can run this suite without manual temp-workspace scripting.

## Verification Run This Pass

- `python -m pytest tests/test_coder_runtime.py tests/test_shell_sandbox.py tests/test_cli.py -q`
- `ruff check src/agentheim_code src/memory src/tools/shell tests --output-format=full`
- `mypy src/agentheim_code src/memory src/tools/shell --follow-imports=skip`
- `npm --prefix apps/web run test -- --run`
- `npm --prefix apps/web run build`

