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

export type TranscriptEntry = {
  role: string;
  content: string;
  timestamp?: string;
};

export type StructuredError = {
  error_code: string;
  message: string;
  technical_detail?: string;
  recovery_action?: string;
  related_event_id?: string;
};

export type ContextPreviewItem = {
  path: string;
  status: string;
  size: number;
  preview: string;
  truncation_reason: string;
  token_estimate: number;
};

export type ContextValidationResult = {
  items: ContextPreviewItem[];
  errors: string[];
  total_token_estimate: number;
};

export type TranscriptRole = "user" | "assistant" | "system";

export type Session = {
  session_id: string;
  status: string;
  mode: string;
  trust_mode?: string;
  workspace_root: string;
  model_selection?: {
    profile?: string;
    provider: string;
    model: string;
    actual_provider?: string | null;
    actual_model?: string | null;
  };
  transcript?: TranscriptEntry[];
  current_user_prompt?: string;
  current_assistant_message?: string;
  changed_files?: string[];
  repair_attempts?: number;
  last_failure_reason?: string;
  last_verification_command?: string[];
  last_verification_exit_code?: number | null;
};

export type SessionEvent = {
  event_id?: string;
  type?: string;
  message?: string;
  timestamp?: string;
  payload?: Record<string, unknown>;
};

export type CommandResult = {
  command?: string[];
  exit_code?: number | null;
  status?: string;
  stdout?: string;
  stderr?: string;
  timestamp?: string;
};

export type SessionDiff = {
  path?: string;
  status?: string;
  before?: string;
  after?: string;
};

export type CoderApproval = {
  request_id: string;
  tool_id: string;
  risk_level: string;
  reason: string;
  status: string;
  params?: Record<string, unknown>;
  target?: string;
  action_kind?: string;
};

export type UsageData = {
  session_id: string;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  estimated_cost_usd: number | null;
  calls: number;
  breakdown: {
    sequence: number;
    timestamp: string;
    model: string | null;
    provider: string | null;
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
    estimated_cost_usd: number | null;
  }[];
};

export type SessionView = {
  session: Session;
  queued_prompts: string[];
  available_commands: string[];
  events?: SessionEvent[];
  approvals?: CoderApproval[];
  diffs?: SessionDiff[];
  command_results?: CommandResult[];
  artifacts?: string[];
};

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
