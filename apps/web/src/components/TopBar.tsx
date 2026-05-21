import React from "react";

import type { SessionView } from "../types";

interface TopBarProps {
  active: SessionView | null;
  onNewSession: () => void;
}

export function TopBar({ active, onNewSession }: TopBarProps) {
  const modelLabel = React.useMemo(() => {
    const model = active?.session.model_selection;
    if (!model) return "Auto";
    return `${model.provider}/${model.model}`;
  }, [active]);

  return (
    <header className="topbar">
      <div>
        <p>Agentheim Code</p>
        <h1>{active ? active.session.workspace_root : "Coder Hub"}</h1>
      </div>
      <div className="top-actions">
        <button className="model-pill">{modelLabel}</button>
        <button className="primary" onClick={onNewSession}>
          New
        </button>
      </div>
    </header>
  );
}
