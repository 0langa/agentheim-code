import React from "react";

import type { CoderCommand, Session, SessionView } from "../types";

interface InspectorProps {
  inspector: string;
  sessions: Session[];
  active: SessionView | null;
  commands: CoderCommand[];
  onSelectSession: (sessionId: string) => void;
}

function EmptyPanel({ message }: { message: string }) {
  return <p className="panel-empty">{message}</p>;
}

export function Inspector({
  inspector,
  sessions,
  active,
  commands,
  onSelectSession,
}: InspectorProps) {
  const title = inspector[0].toUpperCase() + inspector.slice(1);

  return (
    <aside className="inspector" aria-label="Inspector">
      <header>
        <h2>{title}</h2>
      </header>

      {inspector === "timeline" && (
        <div className="panel-list" aria-live="polite">
          {!active && <EmptyPanel message="Start or resume a session to see activity." />}
          {active?.events?.length === 0 && <EmptyPanel message="No activity yet." />}
          {active?.events?.map((event, index) => (
            <article key={event.event_id ?? index} className="panel-item">
              <strong>{event.type ?? "event"}</strong>
              <span>{event.timestamp ?? "live"}</span>
              {event.message && <p>{event.message}</p>}
            </article>
          ))}
        </div>
      )}

      {inspector === "runs" && (
        <div className="panel-list">
          {sessions.length === 0 && <EmptyPanel message="No sessions yet." />}
          {sessions.map((session) => (
            <button
              key={session.session_id}
              onClick={() => onSelectSession(session.session_id)}
            >
              <strong>{session.session_id}</strong>
              <span>
                {session.status} · {session.mode}
              </span>
              <span>{session.workspace_root}</span>
            </button>
          ))}
          {active?.diffs?.map((diff, index) => (
            <article key={`${diff.path}-${index}`} className="panel-item">
              <strong>{diff.path ?? "changed file"}</strong>
              <span>{diff.status ?? "changed"}</span>
            </article>
          ))}
        </div>
      )}

      {inspector === "terminal" && (
        <div className="panel-list">
          {!active && <EmptyPanel message="No active session." />}
          {active?.command_results?.length === 0 && (
            <EmptyPanel message="No command output yet." />
          )}
          {active?.command_results?.map((result, index) => (
            <article key={index} className="panel-item terminal-item">
              <strong>{result.command?.join(" ") || "command"}</strong>
              <span>
                {result.status ?? "finished"} · exit{" "}
                {result.exit_code === null || result.exit_code === undefined
                  ? "-"
                  : result.exit_code}
              </span>
              {result.stdout && <pre>{result.stdout}</pre>}
              {result.stderr && <pre>{result.stderr}</pre>}
            </article>
          ))}
        </div>
      )}

      {inspector === "settings" && (
        <div className="panel-list">
          <article className="panel-item">
            <strong>Session</strong>
            <span>mode: {active?.session.mode ?? "code"}</span>
            <span>trust: {active?.session.trust_mode ?? "ask"}</span>
            <span>
              model:{" "}
              {active?.session.model_selection?.model ??
                active?.session.model_selection?.provider ??
                "auto"}
            </span>
            <span>provider: {active?.session.model_selection?.provider ?? "auto"}</span>
          </article>
          <article className="panel-item">
            <strong>Commands</strong>
            {commands.map((command) => (
              <span key={command.id}>
                {command.label} · {command.cli}
              </span>
            ))}
          </article>
        </div>
      )}
    </aside>
  );
}
