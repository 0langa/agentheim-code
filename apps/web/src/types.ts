export type CoderCommand = {
  id: string;
  label: string;
  cli: string;
  surface: string;
};

export type Session = {
  session_id: string;
  status: string;
  mode: string;
  workspace_root: string;
  model_selection?: {
    provider: string;
    model: string;
  };
};

export type TranscriptEntry = {
  role: string;
  content: string;
  timestamp?: string;
};

export type SessionView = {
  session: Session;
  queued_prompts: string[];
  available_commands: string[];
  transcript?: TranscriptEntry[];
  current_assistant_message?: string;
  current_user_prompt?: string;
};
