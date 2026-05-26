import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import React from "react";
import { describe, expect, it, vi } from "vitest";

import { ProviderAccountEditor } from "../ProviderAccountEditor";

const templates = [
  {
    kind: "azure_foundry",
    display_name: "Azure OpenAI / Foundry",
    endpoint: "https://example.openai.azure.com",
    auth_mode: "api_key",
    provider_type: "azure_foundry",
    capabilities: ["text", "json"],
    docs_url: "https://learn.microsoft.com/",
    support_state: "beta",
    default_timeout_seconds: 180,
    wizard_fields: [],
    capabilities_meta: {
      supports_connection_test: true,
      supports_remote_model_listing: true,
      supports_manual_model_entry: true,
      supports_endpoint_edit: true,
      supports_secret_rotation: true,
      discovery_mode: "remote_list_with_manual_fallback",
      docs_url: "https://learn.microsoft.com/",
      notes: "Azure OpenAI / Foundry.",
    },
  },
  {
    kind: "openai_compatible",
    display_name: "OpenAI-compatible",
    endpoint: "https://api.openai.com/v1",
    auth_mode: "bearer",
    provider_type: "openai_compatible",
    capabilities: ["text", "json", "streaming"],
    docs_url: "https://platform.openai.com/docs",
    support_state: "beta",
    default_timeout_seconds: 60,
    wizard_fields: [],
    capabilities_meta: {
      supports_connection_test: true,
      supports_remote_model_listing: true,
      supports_manual_model_entry: true,
      supports_endpoint_edit: true,
      supports_secret_rotation: true,
      discovery_mode: "remote_list_with_manual_fallback",
      docs_url: "https://platform.openai.com/docs",
      notes: "Remote list with manual fallback.",
    },
  },
];

describe("ProviderAccountEditor", () => {
  it("tests the unsaved draft with the current secret value", async () => {
    const onTestDraft = vi.fn(async () => ({
      ok: true,
      result: { ok: true, latency_ms: 95 },
    }));

    render(
      <ProviderAccountEditor
        templates={templates}
        account={null}
        existingAccounts={[]}
        onClose={() => {}}
        onSave={() => {}}
        onTestDraft={onTestDraft}
      />,
    );

    fireEvent.change(screen.getByLabelText("Account ID"), {
      target: { value: "openai-cloud" },
    });
    fireEvent.change(screen.getByLabelText("Display Name"), {
      target: { value: "OpenAI Cloud" },
    });
    fireEvent.change(screen.getByLabelText("Endpoint"), {
      target: { value: "https://api.openai.com/v1" },
    });
    fireEvent.change(screen.getByLabelText("Secret"), {
      target: { value: "example-draft-secret" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Test Connection" }));

    await waitFor(() => expect(onTestDraft).toHaveBeenCalledTimes(1));
    expect(onTestDraft).toHaveBeenCalledWith(
      expect.objectContaining({
        id: "openai-cloud",
        endpoint: "https://api.openai.com/v1",
        display_name: "OpenAI Cloud",
      }),
      "example-draft-secret",
    );
    expect(screen.getByText(/Connection successful/i)).toBeVisible();
  });

  it("passes the current secret value through save for rotation or create", () => {
    const onSave = vi.fn();

    render(
      <ProviderAccountEditor
        templates={templates}
        account={null}
        existingAccounts={[]}
        onClose={() => {}}
        onSave={onSave}
        onTestDraft={vi.fn()}
      />,
    );

    fireEvent.change(screen.getByLabelText("Account ID"), {
      target: { value: "openai-cloud" },
    });
    fireEvent.change(screen.getByLabelText("Endpoint"), {
      target: { value: "https://api.openai.com/v1" },
    });
    fireEvent.change(screen.getByLabelText("Secret"), {
      target: { value: "example-save-secret" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add Account" }));

    expect(onSave).toHaveBeenCalledWith(
      expect.objectContaining({
        id: "openai-cloud",
        endpoint: "https://api.openai.com/v1",
      }),
      "example-save-secret",
    );
  });

  it("captures Azure deployment name in metadata", () => {
    const onSave = vi.fn();

    render(
      <ProviderAccountEditor
        templates={templates}
        account={null}
        existingAccounts={[]}
        onClose={() => {}}
        onSave={onSave}
        onTestDraft={vi.fn()}
      />,
    );

    fireEvent.change(screen.getByLabelText("Template"), {
      target: { value: "azure_foundry" },
    });
    fireEvent.change(screen.getByLabelText("Account ID"), {
      target: { value: "azure-main" },
    });
    fireEvent.change(screen.getByLabelText("Endpoint"), {
      target: { value: "https://coding-eu-resource.openai.azure.com" },
    });
    fireEvent.change(screen.getByLabelText("Deployment Name"), {
      target: { value: "gpt-4o-deploy" },
    });
    fireEvent.change(screen.getByLabelText("Secret"), {
      target: { value: "example-azure-secret" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add Account" }));

    expect(onSave).toHaveBeenCalledWith(
      expect.objectContaining({
        id: "azure-main",
        timeout_seconds: 180,
        metadata: expect.objectContaining({
          template: "azure_foundry",
          deployment: "gpt-4o-deploy",
        }),
      }),
      "example-azure-secret",
    );
  });
});
