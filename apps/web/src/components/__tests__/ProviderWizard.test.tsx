import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ProviderWizard } from "../ProviderWizard";

vi.mock("../../api", () => ({
  api: vi.fn().mockImplementation((path: string) => {
    if (path === "/providers/wizard-templates") {
      return Promise.resolve([
        {
          kind: "openai_v1",
          display_name: "OpenAI",
          endpoint: "https://api.openai.com/v1",
          auth_mode: "bearer",
          provider_type: "openai",
          capabilities: ["text", "json", "streaming"],
          docs_url: "https://example.com",
          support_state: "stable",
          wizard_fields: [],
        },
      ]);
    }
    return Promise.resolve({ ok: true });
  }),
}));

describe("ProviderWizard", () => {
  it("closes on Escape", async () => {
    const onClose = vi.fn();

    render(<ProviderWizard onClose={onClose} onSaved={() => undefined} />);

    const dialog = await screen.findByRole("dialog", { name: "Add AI Provider" });
    await waitFor(() => expect(screen.getByRole("button", { name: "Close" })).toHaveFocus());

    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });
});
