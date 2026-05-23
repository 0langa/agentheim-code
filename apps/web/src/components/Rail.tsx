import React from "react";
import { Activity, BarChart3, Bot, Command, FileText, GitPullRequest, ShieldCheck, Settings, Terminal } from "lucide-react";

interface RailProps {
  onNewSession: () => void;
  onSetInspector: (name: string) => void;
  onOpenPalette: () => void;
  hasApprovals?: boolean;
}

export function Rail({ onNewSession, onSetInspector, onOpenPalette, hasApprovals = false }: RailProps) {
  return (
    <nav className="rail" aria-label="Main">
      <button aria-label="New session" title="New session" type="button" onClick={onNewSession}>
        <Bot size={20} />
      </button>
      <button aria-label="Timeline" title="Timeline" type="button" onClick={() => onSetInspector("timeline")}>
        <Activity size={20} />
      </button>
      <button aria-label="Runs" title="Runs" type="button" onClick={() => onSetInspector("runs")}>
        <GitPullRequest size={20} />
      </button>
      <button aria-label="Files" title="Files" type="button" onClick={() => onSetInspector("files")}>
        <FileText size={20} />
      </button>
      <button aria-label="Terminal" title="Terminal" type="button" onClick={() => onSetInspector("terminal")}>
        <Terminal size={20} />
      </button>
      <button
        aria-label="Approvals"
        title="Approvals"
        className={hasApprovals ? "needs-attention" : undefined}
        type="button"
        onClick={() => onSetInspector("approvals")}
      >
        <ShieldCheck size={20} />
      </button>
      <button aria-label="Command palette" title="Command palette" type="button" onClick={onOpenPalette}>
        <Command size={20} />
      </button>
      <button aria-label="Usage" title="Usage" type="button" onClick={() => onSetInspector("usage")}>
        <BarChart3 size={20} />
      </button>
      <button aria-label="Settings" title="Settings" type="button" onClick={() => onSetInspector("settings")}>
        <Settings size={20} />
      </button>
    </nav>
  );
}
