import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

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
        onGrantApproval={() => undefined}
        onDenyApproval={() => undefined}
        theme="dark"
        onThemeChange={() => undefined}
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
        onGrantApproval={() => undefined}
        onDenyApproval={() => undefined}
        theme="dark"
        onThemeChange={() => undefined}
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
        onGrantApproval={() => undefined}
        onDenyApproval={() => undefined}
        theme="dark"
        onThemeChange={() => undefined}
      />,
    );
    expect(screen.getByText("trust: ask")).toBeInTheDocument();
    expect(screen.getByText("New Session · /new")).toBeInTheDocument();
    expect(
      await screen.findByText("No providers configured. Add one to get started."),
    ).toBeInTheDocument();
  });

  it("changes theme from settings", async () => {
    const onThemeChange = vi.fn();
    render(
      <Inspector
        inspector="settings"
        sessions={sessions}
        active={active}
        commands={commands}
        onSelectSession={() => undefined}
        onOpenProviderWizard={() => undefined}
        onGrantApproval={() => undefined}
        onDenyApproval={() => undefined}
        theme="dark"
        onThemeChange={onThemeChange}
      />,
    );

    fireEvent.change(screen.getByLabelText("Theme"), {
      target: { value: "high_contrast" },
    });
    expect(onThemeChange).toHaveBeenCalledWith("high_contrast");
  });

  it("renders approval action details and controls", () => {
    const grant = vi.fn();
    const deny = vi.fn();
    render(
      <Inspector
        inspector="approvals"
        sessions={sessions}
        active={{
          ...active,
          approvals: [
            {
              request_id: "req-1",
              tool_id: "shell.execute",
              risk_level: "medium",
              reason: "Run tests",
              status: "pending",
              action_kind: "shell",
              target: "pytest -q",
              params: { command: ["pytest", "-q"], cwd: "." },
            },
          ],
        }}
        commands={commands}
        onSelectSession={() => undefined}
        onOpenProviderWizard={() => undefined}
        onGrantApproval={grant}
        onDenyApproval={deny}
        theme="dark"
        onThemeChange={() => undefined}
      />,
    );

    expect(screen.getByText("shell.execute")).toBeInTheDocument();
    expect(screen.getAllByText("pytest -q").length).toBeGreaterThan(0);
    fireEvent.click(screen.getByText("Grant"));
    fireEvent.click(screen.getByText("Deny"));
    expect(grant).toHaveBeenCalledWith("req-1");
    expect(deny).toHaveBeenCalledWith("req-1");
  });
});
