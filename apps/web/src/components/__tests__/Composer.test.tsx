import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import { Composer } from "../Composer";
import type { ModeCatalog } from "../../types";

const baseProps = {
  selectedProfile: "auto",
  selectedModel: "auto",
  modelOptions: null,
  modeCatalog: {
    modes: [
      { id: "ask", label: "Ask", description: "Answer directly.", edits_expected: false, legacy_aliases: ["plan"] },
      { id: "code", label: "Code", description: "Implement and verify.", edits_expected: true, legacy_aliases: ["fix", "docs", "test"] },
      { id: "review", label: "Review", description: "Inspect critically.", edits_expected: false, legacy_aliases: [] },
    ],
    trust_modes: [
      { id: "ask", label: "ask", description: "Pause for risky tools." },
      { id: "read_only", label: "read_only", description: "Inspect only." },
      { id: "workspace", label: "workspace", description: "Allow workspace edits." },
    ],
  } satisfies ModeCatalog,
  onProfileChange: vi.fn(),
  onModelChange: vi.fn(),
  selectedContextFiles: [],
  fileMatches: [],
  onContextQuery: vi.fn(),
  onContextAdd: vi.fn(),
  onContextRemove: vi.fn(),
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

  it("only shows the public mode set and explains the selected mode", () => {
    render(
      <Composer
        prompt=""
        selectedMode="ask"
        selectedTrustMode="ask"
        {...baseProps}
        onPromptChange={vi.fn()}
        onModeChange={vi.fn()}
        onTrustModeChange={vi.fn()}
        onSend={vi.fn()}
      />,
    );

    expect(screen.getByText("ask")).toBeInTheDocument();
    expect(screen.getByText("code")).toBeInTheDocument();
    expect(screen.getByText("review")).toBeInTheDocument();
    expect(screen.queryByText("plan")).not.toBeInTheDocument();
    expect(screen.getByText(/Answer directly/)).toBeInTheDocument();
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

  it("shows stop control while sending", () => {
    const onCancel = vi.fn();
    render(
      <Composer
        prompt="test prompt"
        selectedMode="code"
        selectedTrustMode="ask"
        {...baseProps}
        onPromptChange={vi.fn()}
        onModeChange={vi.fn()}
        onTrustModeChange={vi.fn()}
        onSend={vi.fn()}
        onCancel={onCancel}
        isSending
      />,
    );
    fireEvent.click(screen.getByText("Stop"));
    expect(onCancel).toHaveBeenCalled();
  });

  it("shows retry control when retry is available", () => {
    const onRetry = vi.fn();
    render(
      <Composer
        prompt=""
        selectedMode="code"
        selectedTrustMode="ask"
        {...baseProps}
        onPromptChange={vi.fn()}
        onModeChange={vi.fn()}
        onTrustModeChange={vi.fn()}
        onSend={vi.fn()}
        onRetry={onRetry}
        canRetry
      />,
    );
    fireEvent.click(screen.getByText("Retry"));
    expect(onRetry).toHaveBeenCalled();
  });

  it("shows resume control when resume is available", () => {
    const onResume = vi.fn();
    render(
      <Composer
        prompt=""
        selectedMode="code"
        selectedTrustMode="ask"
        {...baseProps}
        onPromptChange={vi.fn()}
        onModeChange={vi.fn()}
        onTrustModeChange={vi.fn()}
        onSend={vi.fn()}
        onResume={onResume}
        canResume
      />,
    );
    fireEvent.click(screen.getByText("Resume"));
    expect(onResume).toHaveBeenCalled();
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

  it("locks mode and model controls while a turn is active", () => {
    render(
      <Composer
        prompt="busy"
        selectedMode="code"
        selectedTrustMode="ask"
        {...baseProps}
        onPromptChange={vi.fn()}
        onModeChange={vi.fn()}
        onTrustModeChange={vi.fn()}
        onSend={vi.fn()}
        controlsLocked
      />,
    );

    expect(screen.getByRole("button", { name: "ask" })).toBeDisabled();
    expect(screen.getByLabelText("Trust mode")).toBeDisabled();
    expect(screen.getByLabelText("Provider profile")).toBeDisabled();
  });

  it("shows @ file matches and adds removable context chips", () => {
    const onContextAdd = vi.fn();
    const onContextRemove = vi.fn();
    const { rerender } = render(
      <Composer
        prompt="@ap"
        selectedMode="code"
        selectedTrustMode="ask"
        {...baseProps}
        fileMatches={[{ path: "src/app.py", type: "file" }]}
        onContextAdd={onContextAdd}
        onContextRemove={onContextRemove}
        onPromptChange={vi.fn()}
        onModeChange={vi.fn()}
        onTrustModeChange={vi.fn()}
        onSend={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByText("src/app.py"));
    expect(onContextAdd).toHaveBeenCalledWith("src/app.py");

    rerender(
      <Composer
        prompt=""
        selectedMode="code"
        selectedTrustMode="ask"
        {...baseProps}
        selectedContextFiles={["src/app.py"]}
        onContextRemove={onContextRemove}
        onPromptChange={vi.fn()}
        onModeChange={vi.fn()}
        onTrustModeChange={vi.fn()}
        onSend={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByLabelText("Remove context src/app.py"));
    expect(onContextRemove).toHaveBeenCalledWith("src/app.py");
  });
});
