import React from "react";
import { Play } from "lucide-react";
import type { FileEntry, ModelOptions } from "../types";

interface ComposerProps {
  prompt: string;
  selectedMode: string;
  selectedTrustMode: string;
  selectedProfile: string;
  selectedModel: string;
  modelOptions: ModelOptions | null;
  onPromptChange: (value: string) => void;
  onModeChange: (mode: string) => void;
  onTrustModeChange: (mode: string) => void;
  onProfileChange: (profile: string) => void;
  onModelChange: (model: string) => void;
  onSend: () => void;
  onCancel?: () => void;
  onRetry?: () => void;
  canRetry?: boolean;
  isSending?: boolean;
  selectedContextFiles?: string[];
  fileMatches?: FileEntry[];
  onContextQuery?: (query: string) => void;
  onContextAdd?: (path: string) => void;
  onContextRemove?: (path: string) => void;
}

const MODES = ["ask", "plan", "code", "review", "fix", "docs", "test"];
const TRUST_MODES = ["ask", "read_only", "workspace"];
const TRUST_LABELS: Record<string, string> = {
  read_only: "read_only - inspect only",
  ask: "ask - approve risky actions",
  workspace: "workspace - allow workspace edits",
};

export function Composer({
  prompt,
  selectedMode,
  selectedTrustMode,
  selectedProfile,
  selectedModel,
  modelOptions,
  onPromptChange,
  onModeChange,
  onTrustModeChange,
  onProfileChange,
  onModelChange,
  onSend,
  onCancel,
  onRetry,
  canRetry = false,
  isSending = false,
  selectedContextFiles = [],
  fileMatches = [],
  onContextQuery,
  onContextAdd,
  onContextRemove,
}: ComposerProps) {
  const activeProfile = modelOptions?.profiles?.find(
    (profile) => profile.name === selectedProfile,
  );
  const plannerModels =
    activeProfile?.models.filter((model) => model.role === "planner") ?? [];
  const mention = prompt.match(/(?:^|\s)@([^\s@]*)$/);
  const showFilePicker = Boolean(mention && fileMatches.length > 0);
  React.useEffect(() => {
    if (mention) onContextQuery?.(mention[1]);
  }, [mention?.[1], onContextQuery]);

  return (
    <footer className="composer">
      <div className="modes">
        {MODES.map((mode) => (
          <button
            key={mode}
            aria-pressed={mode === selectedMode}
            style={
              mode === selectedMode
                ? { background: "var(--accent)", borderColor: "var(--accent-hover)" }
                : undefined
            }
            onClick={() => onModeChange(mode)}
          >
            {mode}
          </button>
        ))}
        <select
          aria-label="Trust mode"
          value={selectedTrustMode}
          onChange={(event) => onTrustModeChange(event.target.value)}
        >
          {TRUST_MODES.map((mode) => (
            <option key={mode} value={mode}>
              {TRUST_LABELS[mode]}
            </option>
          ))}
        </select>
        <select
          aria-label="Provider profile"
          value={selectedProfile}
          onChange={(event) => onProfileChange(event.target.value)}
          disabled={!modelOptions?.configured}
        >
          <option value="auto">Auto profile</option>
          {modelOptions?.profiles?.map((profile) => (
            <option key={profile.name} value={profile.name}>
              {profile.name}
            </option>
          ))}
        </select>
        <select
          aria-label="Planner model"
          value={selectedModel}
          onChange={(event) => onModelChange(event.target.value)}
          disabled={!activeProfile}
        >
          <option value="auto">Auto model</option>
          {plannerModels.map((model) => (
            <option key={`${model.provider}:${model.model}`} value={model.model}>
              {model.provider} / {model.display_name ?? model.model}
            </option>
          ))}
        </select>
      </div>
      <textarea
        value={prompt}
        onChange={(event) => onPromptChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
            event.preventDefault();
            if (prompt.trim()) onSend();
          }
        }}
        placeholder="Ask Agentheim Code to build, fix, review, test, or explain..."
      />
      {(selectedContextFiles.length > 0 || showFilePicker) && (
        <div className="context-panel">
          {selectedContextFiles.length > 0 && (
            <div className="context-chips" aria-label="Selected context files">
              {selectedContextFiles.map((path) => (
                <button
                  key={path}
                  type="button"
                  className="context-chip"
                  aria-label={`Remove context ${path}`}
                  onClick={() => onContextRemove?.(path)}
                >
                  {path} x
                </button>
              ))}
            </div>
          )}
          {showFilePicker && (
            <div className="context-picker" aria-label="File context matches">
              {fileMatches.map((file) => (
                <button
                  key={file.path}
                  type="button"
                  onClick={() => onContextAdd?.(file.path)}
                >
                  {file.path}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
      <div className="composer-row">
        <span>Ctrl/Cmd+Enter sends · Shift+Enter adds a line</span>
        <div className="composer-actions">
          {canRetry && !isSending && (
            <button className="secondary" onClick={onRetry} type="button">
              Retry
            </button>
          )}
          {isSending ? (
            <button className="secondary" onClick={onCancel} type="button">
              Stop
            </button>
          ) : (
            <button className="primary" onClick={onSend} disabled={!prompt.trim()}>
              <Play size={16} /> Send
            </button>
          )}
        </div>
      </div>
    </footer>
  );
}
