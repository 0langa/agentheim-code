import React from "react";
import { Play, AlertTriangle } from "lucide-react";
import type {
  ContextPreviewItem,
  FileEntry,
  ModeCatalog,
  ModelOptions,
} from "../types";

interface ComposerProps {
  prompt: string;
  selectedMode: string;
  selectedTrustMode: string;
  selectedProfile: string;
  selectedModel: string;
  modelOptions: ModelOptions | null;
  modeCatalog: ModeCatalog | null;
  onPromptChange: (value: string) => void;
  onModeChange: (mode: string) => void;
  onTrustModeChange: (mode: string) => void;
  onProfileChange: (profile: string) => void;
  onModelChange: (model: string) => void;
  onSend: () => void;
  canSend?: boolean;
  sendDisabledReason?: string | null;
  onCancel?: () => void;
  onRetry?: () => void;
  canRetry?: boolean;
  isSending?: boolean;
  selectedContextFiles?: string[];
  fileMatches?: FileEntry[];
  onContextQuery?: (query: string) => void;
  onContextAdd?: (path: string) => void;
  onContextRemove?: (path: string) => void;
  contextPreviews?: ContextPreviewItem[];
}

const MODES = ["ask", "code", "review"];
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
  modeCatalog,
  onPromptChange,
  onModeChange,
  onTrustModeChange,
  onProfileChange,
  onModelChange,
  onSend,
  canSend = true,
  sendDisabledReason = null,
  onCancel,
  onRetry,
  canRetry = false,
  isSending = false,
  selectedContextFiles = [],
  fileMatches = [],
  onContextQuery,
  onContextAdd,
  onContextRemove,
  contextPreviews = [],
}: ComposerProps) {
  const activeProfile = modelOptions?.profiles?.find(
    (profile) => profile.name === selectedProfile,
  );
  const plannerModels =
    activeProfile?.models.filter((model) => model.role === "planner") ?? [];
  const selectedModeInfo = modeCatalog?.modes.find((mode) => mode.id === selectedMode);
  const selectedTrustInfo = modeCatalog?.trust_modes.find((mode) => mode.id === selectedTrustMode);

  const modelHealth = (model: (typeof plannerModels)[number]) => {
    const h = model.health as {
      available?: boolean;
      bakeoff_passed?: boolean;
      bakeoff_degraded?: boolean;
      known_limitations?: string[];
    } | null;
    if (!h) return null;
    if (!h.available) return { level: "error", text: "Provider unavailable" };
    if (!h.bakeoff_passed) return { level: "warning", text: "No bake-off pass" };
    if (h.bakeoff_degraded) return { level: "warning", text: "Degraded in bake-off" };
    if (h.known_limitations?.length) return { level: "warning", text: h.known_limitations[0] };
    return null;
  };
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
            type="button"
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
          {plannerModels.map((model) => {
            const health = modelHealth(model);
            return (
              <option key={`${model.provider}:${model.model}`} value={model.model}>
                {model.provider} / {model.display_name ?? model.model}
                {health ? ` (${health.text})` : ""}
              </option>
            );
          })}
        </select>
      </div>
      {(selectedModeInfo || selectedTrustInfo) && (
        <div className="composer-hint" aria-live="polite">
          {selectedModeInfo && (
            <span>
              <strong>{selectedModeInfo.label}:</strong> {selectedModeInfo.description}
            </span>
          )}
          {selectedTrustInfo && (
            <span>
              <strong>Trust:</strong> {selectedTrustInfo.description}
            </span>
          )}
        </div>
      )}
      <textarea
        aria-label="Prompt"
        value={prompt}
        onChange={(event) => onPromptChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
            event.preventDefault();
            if (prompt.trim() && canSend) onSend();
          }
        }}
        placeholder="Ask Agentheim Code to help, build, review, or explain..."
      />
      {(selectedContextFiles.length > 0 || showFilePicker || contextPreviews.length > 0) && (
        <div className="context-panel">
          {contextPreviews.length > 0 && (
            <div className="context-previews" aria-label="Context file previews">
              <div style={{ fontSize: "11px", color: "var(--muted)", marginBottom: "4px" }}>
                Context{" "}
                {contextPreviews.filter((i) => i.status === "ok").reduce((s, i) => s + i.token_estimate, 0)}{" "}
                tokens estimated
              </div>
              {contextPreviews.map((item) => (
                <div
                  key={item.path}
                  className="context-preview-item"
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "6px",
                    padding: "2px 0",
                    fontSize: "12px",
                    color: item.status === "ok" ? "inherit" : "var(--error)",
                  }}
                >
                  {item.status !== "ok" && <AlertTriangle size={12} />}
                  <span style={{ fontFamily: "monospace" }}>{item.path}</span>
                  <span style={{ color: "var(--muted)" }}>
                    {item.status === "ok"
                      ? `${item.token_estimate} tokens`
                      : item.status}
                  </span>
                  <button
                    type="button"
                    aria-label={`Remove context ${item.path}`}
                    onClick={() => onContextRemove?.(item.path)}
                    style={{ marginLeft: "auto", fontSize: "11px" }}
                  >
                    Remove
                  </button>
                </div>
              ))}
            </div>
          )}
          {!contextPreviews.length && selectedContextFiles.length > 0 && (
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
            <button
              className="primary"
              onClick={onSend}
              disabled={!prompt.trim() || !canSend}
              title={
                !prompt.trim()
                  ? "Enter a prompt to send"
                  : !canSend
                    ? (sendDisabledReason ?? "Create or select a session first")
                    : undefined
              }
            >
              <Play size={16} /> Send
            </button>
          )}
        </div>
      </div>
      {!canSend && prompt.trim() && (
        <div
          role="status"
          aria-live="polite"
          style={{ fontSize: "12px", color: "var(--warning)", marginTop: "6px" }}
        >
          {sendDisabledReason ?? "Create or select a session first before sending."}
        </div>
      )}
    </footer>
  );
}
