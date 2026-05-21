import React, { useEffect, useRef, useState } from "react";

import type { CoderCommand } from "../types";

interface CommandPaletteProps {
  commands: CoderCommand[];
  onClose: () => void;
  onExecute: (command: CoderCommand) => void;
}

export function CommandPalette({ commands, onClose, onExecute }: CommandPaletteProps) {
  const [query, setQuery] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const filtered = React.useMemo(() => {
    const q = query.toLowerCase();
    return commands.filter(
      (cmd) =>
        cmd.label.toLowerCase().includes(q) || cmd.cli.toLowerCase().includes(q),
    );
  }, [commands, query]);

  return (
    <div
      className="palette"
      role="dialog"
      aria-modal="true"
      aria-label="Command palette"
      aria-expanded="true"
    >
      <input
        ref={inputRef}
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Search commands"
      />
      <div>
        {filtered.map((command) => (
          <button
            key={command.id}
            onClick={() => {
              onExecute(command);
              onClose();
            }}
          >
            <strong>{command.label}</strong>
            <span>{command.cli}</span>
          </button>
        ))}
        {filtered.length === 0 && (
          <div style={{ padding: "0.5rem", color: "var(--muted)" }}>
            No commands found
          </div>
        )}
      </div>
    </div>
  );
}
