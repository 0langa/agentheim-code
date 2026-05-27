import React, { startTransition, useEffect, useState } from "react";

import {
  api,
  cancelSession,
  fetchModeCatalog,
  getDesktopBackendLaunchError,
  isDesktopApp,
  pickDesktopWorkspace,
  streamSessionMessage,
  validateContext,
} from "./api";
import { Chat } from "./components/Chat";
import { CommandPalette } from "./components/CommandPalette";
import { Composer } from "./components/Composer";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { Onboarding } from "./components/Onboarding";
import { Inspector } from "./components/Inspector";
import { ProviderManagementWorkspace } from "./components/providers/ProviderManagementWorkspace";
import { ProviderWizard } from "./components/ProviderWizard";
import { Rail } from "./components/Rail";
import { TopBar } from "./components/TopBar";
import type {
  ContextPreviewItem,
  CoderCommand,
  FileEntry,
  ModelOptions,
  ModeCatalog,
  Session,
  SessionView,
  StructuredError,
  UiConfig,
} from "./types";

export function App() {
  const [commands, setCommands] = useState<CoderCommand[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [active, setActive] = useState<SessionView | null>(null);
  const [modelOptions, setModelOptions] = useState<ModelOptions | null>(null);
  const [modeCatalog, setModeCatalog] = useState<ModeCatalog | null>(null);
  const [uiConfig, setUiConfig] = useState<UiConfig | null>(null);
  const [prompt, setPrompt] = useState("");
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [wizardOpen, setWizardOpen] = useState(false);
  const [managementOpen, setManagementOpen] = useState(false);
  const [inspector, setInspector] = useState("timeline");
  const [selectedMode, setSelectedMode] = useState("code");
  const [selectedTrustMode, setSelectedTrustMode] = useState("ask");
  const [selectedProfile, setSelectedProfile] = useState("auto");
  const [selectedModel, setSelectedModel] = useState("auto");
  const [isLoading, setIsLoading] = useState(false);
  const [streamAbort, setStreamAbort] = useState<AbortController | null>(null);
  const [lastPrompt, setLastPrompt] = useState<string | null>(null);
  const [selectedContextFiles, setSelectedContextFiles] = useState<string[]>([]);
  const [fileMatches, setFileMatches] = useState<FileEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [structuredError, setStructuredError] = useState<StructuredError | null>(null);
  const [sessionBootstrapError, setSessionBootstrapError] = useState<string | null>(null);
  const [contextPreviews, setContextPreviews] = useState<ContextPreviewItem[]>([]);
  const [sessionFilter, setSessionFilter] = useState("");
  const [workspaceDraft, setWorkspaceDraft] = useState("");
  const [workspaceSaveState, setWorkspaceSaveState] = useState<"idle" | "saving">("idle");
  const errorRef = React.useRef<HTMLDivElement | null>(null);

  const effectiveWorkspaceRoot = React.useMemo(() => {
    const activeRoot = active?.session.workspace_root?.trim();
    if (activeRoot && activeRoot !== ".") return activeRoot;
    const configuredRoot = uiConfig?.default_workspace?.trim();
    if (configuredRoot) return configuredRoot;
    return undefined;
  }, [active?.session.workspace_root, uiConfig?.default_workspace]);

  const mergeSession = React.useCallback((session: Session) => {
    setSessions((current) => {
      const withoutCurrent = current.filter((item) => item.session_id !== session.session_id);
      return [session, ...withoutCurrent];
    });
  }, []);

  const applySessionView = React.useCallback(
    (view: SessionView) => {
      startTransition(() => {
        setActive(view);
        mergeSession(view.session);
        setSelectedMode(view.session.mode ?? "code");
        setSelectedTrustMode(view.session.trust_mode ?? "ask");
        setSelectedProfile(view.session.model_selection?.profile ?? "auto");
        setSelectedModel(view.session.model_selection?.model ?? "auto");
      });
    },
    [mergeSession],
  );

  const sessionPath = React.useCallback((sessionId: string, suffix = "", workspaceRoot?: string) => {
    const base = `/coder/sessions/${sessionId}${suffix}`;
    if (!workspaceRoot || workspaceRoot === ".") return base;
    const separator = base.includes("?") ? "&" : "?";
    return `${base}${separator}workspace_root=${encodeURIComponent(workspaceRoot)}`;
  }, []);

  useEffect(() => {
    api<UiConfig>("/config")
      .then(setUiConfig)
      .catch((err) => setError(err.message));
    api<CoderCommand[]>("/coder/commands")
      .then(setCommands)
      .catch((err) => setError(err.message));
    api<Session[]>("/coder/sessions")
      .then(setSessions)
      .catch((err) => setError(err.message));
    api<ModelOptions>("/coder/models")
      .then((options) => {
        setModelOptions(options);
        if (options.default_profile) setSelectedProfile(options.default_profile);
      })
      .catch((err) => setError(err.message));
    fetchModeCatalog()
      .then(setModeCatalog)
      .catch((err) => setError(err.message));
  }, []);

  useEffect(() => {
    const theme = uiConfig?.theme ?? window.localStorage.getItem("agentheim-theme") ?? "dark";
    document.documentElement.dataset.theme = theme;
  }, [uiConfig?.theme]);

  useEffect(() => {
    setWorkspaceDraft(uiConfig?.default_workspace ?? ".");
  }, [uiConfig?.default_workspace]);

  useEffect(() => {
    if ((error || structuredError) && errorRef.current) {
      errorRef.current.focus();
    }
  }, [error, structuredError]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (
        (event.ctrlKey || event.metaKey) &&
        (event.key.toLowerCase() === "k" || event.key.toLowerCase() === "p")
      ) {
        event.preventDefault();
        setPaletteOpen(true);
      }
      if ((event.ctrlKey || event.metaKey) && event.key === ",") {
        event.preventDefault();
        setInspector("settings");
      }
      if ((event.ctrlKey || event.metaKey) && event.shiftKey && event.key.toLowerCase() === "n") {
        event.preventDefault();
        void createSession();
      }
      if (event.key === "Escape") {
        setPaletteOpen(false);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const ensureWorkspaceRoot = async () => {
    const activeRoot = active?.session.workspace_root?.trim();
    if (activeRoot) return activeRoot;
    const configuredRoot = workspaceDraft.trim() || uiConfig?.default_workspace?.trim();
    if (configuredRoot) return configuredRoot;
    if (isDesktopApp()) {
      const picked = await pickDesktopWorkspace();
      if (!picked) return null;
      setWorkspaceDraft(picked);
      await saveDefaultWorkspace(picked);
      return picked;
    }
    return null;
  };

  const createSession = async () => {
    setIsLoading(true);
    setError(null);
    setSessionBootstrapError(null);
    try {
      const workspaceRoot = await ensureWorkspaceRoot();
      if (!workspaceRoot) {
        throw new Error(
          isDesktopApp()
            ? "Choose a workspace before starting a session."
            : "Set a default workspace in Settings before starting a session.",
        );
      }
      const session = await api<Session>("/coder/sessions", {
        method: "POST",
        body: JSON.stringify({
          workspace_root: workspaceRoot,
          trust_mode: selectedTrustMode,
          mode: selectedMode,
          profile: selectedProfile === "auto" ? undefined : selectedProfile,
          model: selectedModel === "auto" ? undefined : selectedModel,
        }),
      });
      setSessions((current) => [session, ...current]);
      const view = await api<SessionView>(
        sessionPath(session.session_id, "/view", session.workspace_root),
      );
      applySessionView(view);
      return view;
    } catch (err) {
      let message = err instanceof Error ? err.message : String(err);
      if (isDesktopApp()) {
        try {
          const desktopError = await getDesktopBackendLaunchError();
          if (desktopError) message = desktopError;
        } catch {
          // Ignore extra desktop error lookup failures.
        }
      }
      setError(message);
      setSessionBootstrapError(message);
      return null;
    } finally {
      setIsLoading(false);
    }
  };

  const skipOnboarding = async () => {
    const config = await api<UiConfig>("/config", {
      method: "PATCH",
      body: JSON.stringify({ onboarding_dismissed: true }),
    });
    setUiConfig(config);
  };

  const completeOnboarding = async (workspace: string) => {
    try {
      const config = await api<UiConfig>("/onboarding/complete", {
        method: "POST",
        body: JSON.stringify({ default_workspace: workspace }),
      });
      setUiConfig(config);
      setWorkspaceDraft(config.default_workspace);
      await createSession();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const saveDefaultWorkspace = async (workspace: string) => {
    setWorkspaceSaveState("saving");
    try {
      const config = await api<UiConfig>("/config", {
        method: "PATCH",
        body: JSON.stringify({ default_workspace: workspace }),
      });
      setUiConfig(config);
      setWorkspaceDraft(config.default_workspace);
      return config;
    } finally {
      setWorkspaceSaveState("idle");
    }
  };

  const handleDefaultWorkspaceChange = (workspace: string) => {
    setWorkspaceDraft(workspace);
    void saveDefaultWorkspace(workspace).catch((err) => {
      setError(err instanceof Error ? err.message : String(err));
    });
  };

  const browseDefaultWorkspace = async () => {
    try {
      const workspace = await pickDesktopWorkspace();
      if (!workspace) return;
      setWorkspaceDraft(workspace);
      await saveDefaultWorkspace(workspace);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const showOnboarding =
    uiConfig &&
    !uiConfig.onboarding_complete &&
    !uiConfig.onboarding_dismissed &&
    !modelOptions?.configured;

  const sendPrompt = async (overridePrompt?: string) => {
    const promptText = overridePrompt ?? prompt;
    if (!promptText.trim()) return;
    let activeView = active;
    if (!activeView) {
      activeView = await createSession();
      if (!activeView) {
        setError((current) => current ?? "Unable to create a session. Start a new session and try again.");
        return;
      }
    }
    const sessionId = activeView.session.session_id;
    const controller = new AbortController();
    setIsLoading(true);
    setStreamAbort(controller);
    setError(null);
    setStructuredError(null);
    setSessionBootstrapError(null);
    setLastPrompt(promptText);
    setPrompt("");
    const optimisticTimestamp = new Date().toISOString();
    setActive((current) => {
      if (!current || current.session.session_id !== sessionId) return current;
      return {
        ...current,
        session: {
          ...current.session,
          status: "running",
          transcript: [
            ...(current.session.transcript ?? []),
            { role: "user", content: promptText, timestamp: optimisticTimestamp },
          ],
          current_assistant_message: "",
        },
      };
    });
    setSessions((current) =>
      current.map((session) =>
        session.session_id === sessionId
          ? {
              ...session,
              status: "running",
              transcript: [
                ...(session.transcript ?? []),
                { role: "user", content: promptText, timestamp: optimisticTimestamp },
              ],
              current_assistant_message: "",
            }
          : session,
      ),
    );
    try {
      await streamSessionMessage(
        sessionId,
        promptText,
        {
          onToken: (token) => {
            setActive((current) => {
              if (!current || current.session.session_id !== sessionId) return current;
              return {
                ...current,
                session: {
                  ...current.session,
                  current_assistant_message: `${current.session.current_assistant_message ?? ""}${token}`,
                },
              };
            });
          },
          onError: (message, structured) => {
            if (structured && typeof structured === "object") {
              setStructuredError(structured as StructuredError);
            } else {
              setError(message);
            }
          },
        },
        controller.signal,
        selectedContextFiles,
        activeView.session.workspace_root,
      );
      const view = await api<SessionView>(
        sessionPath(sessionId, "/view", activeView.session.workspace_root),
      );
      applySessionView(view);
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        setError("Generation stopped.");
      } else {
        setError(err instanceof Error ? err.message : String(err));
      }
    } finally {
      setStreamAbort(null);
      setIsLoading(false);
    }
  };

  const stopPrompt = async () => {
    streamAbort?.abort();
    if (active) {
      try {
        await cancelSession(active.session.session_id, active.session.workspace_root);
        const view = await api<SessionView>(
          sessionPath(active.session.session_id, "/view", active.session.workspace_root),
        );
        applySessionView(view);
      } catch {
        // Best-effort cancel
      }
    }
  };

  const retryPrompt = () => {
    if (lastPrompt) void sendPrompt(lastPrompt);
  };

  const changeMode = async (mode: string) => {
    setSelectedMode(mode);
    if (!active) return;
    try {
      const session = await api<Session>(
        sessionPath(active.session.session_id, "/mode", active.session.workspace_root),
        {
          method: "PATCH",
          body: JSON.stringify({ mode }),
        },
      );
      const view = await api<SessionView>(
        sessionPath(session.session_id, "/view", active.session.workspace_root),
      );
      applySessionView(view);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const changeTrustMode = async (trustMode: string) => {
    setSelectedTrustMode(trustMode);
    if (!active) return;
    try {
      const session = await api<Session>(
        sessionPath(active.session.session_id, "/trust-mode", active.session.workspace_root),
        {
          method: "PATCH",
          body: JSON.stringify({ trust_mode: trustMode }),
        },
      );
      const view = await api<SessionView>(
        sessionPath(session.session_id, "/view", active.session.workspace_root),
      );
      applySessionView(view);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const searchContextFiles = async (query: string) => {
    try {
      const matches = await api<FileEntry[]>(
        `/coder/files/search?q=${encodeURIComponent(query)}&limit=12`,
      );
      setFileMatches(matches);
    } catch {
      setFileMatches([]);
    }
  };

  const addContextFile = async (path: string) => {
    const next = selectedContextFiles.includes(path)
      ? selectedContextFiles
      : [...selectedContextFiles, path];
    setSelectedContextFiles(next);
    setFileMatches([]);
    setPrompt((current) => current.replace(/(?:^|\s)@[^\s@]*$/, "").trimStart());
    if (active) {
      try {
        const result = await validateContext(
          active.session.session_id,
          next,
          active.session.workspace_root,
        );
        setContextPreviews(result.items ?? []);
      } catch {
        setContextPreviews([]);
      }
    }
  };

  const removeContextFile = (path: string) => {
    const next = selectedContextFiles.filter((item) => item !== path);
    setSelectedContextFiles(next);
    setContextPreviews((current) => current.filter((item) => item.path !== path));
  };

  const sendDisabledReason =
    active?.session.status === "running"
      ? "Wait for the current turn to finish or press Stop."
      : active?.session.status === "awaiting_approval"
        ? "This turn is waiting for approval. Open Approvals to continue."
        : !active
          ? sessionBootstrapError
            ? `No active session. Last session creation attempt failed: ${sessionBootstrapError}`
            : `No active session. Send will create one automatically${effectiveWorkspaceRoot ? ` in ${effectiveWorkspaceRoot}` : ""}, or use New session first.`
          : null;

  const sessionControlsLocked =
    active?.session.status === "running" || active?.session.status === "awaiting_approval";
  const canResumeSession =
    active?.session.status === "cancelled" ||
    active?.session.status === "failed" ||
    active?.session.status === "blocked";

  const handleApproval = async (requestId: string, grant: boolean) => {
    if (!active) return;
    setIsLoading(true);
    setError(null);
    try {
      const action = grant ? "grant" : "deny";
      const session = await api<Session>(
        sessionPath(
          active.session.session_id,
          `/approvals/${requestId}/${action}`,
          active.session.workspace_root,
        ),
        { method: "POST" },
      );
      const view = await api<SessionView>(
        sessionPath(session.session_id, "/view", active.session.workspace_root),
      );
      applySessionView(view);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsLoading(false);
    }
  };

  const changeTheme = async (theme: UiConfig["theme"]) => {
    window.localStorage.setItem("agentheim-theme", theme);
    document.documentElement.dataset.theme = theme;
    try {
      const config = await api<UiConfig>("/config", {
        method: "PATCH",
        body: JSON.stringify({ theme }),
      });
      setUiConfig(config);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const selectSession = async (sessionId: string) => {
    setIsLoading(true);
    setError(null);
    try {
      const workspaceRoot =
        sessions.find((session) => session.session_id === sessionId)?.workspace_root ??
        active?.session.workspace_root;
      const view = await api<SessionView>(sessionPath(sessionId, "/view", workspaceRoot));
      applySessionView(view);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsLoading(false);
    }
  };

  const resumeActiveSession = async () => {
    if (!active) return;
    setIsLoading(true);
    setError(null);
    try {
      const session = await api<Session>(
        sessionPath(active.session.session_id, "/resume", active.session.workspace_root),
        { method: "POST" },
      );
      const view = await api<SessionView>(
        sessionPath(session.session_id, "/view", active.session.workspace_root),
      );
      applySessionView(view);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsLoading(false);
    }
  };

  const supportedCommandIds = new Set([
    "new",
    "resume",
    "settings",
    "providers",
    "approvals",
    "runs",
    "timeline",
    "terminal",
    "files",
    "usage",
    "retry",
    "stop",
  ]);
  const allCommands: CoderCommand[] = React.useMemo(() => {
    const builtins: CoderCommand[] = [
      { id: "resume", label: "Resume Session", cli: "/resume", surface: "global" },
      { id: "settings", label: "Open Settings", cli: "/settings", surface: "global" },
      { id: "providers", label: "Open Providers & Models", cli: "/providers", surface: "global" },
      { id: "approvals", label: "Open Approvals", cli: "/approvals", surface: "global" },
      { id: "runs", label: "Open Runs", cli: "/runs", surface: "global" },
      { id: "timeline", label: "Open Timeline", cli: "/timeline", surface: "global" },
      { id: "terminal", label: "Open Terminal", cli: "/terminal", surface: "global" },
      { id: "files", label: "Open Files", cli: "/files", surface: "global" },
      { id: "usage", label: "Open Usage", cli: "/usage", surface: "global" },
      { id: "retry", label: "Retry Last Prompt", cli: "/retry", surface: "global" },
      { id: "stop", label: "Stop Current Run", cli: "/stop", surface: "global" },
    ];
    const byId = new Map<string, CoderCommand>();
    for (const command of [...commands, ...builtins]) {
      if (supportedCommandIds.has(command.id) && !byId.has(command.id)) {
        byId.set(command.id, command);
      }
    }
    return Array.from(byId.values());
  }, [commands]);

  const executeCommand = (command: CoderCommand) => {
    if (command.id === "new") {
      createSession();
    } else if (command.id === "settings") {
      setInspector("settings");
    } else if (command.id === "providers") {
      setManagementOpen(true);
    } else if (command.id === "approvals") {
      setInspector("approvals");
    } else if (command.id === "runs") {
      setInspector("runs");
    } else if (command.id === "timeline") {
      setInspector("timeline");
    } else if (command.id === "terminal") {
      setInspector("terminal");
    } else if (command.id === "files") {
      setInspector("files");
    } else if (command.id === "usage") {
      setInspector("usage");
    } else if (command.id === "resume") {
      void resumeActiveSession();
    } else if (command.id === "retry") {
      retryPrompt();
    } else if (command.id === "stop") {
      stopPrompt();
    }
  };

  const updateActiveModel = async (profile: string, model: string) => {
    if (!active) return;
    const session = await api<Session>(
      sessionPath(active.session.session_id, "/model", active.session.workspace_root),
      {
        method: "PATCH",
        body: JSON.stringify({
          profile,
          model,
        }),
      },
    );
    const view = await api<SessionView>(
      sessionPath(session.session_id, "/view", active.session.workspace_root),
    );
    applySessionView(view);
  };

  const changeProfile = async (profile: string) => {
    setSelectedProfile(profile);
    setSelectedModel("auto");
    try {
      await updateActiveModel(profile, "auto");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const changeModel = async (model: string) => {
    setSelectedModel(model);
    try {
      await updateActiveModel(selectedProfile, model);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <ErrorBoundary>
      <main className="shell">
        <Rail
          onNewSession={createSession}
          onSetInspector={setInspector}
          onOpenPalette={() => setPaletteOpen(true)}
          hasApprovals={Boolean(active?.approvals?.length)}
        />

        <section className="work">
          <TopBar
            active={active}
            onNewSession={createSession}
            hasApprovals={Boolean(active?.approvals?.length)}
            onOpenApprovals={() => setInspector("approvals")}
          />

          {(error || structuredError) && (
            <div
              ref={errorRef}
              role="alert"
              tabIndex={-1}
              style={{
                padding: "0.75rem 1rem",
                background:
                  "color-mix(in srgb, var(--error) 20%, transparent)",
                border: "1px solid var(--error)",
                borderRadius: "8px",
                margin: "0 18px",
                outline: "none",
              }}
            >
              {structuredError ? (
                <div>
                  <strong>Error {structuredError.error_code}:</strong>{" "}
                  {structuredError.message}
                  {structuredError.recovery_action && (
                    <div style={{ marginTop: "0.5rem", fontSize: "12px" }}>
                      Recovery: {structuredError.recovery_action}
                    </div>
                  )}
                </div>
              ) : (
                <strong>Error:</strong>
              )}{" "}
              {!structuredError && error}
              <button
                aria-label="Dismiss error"
                onClick={() => {
                  setError(null);
                  setStructuredError(null);
                }}
                style={{ marginLeft: "1rem", float: "right" }}
                type="button"
              >
                Dismiss
              </button>
            </div>
          )}

          {isLoading && (
            <div
              style={{
                padding: "0.5rem 1rem",
                color: "var(--ai)",
                fontSize: "12px",
                textTransform: "uppercase",
              }}
            >
              Loading…
            </div>
          )}

          <Chat active={active} onOpenApprovals={() => setInspector("approvals")} />

          <Composer
            prompt={prompt}
            selectedMode={selectedMode}
            selectedTrustMode={selectedTrustMode}
            selectedProfile={selectedProfile}
            selectedModel={selectedModel}
            modelOptions={modelOptions}
            modeCatalog={modeCatalog}
            onPromptChange={setPrompt}
            onModeChange={changeMode}
            onTrustModeChange={changeTrustMode}
            onProfileChange={changeProfile}
            onModelChange={changeModel}
            onSend={() => void sendPrompt()}
            canSend={
              !isLoading &&
              !streamAbort &&
              active?.session.status !== "running" &&
              active?.session.status !== "awaiting_approval"
            }
            sendDisabledReason={sendDisabledReason}
            onCancel={stopPrompt}
            onRetry={retryPrompt}
            canRetry={Boolean(lastPrompt)}
            onResume={() => void resumeActiveSession()}
            canResume={Boolean(canResumeSession)}
            isSending={Boolean(streamAbort)}
            controlsLocked={Boolean(sessionControlsLocked)}
            selectedContextFiles={selectedContextFiles}
            fileMatches={fileMatches}
            onContextQuery={(query) => void searchContextFiles(query)}
            onContextAdd={addContextFile}
            onContextRemove={removeContextFile}
            contextPreviews={contextPreviews}
          />
        </section>

        <Inspector
          inspector={inspector}
          sessions={sessions}
          active={active}
          commands={allCommands}
          onSelectSession={selectSession}
          onOpenProviderWizard={() => setManagementOpen(true)}
          onGrantApproval={(requestId) => void handleApproval(requestId, true)}
          onDenyApproval={(requestId) => void handleApproval(requestId, false)}
          theme={uiConfig?.theme ?? "dark"}
          onThemeChange={(theme) => void changeTheme(theme)}
          modeCatalog={modeCatalog}
          defaultWorkspace={workspaceDraft || "."}
          onDefaultWorkspaceChange={handleDefaultWorkspaceChange}
          onBrowseDefaultWorkspace={isDesktopApp() ? () => void browseDefaultWorkspace() : undefined}
          workspaceSaveState={workspaceSaveState}
          onAttachFile={addContextFile}
          sessionFilter={sessionFilter}
          onSessionFilterChange={setSessionFilter}
        />

        {wizardOpen && (
          <ProviderWizard
            onClose={() => setWizardOpen(false)}
            onSaved={() => {
              api<ModelOptions>("/coder/models")
                .then(setModelOptions)
                .catch((err) => setError(err.message));
            }}
          />
        )}

        {managementOpen && (
          <ProviderManagementWorkspace
            onClose={() => setManagementOpen(false)}
            onProfilesChanged={() => {
              api<ModelOptions>("/coder/models")
                .then(setModelOptions)
                .catch((err) => setError(err.message));
            }}
          />
        )}

        {paletteOpen && (
          <CommandPalette
            commands={allCommands}
            onClose={() => setPaletteOpen(false)}
            onExecute={executeCommand}
          />
        )}

        {showOnboarding && (
          <Onboarding
            config={uiConfig}
            onSkip={() => void skipOnboarding()}
            onOpenProviderWizard={() => setWizardOpen(true)}
            onComplete={(workspace) => void completeOnboarding(workspace)}
          />
        )}
      </main>
    </ErrorBoundary>
  );
}
