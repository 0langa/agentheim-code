export type CoderCommand = {
  id: string;
  label: string;
  cli: string;
  surface: string;
};

export type ModelBinding = {
  id: string;
  role: string;
  provider: string;
  model: string;
  display_name?: string;
  capabilities?: string[];
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
};

export type SessionDiff = {
  path?: string;
  status?: string;
};

export type SessionView = {
  session: Session;
  queued_prompts: string[];
  available_commands: string[];
  events?: SessionEvent[];
  approvals?: unknown[];
  diffs?: SessionDiff[];
  command_results?: CommandResult[];
  artifacts?: string[];
};

// Provider wizard types
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
