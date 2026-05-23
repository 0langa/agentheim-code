import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Onboarding } from "../Onboarding";

vi.mock("../../api", () => ({
  api: vi.fn().mockResolvedValue([]),
}));

describe("Onboarding", () => {
  it("focuses the workspace input and closes on Escape", async () => {
    const onSkip = vi.fn();

    render(
      <Onboarding
        config={{
          onboarding_complete: false,
          onboarding_dismissed: false,
          default_workspace: ".",
          theme: "dark",
        }}
        onSkip={onSkip}
        onOpenProviderWizard={() => undefined}
        onComplete={() => undefined}
      />,
    );

    const workspace = screen.getByLabelText("Workspace");
    await waitFor(() => expect(workspace).toHaveFocus());

    fireEvent.keyDown(workspace, { key: "Escape" });
    expect(onSkip).toHaveBeenCalled();
  });
});
