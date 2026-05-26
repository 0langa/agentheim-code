import React, { useState } from "react";

import type { ManagementModelBinding, ManagementProviderAccount, ModelRole } from "../../types";
import { useModalA11y } from "../../hooks/useModalA11y";

interface ModelBindingEditorProps {
  model: ManagementModelBinding | null;
  providers: ManagementProviderAccount[];
  onClose: () => void;
  onSave: (model: ManagementModelBinding) => void;
}

export function ModelBindingEditor({ model, providers, onClose, onSave }: ModelBindingEditorProps) {
  const isEdit = Boolean(model);
  const preservedRole: ModelRole = model?.role === "executor" || model?.role === "verifier" ? model.role : "planner";
  const plannerRole: ModelRole = "planner";
  const editingInternalRole = preservedRole !== "planner";
  const [id, setId] = useState(model?.id || "");
  const [provider, setProvider] = useState(model?.provider || (providers[0]?.id ?? ""));
  const [modelName, setModelName] = useState(model?.model || "");
  const [displayName, setDisplayName] = useState(model?.display_name || "");
  const [capabilities, setCapabilities] = useState<string[]>(model?.capabilities || ["text"]);
  const [contextWindow, setContextWindow] = useState(model?.context_window || "");
  const [maxOutputTokens, setMaxOutputTokens] = useState(model?.max_output_tokens || "");
  const [supportsTools, setSupportsTools] = useState(model?.supports_tools || false);
  const [supportsVision, setSupportsVision] = useState(model?.supports_vision || false);
  const [supportsStreaming, setSupportsStreaming] = useState(model?.supports_streaming || false);
  const [error, setError] = useState<string | null>(null);

  const dialogRef = React.useRef<HTMLDivElement>(null);
  const titleId = React.useId();

  useModalA11y({ containerRef: dialogRef, onEscape: onClose });

  const canSave = id.trim() && provider.trim() && modelName.trim();

  const toggleCapability = (cap: string) => {
    setCapabilities((prev) =>
      prev.includes(cap) ? prev.filter((c) => c !== cap) : [...prev, cap]
    );
  };

  const save = () => {
    if (!canSave) return;
    setError(null);
    const binding: ManagementModelBinding = {
      id: id.trim(),
      provider: provider.trim(),
      model: modelName.trim(),
      role: editingInternalRole ? preservedRole : plannerRole,
      display_name: displayName.trim() || undefined,
      capabilities: capabilities.length ? capabilities : ["text"],
      context_window: contextWindow ? Number(contextWindow) : undefined,
      max_output_tokens: maxOutputTokens ? Number(maxOutputTokens) : undefined,
      supports_tools: supportsTools,
      supports_vision: supportsVision,
      supports_streaming: supportsStreaming,
      source: model?.source || "manual",
      enabled: model?.enabled ?? true,
      is_default: model?.is_default ?? false,
    };
    onSave(binding);
    onClose();
  };

  return (
    <div
      className="modal-overlay"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={dialogRef}
        className="modal-content"
        style={{ maxWidth: 520 }}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
      >
        <header className="modal-header">
          <h3 id={titleId}>{isEdit ? "Edit Model Binding" : "Add Model Binding"}</h3>
          <button onClick={onClose} aria-label="Close" type="button">
            ✕
          </button>
        </header>

        {error && <div className="error-banner">{error}</div>}

        <div className="form-group">
          <label htmlFor="mb-id">Binding ID</label>
          <input id="mb-id" type="text" value={id} onChange={(e) => setId(e.target.value)} disabled={isEdit} placeholder="gpt-4o-mini" />
        </div>

        <div className="form-group">
          <label htmlFor="mb-provider">Provider Account</label>
          <select id="mb-provider" value={provider} onChange={(e) => setProvider(e.target.value)}>
            {providers.map((p) => (
              <option key={p.id} value={p.id}>
                {p.display_name || p.id}
              </option>
            ))}
          </select>
        </div>

        <div className="form-group">
          <label htmlFor="mb-model">Model Name</label>
          <input id="mb-model" type="text" value={modelName} onChange={(e) => setModelName(e.target.value)} placeholder="gpt-4o-mini" />
          <small>The exact model identifier from the provider</small>
        </div>

        <div className="form-group">
          <label htmlFor="mb-display">Display Name</label>
          <input id="mb-display" type="text" value={displayName} onChange={(e) => setDisplayName(e.target.value)} placeholder="GPT-4o Mini" />
        </div>

        <div className="form-group">
          <label>Role</label>
          <div
            style={{
              padding: "0.65rem 0.8rem",
              border: "1px solid var(--border)",
              borderRadius: 8,
              background: "var(--surface-elevated)",
            }}
          >
            <strong>{editingInternalRole ? preservedRole : "planner"}</strong>
            <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 4 }}>
              {editingInternalRole
                ? "Legacy internal binding preserved for compatibility. New UI-created models use planner."
                : "Agentheim Code uses planner models for user-facing sessions."}
            </div>
          </div>
        </div>

        <div className="form-group">
          <label>Capabilities</label>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {["text", "json", "vision", "tools", "streaming", "embeddings", "rerank"].map((cap) => (
              <label key={cap} style={{ fontSize: 13, display: "flex", alignItems: "center", gap: 4 }}>
                <input type="checkbox" checked={capabilities.includes(cap)} onChange={() => toggleCapability(cap)} />
                {cap}
              </label>
            ))}
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <div className="form-group">
            <label htmlFor="mb-ctx">Context Window</label>
            <input id="mb-ctx" type="number" value={contextWindow} onChange={(e) => setContextWindow(e.target.value)} placeholder="128000" />
          </div>
          <div className="form-group">
            <label htmlFor="mb-out">Max Output Tokens</label>
            <input id="mb-out" type="number" value={maxOutputTokens} onChange={(e) => setMaxOutputTokens(e.target.value)} placeholder="4096" />
          </div>
        </div>

        <div className="form-group">
          <label style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
            <input type="checkbox" checked={supportsTools} onChange={(e) => setSupportsTools(e.target.checked)} />
            Supports Tools
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
            <input type="checkbox" checked={supportsVision} onChange={(e) => setSupportsVision(e.target.checked)} />
            Supports Vision
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <input type="checkbox" checked={supportsStreaming} onChange={(e) => setSupportsStreaming(e.target.checked)} />
            Supports Streaming
          </label>
        </div>

        <div className="wizard-actions">
          <button className="primary" onClick={save} disabled={!canSave} type="button">
            {isEdit ? "Save Changes" : "Add Model"}
          </button>
        </div>
      </div>
    </div>
  );
}
