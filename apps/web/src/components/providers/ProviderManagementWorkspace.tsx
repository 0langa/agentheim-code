import React, { useCallback, useEffect, useMemo, useState } from "react";

import {
  addManagementAccount,
  addManagementModel,
  createManagementProfile,
  deleteManagementAccount,
  deleteManagementModel,
  deleteManagementProfile,
  discoverManagementModels,
  duplicateManagementProfile,
  exportManagementProfile,
  getManagementTemplates,
  importManagementProfile,
  importDiscoveredManagementModels,
  listManagementProfiles,
  rotateManagementSecret,
  setDefaultManagementModel,
  setDefaultManagementProfile,
  testDraftManagementAccount,
  testManagementAccount,
  updateManagementAccount,
  updateManagementModel,
} from "../../api";
import type {
  ManagementAccountTestResult,
  DiscoveredModel,
  ManagementModelBinding,
  ManagementProfile,
  ManagementProviderAccount,
  ProviderTemplate,
} from "../../types";
import { useModalA11y } from "../../hooks/useModalA11y";
import { ProviderAccountEditor } from "./ProviderAccountEditor";
import { ModelBindingEditor } from "./ModelBindingEditor";
import { ModelDiscoveryDialog } from "./ModelDiscoveryDialog";

interface ProviderManagementWorkspaceProps {
  onClose: () => void;
  onProfilesChanged?: () => void;
}

type TabKey = "accounts" | "models" | "defaults" | "diagnostics";

const TABS: { key: TabKey; label: string }[] = [
  { key: "accounts", label: "Accounts" },
  { key: "models", label: "Models" },
  { key: "defaults", label: "Defaults" },
  { key: "diagnostics", label: "Diagnostics" },
];

export function ProviderManagementWorkspace({
  onClose,
  onProfilesChanged,
}: ProviderManagementWorkspaceProps) {
  const [profiles, setProfiles] = useState<ManagementProfile[]>([]);
  const [defaultProfile, setDefaultProfile] = useState<string>("");
  const [selectedProfileName, setSelectedProfileName] = useState<string>("");
  const [activeTab, setActiveTab] = useState<TabKey>("accounts");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [templates, setTemplates] = useState<ProviderTemplate[]>([]);

  const [showAccountEditor, setShowAccountEditor] = useState(false);
  const [editingAccount, setEditingAccount] = useState<ManagementProviderAccount | null>(null);

  const [showModelEditor, setShowModelEditor] = useState(false);
  const [editingModel, setEditingModel] = useState<ManagementModelBinding | null>(null);

  const [showDiscovery, setShowDiscovery] = useState(false);
  const [discoveryAccount, setDiscoveryAccount] = useState<ManagementProviderAccount | null>(null);

  const [deleteConfirm, setDeleteConfirm] = useState<{
    type: "account" | "model" | "profile";
    id: string;
    name: string;
    cascade?: boolean;
  } | null>(null);
  const [profileDialog, setProfileDialog] = useState<{
    mode: "create" | "duplicate" | "import";
    name: string;
    payload: string;
  } | null>(null);
  const [exportPayload, setExportPayload] = useState<string | null>(null);
  const [rotatingAccount, setRotatingAccount] = useState<ManagementProviderAccount | null>(null);
  const [rotationSecret, setRotationSecret] = useState("");
  const [rotationError, setRotationError] = useState<string | null>(null);
  const [inlineMessage, setInlineMessage] = useState<string | null>(null);

  const dialogRef = React.useRef<HTMLDivElement>(null);
  const titleId = React.useId();

  useModalA11y({ containerRef: dialogRef, onEscape: onClose });

  const selectedProfile = useMemo(
    () => profiles.find((p) => p.name === selectedProfileName) || null,
    [profiles, selectedProfileName]
  );
  const internalRoleModels = useMemo(
    () => selectedProfile?.models.filter((model) => model.role !== "planner") ?? [],
    [selectedProfile]
  );

  const refresh = useCallback(async (preferredSelection?: string) => {
    setLoading(true);
    setError(null);
    try {
      const data = await listManagementProfiles();
      setProfiles(data.profiles);
      setDefaultProfile(data.default_profile || "");
      const availableNames = new Set(data.profiles.map((profile) => profile.name));
      const preferredProfile =
        (preferredSelection && availableNames.has(preferredSelection) ? preferredSelection : "") ||
        (selectedProfileName && availableNames.has(selectedProfileName) ? selectedProfileName : "") ||
        (data.default_profile && availableNames.has(data.default_profile) ? data.default_profile : "") ||
        data.profiles[0]?.name ||
        "";
      if (preferredProfile !== selectedProfileName) {
        setSelectedProfileName(preferredProfile);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [selectedProfileName]);

  const clearTransientUi = () => {
    setProfileDialog(null);
    setExportPayload(null);
    setRotatingAccount(null);
    setRotationSecret("");
    setRotationError(null);
  };

  useEffect(() => {
    refresh();
    getManagementTemplates().then(setTemplates).catch(() => {});
  }, [refresh]);

  const handleCreateProfile = () => {
    setProfileDialog({ mode: "create", name: "", payload: "" });
  };

  const handleDuplicateProfile = () => {
    if (!selectedProfileName) return;
    setProfileDialog({
      mode: "duplicate",
      name: `${selectedProfileName} copy`,
      payload: "",
    });
  };

  const submitProfileDialog = async () => {
    if (!profileDialog) return;
    try {
      let nextSelection = selectedProfileName;
      if (profileDialog.mode === "create") {
        const created = await createManagementProfile(profileDialog.name);
        nextSelection = created.profile.name;
      } else if (profileDialog.mode === "duplicate") {
        const duplicated = await duplicateManagementProfile(selectedProfileName, profileDialog.name);
        nextSelection = duplicated.profile.name;
      } else {
        const parsed = JSON.parse(profileDialog.payload);
        const imported = await importManagementProfile(parsed, profileDialog.name || undefined);
        nextSelection = imported.profile.name;
      }
      clearTransientUi();
      await refresh(nextSelection);
      onProfilesChanged?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const handleImportProfile = () => {
    setProfileDialog({ mode: "import", name: "", payload: "" });
  };

  const handleExportProfile = async () => {
    if (!selectedProfileName) return;
    try {
      const exported = await exportManagementProfile(selectedProfileName);
      setExportPayload(JSON.stringify(exported.data, null, 2));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const handleSetDefaultProfile = async () => {
    if (!selectedProfileName) return;
    try {
      await setDefaultManagementProfile(selectedProfileName);
      await refresh();
      onProfilesChanged?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const handleDeleteProfile = async () => {
    if (!selectedProfileName) return;
    setDeleteConfirm({ type: "profile", id: selectedProfileName, name: selectedProfileName });
  };

  const handleDeleteAccount = (account: ManagementProviderAccount) => {
    const dependentCount = selectedProfile?.models.filter((m) => m.provider === account.id).length || 0;
    if (dependentCount > 0) {
      setDeleteConfirm({ type: "account", id: account.id, name: account.id, cascade: true });
    } else {
      setDeleteConfirm({ type: "account", id: account.id, name: account.id });
    }
  };

  const handleDeleteModel = (model: ManagementModelBinding) => {
    setDeleteConfirm({ type: "model", id: model.id, name: model.id });
  };

  const executeDelete = async () => {
    if (!deleteConfirm || !selectedProfileName) return;
    try {
      if (deleteConfirm.type === "profile") {
        await deleteManagementProfile(deleteConfirm.id);
        setSelectedProfileName("");
      } else if (deleteConfirm.type === "account") {
        await deleteManagementAccount(selectedProfileName, deleteConfirm.id, deleteConfirm.cascade || false);
      } else if (deleteConfirm.type === "model") {
        await deleteManagementModel(selectedProfileName, deleteConfirm.id);
      }
      await refresh();
      onProfilesChanged?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setDeleteConfirm(null);
    }
  };

  const handleSaveAccount = async (account: ManagementProviderAccount, secretValue?: string) => {
    if (!selectedProfileName) return;
    try {
      if (editingAccount) {
        await updateManagementAccount(selectedProfileName, editingAccount.id, account);
        if (secretValue) {
          await rotateManagementSecret(selectedProfileName, editingAccount.id, "api_key", secretValue);
          setInlineMessage(`Secret rotated for ${editingAccount.id}.`);
        }
      } else {
        await addManagementAccount(selectedProfileName, account);
        if (secretValue) {
          await rotateManagementSecret(selectedProfileName, account.id, "api_key", secretValue);
          setInlineMessage(`Secret saved for ${account.id}.`);
        }
      }
      await refresh();
      onProfilesChanged?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const handleTestAccount = async (accountId: string) => {
    if (!selectedProfileName) return null;
    return testManagementAccount(selectedProfileName, accountId);
  };

  const handleTestDraftAccount = async (
    account: ManagementProviderAccount,
    secretValue?: string,
  ): Promise<{ ok: boolean; result: ManagementAccountTestResult } | null> => {
    if (!selectedProfileName) return null;
    return testDraftManagementAccount(account, {
      secretValue,
      profileName: selectedProfileName,
      existingAccountId: editingAccount?.id,
    });
  };

  const handleRotateSecret = async () => {
    if (!selectedProfileName || !rotatingAccount) return;
    if (!rotationSecret.trim()) {
      setRotationError("Enter a new secret value.");
      return;
    }
    try {
      await rotateManagementSecret(
        selectedProfileName,
        rotatingAccount.id,
        "api_key",
        rotationSecret.trim(),
      );
      clearTransientUi();
      setInlineMessage(`Secret rotated for ${rotatingAccount.id}.`);
      await refresh();
    } catch (err) {
      setRotationError(err instanceof Error ? err.message : String(err));
    }
  };

  const handleDiscover = (account: ManagementProviderAccount) => {
    setDiscoveryAccount(account);
    setShowDiscovery(true);
  };

  const handleImportDiscovered = async (models: DiscoveredModel[]) => {
    if (!selectedProfileName || !discoveryAccount) return;
    try {
      await importDiscoveredManagementModels(selectedProfileName, discoveryAccount.id, models);
      await refresh();
      onProfilesChanged?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const handleSaveModel = async (model: ManagementModelBinding) => {
    if (!selectedProfileName) return;
    try {
      if (editingModel) {
        await updateManagementModel(selectedProfileName, editingModel.id, model);
      } else {
        await addManagementModel(selectedProfileName, model);
      }
      await refresh();
      onProfilesChanged?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const handleSetDefaultModel = async (modelId: string) => {
    if (!selectedProfileName) return;
    try {
      await setDefaultManagementModel(selectedProfileName, modelId);
      await refresh();
      onProfilesChanged?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
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
        style={{ maxWidth: 1180, height: "86vh", display: "flex", flexDirection: "column" }}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
      >
        <header className="modal-header">
          <h2 id={titleId}>Providers &amp; Models</h2>
          <button onClick={onClose} aria-label="Close" type="button">
            ✕
          </button>
        </header>

        {error && (
          <div className="error-banner" role="alert">
            {error}
            <button onClick={() => setError(null)} style={{ marginLeft: 8 }} type="button">
              Dismiss
            </button>
          </div>
        )}
        {inlineMessage && (
          <div className="error-banner" role="status" style={{ borderColor: "var(--success)" }}>
            {inlineMessage}
            <button onClick={() => setInlineMessage(null)} style={{ marginLeft: 8 }} type="button">
              Dismiss
            </button>
          </div>
        )}

        <div className="workspace-toolbar">
          <select
            aria-label="Profile"
            value={selectedProfileName}
            onChange={(e) => setSelectedProfileName(e.target.value)}
            style={{ minWidth: 180 }}
          >
            {profiles.map((p) => (
              <option key={p.name} value={p.name}>
                {p.name} {defaultProfile === p.name ? "(default)" : ""}
              </option>
            ))}
          </select>
          <button className="secondary small" onClick={handleCreateProfile} type="button">
            + New Profile
          </button>
          <button className="secondary small" onClick={handleDuplicateProfile} disabled={!selectedProfile} type="button">
            Duplicate
          </button>
          <button className="secondary small" onClick={handleExportProfile} disabled={!selectedProfile} type="button">
            Export
          </button>
          <button className="secondary small" onClick={handleImportProfile} type="button">
            Import
          </button>
          <button className="secondary small" onClick={handleSetDefaultProfile} disabled={!selectedProfile} type="button">
            Set Default
          </button>
          <button className="secondary small danger" onClick={handleDeleteProfile} disabled={!selectedProfile || profiles.length <= 1} type="button">
            Delete Profile
          </button>
        </div>

        <div className="workspace-tabs">
          {TABS.map((t) => (
            <button
              key={t.key}
              onClick={() => setActiveTab(t.key)}
              type="button"
              className={`workspace-tab${activeTab === t.key ? " is-active" : ""}`}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div className="workspace-body">
          {loading && <p style={{ color: "var(--muted)" }}>Loading…</p>}

          {!loading && activeTab === "accounts" && (
            <div>
              <div className="workspace-section-header">
                <strong>Provider Accounts</strong>
                <button
                  className="primary small"
                  onClick={() => {
                    setEditingAccount(null);
                    setShowAccountEditor(true);
                  }}
                  type="button"
                >
                  + Add Account
                </button>
              </div>
              {!selectedProfile?.providers?.length && (
                <p className="panel-empty">No accounts yet. Add a provider account to get started.</p>
              )}
              {selectedProfile?.providers?.map((account) => (
                <div key={account.id} className="workspace-card" style={{ opacity: account.disabled ? 0.6 : 1 }}>
                  <div className="workspace-card-header">
                    <div>
                      <strong>{account.display_name || account.id}</strong>
                      <span style={{ fontSize: 12, color: "var(--muted)", marginLeft: 8 }}>
                        {account.kind} · {account.auth_mode}
                      </span>
                      {account.disabled && <span className="badge">disabled</span>}
                    </div>
                    <div className="workspace-actions">
                      <button
                        className="secondary small"
                        onClick={() => {
                          setEditingAccount(account);
                          setShowAccountEditor(true);
                        }}
                        type="button"
                      >
                        Edit
                      </button>
                      <button
                        className="secondary small"
                        onClick={() => handleDiscover(account)}
                        type="button"
                      >
                        Discover Models
                      </button>
                      <button
                        className="secondary small"
                        onClick={async () => {
                          const result = await handleTestAccount(account.id);
                          if (result) {
                            setInlineMessage(
                              result.result.ok
                                ? `Test passed for ${account.id} (${result.result.latency_ms ?? "?"}ms).`
                                : `Test failed for ${account.id}: ${result.result.error ?? "unknown error"}.`
                            );
                          }
                          await refresh();
                        }}
                        type="button"
                      >
                        Test
                      </button>
                      {account.auth_mode !== "none" && (
                        <button
                          className="secondary small"
                          onClick={() => {
                            setRotatingAccount(account);
                            setRotationSecret("");
                            setRotationError(null);
                          }}
                          type="button"
                        >
                          Rotate Secret
                        </button>
                      )}
                      <button
                        className="secondary small danger"
                        onClick={() => handleDeleteAccount(account)}
                        type="button"
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                  <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 4 }}>
                    {account.endpoint}
                    {account.last_verified_at && (
                      <span style={{ marginLeft: 8 }}>
                        Last verified: {new Date(account.last_verified_at).toLocaleString()} ({account.last_verified_status})
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}

          {!loading && activeTab === "models" && (
            <div>
              <div className="workspace-section-header">
                <strong>Model Bindings</strong>
                <button
                  className="primary small"
                  onClick={() => {
                    setEditingModel(null);
                    setShowModelEditor(true);
                  }}
                  type="button"
                >
                  + Add Model
                </button>
              </div>
              {!selectedProfile?.models?.length && (
                <p className="panel-empty">No model bindings yet.</p>
              )}
              <div className="workspace-table-wrap">
              <table className="workspace-table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Provider</th>
                    <th>Model</th>
                    <th>Role</th>
                    <th>Default</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {selectedProfile?.models?.map((m) => (
                    <tr key={m.id}>
                      <td>{m.display_name || m.id}</td>
                      <td>{m.provider}</td>
                      <td>{m.model}</td>
                      <td>{m.role}</td>
                      <td>{m.is_default ? "★" : ""}</td>
                      <td>
                        <div className="workspace-actions">
                        <button
                          className="secondary small"
                          onClick={() => {
                            setEditingModel(m);
                            setShowModelEditor(true);
                          }}
                          type="button"
                        >
                          Edit
                        </button>
                        {!m.is_default && (
                          <button
                            className="secondary small"
                            onClick={() => handleSetDefaultModel(m.id)}
                            type="button"
                          >
                            Set Default
                          </button>
                        )}
                        <button
                          className="secondary small danger"
                          onClick={() => handleDeleteModel(m)}
                          type="button"
                        >
                          Delete
                        </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              </div>
            </div>
          )}

          {!loading && activeTab === "defaults" && (
            <div>
              <p style={{ color: "var(--muted)", marginBottom: 16 }}>
                Default coding model is used for new sessions when no explicit model is selected.
              </p>
              {selectedProfile?.models
                ?.filter((m) => m.is_default)
                .map((m) => (
                  <div key={m.id} style={{ padding: 12, border: "1px solid var(--border)", borderRadius: 8 }}>
                    <strong>Default Coding Model</strong>
                    <div>{m.display_name || m.id}</div>
                    <div style={{ fontSize: 12, color: "var(--muted)" }}>
                      {m.provider} / {m.model}
                    </div>
                  </div>
                ))}
              {!selectedProfile?.models?.some((m) => m.is_default) && (
                <p className="panel-empty">No default model set. Go to the Models tab and set one.</p>
              )}
              {internalRoleModels.length > 0 && (
                <div style={{ marginTop: 16, padding: 12, border: "1px solid var(--border)", borderRadius: 8 }}>
                  <strong>Legacy internal bindings</strong>
                  <p style={{ color: "var(--muted)", margin: "8px 0 0" }}>
                    Planner is the only user-facing role. Internal compatibility bindings remain visible here but are not part of normal setup.
                  </p>
                  <ul style={{ margin: "8px 0 0 18px" }}>
                    {internalRoleModels.map((model) => (
                      <li key={model.id}>
                        {model.id} — {model.role}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          {!loading && activeTab === "diagnostics" && (
            <div>
              {selectedProfile?.providers?.map((account) => (
                <div
                  key={account.id}
                  style={{ border: "1px solid var(--border)", borderRadius: 8, padding: 12, marginBottom: 12 }}
                >
                  <strong>{account.display_name || account.id}</strong>
                  <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 4 }}>
                    Status: {account.last_verified_status || "never tested"}
                  </div>
                  {account.last_verified_at && (
                    <div style={{ fontSize: 12, color: "var(--muted)" }}>
                      Last tested: {new Date(account.last_verified_at).toLocaleString()}
                    </div>
                  )}
                  {account.last_verified_error && (
                    <div style={{ fontSize: 12, color: "var(--error)", marginTop: 4 }}>
                      Error: {account.last_verified_error}
                    </div>
                  )}
                  {account.last_model_sync_at && (
                    <div style={{ fontSize: 12, color: "var(--muted)" }}>
                      Last sync: {new Date(account.last_model_sync_at).toLocaleString()}
                    </div>
                  )}
                </div>
              ))}
              {!selectedProfile?.providers?.length && <p className="panel-empty">No accounts to diagnose.</p>}
            </div>
          )}
        </div>

        {showAccountEditor && (
          <ProviderAccountEditor
            templates={templates}
            account={editingAccount}
            onClose={() => setShowAccountEditor(false)}
            onSave={handleSaveAccount}
            onTestDraft={handleTestDraftAccount}
            existingAccounts={selectedProfile?.providers.map((p) => p.id) || []}
          />
        )}

        {showModelEditor && (
          <ModelBindingEditor
            model={editingModel}
            providers={selectedProfile?.providers || []}
            onClose={() => setShowModelEditor(false)}
            onSave={handleSaveModel}
          />
        )}

        {showDiscovery && discoveryAccount && selectedProfile && (
          <ModelDiscoveryDialog
            profileName={selectedProfile.name}
            account={discoveryAccount}
            onClose={() => setShowDiscovery(false)}
            onImport={handleImportDiscovered}
          />
        )}

        {deleteConfirm && (
          <div
            className="modal-overlay"
            onClick={(e) => {
              if (e.target === e.currentTarget) setDeleteConfirm(null);
            }}
          >
            <div className="modal-content" style={{ maxWidth: 420 }} role="alertdialog" aria-modal="true">
              <h3>Confirm Delete</h3>
              <p>
                Are you sure you want to delete{" "}
                <strong>{deleteConfirm.name}</strong>?
                {deleteConfirm.type === "profile" && " This will remove the entire profile, all accounts, and all model bindings."}
                {deleteConfirm.type === "account" && deleteConfirm.cascade && " All dependent model bindings will also be removed because this account is still referenced by them."}
              </p>
              <div className="wizard-actions">
                <button className="secondary" onClick={() => setDeleteConfirm(null)} type="button">
                  Cancel
                </button>
                <button className="primary danger" onClick={executeDelete} type="button">
                  Delete
                </button>
              </div>
            </div>
          </div>
        )}

        {profileDialog && (
          <div
            className="modal-overlay"
            onClick={(e) => {
              if (e.target === e.currentTarget) setProfileDialog(null);
            }}
          >
            <div className="modal-content" style={{ maxWidth: 520 }} role="dialog" aria-modal="true">
              <h3>
                {profileDialog.mode === "create"
                  ? "Create Profile"
                  : profileDialog.mode === "duplicate"
                    ? "Duplicate Profile"
                    : "Import Profile"}
              </h3>
              <div className="form-group">
                <label htmlFor="profile-name-input">Profile Name</label>
                <input
                  id="profile-name-input"
                  type="text"
                  value={profileDialog.name}
                  onChange={(e) =>
                    setProfileDialog((current) =>
                      current ? { ...current, name: e.target.value } : current
                    )
                  }
                />
              </div>
              {profileDialog.mode === "import" && (
                <div className="form-group">
                  <label htmlFor="profile-import-json">Exported Profile JSON</label>
                  <textarea
                    id="profile-import-json"
                    rows={10}
                    value={profileDialog.payload}
                    onChange={(e) =>
                      setProfileDialog((current) =>
                        current ? { ...current, payload: e.target.value } : current
                      )
                    }
                  />
                </div>
              )}
              <div className="wizard-actions">
                <button className="secondary" onClick={() => setProfileDialog(null)} type="button">
                  Cancel
                </button>
                <button
                  className="primary"
                  onClick={submitProfileDialog}
                  disabled={
                    (profileDialog.mode !== "import" && !profileDialog.name.trim()) ||
                    (profileDialog.mode === "import" && !profileDialog.payload.trim())
                  }
                  type="button"
                >
                  {profileDialog.mode === "import" ? "Import" : "Save"}
                </button>
              </div>
            </div>
          </div>
        )}

        {exportPayload && (
          <div
            className="modal-overlay"
            onClick={(e) => {
              if (e.target === e.currentTarget) setExportPayload(null);
            }}
          >
            <div className="modal-content" style={{ maxWidth: 620 }} role="dialog" aria-modal="true">
              <h3>Export Profile</h3>
              <div className="form-group">
                <label htmlFor="profile-export-json">Profile JSON</label>
                <textarea id="profile-export-json" rows={14} readOnly value={exportPayload} />
              </div>
              <div className="wizard-actions">
                <button
                  className="secondary"
                  onClick={() => navigator.clipboard?.writeText(exportPayload)}
                  type="button"
                >
                  Copy JSON
                </button>
                <button className="primary" onClick={() => setExportPayload(null)} type="button">
                  Close
                </button>
              </div>
            </div>
          </div>
        )}

        {rotatingAccount && (
          <div
            className="modal-overlay"
            onClick={(e) => {
              if (e.target === e.currentTarget) clearTransientUi();
            }}
          >
            <div className="modal-content" style={{ maxWidth: 440 }} role="dialog" aria-modal="true">
              <h3>Rotate Secret</h3>
              <p style={{ color: "var(--muted)" }}>
                Update credentials for <strong>{rotatingAccount.display_name || rotatingAccount.id}</strong>.
              </p>
              {rotationError && <div className="error-banner">{rotationError}</div>}
              <div className="form-group">
                <label htmlFor="rotate-secret-input">New Secret</label>
                <input
                  id="rotate-secret-input"
                  type="password"
                  value={rotationSecret}
                  onChange={(e) => setRotationSecret(e.target.value)}
                  placeholder="sk-..."
                />
              </div>
              <div className="wizard-actions">
                <button className="secondary" onClick={clearTransientUi} type="button">
                  Cancel
                </button>
                <button className="primary" onClick={handleRotateSecret} type="button">
                  Save Secret
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
