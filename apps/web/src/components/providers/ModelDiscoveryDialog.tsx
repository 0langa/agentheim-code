import React, { useEffect, useState } from "react";

import { discoverManagementModels } from "../../api";
import type { DiscoveredModel, ManagementProviderAccount } from "../../types";
import { useModalA11y } from "../../hooks/useModalA11y";

interface ModelDiscoveryDialogProps {
  profileName: string;
  account: ManagementProviderAccount;
  onClose: () => void;
  onImport: (models: DiscoveredModel[]) => void;
}

export function ModelDiscoveryDialog({ profileName, account, onClose, onImport }: ModelDiscoveryDialogProps) {
  const [models, setModels] = useState<DiscoveredModel[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [supported, setSupported] = useState(true);
  const [discoveryMode, setDiscoveryMode] = useState("");

  const dialogRef = React.useRef<HTMLDivElement>(null);
  const titleId = React.useId();

  useModalA11y({ containerRef: dialogRef, onEscape: onClose });

  useEffect(() => {
    setLoading(true);
    discoverManagementModels(profileName, account.id)
      .then((res) => {
        setSupported(res.supported);
        setDiscoveryMode(res.discovery_mode);
        setModels(res.models);
        if (!res.supported) {
          setError("Remote model listing is not supported for this provider. Use manual model entry instead.");
        }
      })
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  }, [profileName, account.id]);

  const toggle = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const importSelected = () => {
    const toImport = models.filter((m) => selected.has(m.id));
    onImport(toImport);
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
        style={{ maxWidth: 640, maxHeight: "70vh", display: "flex", flexDirection: "column" }}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
      >
        <header className="modal-header">
          <h3 id={titleId}>Discover Models — {account.display_name || account.id}</h3>
          <button onClick={onClose} aria-label="Close" type="button">
            ✕
          </button>
        </header>

        {error && <div className="error-banner">{error}</div>}
        {loading && <p style={{ padding: 16, color: "var(--muted)" }}>Discovering models…</p>}

        {!loading && supported && (
          <>
            <div style={{ flex: 1, overflow: "auto", padding: "0 16px" }}>
              {models.length === 0 && <p className="panel-empty">No models discovered.</p>}
              {models.map((m) => (
                <label
                  key={m.id}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 10,
                    padding: "8px 0",
                    borderBottom: "1px solid var(--border)",
                    cursor: "pointer",
                  }}
                >
                  <input
                    type="checkbox"
                    checked={selected.has(m.id)}
                    onChange={() => toggle(m.id)}
                  />
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 500 }}>{m.display_name || m.provider_model_name}</div>
                    <div style={{ fontSize: 12, color: "var(--muted)" }}>
                      {m.provider_model_name} · {m.capabilities.join(" · ")}
                      {m.context_window ? ` · ctx=${m.context_window}` : ""}
                      {m.deprecation_status ? ` · ${m.deprecation_status}` : ""}
                    </div>
                  </div>
                </label>
              ))}
            </div>
            <div
              style={{
                padding: "12px 16px",
                borderTop: "1px solid var(--border)",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
              }}
            >
              <span style={{ fontSize: 12, color: "var(--muted)" }}>
                {selected.size} selected · mode: {discoveryMode}
              </span>
              <div style={{ display: "flex", gap: 8 }}>
                <button className="secondary small" onClick={onClose} type="button">
                  Cancel
                </button>
                <button
                  className="primary small"
                  onClick={importSelected}
                  disabled={selected.size === 0}
                  type="button"
                >
                  Import Selected
                </button>
              </div>
            </div>
          </>
        )}

        {!loading && !supported && (
          <div style={{ padding: 16 }}>
            <p style={{ color: "var(--muted)" }}>
              This provider does not support automatic model discovery. You can still add models manually from the Models tab.
            </p>
            <div className="wizard-actions">
              <button className="secondary" onClick={onClose} type="button">
                Close
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
