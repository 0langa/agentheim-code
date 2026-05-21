import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import { Composer } from "../Composer";

describe("Composer", () => {
  it("calls onPromptChange when typing", () => {
    const onPromptChange = vi.fn();
    render(
      <Composer
        prompt=""
        selectedMode="code"
        onPromptChange={onPromptChange}
        onModeChange={vi.fn()}
        onSend={vi.fn()}
      />,
    );
    const textarea = screen.getByPlaceholderText(/Ask Agentheim Code/);
    fireEvent.change(textarea, { target: { value: "hello" } });
    expect(onPromptChange).toHaveBeenCalledWith("hello");
  });

  it("calls onSend when send is clicked", () => {
    const onSend = vi.fn();
    render(
      <Composer
        prompt="test prompt"
        selectedMode="code"
        onPromptChange={vi.fn()}
        onModeChange={vi.fn()}
        onSend={onSend}
      />,
    );
    fireEvent.click(screen.getByText(/Send/));
    expect(onSend).toHaveBeenCalled();
  });

  it("calls onModeChange when a mode is clicked", () => {
    const onModeChange = vi.fn();
    render(
      <Composer
        prompt=""
        selectedMode="code"
        onPromptChange={vi.fn()}
        onModeChange={onModeChange}
        onSend={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByText("review"));
    expect(onModeChange).toHaveBeenCalledWith("review");
  });
});
