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
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  // Focus trap: keep focus inside the palette
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Tab") return;
      const focusable = container.querySelectorAll<HTMLElement>(
        "input, button",
      );
      const first = focusable[0];
      const last = focusable[focusable.length - 1];

      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    container.addEventListener("keydown", handleKeyDown);
    return () => container.removeEventListener("keydown", handleKeyDown);
  }, []);

  const filtered = React.useMemo(() => {
    const q = query.toLowerCase();
    return commands.filter(
      (cmd) =>
        cmd.label.toLowerCase().includes(q) ||
        cmd.cli.toLowerCase().includes(q),
    );
  }, [commands, query]);

  return (
    <div
      ref={containerRef}
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
