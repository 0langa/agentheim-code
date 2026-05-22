import React, { useEffect, useState } from "react";

import { api } from "./api";
import { Chat } from "./components/Chat";
import { CommandPalette } from "./components/CommandPalette";
import { Composer } from "./components/Composer";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { Inspector } from "./components/Inspector";
import { ProviderWizard } from "./components/ProviderWizard";
import { Rail } from "./components/Rail";
import { TopBar } from "./components/TopBar";
import type { CoderCommand, ModelOptions, Session, SessionView } from "./types";

export function App() {
  const [commands, setCommands] = useState<CoderCommand[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [active, setActive] = useState<SessionView | null>(null);
  const [modelOptions, setModelOptions] = useState<ModelOptions | null>(null);
  const [prompt, setPrompt] = useState("");
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [wizardOpen, setWizardOpen] = useState(false);
  const [inspector, setInspector] = useState("timeline");
  const [selectedMode, setSelectedMode] = useState("code");
  const [selectedTrustMode, setSelectedTrustMode] = useState("ask");
  const [selectedProfile, setSelectedProfile] = useState("auto");
  const [selectedModel, setSelectedModel] = useState("auto");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
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
  }, []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (
        (event.ctrlKey || event.metaKey) &&
        (event.key.toLowerCase() === "k" || event.key.toLowerCase() === "p")
      ) {
        event.preventDefault();
        setPaletteOpen(true);
      }
      if (event.key === "Escape") {
        setPaletteOpen(false);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const createSession = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const session = await api<Session>("/coder/sessions", {
        method: "POST",
        body: JSON.stringify({
          trust_mode: selectedTrustMode,
          mode: selectedMode,
          profile: selectedProfile === "auto" ? undefined : selectedProfile,
          model: selectedModel === "auto" ? undefined : selectedModel,
        }),
      });
      setSessions((current) => [session, ...current]);
      const view = await api<SessionView>(
        `/coder/sessions/${session.session_id}/view`,
      );
      setActive(view);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsLoading(false);
    }
  };

  const sendPrompt = async () => {
    if (!active || !prompt.trim()) return;
    setIsLoading(true);
    setError(null);
    try {
      await api<Session>(
        `/coder/sessions/${active.session.session_id}/messages`,
        {
          method: "POST",
          body: JSON.stringify({ prompt }),
        },
      );
      const view = await api<SessionView>(
        `/coder/sessions/${active.session.session_id}/view`,
      );
      setActive(view);
      setPrompt("");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsLoading(false);
    }
  };

  const selectSession = async (sessionId: string) => {
    setIsLoading(true);
    setError(null);
    try {
      const view = await api<SessionView>(`/coder/sessions/${sessionId}/view`);
      setActive(view);
      setSelectedMode(view.session.mode ?? "code");
      setSelectedTrustMode(view.session.trust_mode ?? "ask");
      setSelectedProfile(view.session.model_selection?.profile ?? "auto");
      setSelectedModel(view.session.model_selection?.model ?? "auto");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsLoading(false);
    }
  };

  const executeCommand = (command: CoderCommand) => {
    if (command.id === "new") {
      createSession();
    } else {
      console.log("Execute command:", command.cli);
    }
  };

  const updateActiveModel = async (profile: string, model: string) => {
    if (!active) return;
    const session = await api<Session>(
      `/coder/sessions/${active.session.session_id}/model`,
      {
        method: "PATCH",
        body: JSON.stringify({
          profile,
          model,
        }),
      },
    );
    const view = await api<SessionView>(`/coder/sessions/${session.session_id}/view`);
    setActive(view);
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
        />

        <section className="work">
          <TopBar active={active} onNewSession={createSession} />

          {error && (
            <div
              style={{
                padding: "0.75rem 1rem",
                background:
                  "color-mix(in srgb, var(--error) 20%, transparent)",
                border: "1px solid var(--error)",
                borderRadius: "8px",
                margin: "0 18px",
              }}
            >
              <strong>Error:</strong> {error}
              <button
                onClick={() => setError(null)}
                style={{ marginLeft: "1rem", float: "right" }}
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

          <Chat active={active} />

          <Composer
            prompt={prompt}
            selectedMode={selectedMode}
            selectedTrustMode={selectedTrustMode}
            selectedProfile={selectedProfile}
            selectedModel={selectedModel}
            modelOptions={modelOptions}
            onPromptChange={setPrompt}
            onModeChange={setSelectedMode}
            onTrustModeChange={setSelectedTrustMode}
            onProfileChange={changeProfile}
            onModelChange={changeModel}
            onSend={sendPrompt}
          />
        </section>

        <Inspector
          inspector={inspector}
          sessions={sessions}
          active={active}
          commands={commands}
          onSelectSession={selectSession}
          onOpenProviderWizard={() => setWizardOpen(true)}
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

        {paletteOpen && (
          <CommandPalette
            commands={commands}
            onClose={() => setPaletteOpen(false)}
            onExecute={executeCommand}
          />
        )}
      </main>
    </ErrorBoundary>
  );
}
