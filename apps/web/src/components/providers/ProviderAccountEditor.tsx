import React, { useEffect, useState } from "react";

import type {
  ManagementAccountTestResult,
  ManagementProviderAccount,
  ProviderTemplate,
} from "../../types";
import { useModalA11y } from "../../hooks/useModalA11y";

interface ProviderAccountEditorProps {
  templates: ProviderTemplate[];
  account: ManagementProviderAccount | null;
  existingAccounts: string[];
  onClose: () => void;
  onSave: (account: ManagementProviderAccount, secretValue?: string) => void;
  onTestDraft: (
    account: ManagementProviderAccount,
    secretValue?: string,
  ) => Promise<{ ok: boolean; result: ManagementAccountTestResult } | null> | null;
}

export function ProviderAccountEditor({
  templates,
  account,
  existingAccounts,
  onClose,
  onSave,
  onTestDraft,
}: ProviderAccountEditorProps) {
  const timeoutForTemplate = (templateKind: string) =>
    templates.find((t) => t.kind === templateKind)?.default_timeout_seconds || 60;
  const isEdit = Boolean(account);
  const [templateId, setTemplateId] = useState((account?.metadata?.template as string) || "openai_compatible");
  const [id, setId] = useState(account?.id || "");
  const [displayName, setDisplayName] = useState(account?.display_name || "");
  const [endpoint, setEndpoint] = useState(account?.endpoint || "");
  const [authMode, setAuthMode] = useState(account?.auth_mode || "api_key");
  const [secretValue, setSecretValue] = useState("");
  const [timeout, setTimeout] = useState(account?.timeout_seconds || timeoutForTemplate(templateId));
  const [notes, setNotes] = useState(account?.notes || "");
  const [disabled, setDisabled] = useState(account?.disabled || false);
  const [headers, setHeaders] = useState<Record<string, string>>(account?.headers || {});
  const [metadata, setMetadata] = useState<Record<string, unknown>>(account?.metadata || {});
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const dialogRef = React.useRef<HTMLDivElement>(null);
  const titleId = React.useId();

  useModalA11y({ containerRef: dialogRef, onEscape: onClose });

  const selectedTemplate = templates.find((t) => t.kind === templateId);

  useEffect(() => {
    if (selectedTemplate && !isEdit) {
      setEndpoint(selectedTemplate.endpoint);
      setAuthMode(selectedTemplate.auth_mode);
      setTimeout(selectedTemplate.default_timeout_seconds || 60);
    }
  }, [selectedTemplate, isEdit]);

  const canSave =
    id.trim() &&
    endpoint.trim() &&
    (!existingAccounts.includes(id) || isEdit) &&
    selectedTemplate != null;

  const buildAccount = (): ManagementProviderAccount => ({
    id: id.trim(),
    kind: selectedTemplate?.kind || "openai_compatible",
    endpoint: endpoint.trim(),
    auth_mode: authMode as any,
    timeout_seconds: Number(timeout) || 60,
    headers,
    metadata: { ...metadata, template: templateId },
    display_name: displayName.trim() || undefined,
    notes: notes.trim() || undefined,
    disabled,
    secret_ref: account?.secret_ref,
  });

  const runTest = async () => {
    if (!canSave) return;
    setTesting(true);
    setTestResult(null);
    try {
      const acc = buildAccount();
      const result = await onTestDraft(acc, secretValue || undefined);
      if (result) {
        setTestResult({
          ok: result.result.ok,
          message: result.result.ok
            ? `Connection successful (${result.result.latency_ms}ms)`
            : `Connection failed: ${result.result.error || "unknown error"}`,
        });
      }
    } catch (err) {
      setTestResult({
        ok: false,
        message: err instanceof Error ? err.message : String(err),
      });
    } finally {
      setTesting(false);
    }
  };

  const save = () => {
    if (!canSave) return;
    setError(null);
    try {
      const acc = buildAccount();
      onSave(acc, secretValue || undefined);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const updateHeader = (key: string, value: string) => {
    setHeaders((prev) => {
      const next = { ...prev };
      if (value.trim()) {
        next[key] = value;
      } else {
        delete next[key];
      }
      return next;
    });
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
        style={{ maxWidth: 560 }}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
      >
        <header className="modal-header">
          <h3 id={titleId}>{isEdit ? "Edit Provider Account" : "Add Provider Account"}</h3>
          <button onClick={onClose} aria-label="Close" type="button">
            ✕
          </button>
        </header>

        {error && <div className="error-banner">{error}</div>}

        <div className="form-group">
          <label htmlFor="acct-template">Template</label>
          <select id="acct-template" value={templateId} onChange={(e) => setTemplateId(e.target.value)}>
            {templates.map((t) => (
              <option key={t.kind} value={t.kind}>
                {t.display_name} ({t.support_state})
              </option>
            ))}
          </select>
          {selectedTemplate?.capabilities_meta?.notes && (
            <small>{selectedTemplate.capabilities_meta.notes}</small>
          )}
        </div>

        <div className="form-group">
          <label htmlFor="acct-id">Account ID</label>
          <input
            id="acct-id"
            type="text"
            value={id}
            onChange={(e) => setId(e.target.value)}
            disabled={isEdit}
            placeholder="my-openai"
          />
          <small>Short unique identifier</small>
        </div>

        <div className="form-group">
          <label htmlFor="acct-display">Display Name</label>
          <input
            id="acct-display"
            type="text"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            placeholder="My OpenAI Account"
          />
        </div>

        <div className="form-group">
          <label htmlFor="acct-endpoint">Endpoint</label>
          <input
            id="acct-endpoint"
            type="url"
            value={endpoint}
            onChange={(e) => setEndpoint(e.target.value)}
            placeholder="https://api.openai.com/v1"
          />
        </div>

        <div className="form-group">
          <label htmlFor="acct-auth">Auth Mode</label>
          <select id="acct-auth" value={authMode} onChange={(e) => setAuthMode(e.target.value)}>
            <option value="api_key">API Key</option>
            <option value="bearer">Bearer Token</option>
            <option value="x_api_key">x-api-key</option>
            <option value="none">None</option>
          </select>
        </div>

        {authMode !== "none" && (
          <div className="form-group">
            <label htmlFor="acct-secret">
              {isEdit ? "Rotate Secret (leave blank to keep current)" : "Secret"}
            </label>
            <input
              id="acct-secret"
              type="password"
              value={secretValue}
              onChange={(e) => setSecretValue(e.target.value)}
              placeholder={isEdit ? "••••••••" : "sk-..."}
            />
          </div>
        )}

        <div className="form-group">
          <label htmlFor="acct-timeout">Timeout (seconds)</label>
          <input
            id="acct-timeout"
            type="number"
            min={1}
            value={timeout}
            onChange={(e) => setTimeout(Number(e.target.value))}
          />
        </div>

        <div className="form-group">
          <label>
            <input type="checkbox" checked={disabled} onChange={(e) => setDisabled(e.target.checked)} />
            Disabled
          </label>
        </div>

        <div className="form-group">
          <label htmlFor="acct-notes">Notes</label>
          <textarea
            id="acct-notes"
            rows={2}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
          />
        </div>

        {selectedTemplate?.kind === "aws_bedrock" && (
          <>
            <div className="form-group">
              <label htmlFor="hdr-region">AWS Region</label>
              <input
                id="hdr-region"
                type="text"
                value={headers["aws-region"] || ""}
                onChange={(e) => updateHeader("aws-region", e.target.value)}
                placeholder="us-east-1"
              />
            </div>
            <div className="form-group">
              <label htmlFor="hdr-access-key">Access Key ID</label>
              <input
                id="hdr-access-key"
                type="text"
                value={headers["aws-access-key-id"] || ""}
                onChange={(e) => updateHeader("aws-access-key-id", e.target.value)}
              />
            </div>
          </>
        )}

        {selectedTemplate?.kind === "azure_foundry" && (
          <div className="form-group">
            <label htmlFor="meta-deployment">Deployment Name</label>
            <input
              id="meta-deployment"
              type="text"
              value={(metadata["deployment"] as string) || ""}
              onChange={(e) => setMetadata((m) => ({ ...m, deployment: e.target.value }))}
              placeholder="gpt-4o-deploy"
            />
            <small>Used for connection tests and should match your Azure deployment name exactly.</small>
          </div>
        )}

        {selectedTemplate?.kind === "oci_genai" && (
          <>
            <div className="form-group">
              <label htmlFor="meta-config">OCI Config Path</label>
              <input
                id="meta-config"
                type="text"
                value={(metadata["oci_config_path"] as string) || "~/.oci/config"}
                onChange={(e) => setMetadata((m) => ({ ...m, oci_config_path: e.target.value }))}
              />
            </div>
            <div className="form-group">
              <label htmlFor="meta-profile">OCI Profile</label>
              <input
                id="meta-profile"
                type="text"
                value={(metadata["oci_profile"] as string) || "DEFAULT"}
                onChange={(e) => setMetadata((m) => ({ ...m, oci_profile: e.target.value }))}
              />
            </div>
          </>
        )}

        <div className="wizard-actions">
          <button className="secondary" onClick={runTest} disabled={testing || !canSave} type="button">
            {testing ? "Testing…" : "Test Connection"}
          </button>
          <button className="primary" onClick={save} disabled={!canSave} type="button">
            {isEdit ? "Save Changes" : "Add Account"}
          </button>
        </div>

        {testResult && (
          <div
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
            <strong>{testResult.ok ? "✓" : "✗"}</strong> {testResult.message}
          </div>
        )}
      </div>
    </div>
  );
}
