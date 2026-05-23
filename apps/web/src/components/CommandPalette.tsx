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
  const [selectedIndex, setSelectedIndex] = useState(0);
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

  useEffect(() => {
    setSelectedIndex(0);
  }, [filtered.length, query]);

  const executeSelected = () => {
    const cmd = filtered[selectedIndex];
    if (cmd) {
      onExecute(cmd);
      onClose();
    }
  };

  const handleKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setSelectedIndex((i) => (filtered.length ? (i + 1) % filtered.length : 0));
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      setSelectedIndex((i) => (filtered.length ? (i - 1 + filtered.length) % filtered.length : 0));
    }
    if (event.key === "Enter") {
      event.preventDefault();
      executeSelected();
    }
    if (event.key === "Escape") {
      event.preventDefault();
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
        Search commands, press Enter to run the selected result, or Escape to close.
      </p>
      <input
        ref={inputRef}
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Search commands"
      />
      <div>
        {filtered.map((command, index) => (
          <button
            key={command.id}
            type="button"
            onClick={() => {
              onExecute(command);
              onClose();
            }}
            style={{
              background:
                index === selectedIndex
                  ? "color-mix(in srgb, var(--accent) 20%, transparent)"
                  : undefined,
              borderColor:
                index === selectedIndex
                  ? "color-mix(in srgb, var(--accent) 50%, transparent)"
                  : undefined,
            }}
          >
            <strong>{command.label}</strong>
            <span>{command.cli}</span>
          </button>
        ))}
        {filtered.length === 0 && (
          <div style={{ padding: "0.5rem", color: "var(--muted)" }}>
            No matching commands
          </div>
        )}
      </div>
      <div
        style={{
          padding: "4px 8px",
          fontSize: "11px",
          color: "var(--muted)",
          borderTop: "1px solid var(--border-subtle)",
        }}
      >
        ↑↓ navigate · Enter run · Escape close
      </div>
    </div>
  );
}
