import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import { CommandPalette } from "../CommandPalette";
import type { CoderCommand } from "../../types";

const COMMANDS: CoderCommand[] = [
  { id: "new", label: "New Session", cli: "/new", surface: "cli" },
  { id: "resume", label: "Resume Session", cli: "/resume", surface: "cli" },
];

describe("CommandPalette", () => {
  it("renders all commands", () => {
    render(
      <CommandPalette commands={COMMANDS} onClose={vi.fn()} onExecute={vi.fn()} />,
    );
    expect(screen.getByText("New Session")).toBeInTheDocument();
    expect(screen.getByText("Resume Session")).toBeInTheDocument();
  });

  it("filters by query", () => {
    render(
      <CommandPalette commands={COMMANDS} onClose={vi.fn()} onExecute={vi.fn()} />,
    );
    const input = screen.getByPlaceholderText("Search commands");
    fireEvent.change(input, { target: { value: "new" } });
    expect(screen.getByText("New Session")).toBeInTheDocument();
    expect(screen.queryByText("Resume Session")).not.toBeInTheDocument();
  });

  it("calls onExecute when a command is clicked", () => {
    const onExecute = vi.fn();
    render(
      <CommandPalette commands={COMMANDS} onClose={vi.fn()} onExecute={onExecute} />,
    );
    fireEvent.click(screen.getByText("New Session"));
    expect(onExecute).toHaveBeenCalledWith(COMMANDS[0]);
  });
});
