import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import React from "react";
import { describe, expect, it, vi } from "vitest";

import { ProviderManagementWorkspace } from "../ProviderManagementWorkspace";

const apiMocks = vi.hoisted(() => ({
  rotateManagementSecret: vi.fn(async () => ({ ok: true })),
}));

const mockProfiles = [
  {
    name: "default",
    providers: [
      {
        id: "openai",
        kind: "openai_v1",
        endpoint: "https://api.openai.com/v1",
        auth_mode: "bearer",
        has_secret: true,
        timeout_seconds: 60,
        headers: {},
        metadata: { template: "openai_v1" },
        disabled: false,
      },
    ],
    models: [
      {
        id: "planner",
        role: "planner",
        provider: "openai",
        model: "gpt-4o-mini",
        capabilities: ["text", "json"],
        is_default: true,
        enabled: true,
      },
    ],
  },
];

vi.mock("../../../api", () => ({
  listManagementProfiles: vi.fn(async () => ({
    configured: true,
    default_profile: "default",
    profiles: mockProfiles,
  })),
  getManagementTemplates: vi.fn(async () => [
    {
      kind: "openai_v1",
      display_name: "OpenAI",
      endpoint: "https://api.openai.com/v1",
      auth_mode: "bearer",
      provider_type: "openai_v1",
      capabilities: ["text", "json"],
      docs_url: "",
      support_state: "beta",
      wizard_fields: [],
    },
  ]),
  createManagementProfile: vi.fn(async () => ({ ok: true, profile: { name: "new" } })),
  duplicateManagementProfile: vi.fn(async () => ({ ok: true, profile: { name: "copy" } })),
  exportManagementProfile: vi.fn(async () => ({ ok: true, data: { name: "default" } })),
  importManagementProfile: vi.fn(async () => ({ ok: true, profile: { name: "imported" } })),
  setDefaultManagementProfile: vi.fn(async () => ({ ok: true })),
  deleteManagementProfile: vi.fn(async () => ({ ok: true })),
  deleteManagementAccount: vi.fn(async () => ({ ok: true })),
  deleteManagementModel: vi.fn(async () => ({ ok: true })),
  testManagementAccount: vi.fn(async () => ({
    ok: true,
    result: { ok: true, latency_ms: 120 },
  })),
  testDraftManagementAccount: vi.fn(async () => ({
    ok: true,
    result: { ok: true, latency_ms: 95 },
  })),
  rotateManagementSecret: apiMocks.rotateManagementSecret,
  discoverManagementModels: vi.fn(async () => ({
    ok: true,
    supported: true,
    discovery_mode: "remote_list",
    models: [],
  })),
  importDiscoveredManagementModels: vi.fn(async () => ({ ok: true, models: [] })),
  addManagementAccount: vi.fn(async () => ({ ok: true, account: mockProfiles[0].providers[0] })),
  updateManagementAccount: vi.fn(async () => ({ ok: true, account: mockProfiles[0].providers[0] })),
  addManagementModel: vi.fn(async () => ({ ok: true, model: mockProfiles[0].models[0] })),
  updateManagementModel: vi.fn(async () => ({ ok: true, model: mockProfiles[0].models[0] })),
  setDefaultManagementModel: vi.fn(async () => ({ ok: true, model: mockProfiles[0].models[0] })),
}));

describe("ProviderManagementWorkspace", () => {
  it("renders profile selector and tabs", async () => {
    render(<ProviderManagementWorkspace onClose={() => {}} />);
    await waitFor(() => expect(screen.getByText("Providers & Models")).toBeInTheDocument());
    expect(screen.getByLabelText("Profile")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /Accounts/i }).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByRole("button", { name: /Models/i }).length).toBeGreaterThanOrEqual(1);
  });

  it("shows accounts in accounts tab", async () => {
    render(<ProviderManagementWorkspace onClose={() => {}} />);
    await waitFor(() => expect(screen.getByText("Provider Accounts")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: /Add Account/i })).toBeInTheDocument();
  });

  it("switches to models tab", async () => {
    render(<ProviderManagementWorkspace onClose={() => {}} />);
    await waitFor(() => expect(screen.getByText("Provider Accounts")).toBeInTheDocument());
    const tabs = screen.getAllByRole("button");
    const modelsTab = tabs.find((t) => t.textContent?.includes("Models"));
    expect(modelsTab).toBeDefined();
    if (modelsTab) fireEvent.click(modelsTab);
    await waitFor(() => expect(screen.getByText("Model Bindings")).toBeInTheDocument());
  });

  it("opens import and export actions from the header", async () => {
    render(<ProviderManagementWorkspace onClose={() => {}} />);
    await waitFor(() => expect(screen.getByText("Providers & Models")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Export" }));
    await waitFor(() => expect(screen.getByText("Export Profile")).toBeInTheDocument());
    fireEvent.click(screen.getAllByRole("button", { name: "Close" })[1]);

    fireEvent.click(screen.getByRole("button", { name: "Import" }));
    await waitFor(() => expect(screen.getByText("Import Profile")).toBeInTheDocument());
  });

  it("opens rotate secret modal and saves the new secret", async () => {
    render(<ProviderManagementWorkspace onClose={() => {}} />);
    await waitFor(() => expect(screen.getByText("Provider Accounts")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Rotate Secret" }));
    await waitFor(() => expect(screen.getByRole("heading", { name: "Rotate Secret" })).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText("New Secret"), {
      target: { value: "sk-rotated" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save Secret" }));
    await waitFor(() =>
      expect(apiMocks.rotateManagementSecret).toHaveBeenCalledWith(
        "default",
        "openai",
        "api_key",
        "sk-rotated",
      ),
    );
  });
});
