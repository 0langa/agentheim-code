import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ProviderWizard } from "../ProviderWizard";

vi.mock("../providers/ProviderManagementWorkspace", () => ({
  ProviderManagementWorkspace: ({
    onClose,
  }: {
    onClose: () => void;
    onProfilesChanged?: () => void;
  }) => (
    <div role="dialog" aria-label="Providers & Models">
      <button aria-label="Close" onClick={onClose} type="button">
        Close
      </button>
    </div>
  ),
}));

describe("ProviderWizard", () => {
  it("renders the provider management workspace wrapper", async () => {
    const onClose = vi.fn();

    render(<ProviderWizard onClose={onClose} onSaved={() => undefined} />);

    await waitFor(() => expect(screen.getByRole("dialog", { name: "Providers & Models" })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(onClose).toHaveBeenCalled();
  });
});
