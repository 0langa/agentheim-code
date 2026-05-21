import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { Bot, Command, FolderOpen, GitPullRequest, Play, Settings, Terminal } from "lucide-react";
import "./styles.css";

type CoderCommand = {
  id: string;
  label: string;
  cli: string;
  surface: string;
};

type Session = {
  session_id: string;
  status: string;
  mode: string;
  workspace_root: string;
  model_selection?: {
    provider: string;
    model: string;
  };
};

type SessionView = {
  session: Session;
  queued_prompts: string[];
  available_commands: string[];
};

const api = async <T,>(path: string, init?: RequestInit): Promise<T> => {
  const response = await fetch(path, {
    headers: { "content-type": "application/json" },
    ...init
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json() as Promise<T>;
};

function App() {
  const [commands, setCommands] = useState<CoderCommand[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [active, setActive] = useState<SessionView | null>(null);
  const [prompt, setPrompt] = useState("");
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [inspector, setInspector] = useState("timeline");

  useEffect(() => {
    api<CoderCommand[]>("/api/coder/commands").then(setCommands).catch(console.error);
    api<Session[]>("/api/coder/sessions").then(setSessions).catch(console.error);
  }, []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && (event.key.toLowerCase() === "k" || event.key.toLowerCase() === "p")) {
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

  const modelLabel = useMemo(() => {
    const model = active?.session.model_selection;
    if (!model) return "Auto";
    return `${model.provider}/${model.model}`;
  }, [active]);

  const createSession = async () => {
    const session = await api<Session>("/api/coder/sessions", {
      method: "POST",
      body: JSON.stringify({ workspace_root: ".", trust_mode: "ask", mode: "code" })
    });
    setSessions((current) => [session, ...current]);
    const view = await api<SessionView>(`/api/coder/sessions/${session.session_id}`);
    setActive(view);
  };

  const sendPrompt = async () => {
    if (!active || !prompt.trim()) return;
    const session = await api<Session>(`/api/coder/sessions/${active.session.session_id}/messages`, {
      method: "POST",
      body: JSON.stringify({ prompt })
    });
    setActive({ ...active, session });
    setPrompt("");
  };

  return (
    <main className="shell">
      <nav className="rail" aria-label="Main">
        <button title="New session" onClick={createSession}><Bot size={20} /></button>
        <button title="Open workspace"><FolderOpen size={20} /></button>
        <button title="Runs" onClick={() => setInspector("runs")}><GitPullRequest size={20} /></button>
        <button title="Terminal" onClick={() => setInspector("terminal")}><Terminal size={20} /></button>
        <button title="Command palette" onClick={() => setPaletteOpen(true)}><Command size={20} /></button>
        <button title="Settings" onClick={() => setInspector("settings")}><Settings size={20} /></button>
      </nav>

      <section className="work">
        <header className="topbar">
          <div>
            <p>Agentheim Code</p>
            <h1>{active ? active.session.workspace_root : "Coder Hub"}</h1>
          </div>
          <div className="top-actions">
            <button className="model-pill">{modelLabel}</button>
            <button className="primary" onClick={createSession}>New</button>
          </div>
        </header>

        <section className="chat" aria-live="polite">
          {active ? (
            <article className="message">
              <strong>{active.session.status}</strong>
              <span>{active.session.mode}</span>
            </article>
          ) : (
            <div className="empty">
              <strong>Start a focused coding session</strong>
              <span>Use the composer, command palette, or session rail.</span>
            </div>
          )}
        </section>

        <footer className="composer">
          <div className="modes">
            {["ask", "plan", "code", "review", "fix", "docs", "test"].map((mode) => (
              <button key={mode}>{mode}</button>
            ))}
          </div>
          <textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} placeholder="Ask Agentheim Code to build, fix, review, test, or explain..." />
          <div className="composer-row">
            <span>Ctrl+K</span>
            <button className="primary" onClick={sendPrompt}><Play size={16} /> Send</button>
          </div>
        </footer>
      </section>

      <aside className="inspector" aria-label="Inspector">
        <header>
          <h2>{inspector}</h2>
        </header>
        <div className="panel-list">
          {sessions.map((session) => (
            <button key={session.session_id} onClick={async () => setActive(await api<SessionView>(`/api/coder/sessions/${session.session_id}`))}>
              <strong>{session.session_id}</strong>
              <span>{session.status}</span>
            </button>
          ))}
        </div>
      </aside>

      {paletteOpen && (
        <div className="palette" role="dialog" aria-modal="true" aria-label="Command palette">
          <input autoFocus placeholder="Search commands" />
          <div>
            {commands.map((command) => (
              <button key={command.id} onClick={() => setPaletteOpen(false)}>
                <strong>{command.label}</strong>
                <span>{command.cli}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<App />);

