import React from "react";

import type { Session, SessionView } from "../types";

interface InspectorProps {
  inspector: string;
  sessions: Session[];
  onSelectSession: (sessionId: string) => void;
}

export function Inspector({ inspector, sessions, onSelectSession }: InspectorProps) {
  return (
    <aside className="inspector" aria-label="Inspector">
      <header>
        <h2>{inspector}</h2>
      </header>
      <div className="panel-list">
        {sessions.map((session) => (
          <button
            key={session.session_id}
            onClick={() => onSelectSession(session.session_id)}
          >
            <strong>{session.session_id}</strong>
            <span>{session.status}</span>
          </button>
        ))}
      </div>
    </aside>
  );
}
