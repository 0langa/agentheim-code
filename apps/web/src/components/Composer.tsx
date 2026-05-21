import React from "react";
import { Play } from "lucide-react";

interface ComposerProps {
  prompt: string;
  selectedMode: string;
  onPromptChange: (value: string) => void;
  onModeChange: (mode: string) => void;
  onSend: () => void;
}

const MODES = ["ask", "plan", "code", "review", "fix", "docs", "test"];

export function Composer({
  prompt,
  selectedMode,
  onPromptChange,
  onModeChange,
  onSend,
}: ComposerProps) {
  return (
    <footer className="composer">
      <div className="modes">
        {MODES.map((mode) => (
          <button
            key={mode}
            aria-pressed={mode === selectedMode}
            style={
              mode === selectedMode
                ? { background: "var(--accent)", borderColor: "var(--accent-hover)" }
                : undefined
            }
            onClick={() => onModeChange(mode)}
          >
            {mode}
          </button>
        ))}
      </div>
      <textarea
        value={prompt}
        onChange={(event) => onPromptChange(event.target.value)}
        placeholder="Ask Agentheim Code to build, fix, review, test, or explain..."
      />
      <div className="composer-row">
        <span>Ctrl+K</span>
        <button className="primary" onClick={onSend} disabled={!prompt.trim()}>
          <Play size={16} /> Send
        </button>
      </div>
    </footer>
  );
}
