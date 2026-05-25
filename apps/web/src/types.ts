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
export type Session = ApiSchemas["SessionResponse"];
export type SessionEvent = ApiSchemas["SessionEventResponse"];
export type CommandResult = ApiSchemas["CommandResultResponse"];
export type SessionDiff = ApiSchemas["SessionDiffResponse"];
export type CoderApproval = ApiSchemas["ApprovalDisplayResponse"];
export type UsageData = ApiSchemas["UsageResponse"];
export type SessionView = ApiResponse<"/api/coder/sessions/{session_id}/view", "get">;
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
  wizard_fields: WizardField[];
};
