import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { Chat } from "../Chat";
import type { SessionView } from "../../types";

const ACTIVE_VIEW: SessionView = {
  session: {
    session_id: "test-123",
    status: "idle",
    mode: "code",
    workspace_root: ".",
    transcript: [
      { role: "user", content: "Hello" },
      { role: "assistant", content: "Hi there" },
    ],
    current_assistant_message: "Typing...",
  },
  queued_prompts: [],
  available_commands: [],
};

const NO_TRANSCRIPT_VIEW: SessionView = {
  session: {
    session_id: "test-456",
    status: "running",
    mode: "ask",
    workspace_root: ".",
  },
  queued_prompts: [],
  available_commands: [],
};

describe("Chat", () => {
  it("shows empty state when no session is active", () => {
    render(<Chat active={null} />);
    expect(screen.getByText("Start a focused coding session")).toBeInTheDocument();
  });

  it("renders transcript messages from session.transcript", () => {
    render(<Chat active={ACTIVE_VIEW} />);
    expect(screen.getByText("Hello")).toBeInTheDocument();
    expect(screen.getByText("Hi there")).toBeInTheDocument();
  });

  it("renders current_assistant_message from session", () => {
    render(<Chat active={ACTIVE_VIEW} />);
    expect(screen.getByText("Typing...")).toBeInTheDocument();
  });

  it("shows 'No messages yet' when transcript is empty", () => {
    render(<Chat active={NO_TRANSCRIPT_VIEW} />);
    expect(screen.getByText("No messages yet")).toBeInTheDocument();
  });
});
