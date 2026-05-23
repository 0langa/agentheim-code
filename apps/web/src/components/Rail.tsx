import React from "react";
import { Activity, BarChart3, Bot, Command, GitPullRequest, ShieldCheck, Settings, Terminal } from "lucide-react";

interface RailProps {
  onNewSession: () => void;
  onSetInspector: (name: string) => void;
  onOpenPalette: () => void;
  hasApprovals?: boolean;
}

export function Rail({ onNewSession, onSetInspector, onOpenPalette, hasApprovals = false }: RailProps) {
  return (
    <nav className="rail" aria-label="Main">
      <button title="New session" onClick={onNewSession}>
        <Bot size={20} />
      </button>
      <button title="Timeline" onClick={() => onSetInspector("timeline")}>
        <Activity size={20} />
      </button>
      <button title="Runs" onClick={() => onSetInspector("runs")}>
        <GitPullRequest size={20} />
      </button>
      <button title="Terminal" onClick={() => onSetInspector("terminal")}>
        <Terminal size={20} />
      </button>
      <button
        title="Approvals"
        className={hasApprovals ? "needs-attention" : undefined}
        onClick={() => onSetInspector("approvals")}
      >
        <ShieldCheck size={20} />
      </button>
      <button title="Command palette" onClick={onOpenPalette}>
        <Command size={20} />
      </button>
      <button title="Usage" onClick={() => onSetInspector("usage")}>
        <BarChart3 size={20} />
      </button>
      <button title="Settings" onClick={() => onSetInspector("settings")}>
        <Settings size={20} />
      </button>
    </nav>
  );
}
