import React, { useEffect, useState } from "react";

import { api } from "../api";
import type { ProviderTemplate } from "../types";

interface ProviderWizardProps {
  onClose: () => void;
  onSaved: () => void;
}

const STEPS = ["select", "configure", "test"] as const;
type Step = (typeof STEPS)[number];

export function ProviderWizard({ onClose, onSaved }: ProviderWizardProps) {
  const [step, setStep] = useState<Step>("select");
  const [templates, setTemplates] = useState<ProviderTemplate[]>([]);
  const [selectedTemplate, setSelectedTemplate] = useState<ProviderTemplate | null>(null);
  const [profileName, setProfileName] = useState("");
  const [providerId, setProviderId] = useState("");
  const [modelId, setModelId] = useState("");
  const [fields, setFields] = useState<Record<string, string>>({});
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{
    ok: boolean;
    message?: string;
    error?: string;
    latency_ms?: number;
    model?: string;
    usage?: { input_tokens: number; output_tokens: number; total_tokens: number; estimated_cost_usd?: number };
    usage_warning?: string;
    warning?: string;
  } | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<ProviderTemplate[]>("/providers/wizard-templates")
      .then(setTemplates)
      .catch((err) => setError(err.message));
  }, []);

  const selectTemplate = (template: ProviderTemplate) => {
    setSelectedTemplate(template);
    const defaults: Record<string, string> = {};
    for (const field of template.wizard_fields) {
      if (field.default) defaults[field.name] = field.default;
    }
    if (template.endpoint && template.endpoint !== "-") {
      defaults.endpoint = template.endpoint;
    }
    setFields(defaults);
    setProviderId(template.kind);
    setProfileName(template.display_name);
    setStep("configure");
    setTestResult(null);
  };

  const updateField = (name: string, value: string) => {
    setFields((prev) => ({ ...prev, [name]: value }));
    setTestResult(null);
  };

  const runTest = async () => {
    if (!selectedTemplate) return;
    setTesting(true);
    setTestResult(null);
    try {
      const result = await api<{
        ok: boolean;
        error?: string;
        message?: string;
        latency_ms?: number;
        usage?: { input_tokens: number; output_tokens: number; total_tokens: number; estimated_cost_usd?: number };
        usage_warning?: string;
        warning?: string;
      }>("/providers/test", {
        method: "POST",
        body: JSON.stringify({
          provider_kind: selectedTemplate.kind,
          fields,
          model_id: modelId,
        }),
      });
      setTestResult(result);
    } catch (err) {
      setTestResult({ ok: false, error: err instanceof Error ? err.message : String(err) });
    } finally {
      setTesting(false);
    }
  };

  const save = async () => {
    if (!selectedTemplate) return;
    setSaving(true);
    try {
      await api("/providers/profiles", {
        method: "POST",
        body: JSON.stringify({
          name: profileName,
          provider_kind: selectedTemplate.kind,
          provider_id: providerId,
          model_id: modelId,
          fields,
          set_as_default: true,
        }),
      });
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  };

  const canSave =
    profileName.trim() &&
    providerId.trim() &&
    modelId.trim() &&
    selectedTemplate?.wizard_fields.every((f) => !f.required || fields[f.name]?.trim());

  return (
    <div
      className="modal-overlay"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      role="dialog"
      aria-modal="true"
      aria-label="Add AI Provider"
    >
      <div className="modal-content" style={{ maxWidth: 560 }}>
        <header className="modal-header">
          <h2>Add AI Provider</h2>
          <button onClick={onClose} aria-label="Close">
            ✕
          </button>
        </header>

        {error && (
          <div className="error-banner" role="alert">
            {error}
          </div>
        )}

        {step === "select" && (
          <div className="wizard-step">
            <p style={{ marginBottom: 16, color: "var(--muted)" }}>
              Choose your AI provider. You can add more later.
            </p>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))",
                gap: 12,
              }}
            >
              {templates.map((template) => (
                <button
                  key={template.kind}
                  className="provider-card"
                  onClick={() => selectTemplate(template)}
                  title={template.display_name}
                >
                  <strong>{template.display_name}</strong>
                  <span style={{ fontSize: 11, color: "var(--muted)" }}>
                    {template.capabilities.slice(0, 3).join(" · ")}
                  </span>
                  {template.support_state !== "stable" && (
                    <span className="badge">{template.support_state}</span>
                  )}
                </button>
              ))}
              <button
                className="provider-card"
                onClick={() =>
                  selectTemplate({
                    kind: "openai_compatible",
                    display_name: "Custom Endpoint",
                    endpoint: "https://example.com/v1",
                    auth_mode: "bearer",
                    provider_type: "openai_compatible",
                    capabilities: ["text", "json", "streaming"],
                    docs_url: "",
                    support_state: "beta",
                    wizard_fields: [
                      { name: "endpoint", label: "Base URL", type: "url", required: true },
                      { name: "api_key", label: "API Key", type: "password", required: false },
                    ],
                  })
                }
                title="Custom OpenAI-compatible endpoint"
              >
                <strong>Custom Endpoint</strong>
                <span style={{ fontSize: 11, color: "var(--muted)" }}>
                  Any OpenAI-compatible API
                </span>
              </button>
            </div>
          </div>
        )}

        {step === "configure" && selectedTemplate && (
          <div className="wizard-step">
            <div style={{ marginBottom: 16 }}>
              <button className="link-button" onClick={() => setStep("select")}>
                ← Back to providers
              </button>
            </div>

            <div className="form-group">
              <label htmlFor="profile-name">Profile Name</label>
              <input
                id="profile-name"
                type="text"
                value={profileName}
                onChange={(e) => setProfileName(e.target.value)}
                placeholder="My OpenAI"
              />
            </div>

            <div className="form-group">
              <label htmlFor="provider-id">Provider ID</label>
              <input
                id="provider-id"
                type="text"
                value={providerId}
                onChange={(e) => setProviderId(e.target.value)}
                placeholder={selectedTemplate.kind}
              />
              <small>A short identifier used internally</small>
            </div>

            <div className="form-group">
              <label htmlFor="model-id">Model ID</label>
              <input
                id="model-id"
                type="text"
                value={modelId}
                onChange={(e) => setModelId(e.target.value)}
                placeholder="gpt-4.1"
              />
              <small>
                The exact model name from the provider{" "}
                <a href={selectedTemplate.docs_url} target="_blank" rel="noreferrer">
                  (docs ↗)
                </a>
              </small>
            </div>

            {selectedTemplate.wizard_fields.map((field) => (
              <div className="form-group" key={field.name}>
                <label htmlFor={`field-${field.name}`}>
                  {field.label}
                  {field.required && <span className="required">*</span>}
                </label>
                <input
                  id={`field-${field.name}`}
                  type={field.type}
                  value={fields[field.name] ?? ""}
                  onChange={(e) => updateField(field.name, e.target.value)}
                  placeholder={field.default}
                />
              </div>
            ))}

            <div className="wizard-actions">
              <button
                onClick={runTest}
                disabled={testing || !canSave}
                className="secondary"
              >
                {testing ? "Testing…" : "Test Connection"}
              </button>
              <button onClick={save} disabled={saving || !canSave} className="primary">
                {saving ? "Saving…" : "Save Provider"}
              </button>
            </div>

            {testResult && (
              <div
                className="test-result"
                style={{
                  marginTop: 12,
                  padding: "0.75rem",
                  borderRadius: 8,
                  background: testResult.ok
                    ? "color-mix(in srgb, var(--success) 15%, transparent)"
                    : "color-mix(in srgb, var(--error) 15%, transparent)",
                  border: `1px solid ${testResult.ok ? "var(--success)" : "var(--error)"}`,
                }}
              >
                <strong>{testResult.ok ? "✓ Connection successful" : "✗ Connection failed"}</strong>
                {testResult.error && <p>{testResult.error}</p>}
                {testResult.message && <p>{testResult.message}</p>}
                {testResult.ok && testResult.latency_ms !== undefined && (
                  <p style={{ fontSize: 12, color: "var(--muted)" }}>
                    Latency: {testResult.latency_ms}ms
                    {testResult.usage && (
                      <>
                        {" · "}
                        Tokens: {testResult.usage.input_tokens} → {testResult.usage.output_tokens}
                        {testResult.usage.estimated_cost_usd !== undefined && (
                          <>
                            {" · "}Cost: ${testResult.usage.estimated_cost_usd.toFixed(6)}
                          </>
                        )}
                      </>
                    )}
                  </p>
                )}
                {testResult.ok && testResult.usage_warning && (
                  <p style={{ fontSize: 12, color: "var(--warning)" }}>⚠ {testResult.usage_warning}</p>
                )}
                {testResult.ok && testResult.warning && (
                  <p style={{ fontSize: 12, color: "var(--warning)" }}>⚠ {testResult.warning}</p>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
