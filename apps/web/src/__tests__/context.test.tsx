import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import { Composer } from "../components/Composer";
import type { ModeCatalog } from "../types";

const modeCatalog: ModeCatalog = {
  modes: [
    {
      id: "ask",
      label: "Ask",
      description: "Answer directly.",
      edits_expected: false,
      legacy_aliases: ["plan"],
    },
    {
      id: "code",
      label: "Code",
      description: "Implement and verify.",
      edits_expected: true,
      legacy_aliases: ["fix", "docs", "test"],
    },
    {
      id: "review",
      label: "Review",
      description: "Inspect critically.",
      edits_expected: false,
      legacy_aliases: [],
    },
  ],
  trust_modes: [
    { id: "ask", label: "ask", description: "Pause for risky tools." },
    { id: "read_only", label: "read_only", description: "Inspect only." },
    {
      id: "workspace",
      label: "workspace",
      description: "Allow workspace edits.",
    },
  ],
};

describe("Composer context", () => {
  it("renders context preview items with token estimates", () => {
    render(
      <Composer
        prompt=""
        selectedMode="code"
        selectedTrustMode="ask"
        selectedProfile="auto"
        selectedModel="auto"
        modelOptions={null}
        modeCatalog={modeCatalog}
        onPromptChange={() => {}}
        onModeChange={() => {}}
        onTrustModeChange={() => {}}
        onProfileChange={() => {}}
        onModelChange={() => {}}
        onSend={() => {}}
        selectedContextFiles={["src/app.py"]}
        contextPreviews={[
          {
            path: "src/app.py",
            status: "ok",
            size: 42,
            preview: "print(1)",
            truncation_reason: "",
            token_estimate: 10,
          },
        ]}
      />,
    );

    expect(screen.getByText("src/app.py")).toBeInTheDocument();
    expect(screen.getAllByText("10 tokens").length).toBeGreaterThanOrEqual(1);
  });

  it("renders rejected context with warning icon", () => {
    render(
      <Composer
        prompt=""
        selectedMode="code"
        selectedTrustMode="ask"
        selectedProfile="auto"
        selectedModel="auto"
        modelOptions={null}
        modeCatalog={modeCatalog}
        onPromptChange={() => {}}
        onModeChange={() => {}}
        onTrustModeChange={() => {}}
        onProfileChange={() => {}}
        onModelChange={() => {}}
        onSend={() => {}}
        selectedContextFiles={["missing.txt"]}
        contextPreviews={[
          {
            path: "missing.txt",
            status: "missing",
            size: 0,
            preview: "",
            truncation_reason: "",
            token_estimate: 0,
          },
        ]}
      />,
    );

    expect(screen.queryByText("src/app.py")).not.toBeInTheDocument();
    expect(screen.getByText("missing.txt")).toBeInTheDocument();
    expect(screen.getByText("missing")).toBeInTheDocument();
  });

  it("calls onCancel when stop is clicked", () => {
    const onCancel = vi.fn();
    render(
      <Composer
        prompt="hi"
        selectedMode="code"
        selectedTrustMode="ask"
        selectedProfile="auto"
        selectedModel="auto"
        modelOptions={null}
        modeCatalog={modeCatalog}
        onPromptChange={() => {}}
        onModeChange={() => {}}
        onTrustModeChange={() => {}}
        onProfileChange={() => {}}
        onModelChange={() => {}}
        onSend={() => {}}
        onCancel={onCancel}
        isSending={true}
      />,
    );

    const stopBtn = screen.getByText("Stop");
    fireEvent.click(stopBtn);
    expect(onCancel).toHaveBeenCalled();
  });
});
