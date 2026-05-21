import React, { useEffect, useState } from "react";

import { api } from "./api";
import { Chat } from "./components/Chat";
import { CommandPalette } from "./components/CommandPalette";
import { Composer } from "./components/Composer";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { Inspector } from "./components/Inspector";
import { Rail } from "./components/Rail";
import { TopBar } from "./components/TopBar";
import type { CoderCommand, Session, SessionView } from "./types";

export function App() {
  const [commands, setCommands] = useState<CoderCommand[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [active, setActive] = useState<SessionView | null>(null);
  const [prompt, setPrompt] = useState("");
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [inspector, setInspector] = useState("timeline");
  const [selectedMode, setSelectedMode] = useState("code");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<CoderCommand[]>("/coder/commands")
      .then(setCommands)
      .catch((err) => setError(err.message));
    api<Session[]>("/coder/sessions")
      .then(setSessions)
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
          workspace_root: ".",
          trust_mode: "ask",
          mode: selectedMode,
        }),
      });
      setSessions((current) => [session, ...current]);
      const view = await api<SessionView>(`/coder/sessions/${session.session_id}`);
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
      const session = await api<Session>(
        `/coder/sessions/${active.session.session_id}/messages`,
        {
          method: "POST",
          body: JSON.stringify({ prompt }),
        },
      );
      setActive({ ...active, session });
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
      const view = await api<SessionView>(`/coder/sessions/${sessionId}`);
      setActive(view);
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
      // For CLI-only commands, we could show a toast or copy to clipboard
      console.log("Execute command:", command.cli);
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
                background: "color-mix(in srgb, var(--error) 20%, transparent)",
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
            onPromptChange={setPrompt}
            onModeChange={setSelectedMode}
            onSend={sendPrompt}
          />
        </section>

        <Inspector
          inspector={inspector}
          sessions={sessions}
          onSelectSession={selectSession}
        />

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
