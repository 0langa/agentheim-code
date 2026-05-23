import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { Inspector } from "../Inspector";
import type { CoderCommand, Session, SessionView } from "../../types";

const sessions: Session[] = [
  { session_id: "sess-1", status: "idle", mode: "code", workspace_root: "." },
];

const commands: CoderCommand[] = [
  { id: "new", label: "New Session", cli: "/new", surface: "cli" },
];

const active: SessionView = {
  session: {
    session_id: "sess-1",
    status: "idle",
    mode: "code",
    trust_mode: "ask",
    workspace_root: ".",
    model_selection: { provider: "auto", model: "auto" },
  },
  queued_prompts: [],
  available_commands: [],
  events: [{ type: "tool", message: "listed files" }],
  command_results: [{ command: ["pytest"], exit_code: 0, stdout: "passed" }],
  diffs: [{ path: "src/app.ts", status: "modified" }],
};

describe("Inspector", () => {
  it("renders timeline activity", () => {
    render(
      <Inspector
        inspector="timeline"
        sessions={sessions}
        active={active}
        commands={commands}
        onSelectSession={() => undefined}
        onOpenProviderWizard={() => undefined}
      />,
    );
    expect(screen.getByText("listed files")).toBeInTheDocument();
  });

  it("renders terminal command output", () => {
    render(
      <Inspector
        inspector="terminal"
        sessions={sessions}
        active={active}
        commands={commands}
        onSelectSession={() => undefined}
        onOpenProviderWizard={() => undefined}
      />,
    );
    expect(screen.getByText("pytest")).toBeInTheDocument();
    expect(screen.getByText("passed")).toBeInTheDocument();
  });

  it("renders settings summary and commands", async () => {
    render(
      <Inspector
        inspector="settings"
        sessions={sessions}
        active={active}
        commands={commands}
        onSelectSession={() => undefined}
        onOpenProviderWizard={() => undefined}
      />,
    );
    expect(screen.getByText("trust: ask")).toBeInTheDocument();
    expect(screen.getByText("New Session · /new")).toBeInTheDocument();
    expect(
      await screen.findByText("No providers configured. Add one to get started."),
    ).toBeInTheDocument();
  });
});
