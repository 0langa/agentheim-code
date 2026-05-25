import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { Chat } from "../Chat";
import type { SessionView } from "../../types";

const BASE_SESSION = {
  session_id: "test-123",
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
} as const;

const ACTIVE_VIEW: SessionView = {
  session: {
    ...BASE_SESSION,
    transcript: [
      { role: "user", content: "Hello", timestamp: "2026-05-25T12:00:00Z" },
      { role: "assistant", content: "Hi there", timestamp: "2026-05-25T12:00:01Z" },
    ],
    current_assistant_message: "Typing...",
  },
  queued_prompts: [],
  available_commands: [],
};

const NO_TRANSCRIPT_VIEW: SessionView = {
  session: {
    ...BASE_SESSION,
    session_id: "test-456",
    status: "running",
    mode: "ask",
  },
  queued_prompts: [],
  available_commands: [],
};

describe("Chat", () => {
  it("shows empty state when no session is active", () => {
    render(<Chat active={null} />);
    expect(screen.getByText("Start a focused coding session")).toBeInTheDocument();
    expect(screen.getByRole("log", { name: "Conversation transcript" })).toBeInTheDocument();
  });

  it("renders transcript messages from session.transcript", () => {
    render(<Chat active={ACTIVE_VIEW} />);
    expect(screen.getByText("Hello")).toBeInTheDocument();
    expect(screen.getByText("Hi there")).toBeInTheDocument();
  });

  it("renders current_assistant_message from session", () => {
    render(<Chat active={ACTIVE_VIEW} />);
    expect(screen.getByText("Typing...")).toBeInTheDocument();
    expect(screen.getByRole("log", { name: "Conversation transcript" })).toHaveAttribute(
      "aria-busy",
      "false",
    );
  });

  it("shows 'No messages yet' when transcript is empty", () => {
    render(<Chat active={NO_TRANSCRIPT_VIEW} />);
    expect(screen.getByText("No messages yet")).toBeInTheDocument();
  });

  it("renders markdown code blocks with copy controls", () => {
    render(
      <Chat
        active={{
          ...ACTIVE_VIEW,
          session: {
            ...ACTIVE_VIEW.session,
            transcript: [
              {
                role: "assistant",
                content: "Use this:\n\n```ts\nconst ok = true;\n```",
                timestamp: "2026-05-25T12:00:02Z",
              },
            ],
            current_assistant_message: undefined,
          },
        }}
      />,
    );

    expect(screen.getByText("Use this:")).toBeInTheDocument();
    expect(screen.getByText("const ok = true;")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copy code block" })).toBeInTheDocument();
  });

  it("marks the transcript busy while a response is streaming", () => {
    render(
      <Chat
        active={{
          ...ACTIVE_VIEW,
          session: {
            ...ACTIVE_VIEW.session,
            status: "running",
          },
        }}
      />,
    );

    expect(screen.getByRole("log", { name: "Conversation transcript" })).toHaveAttribute(
      "aria-busy",
      "true",
    );
  });
});
