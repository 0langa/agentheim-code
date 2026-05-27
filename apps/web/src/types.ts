/**
 * Canonical frontend types.
 *
 * Generated OpenAPI types are used where the backend contract is explicit.
 * Hand-written shapes remain for richer UI-only models that the backend does
 * not yet describe precisely enough in OpenAPI.
 */

import type { components, paths } from "./generated/api-types";

type ApiResponse<
  Path extends keyof paths,
  Method extends keyof paths[Path],
> = paths[Path][Method] extends {
  responses: { 200: { content: { "application/json": infer Payload } } };
}
  ? Payload
  : never;

type ApiSchemas = components["schemas"];

export type CoderCommand = ApiResponse<"/api/coder/commands", "get">[number];
export type UiConfig = ApiResponse<"/api/config", "get">;
export type UiConfigPatch = ApiSchemas["UiConfigPatch"];
export type LocalProvider = ApiResponse<"/api/onboarding/local-providers", "get">[number];
export type FileEntry = ApiResponse<"/api/coder/files", "get">[number];
export type FileBrowsePage = ApiResponse<"/api/coder/files/browser", "get">;
export type CoderSessionCreateRequest = ApiSchemas["CoderSessionCreateRequest"];
export type CoderSessionMessageRequest = ApiSchemas["CoderSessionMessageRequest"];
export type ContextValidateRequest = ApiSchemas["ContextValidateRequest"];
export type TranscriptEntry = ApiSchemas["TranscriptEntryResponse"];
export type ContextPreviewItem = ApiSchemas["ContextPreviewResponse"];
export type ContextValidationResult = ApiSchemas["ContextValidationResponse"];
export type Session = ApiSchemas["SessionResponse"] & {
  pending_assistant_message?: string | null;
};
export type SessionEvent = ApiSchemas["SessionEventResponse"];
export type CommandResult = ApiSchemas["CommandResultResponse"];
export type SessionDiff = ApiSchemas["SessionDiffResponse"];
export type CoderApproval = ApiSchemas["ApprovalDisplayResponse"];
export type UsageData = ApiSchemas["UsageResponse"];
export type SessionView = Omit<
  ApiResponse<"/api/coder/sessions/{session_id}/view", "get">,
  "session"
> & {
  session: Session;
};
export type RunView = ApiSchemas["RunView"];

export type ModelBinding = {
  id: string;
  role: string;
  provider: string;
  model: string;
  display_name?: string;
  capabilities?: string[];
  health?: unknown;
  recommendations?: unknown;
};

export type ProviderProfile = {
  name: string;
  default?: boolean;
  providers: { id: string; kind: string; auth_mode: string; endpoint: string }[];
  models: ModelBinding[];
};

export type ModelOptions = {
  configured: boolean;
  default_profile?: string;
  profiles: ProviderProfile[];
  error?: string;
};

export type StructuredError = {
  error_code: string;
  message: string;
  technical_detail?: string;
  recovery_action?: string;
  related_event_id?: string;
};

export type ModeDescriptor = {
  id: "ask" | "code" | "review";
  label: string;
  description: string;
  edits_expected: boolean;
  legacy_aliases: string[];
};

export type TrustModeDescriptor = {
  id: "ask" | "read_only" | "workspace";
  label: string;
  description: string;
};

export type ModeCatalog = {
  modes: ModeDescriptor[];
  trust_modes: TrustModeDescriptor[];
};

export type TranscriptRole = "user" | "assistant" | "system";

export type WizardField = {
  name: string;
  label: string;
  type: "text" | "password" | "url";
  required: boolean;
  default?: string;
};

export type ProviderTemplate = {
  kind: string;
  display_name: string;
  endpoint: string;
  auth_mode: string;
  provider_type: string;
  capabilities: string[];
  docs_url: string;
  support_state: string;
  default_timeout_seconds?: number;
  wizard_fields: WizardField[];
  capabilities_meta?: {
    supports_connection_test: boolean;
    supports_remote_model_listing: boolean;
    supports_manual_model_entry: boolean;
    supports_endpoint_edit: boolean;
    supports_secret_rotation: boolean;
    discovery_mode: string;
    docs_url: string;
    notes: string;
  };
};

export type ManagementProviderAccount = {
  id: string;
  kind: string;
  endpoint: string;
  auth_mode: string;
  secret_ref?: string;
  has_secret?: boolean;
  timeout_seconds: number;
  headers: Record<string, string>;
  metadata: Record<string, unknown>;
  display_name?: string;
  notes?: string;
  disabled?: boolean;
  last_verified_at?: string;
  last_verified_status?: string;
  last_verified_error?: string;
  last_model_sync_at?: string;
};

export type ModelRole = "planner" | "executor" | "verifier";

export type ManagementModelBinding = {
  id: string;
  role: ModelRole;
  provider: string;
  model: string;
  display_name?: string;
  capabilities: string[];
  source?: string;
  remote_id?: string;
  enabled?: boolean;
  is_default?: boolean;
  context_window?: number;
  max_output_tokens?: number;
  supports_tools?: boolean;
  supports_vision?: boolean;
  supports_streaming?: boolean;
};

export type ManagementProfile = {
  name: string;
  providers: ManagementProviderAccount[];
  models: ManagementModelBinding[];
};

export type ManagementAccountTestResult = {
  ok: boolean;
  error?: string;
  latency_ms?: number;
  model?: string;
  usage?: unknown;
  usage_warning?: string;
  warning?: string;
};

export type DiscoveredModel = {
  id: string;
  display_name: string;
  provider_model_name: string;
  capabilities: string[];
  context_window?: number;
  max_output_tokens?: number;
  supports_tools?: boolean;
  supports_vision?: boolean;
  supports_streaming?: boolean;
  deprecation_status?: string;
  source?: string;
};
