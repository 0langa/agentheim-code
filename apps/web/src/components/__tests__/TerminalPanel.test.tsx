import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import { TerminalPanel } from "../TerminalPanel";

describe("TerminalPanel", () => {
  it("renders terminal output without raw ansi escapes", () => {
    render(
      <TerminalPanel
        results={[
          {
            command: ["pytest"],
            stdout: "\u001b[31mFAIL\u001b[0m",
            stderr: "",
            exit_code: 1,
          },
        ]}
      />,
    );
    expect(screen.getByText("FAIL")).toBeInTheDocument();
    expect(screen.queryByText("\u001b[31mFAIL\u001b[0m")).not.toBeInTheDocument();
  });

  it("shows relative timestamps when available", () => {
    const now = new Date("2026-05-23T12:00:00Z");
    vi.setSystemTime(now);

    render(
      <TerminalPanel
        results={[
          {
            command: ["echo", "hi"],
            stdout: "hi",
            stderr: "",
            exit_code: 0,
            timestamp: "2026-05-23T11:58:00Z",
          },
        ]}
      />,
    );

    expect(screen.getByText("2m ago")).toBeInTheDocument();
    vi.useRealTimers();
  });

  it("shows command count in header", () => {
    render(
      <TerminalPanel
        results={[
          { command: ["a"], stdout: "", stderr: "", exit_code: 0 },
          { command: ["b"], stdout: "", stderr: "", exit_code: 0 },
        ]}
      />,
    );

    expect(screen.getByText("2 commands")).toBeInTheDocument();
  });

  it("groups consecutive successful commands within 5 seconds without a separator", () => {
    const baseTime = new Date("2026-05-23T12:00:00Z").getTime();

    render(
      <TerminalPanel
        results={[
          {
            command: ["a"],
            stdout: "",
            stderr: "",
            exit_code: 0,
            timestamp: new Date(baseTime).toISOString(),
          },
          {
            command: ["b"],
            stdout: "",
            stderr: "",
            exit_code: 0,
            timestamp: new Date(baseTime + 3000).toISOString(),
          },
        ]}
      />,
    );

    const separators = document.querySelectorAll("hr");
    expect(separators.length).toBe(0);
  });

  it("adds a separator between successful commands with a gap over 5 seconds", () => {
    const baseTime = new Date("2026-05-23T12:00:00Z").getTime();

    render(
      <TerminalPanel
        results={[
          {
            command: ["a"],
            stdout: "",
            stderr: "",
            exit_code: 0,
            timestamp: new Date(baseTime).toISOString(),
          },
          {
            command: ["b"],
            stdout: "",
            stderr: "",
            exit_code: 0,
            timestamp: new Date(baseTime + 6000).toISOString(),
          },
        ]}
      />,
    );

    const separators = document.querySelectorAll("hr");
    expect(separators.length).toBe(1);
  });
});
