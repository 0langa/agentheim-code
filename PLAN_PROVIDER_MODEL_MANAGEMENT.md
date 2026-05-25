# Provider And Model Management Delivery Plan

## Purpose

Agentheim Code already has the underlying storage concepts needed for serious provider and model management, but the current product surface does not expose them in a production-ready way. Users can create a provider profile through the onboarding/provider wizard, but ongoing management is still too limited, too profile-centric, and too hard to trust for real day-to-day use.

This plan defines how to deliver a fully usable, production-ready provider and model management experience in the current codebase. The end result should let a user:

- add, edit, test, remove, and switch providers without touching JSON
- add, edit, remove, discover, and sync hosted models
- assign sensible defaults globally and per session
- rotate secrets safely
- understand provider health and failure states
- work with both first-party provider integrations and generic OpenAI-compatible/self-hosted endpoints
- manage everything from one coherent product surface instead of scattered UI fragments

This plan is intentionally grounded in the current repository state rather than a greenfield rewrite.

## Current State Audit

### What already exists

- Shared provider/profile storage already exists in `src/config/config.py`.
- `ProfilesDocument`, `TeamProfile`, `ProviderAccount`, and `ModelBinding` already support:
  - multiple profiles
  - multiple provider accounts inside a profile
  - multiple model bindings inside a profile
- Secrets already go through the shared secret store abstraction.
- The backend already exposes basic provider routes in `src/agentheim_code/backend.py`:
  - `GET /api/coder/models`
  - `GET /api/providers/templates`
  - `GET /api/providers/profiles`
  - `GET /api/providers/wizard-templates`
  - `POST /api/providers/profiles`
  - `DELETE /api/providers/profiles/{name}`
  - `POST /api/providers/test`
- The frontend already has:
  - `ProviderWizard.tsx` for initial setup
  - session-level profile/model switching in `App.tsx`
  - a small provider summary in `Inspector.tsx`

### What is missing

- There is no dedicated management surface for existing providers and models.
- `ProviderWizard.tsx` is optimized for create-once onboarding, not lifecycle management.
- Provider profiles can only be created or deleted as a whole; they cannot be managed in a granular way.
- There is no backend CRUD for:
  - editing a provider profile
  - editing a provider account within a profile
  - editing a model binding within a profile
  - duplicating a profile
  - rotating a secret independently
  - syncing models from a remote provider
- There is no explicit provider-model discovery abstraction.
- There is no “manual fallback plus best-effort remote discovery” architecture for providers with different API capabilities.
- There is no first-class UX for:
  - changing the default profile
  - changing the default model for active coding
  - assigning model roles beyond the current planner-centric path
  - seeing provider/model health and last verification results

### Important architecture truth

The storage model is more capable than the current UX.

That means the best path is not to invent a new provider system. The best path is to:

- keep the existing profile/account/model concepts
- expand the backend contract around them
- refactor the wizard into reusable management components
- add a dedicated “Providers & Models” management workspace

## Product Goal

Deliver a **first-class “Providers & Models” management workspace** inside Agentheim Code that becomes the single home for:

- provider account setup
- model discovery
- model binding
- role/default assignment
- provider testing
- secret rotation
- health visibility
- profile switching and profile management

The current onboarding flow should reuse that same underlying UI and backend contract rather than maintaining a parallel special-case wizard forever.

## UX Direction

## Primary UX Decision

Use a **dedicated settings workspace/page** called **Providers & Models**, not just another modal.

Why this is the right fit for the current project:

- The configuration space is too large for a small modal.
- Users need to revisit it often, not only during onboarding.
- The product already has enough complexity that a proper management surface is warranted.
- The wizard can still exist, but only as a guided wrapper around the same underlying forms and APIs.

## Proposed Information Architecture

Add a top-level settings destination or full-screen settings view:

- `Providers & Models`

Inside that workspace:

- Profile header
  - profile selector
  - set default profile
  - duplicate profile
  - export/import profile
  - delete profile
- Accounts tab
  - list provider accounts in the selected profile
  - add account
  - edit account
  - rotate secret
  - test connection
  - refresh health
  - discover/sync models
- Models tab
  - list model bindings for the selected profile
  - add model manually
  - add discovered model
  - edit binding
  - remove binding
  - set default coding model
  - assign role(s)
  - group by provider
- Defaults & Roles tab
  - planner/default coding model
  - optional advanced roles such as reviewer/verifier/generator if surfaced
  - reset to safe defaults
- Diagnostics tab
  - last test result
  - provider health state
  - last successful sync
  - auth mode
  - docs link
  - known limitations

## UX Rules

- The onboarding wizard must reuse the same account/model editors and validation logic.
- Destructive actions must show explicit confirmation.
- Editing a provider account must not require recreating every model binding.
- Rotating a secret must not require re-entering non-secret fields.
- Providers that do not support remote model discovery must still feel first-class through manual model entry with smart guidance.
- Providers that do support discovery should offer one-click model import/sync.
- The active session selector should remain lightweight and fast; the heavy management work belongs in the dedicated workspace.

## Domain Model And Architecture Plan

## Keep The Existing Core Concepts

Build on these existing concepts:

- `ProfilesDocument`
- `TeamProfile`
- `ProviderAccount`
- `ModelBinding`
- `ProviderTemplate`

Do not replace them with a fundamentally different abstraction unless implementation reveals a hard blocker.

## Add A Discovery And Management Layer

Introduce a management layer between raw storage and the web API.

Recommended new backend modules:

- `src/agentheim_code/provider_management.py`
  - profile CRUD
  - provider account CRUD
  - model binding CRUD
  - secret rotation helpers
  - import/export helpers
- `src/agentheim_code/provider_discovery.py`
  - account capability inspection
  - remote model listing
  - normalization into a common model-discovery shape
- `src/agentheim_code/provider_capabilities.py`
  - template/provider capability matrix
  - discovery mode metadata
  - manual-vs-remote rules

## Extend Existing Models Carefully

Add optional fields rather than breaking the existing shape if possible.

Recommended optional additions to `ProviderAccount`:

- `display_name: str | None`
- `notes: str | None`
- `disabled: bool`
- `last_verified_at: str | None`
- `last_verified_status: str | None`
- `last_verified_error: str | None`
- `last_model_sync_at: str | None`
- `metadata.discovery_mode`
- `metadata.supports_model_listing`

Recommended optional additions to `ModelBinding`:

- `source: Literal["manual", "discovered"]`
- `remote_id: str | None`
- `enabled: bool`
- `is_default: bool`
- `context_window: int | None`
- `max_output_tokens: int | None`
- `supports_tools: bool | None`
- `supports_vision: bool | None`
- `supports_streaming: bool | None`
- `metadata.sync_fingerprint`

If these additions fit cleanly into existing optional fields and metadata, avoid a storage-version migration. Only bump the profile document version if the final implementation truly requires a structural rewrite.

## Provider Discovery Strategy

The product cannot rely on one discovery path for every provider. It needs a capability-driven model.

Each provider template should declare:

- `supports_connection_test`
- `supports_remote_model_listing`
- `supports_manual_model_entry`
- `supports_endpoint_edit`
- `supports_secret_rotation`
- `discovery_mode`

Recommended `discovery_mode` values:

- `remote_list`
- `remote_list_with_manual_fallback`
- `manual_only`
- `local_scan`
- `sdk_hybrid`

## “Any Provider” Strategy

A truly production-usable result does **not** mean every provider gets bespoke perfect native support on day one.

It means:

- every built-in provider template in `src/config/config.py` gets a defined management path
- providers with official model-list APIs get remote discovery
- providers without reliable model-list APIs get manual entry plus validation
- OpenAI-compatible custom endpoints become the universal escape hatch for unsupported hosted providers

That is the right product definition for “basically any provider out there.”

## Backend API Plan

## Keep Existing Routes Stable Where Possible

Keep current endpoints working for backward compatibility:

- `GET /api/coder/models`
- `GET /api/providers/templates`
- `GET /api/providers/profiles`
- `GET /api/providers/wizard-templates`
- `POST /api/providers/profiles`
- `DELETE /api/providers/profiles/{name}`
- `POST /api/providers/test`

Refactor internals so these become compatibility wrappers over the new management services where practical.

## Add New Management Endpoints

Recommended API surface:

### Profiles

- `GET /api/provider-management/profiles`
- `POST /api/provider-management/profiles`
- `GET /api/provider-management/profiles/{profile_name}`
- `PATCH /api/provider-management/profiles/{profile_name}`
- `DELETE /api/provider-management/profiles/{profile_name}`
- `POST /api/provider-management/profiles/{profile_name}/duplicate`
- `POST /api/provider-management/profiles/{profile_name}/set-default`
- `GET /api/provider-management/profiles/{profile_name}/export`
- `POST /api/provider-management/profiles/import`

### Provider Accounts

- `POST /api/provider-management/profiles/{profile_name}/accounts`
- `PATCH /api/provider-management/profiles/{profile_name}/accounts/{account_id}`
- `DELETE /api/provider-management/profiles/{profile_name}/accounts/{account_id}`
- `POST /api/provider-management/profiles/{profile_name}/accounts/{account_id}/test`
- `POST /api/provider-management/profiles/{profile_name}/accounts/{account_id}/rotate-secret`
- `POST /api/provider-management/profiles/{profile_name}/accounts/{account_id}/discover-models`
- `GET /api/provider-management/profiles/{profile_name}/accounts/{account_id}/discovered-models`

### Model Bindings

- `POST /api/provider-management/profiles/{profile_name}/models`
- `PATCH /api/provider-management/profiles/{profile_name}/models/{binding_id}`
- `DELETE /api/provider-management/profiles/{profile_name}/models/{binding_id}`
- `POST /api/provider-management/profiles/{profile_name}/models/{binding_id}/set-default`
- `POST /api/provider-management/profiles/{profile_name}/models/{binding_id}/assign-role`
- `POST /api/provider-management/profiles/{profile_name}/models/import-discovered`

### Templates And Capabilities

- `GET /api/provider-management/templates`
- `GET /api/provider-management/templates/{template_id}`

## Response Design Principles

- Use generated frontend types from backend schemas.
- Return redacted secrets only.
- Include capability flags in account/model responses so the frontend does not need to guess which actions to show.
- Include verification/sync timestamps and status summaries.
- Return structured validation errors for:
  - invalid endpoint
  - missing auth field
  - duplicate provider id
  - duplicate model binding id
  - unknown model binding role
  - provider/model mismatch
  - discovery unsupported

## Provider Discovery Adapter Plan

Create a backend adapter interface such as:

- `list_remote_models(account, template) -> list[DiscoveredModel]`
- `test_account(account, template, sample_model?) -> VerificationResult`
- `normalize_remote_model(raw, template) -> DiscoveredModel`

Recommended `DiscoveredModel` fields:

- `id`
- `display_name`
- `provider_model_name`
- `capabilities`
- `context_window`
- `max_output_tokens`
- `supports_tools`
- `supports_vision`
- `supports_streaming`
- `deprecation_status`
- `source`

## Research Requirements For Discovery

The implementation agent must research the current official documentation for each provider family before finalizing discovery logic.

Only use primary or official documentation for technical behavior:

- OpenAI
- Azure OpenAI / Azure AI Foundry
- Anthropic
- Google Gemini API
- Vertex AI
- AWS Bedrock
- OCI Generative AI
- Cohere
- Perplexity
- local/self-hosted OpenAI-compatible providers such as Ollama, LM Studio, vLLM, TGI, llama.cpp

Do not assume that “all OpenAI-compatible providers” implement `/models` correctly. Treat that as a capability to verify, not a promise.

## Frontend Implementation Plan

## Replace The Current Fragmented UX

Keep `ProviderWizard.tsx`, but refactor it into a guided wrapper around shared components rather than the only real provider UI.

Recommended new frontend components:

- `apps/web/src/components/providers/ProviderManagementWorkspace.tsx`
- `apps/web/src/components/providers/ProfileSelector.tsx`
- `apps/web/src/components/providers/ProfileActions.tsx`
- `apps/web/src/components/providers/ProviderAccountsTab.tsx`
- `apps/web/src/components/providers/ProviderAccountCard.tsx`
- `apps/web/src/components/providers/ProviderAccountEditor.tsx`
- `apps/web/src/components/providers/ProviderAccountTestDialog.tsx`
- `apps/web/src/components/providers/ModelBindingsTab.tsx`
- `apps/web/src/components/providers/ModelBindingTable.tsx`
- `apps/web/src/components/providers/ModelBindingEditor.tsx`
- `apps/web/src/components/providers/ModelDiscoveryDialog.tsx`
- `apps/web/src/components/providers/ProviderHealthBadge.tsx`
- `apps/web/src/components/providers/DefaultsAndRolesTab.tsx`
- `apps/web/src/components/providers/ProviderDiagnosticsTab.tsx`

Recommended frontend utility additions:

- `apps/web/src/lib/provider-actions.ts`
- `apps/web/src/lib/provider-labels.ts`
- `apps/web/src/generated/api-types.ts` regeneration as needed

## Integrate Into The Existing App Shell

Update:

- `apps/web/src/App.tsx`
- `apps/web/src/components/Inspector.tsx`
- `apps/web/src/types.ts`
- `apps/web/src/api.ts`

Target integration:

- replace the tiny provider summary in `Inspector.tsx` with an entry point into the full management workspace
- preserve quick session switching in the main app
- open the full management workspace from:
  - settings
  - onboarding
  - empty-provider state
  - provider-related errors

## Required Frontend Behaviors

- Adding a provider account must support:
  - template selection
  - endpoint editing when allowed
  - auth-mode-specific fields
  - test before save
  - save without immediate model creation when appropriate
- Adding models must support:
  - discover from provider
  - manual entry
  - bulk import from discovered list
  - per-model edit after import
- Editing must support:
  - account rename/display rename
  - endpoint changes
  - auth changes when valid
  - default model changes
  - role changes
- Deleting must support:
  - remove only model binding
  - remove provider account and optionally all dependent model bindings
- Switching must support:
  - default profile changes
  - active session model changes
  - default coding model changes
- Diagnostics must show:
  - last verified time
  - health state
  - last error
  - last sync time

## Reuse Rather Than Duplicate

The onboarding flow must reuse the same account editor and model selection/editor components.

The implementation should reduce, not increase, duplicated provider logic between:

- onboarding
- settings
- session switching
- backend provider routes

## Runtime Integration Plan

The runtime currently centers planner/default model selection through `list_model_options()` and session model updates.

This work should:

- preserve current session selection behavior
- improve default selection clarity
- expose richer role bindings in a controlled way

Recommended staged approach:

- Required for this feature:
  - one clear “default coding model” per profile
  - explicit provider/model choice for the active session
- Optional advanced path if implementation is stable:
  - expose advanced roles such as reviewer/verifier/generator in the management workspace
  - keep them in an “Advanced roles” section to avoid confusing the primary product UX

## Migration And Compatibility Plan

- Preserve existing `providers.json` data.
- Load older profiles without requiring user action.
- If optional fields are introduced, default them safely during load.
- Only migrate the stored document version if the final shape requires it.
- Maintain compatibility for current routes long enough for the frontend refactor to land cleanly.

## Security And Trust Requirements

- Never return raw secrets to the frontend.
- Secret rotation must be a dedicated backend operation.
- Redact auth-sensitive headers in diagnostics and UI responses.
- Provider test endpoints must not log secrets.
- Destructive profile/account/model operations must require explicit confirmation.
- Imported profile data must be validated and sanitized before persistence.

## Phased Delivery Plan

## Phase 0: Research, Contract Freeze, And UX Spec

Deliverables:

- audit live provider templates in `src/config/config.py`
- research official provider model-list and auth/test flows where applicable
- define capability matrix for every built-in template
- freeze terminology:
  - profile
  - provider account
  - model binding
  - discovered model
  - default coding model
- confirm final UX layout and interactions

Acceptance:

- a written capability matrix exists for all built-in provider templates
- discovery strategy is explicitly defined per provider family
- frontend terminology is no longer ambiguous

## Phase 1: Backend Management Service And API Foundation

Deliverables:

- add `provider_management.py`
- add `provider_discovery.py`
- move profile/account/model CRUD logic out of ad hoc wizard helpers
- add new provider-management API routes
- add structured validation and structured errors
- keep old endpoints working

Acceptance:

- provider profiles can be created, updated, duplicated, exported, imported, and deleted
- provider accounts can be created, updated, tested, rotated, and deleted
- model bindings can be created, updated, defaulted, role-assigned, and deleted
- backend tests cover success and failure paths

## Phase 2: Dedicated Providers & Models Workspace

Deliverables:

- build the new management workspace
- add profile selector and actions
- add Accounts tab
- add Models tab
- add Defaults & Roles tab
- add Diagnostics tab
- connect the workspace to the new backend APIs
- keep onboarding using the same editors/components

Acceptance:

- a user can manage providers and models without the old wizard being their only option
- the UI supports edit/remove/test/rotate/switch flows end-to-end
- quick session switching still works

## Phase 3: Remote Model Discovery And Sync

Deliverables:

- implement discovery adapters for provider families that support it
- implement hybrid/manual fallback for providers that do not
- allow bulk import from discovered models
- allow re-sync with change reconciliation
- store last sync status and timestamps

Acceptance:

- remote listing works where officially supported
- unsupported providers degrade gracefully to manual entry
- a user can discover and import hosted models without retyping everything

## Phase 4: Production Hardening, Role Defaults, And Trust Polish

Deliverables:

- better health/status surfaces
- better destructive-action UX
- profile import/export validation
- role/default assignment polish
- improved help text and docs links
- supportability improvements in diagnostics

Acceptance:

- destructive and recovery flows are understandable
- users can confidently switch defaults and recover from bad provider config
- the feature feels like a polished product surface, not an admin backdoor

## Phase 5: Docs, QA, Packaging, And Release Readiness

Deliverables:

- docs rewrite/update
- screenshots
- API reference updates
- troubleshooting updates
- onboarding/provider docs sync
- release checklist refresh
- full verification wall

Acceptance:

- docs match the code
- browser and desktop flows both work
- no baseline provider-management path requires editing files manually

## File Targets

Likely backend files:

- `src/agentheim_code/backend.py`
- `src/agentheim_code/provider_wizard.py`
- `src/agentheim_code/provider_management.py`
- `src/agentheim_code/provider_discovery.py`
- `src/agentheim_code/provider_capabilities.py`
- `src/config/config.py`
- `src/workflows/coder/runtime.py`
- related tests under `tests/`

Likely frontend files:

- `apps/web/src/App.tsx`
- `apps/web/src/api.ts`
- `apps/web/src/types.ts`
- `apps/web/src/components/Inspector.tsx`
- `apps/web/src/components/ProviderWizard.tsx`
- new `apps/web/src/components/providers/*`
- related tests under `apps/web/src/**/__tests__`
- Playwright specs under `apps/web/e2e/`

Docs likely to update:

- `README.md`
- `docs/PROVIDERS.md`
- `docs/USER_GUIDE.md`
- `docs/API_REFERENCE.md`
- `docs/TROUBLESHOOTING.md`
- `docs/ARCHITECTURE.md`
- `docs/RELEASE_CHECKLIST.md`
- `PRODUCT_ROADMAP.md`
- `CHANGELOG.md`

## Testing Plan

## Backend Tests

Add or expand tests for:

- profile CRUD
- provider account CRUD
- model binding CRUD
- default profile changes
- default model changes
- secret rotation
- provider test endpoint
- model discovery normalization
- manual fallback behavior
- import/export validation
- invalid provider/model references
- structured error payloads

## Frontend Tests

Add or expand tests for:

- workspace rendering
- provider account editor validation
- model binding editor validation
- discovery/import dialogs
- account test flow
- rotate secret flow
- delete confirmation flow
- default switch flow
- stale request handling
- empty/error/loading states

## Playwright E2E

At minimum cover:

- fresh user adds an OpenAI-compatible provider and manual model
- user tests provider, saves it, and starts a session
- user discovers models from a provider that supports listing
- user imports discovered models and sets a default
- user edits provider endpoint/credentials
- user deletes a model binding
- user deletes a provider account with dependent-model warning
- browser path and packaged desktop path both keep working

## Verification Wall

Minimum final verification commands:

- `ruff check src/agentheim_code src/memory src/tools/shell tests/`
- `ruff format --check src/agentheim_code src/memory src/tools/shell tests/`
- `mypy src/agentheim_code src/memory src/tools/shell --follow-imports=skip`
- `pytest --cov --cov-report=term-missing --cov-fail-under=80 -m "not integration"`
- `npm --prefix apps/web run test -- --run`
- `npm --prefix apps/web run build`
- `npm --prefix apps/web run e2e`
- `cd apps/desktop/src-tauri && cargo test`
- `python -m build --wheel`
- `powershell -ExecutionPolicy Bypass -File scripts/package-beta.ps1`

Also perform real product smoke checks:

- launch backend and confirm health/version
- open the browser UI and exercise provider management
- launch the packaged desktop app and exercise provider management

## Documentation Requirements

The implementation is not done until docs are updated to match reality.

Required docs outcomes:

- `docs/PROVIDERS.md` becomes the main user/operator guide for provider and model management
- `README.md` mentions the dedicated Providers & Models workspace
- `docs/API_REFERENCE.md` documents the new management endpoints
- `docs/USER_GUIDE.md` covers adding, editing, switching, testing, and removing providers/models
- `docs/TROUBLESHOOTING.md` covers failed auth, missing model-list permissions, unsupported discovery, and manual fallback flows
- `docs/ARCHITECTURE.md` explains the profile/account/model/discovery architecture
- `docs/RELEASE_CHECKLIST.md` includes fresh verification output and provider-management smoke checks

## Definition Of Done

This feature is only done when all of the following are true:

- provider and model management has a dedicated first-class workspace
- onboarding reuses the same underlying components and validation logic
- users can add, edit, delete, test, rotate, switch, and inspect provider accounts
- users can add, edit, delete, discover, sync, and switch models
- default profile and default coding model are easy to understand and change
- all built-in provider templates have a defined supported path
- unsupported or partially supported providers still work through a clear manual/custom flow
- browser and desktop paths both work
- docs are truthful
- tests and verification are green

## Explicit Non-Goals

To keep the feature disciplined, do not treat these as mandatory unless they become necessary during implementation:

- building a marketplace-style provider plugin system
- perfect bespoke native discovery for every provider on day one
- exposing every advanced model role in the main UX if it harms clarity
- replacing the existing storage system wholesale

## Recommended Commit Boundaries

- `feat: add provider management backend services and api`
- `feat: add providers and models management workspace`
- `feat: add provider model discovery and sync flows`
- `feat: polish provider defaults roles and diagnostics`
- `docs: sync provider management docs and release checklist`

## Handoff Notes

The next implementation agent should treat this as a full product-delivery task, not a small feature patch.

The right outcome is:

- one coherent provider/model management story
- strong manual fallback for generic/custom endpoints
- best-effort discovery for built-in provider families
- minimal duplicated logic
- production-ready testing and docs
