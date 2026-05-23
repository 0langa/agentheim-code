import React, { useEffect, useRef, useState } from "react";

import type { CoderCommand } from "../types";
import { useModalA11y } from "../hooks/useModalA11y";

interface CommandPaletteProps {
  commands: CoderCommand[];
  onClose: () => void;
  onExecute: (command: CoderCommand) => void;
}

export function CommandPalette({ commands, onClose, onExecute }: CommandPaletteProps) {
  const [query, setQuery] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const descriptionId = React.useId();

  useModalA11y({
    containerRef,
    initialFocusRef: inputRef,
    onEscape: onClose,
  });

  const filtered = React.useMemo(() => {
    const q = query.toLowerCase();
    return commands.filter(
      (cmd) =>
        cmd.label.toLowerCase().includes(q) ||
        cmd.cli.toLowerCase().includes(q),
    );
  }, [commands, query]);

  const executeFirst = () => {
    if (filtered[0]) {
      onExecute(filtered[0]);
      onClose();
    }
  };

  return (
    <div
      ref={containerRef}
      className="palette"
      role="dialog"
      aria-modal="true"
      aria-label="Command palette"
      aria-describedby={descriptionId}
      tabIndex={-1}
    >
      <p id={descriptionId} className="sr-only">
        Search commands, press Enter to run the first result, or Escape to close.
      </p>
      <input
        ref={inputRef}
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            executeFirst();
          }
          if (event.key === "Escape") {
            event.preventDefault();
            onClose();
          }
        }}
        placeholder="Search commands"
      />
      <div>
        {filtered.map((command) => (
          <button
            key={command.id}
            type="button"
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
