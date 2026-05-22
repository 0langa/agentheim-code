import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import { Composer } from "../Composer";

const baseProps = {
  selectedProfile: "auto",
  selectedModel: "auto",
  modelOptions: null,
  onProfileChange: vi.fn(),
  onModelChange: vi.fn(),
};

describe("Composer", () => {
  it("calls onPromptChange when typing", () => {
    const onPromptChange = vi.fn();
    render(
      <Composer
        prompt=""
        selectedMode="code"
        selectedTrustMode="ask"
        {...baseProps}
        onPromptChange={onPromptChange}
        onModeChange={vi.fn()}
        onTrustModeChange={vi.fn()}
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
        selectedTrustMode="ask"
        {...baseProps}
        onPromptChange={vi.fn()}
        onModeChange={vi.fn()}
        onTrustModeChange={vi.fn()}
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
        selectedTrustMode="ask"
        {...baseProps}
        onPromptChange={vi.fn()}
        onModeChange={onModeChange}
        onTrustModeChange={vi.fn()}
        onSend={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByText("review"));
    expect(onModeChange).toHaveBeenCalledWith("review");
  });

  it("calls onSend with Ctrl+Enter", () => {
    const onSend = vi.fn();
    render(
      <Composer
        prompt="test prompt"
        selectedMode="code"
        selectedTrustMode="ask"
        {...baseProps}
        onPromptChange={vi.fn()}
        onModeChange={vi.fn()}
        onTrustModeChange={vi.fn()}
        onSend={onSend}
      />,
    );
    fireEvent.keyDown(screen.getByPlaceholderText(/Ask Agentheim Code/), {
      key: "Enter",
      ctrlKey: true,
    });
    expect(onSend).toHaveBeenCalled();
  });

  it("calls onTrustModeChange when trust mode changes", () => {
    const onTrustModeChange = vi.fn();
    render(
      <Composer
        prompt=""
        selectedMode="code"
        selectedTrustMode="ask"
        {...baseProps}
        onPromptChange={vi.fn()}
        onModeChange={vi.fn()}
        onTrustModeChange={onTrustModeChange}
        onSend={vi.fn()}
      />,
    );
    fireEvent.change(screen.getByLabelText("Trust mode"), {
      target: { value: "workspace" },
    });
    expect(onTrustModeChange).toHaveBeenCalledWith("workspace");
  });
});
