import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { Inspector } from "../Inspector";
import type { CoderCommand, Session, SessionView } from "../../types";

const mockApi = vi.fn((_path: string) => Promise.reject(new Error("network")));
vi.mock("../../api", () => ({
  api: <T,>(path: string, _init?: RequestInit): Promise<T> => mockApi(path) as Promise<T>,
}));

const makeSession = (overrides: Partial<Session> = {}): Session => ({
  session_id: "sess-1",
  status: "idle",
  mode: "code",
  trust_mode: "ask",
  workspace_root: ".",
  model_selection: {
    profile: "local",
    provider: "ollama",
    model: "llama3.2",
  },
  repair_attempts: 0,
  last_failure_reason: "",
  ...overrides,
});

const sessions: Session[] = [makeSession()];

const commands: CoderCommand[] = [
  { id: "new", label: "New Session", cli: "/new", surface: "cli" },
];

const defaultInspectorProps = {
  onSelectSession: () => undefined,
  onOpenProviderWizard: () => undefined,
  onGrantApproval: () => undefined,
  onDenyApproval: () => undefined,
  theme: "dark" as const,
  onThemeChange: () => undefined,
  defaultWorkspace: ".",
  onDefaultWorkspaceChange: () => undefined,
};

const active: SessionView = {
  session: {
    ...makeSession(),
    model_selection: { profile: "auto", provider: "auto", model: "auto" },
  },
  queued_prompts: [],
  available_commands: [],
  events: [
    {
      event_id: "evt-1",
      type: "tool",
      message: "listed files",
      timestamp: "2026-05-25T12:00:00Z",
    },
  ],
  command_results: [
    {
      command: ["pytest"],
      exit_code: 0,
      status: "ok",
      stdout: "passed",
      stderr: "",
      timestamp: "2026-05-25T12:00:01Z",
    },
  ],
  diffs: [
    {
      path: "src/app.ts",
      status: "modified",
      before: "before",
      after: "after",
      timestamp: "2026-05-25T12:00:02Z",
    },
  ],
};

describe("Inspector", () => {
  it("renders timeline activity", () => {
    render(
      <Inspector
        inspector="timeline"
        sessions={sessions}
        active={active}
        commands={commands}
        {...defaultInspectorProps}
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
        {...defaultInspectorProps}
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
        {...defaultInspectorProps}
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
        {...defaultInspectorProps}
        theme="dark"
        onThemeChange={onThemeChange}
      />,
    );

    await screen.findByText("No providers configured. Add one to get started.");
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
        {...defaultInspectorProps}
        onGrantApproval={grant}
        onDenyApproval={deny}
      />,
    );

    expect(screen.getByText("shell.execute")).toBeInTheDocument();
    expect(screen.getAllByText("pytest -q").length).toBeGreaterThan(0);
    fireEvent.click(screen.getByText("Grant"));
    fireEvent.click(screen.getByText("Deny"));
    expect(grant).toHaveBeenCalledWith("req-1");
    expect(deny).toHaveBeenCalledWith("req-1");
  });

  it("renders relative timestamps in timeline", () => {
    const now = new Date("2026-05-23T12:00:00Z");
    vi.setSystemTime(now);

    render(
      <Inspector
        inspector="timeline"
        sessions={sessions}
        active={{
          ...active,
          events: [
            {
              event_id: "evt-2",
              type: "tool",
              message: "listed files",
              timestamp: "2026-05-23T11:55:00Z",
            },
          ],
        }}
        commands={commands}
        {...defaultInspectorProps}
      />,
    );

    expect(screen.getByText("5m ago")).toBeInTheDocument();
    vi.useRealTimers();
  });

  it("supports keyboard navigation in runs panel", () => {
    render(
      <Inspector
        inspector="runs"
        sessions={[
          makeSession(),
          makeSession({ session_id: "sess-2", status: "running" }),
        ]}
        active={active}
        commands={commands}
        {...defaultInspectorProps}
      />,
    );

    const buttons = screen.getAllByRole("button").filter((b) => b.classList.contains("run-session-button"));
    expect(buttons.length).toBe(2);

    buttons[0].focus();
    fireEvent.keyDown(buttons[0], { key: "ArrowDown" });
    expect(buttons[1]).toHaveFocus();

    fireEvent.keyDown(buttons[1], { key: "ArrowUp" });
    expect(buttons[0]).toHaveFocus();
  });

  it("renders file edit approvals with before/after preview", () => {
    render(
      <Inspector
        inspector="approvals"
        sessions={sessions}
        active={{
          ...active,
          approvals: [
            {
              request_id: "req-2",
              tool_id: "file.write",
              risk_level: "low",
              reason: "Update config",
              status: "pending",
              action_kind: "file",
              target: "config.json",
              params: { old_content: '{"a":1}', content: '{"a":2}' },
            },
          ],
        }}
        commands={commands}
        {...defaultInspectorProps}
      />,
    );

    expect(screen.getByText("Before")).toBeInTheDocument();
    expect(screen.getByText("After")).toBeInTheDocument();
    expect(screen.getByText('{"a":1}')).toBeInTheDocument();
    expect(screen.getByText('{"a":2}')).toBeInTheDocument();
  });

  it("renders keyboard shortcuts in settings", async () => {
    render(
      <Inspector
        inspector="settings"
        sessions={sessions}
        active={active}
        commands={commands}
        {...defaultInspectorProps}
      />,
    );

    await screen.findByText("No providers configured. Add one to get started.");
    expect(screen.getByText("Keyboard Shortcuts")).toBeInTheDocument();
    expect(screen.getByText(/Ctrl\+K/)).toBeInTheDocument();
    expect(screen.getByText(/Ctrl\+,/)).toBeInTheDocument();
  });
});
