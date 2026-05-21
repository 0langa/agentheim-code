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
  },
  queued_prompts: [],
  available_commands: [],
  transcript: [
    { role: "user", content: "Hello" },
    { role: "assistant", content: "Hi there" },
  ],
};

describe("Chat", () => {
  it("shows empty state when no session is active", () => {
    render(<Chat active={null} />);
    expect(screen.getByText("Start a focused coding session")).toBeInTheDocument();
  });

  it("renders transcript messages when active", () => {
    render(<Chat active={ACTIVE_VIEW} />);
    expect(screen.getByText("Hello")).toBeInTheDocument();
    expect(screen.getByText("Hi there")).toBeInTheDocument();
  });
});
