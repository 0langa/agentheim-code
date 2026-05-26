import { expect, test, type Page } from "@playwright/test";

type SessionState = {
  activeSessionId: string | null;
  sessions: Array<Record<string, unknown>>;
  view: Record<string, unknown> | null;
  providersConfigured: boolean;
  providers: Array<Record<string, unknown>>;
  discoveredModels: Record<string, Array<Record<string, unknown>>>;
  onboardingComplete: boolean;
  onboardingDismissed: boolean;
};

type FileBrowserPage = {
  items: Array<Record<string, unknown>>;
  has_more: boolean;
  next_offset: number | null;
  query: string;
};

type UsagePayload = {
  session_id: string;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  estimated_cost_usd: number | null;
  calls: number;
  breakdown: Array<Record<string, unknown>>;
};

function createMockState(): SessionState {
  return {
    activeSessionId: null,
    sessions: [],
    view: null,
    providersConfigured: false,
    providers: [],
    discoveredModels: {},
    onboardingComplete: true,
    onboardingDismissed: false,
  };
}

function buildSessionView(
  session: Record<string, unknown>,
  approvals: Array<Record<string, unknown>> = [],
) {
  return {
    session: {
      ...session,
      transcript: (session.transcript as Array<Record<string, unknown>> | undefined) ?? [],
      current_assistant_message: session.current_assistant_message ?? "",
    },
    queued_prompts: [],
    available_commands: ["new"],
    approvals,
    events: [],
    command_results: [],
    diffs: [],
    artifacts: [],
  };
}

type WizardTemplate = {
  kind: string;
  display_name: string;
  endpoint: string;
  auth_mode: string;
  provider_type: string;
  capabilities: string[];
  docs_url: string;
  support_state: string;
  wizard_fields: Array<{
    name: string;
    label: string;
    type: string;
    required?: boolean;
    default?: string;
  }>;
};

type MockApiOptions = {
  withApproval?: boolean;
  onboardingComplete?: boolean;
  onboardingDismissed?: boolean;
  modelConfigured?: boolean;
  wizardTemplates?: WizardTemplate[];
  streamDelayMs?: number;
  fileBrowserPages?: Record<string, FileBrowserPage>;
  filePreviews?: Record<string, string>;
  usagePayload?: UsagePayload;
  initialSessions?: Array<Record<string, unknown>>;
  initialView?: Record<string, unknown> | null;
};

async function mockApi(page: Page, options: boolean | MockApiOptions = {}) {
  const opts = typeof options === "boolean" ? { withApproval: options } : options;
  const {
    withApproval = false,
    onboardingComplete = true,
    onboardingDismissed = false,
    modelConfigured = true,
    wizardTemplates = [],
    streamDelayMs = 0,
    fileBrowserPages = {},
    filePreviews = {},
    usagePayload,
    initialSessions = [],
    initialView = null,
  } = opts;

  const state = createMockState();
  state.onboardingComplete = onboardingComplete;
  state.onboardingDismissed = onboardingDismissed;
  state.providersConfigured = modelConfigured;
  state.sessions = initialSessions;
  state.view = initialView;
  state.activeSessionId =
    typeof initialView?.session === "object" && initialView?.session
      ? String((initialView.session as Record<string, unknown>).session_id ?? "")
      : initialSessions[0]
        ? String(initialSessions[0].session_id ?? "")
        : null;

  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const method = route.request().method();

    const json = async (payload: unknown) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(payload),
      });
    };

    if (path === "/api/config") {
      await json({
        onboarding_complete: state.onboardingComplete,
        onboarding_dismissed: state.onboardingDismissed,
        default_workspace: ".",
        theme: "dark",
      });
      return;
    }

    if (path === "/api/onboarding/local-providers") {
      await json([]);
      return;
    }

    if (path === "/api/onboarding/complete" && method === "POST") {
      state.onboardingComplete = true;
      await json({
        onboarding_complete: true,
        onboarding_dismissed: false,
        default_workspace: ".",
        theme: "dark",
      });
      return;
    }

    if (path === "/api/coder/commands") {
      await json([{ id: "new", label: "New Session", cli: "/new", surface: "global" }]);
      return;
    }

    if (path === "/api/coder/models") {
      if (state.providersConfigured && state.providers.length > 0) {
        const first = state.providers[0];
        await json({
          configured: true,
          default_profile: (first.name as string) ?? "local",
          profiles: state.providers.map((p: Record<string, unknown>) => ({
            name: p.name,
            default: p.default ?? true,
            providers: p.providers,
            models: p.models,
          })),
        });
      } else if (state.providersConfigured) {
        await json({
          configured: true,
          default_profile: "local",
          profiles: [
            {
              name: "local",
              default: true,
              providers: [
                {
                  id: "ollama",
                  kind: "ollama",
                  auth_mode: "none",
                  endpoint: "http://localhost:11434/v1",
                },
              ],
              models: [
                {
                  id: "planner",
                  role: "planner",
                  provider: "ollama",
                  model: "llama3.2",
                  display_name: "Llama 3.2",
                },
              ],
            },
          ],
        });
      } else {
        await json({ configured: false, profiles: [] });
      }
      return;
    }

    if (path === "/api/coder/sessions" && method === "GET") {
      await json(state.sessions);
      return;
    }

    if (path === "/api/coder/files/browser") {
      const key = `${url.searchParams.get("q") ?? ""}|${url.searchParams.get("offset") ?? "0"}`;
      await json(
        fileBrowserPages[key] ?? {
          items: [],
          has_more: false,
          next_offset: null,
          query: url.searchParams.get("q") ?? "",
        },
      );
      return;
    }

    if (path === "/api/coder/files/preview") {
      const previewPath = url.searchParams.get("path") ?? "";
      await json(filePreviews[previewPath] ?? "No preview available.");
      return;
    }

    if (path === "/api/providers/profiles") {
      if (method === "GET") {
        await json({
          configured: state.providersConfigured,
          profiles: state.providers,
        });
      } else if (method === "POST") {
        const body = route.request().postDataJSON() as Record<string, unknown>;
        state.providersConfigured = true;
        state.providers.push({
          name: body.name,
          default: true,
          providers: [
            {
              id: body.provider_id,
              kind: body.provider_kind,
              auth_mode: "bearer",
              endpoint:
                (body.fields as Record<string, string>)?.endpoint ??
                "https://api.openai.com/v1",
            },
          ],
          models: [
            {
              id: "planner",
              role: "planner",
              provider: body.provider_id,
              model: body.model_id,
            },
          ],
        });
        await json({ ok: true });
      }
      return;
    }

    if (path === "/api/providers/wizard-templates") {
      await json(wizardTemplates);
      return;
    }

    if (path === "/api/provider-management/profiles") {
      if (method === "GET") {
        await json({
          configured: state.providersConfigured,
          default_profile: state.providers[0]?.name ?? "default",
          profiles: state.providers.map((p: Record<string, unknown>) => ({
            name: p.name,
            providers: p.providers,
            models: p.models,
          })),
        });
      } else if (method === "POST") {
        const body = route.request().postDataJSON() as Record<string, unknown>;
        state.providersConfigured = true;
        state.providers.push({
          name: body.name,
          providers: [],
          models: [],
        });
        await json({ ok: true, profile: { name: body.name } });
      }
      return;
    }

    if (path === "/api/provider-management/profiles/import" && method === "POST") {
      const body = route.request().postDataJSON() as Record<string, unknown>;
      const imported = body.data as Record<string, unknown>;
      const importedName =
        String(body.name ?? imported.name ?? `imported-${state.providers.length + 1}`);
      state.providersConfigured = true;
      state.providers.push({
        name: importedName,
        providers: Array.isArray(imported.providers) ? imported.providers : [],
        models: Array.isArray(imported.models) ? imported.models : [],
      });
      await json({ ok: true, profile: { name: importedName } });
      return;
    }

    if (path.startsWith("/api/provider-management/profiles/") && path.endsWith("/export")) {
      const profileName = path.split("/")[4];
      const profile = state.providers.find((p: Record<string, unknown>) => p.name === profileName);
      await json({ ok: true, data: profile ?? {} });
      return;
    }

    if (
      path.startsWith("/api/provider-management/profiles/") &&
      path.endsWith("/duplicate") &&
      method === "POST"
    ) {
      const profileName = path.split("/")[4];
      const profile = state.providers.find((p: Record<string, unknown>) => p.name === profileName);
      const body = route.request().postDataJSON() as Record<string, unknown>;
      const targetName = String(body.target_name ?? `${profileName}-copy`);
      state.providers.push({
        name: targetName,
        providers: Array.isArray(profile?.providers)
          ? structuredClone(profile.providers as Array<Record<string, unknown>>)
          : [],
        models: Array.isArray(profile?.models)
          ? structuredClone(profile.models as Array<Record<string, unknown>>)
          : [],
      });
      await json({ ok: true, profile: { name: targetName } });
      return;
    }

    if (
      path.startsWith("/api/provider-management/profiles/") &&
      path.endsWith("/set-default") &&
      method === "POST"
    ) {
      const profileName = path.split("/")[4];
      const index = state.providers.findIndex((p: Record<string, unknown>) => p.name === profileName);
      if (index > 0) {
        const [profile] = state.providers.splice(index, 1);
        state.providers.unshift(profile);
      }
      await json({ ok: true, default_profile: profileName });
      return;
    }

    if (
      path.startsWith("/api/provider-management/profiles/") &&
      path.includes("/accounts/") &&
      path.endsWith("/rotate-secret") &&
      method === "POST"
    ) {
      await json({ ok: true });
      return;
    }

    if (
      path === "/api/provider-management/accounts/test-draft" &&
      method === "POST"
    ) {
      await json({
        ok: true,
        result: {
          ok: true,
          latency_ms: 98,
        },
      });
      return;
    }

    if (
      path.startsWith("/api/provider-management/profiles/") &&
      path.includes("/accounts/") &&
      path.endsWith("/test") &&
      method === "POST"
    ) {
      await json({
        ok: true,
        result: {
          ok: true,
          latency_ms: 120,
        },
      });
      return;
    }

    if (
      path.startsWith("/api/provider-management/profiles/") &&
      path.includes("/accounts/") &&
      path.endsWith("/discover-models") &&
      method === "POST"
    ) {
      const [, , , , profileName, , accountId] = path.split("/");
      const profile = state.providers.find((p: Record<string, unknown>) => p.name === profileName);
      const account = (profile?.providers as Array<Record<string, unknown>> | undefined)?.find(
        (item) => item.id === accountId
      );
      const template = String(account?.metadata?.template ?? account?.kind ?? "");
      if (template === "aws_bedrock") {
        await json({
          ok: true,
          supported: false,
          discovery_mode: "manual_only",
          models: [],
        });
        return;
      }
      const models =
        state.discoveredModels[accountId] ?? [
          {
            id: "gpt-4.1-mini",
            display_name: "GPT-4.1 Mini",
            provider_model_name: "gpt-4.1-mini",
            capabilities: ["text", "json", "streaming"],
          },
        ];
      state.discoveredModels[accountId] = models;
      await json({
        ok: true,
        supported: true,
        discovery_mode: "remote_list_with_manual_fallback",
        models,
      });
      return;
    }

    if (
      path.startsWith("/api/provider-management/profiles/") &&
      path.endsWith("/accounts") &&
      method === "POST"
    ) {
      const profileName = path.split("/")[4];
      const profile = state.providers.find((p: Record<string, unknown>) => p.name === profileName);
      const body = route.request().postDataJSON() as Record<string, unknown>;
      const account = {
        ...body,
        display_name: body.display_name ?? body.id,
        metadata: body.metadata ?? {},
      };
      (profile?.providers as Array<Record<string, unknown>>).push(account);
      await json({ ok: true, account });
      return;
    }

    if (
      path.startsWith("/api/provider-management/profiles/") &&
      path.includes("/accounts/") &&
      method === "PATCH"
    ) {
      const [, , , , profileName, , accountId] = path.split("/");
      const profile = state.providers.find((p: Record<string, unknown>) => p.name === profileName);
      const body = route.request().postDataJSON() as Record<string, unknown>;
      const providers = (profile?.providers as Array<Record<string, unknown>> | undefined) ?? [];
      const index = providers.findIndex((item) => item.id === accountId);
      providers[index] = { ...providers[index], ...body };
      await json({ ok: true, account: providers[index] });
      return;
    }

    if (
      path.startsWith("/api/provider-management/profiles/") &&
      path.includes("/accounts/") &&
      method === "DELETE"
    ) {
      const [, , , , profileName, , accountId] = path.split("/");
      const profile = state.providers.find((p: Record<string, unknown>) => p.name === profileName);
      const providers = (profile?.providers as Array<Record<string, unknown>> | undefined) ?? [];
      profile!.providers = providers.filter((item) => item.id !== accountId);
      if (url.searchParams.get("cascade") === "true") {
        const models = (profile?.models as Array<Record<string, unknown>> | undefined) ?? [];
        profile!.models = models.filter((item) => item.provider !== accountId);
      }
      await json({ ok: true });
      return;
    }

    if (
      path.startsWith("/api/provider-management/profiles/") &&
      path.endsWith("/models") &&
      method === "POST"
    ) {
      const profileName = path.split("/")[4];
      const profile = state.providers.find((p: Record<string, unknown>) => p.name === profileName);
      const body = route.request().postDataJSON() as Record<string, unknown>;
      const model = { ...body, display_name: body.display_name ?? body.id };
      (profile?.models as Array<Record<string, unknown>>).push(model);
      await json({ ok: true, model });
      return;
    }

    if (
      path.startsWith("/api/provider-management/profiles/") &&
      path.includes("/models/") &&
      path.endsWith("/set-default") &&
      method === "POST"
    ) {
      const [, , , , profileName, , modelId] = path.split("/");
      const profile = state.providers.find((p: Record<string, unknown>) => p.name === profileName);
      const models = (profile?.models as Array<Record<string, unknown>> | undefined) ?? [];
      const target = models.find((item) => item.id === modelId);
      if (target) {
        for (const model of models) {
          if (model.role === target.role) model.is_default = false;
        }
        target.is_default = true;
      }
      await json({ ok: true, model: target });
      return;
    }

    if (
      path.startsWith("/api/provider-management/profiles/") &&
      path.includes("/models/") &&
      method === "PATCH"
    ) {
      const [, , , , profileName, , modelId] = path.split("/");
      const profile = state.providers.find((p: Record<string, unknown>) => p.name === profileName);
      const body = route.request().postDataJSON() as Record<string, unknown>;
      const models = (profile?.models as Array<Record<string, unknown>> | undefined) ?? [];
      const index = models.findIndex((item) => item.id === modelId);
      models[index] = { ...models[index], ...body };
      await json({ ok: true, model: models[index] });
      return;
    }

    if (
      path.startsWith("/api/provider-management/profiles/") &&
      path.includes("/models/") &&
      method === "DELETE"
    ) {
      const [, , , , profileName, , modelId] = path.split("/");
      const profile = state.providers.find((p: Record<string, unknown>) => p.name === profileName);
      const models = (profile?.models as Array<Record<string, unknown>> | undefined) ?? [];
      profile!.models = models.filter((item) => item.id !== modelId);
      await json({ ok: true });
      return;
    }

    if (
      path.startsWith("/api/provider-management/profiles/") &&
      path.endsWith("/models/import-discovered") &&
      method === "POST"
    ) {
      const profileName = path.split("/")[4];
      const profile = state.providers.find((p: Record<string, unknown>) => p.name === profileName);
      const body = route.request().postDataJSON() as Record<string, unknown>;
      const accountId = String(body.account_id ?? "");
      const selectedModels = Array.isArray(body.models)
        ? (body.models as Array<Record<string, unknown>>)
        : [];
      const imported = selectedModels.map((item) => ({
        id: String(item.id),
        provider: accountId,
        model: String(item.provider_model_name ?? item.id),
        role: "planner",
        display_name: item.display_name,
        capabilities: Array.isArray(item.capabilities) ? item.capabilities : ["text"],
        source: "discovered",
        is_default: false,
        enabled: true,
      }));
      (profile?.models as Array<Record<string, unknown>>).push(...imported);
      await json({ ok: true, models: imported });
      return;
    }

    if (path === "/api/provider-management/templates") {
      await json(wizardTemplates);
      return;
    }

    if (path === "/api/providers/test" && method === "POST") {
      await json({
        ok: true,
        latency_ms: 120,
        message: "Connection successful",
      });
      return;
    }

    if (path === "/api/coder/sessions" && method === "POST") {
      state.activeSessionId = "sess-1";
      const session = {
        session_id: "sess-1",
        status: "idle",
        mode: "code",
        trust_mode: "ask",
        workspace_root: ".",
        model_selection: {
          profile: "local",
          provider: "ollama",
          model: "llama3.2",
        },
      };
      state.sessions = [session];
      state.view ??= buildSessionView(
        session,
        withApproval
          ? [
              {
                request_id: "req-1",
                tool_id: "shell.execute",
                risk_level: "medium",
                reason: "Run tests",
                status: "pending",
                action_kind: "shell",
                target: "pytest -q",
                params: {
                  command: ["pytest", "-q"],
                  cwd: ".",
                },
              },
            ]
          : [],
      );
      await json(session);
      return;
    }

    if (path === "/api/coder/sessions/sess-1/view") {
      await json(state.view);
      return;
    }

    if (path === "/api/coder/sessions/sess-1/usage") {
      await json(
        usagePayload ?? {
          session_id: "sess-1",
          input_tokens: 1200,
          output_tokens: 340,
          total_tokens: 1540,
          estimated_cost_usd: 0.0123,
          calls: 2,
          breakdown: [
            {
              sequence: 1,
              timestamp: "2026-05-25T12:00:00+00:00",
              model: "llama3.2",
              provider: "ollama",
              input_tokens: 800,
              output_tokens: 200,
              total_tokens: 1000,
              estimated_cost_usd: 0.008,
            },
            {
              sequence: 2,
              timestamp: "2026-05-25T12:01:00+00:00",
              model: "llama3.2",
              provider: "ollama",
              input_tokens: 400,
              output_tokens: 140,
              total_tokens: 540,
              estimated_cost_usd: 0.0043,
            },
          ],
        },
      );
      return;
    }

    if (path === "/api/coder/sessions/sess-1/messages/stream") {
      const body = route.request().postDataJSON() as { prompt: string };
      const session = {
        ...((state.view?.session as Record<string, unknown>) ?? {}),
        session_id: "sess-1",
        status: "idle",
        mode: "code",
        trust_mode: "ask",
        workspace_root: ".",
        model_selection: {
          profile: "local",
          provider: "ollama",
          model: "llama3.2",
        },
        transcript: [
          { role: "user", content: body.prompt },
          { role: "assistant", content: "Done from stream." },
        ],
        current_assistant_message: "",
      };
      state.view = buildSessionView(session, (state.view?.approvals as Array<Record<string, unknown>> | undefined) ?? []);
      if (streamDelayMs > 0) {
        await new Promise((resolve) => setTimeout(resolve, streamDelayMs));
      }
      await route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: [
          'event: token\ndata: {"token":"Done "}',
          'event: token\ndata: {"token":"from stream."}',
          'event: done\ndata: {"session_id":"sess-1"}',
          "",
        ].join("\n\n"),
      });
      return;
    }

    if (path === "/api/coder/sessions/sess-1/approvals/req-1/grant") {
      state.view = {
        ...state.view,
        approvals: [],
      };
      await json({
        session_id: "sess-1",
        status: "idle",
        mode: "code",
        trust_mode: "ask",
        workspace_root: ".",
      });
      return;
    }

    await route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ error: `Unhandled route ${method} ${path}` }),
    });
  });
}

test.describe("Agentheim Code Web", () => {
  test("keyboard flow opens settings, closes palette, and sends a prompt", async ({ page }) => {
    await mockApi(page);
    await page.goto("/");

    await expect(page.locator("main.shell")).toBeVisible();

    await page.keyboard.press("Control+K");
    await expect(page.getByRole("dialog", { name: "Command palette" })).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog", { name: "Command palette" })).toHaveCount(0);

    await page.keyboard.press("Tab");
    await page.keyboard.press("Enter");

    await page.keyboard.press("Control+,");
    await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();

    const prompt = page.getByRole("textbox", { name: "Prompt" });
    await prompt.click();
    await prompt.fill("Ship it");
    await page.keyboard.press("Control+Enter");

    const chat = page.getByRole("log", { name: "Conversation transcript" });
    await expect(chat.getByText("Done from stream.")).toBeVisible();
  });

  test("pending approvals can be granted from the keyboard", async ({ page }) => {
    await mockApi(page, true);
    await page.goto("/");

    await page.keyboard.press("Tab");
    await page.keyboard.press("Enter");

    await expect(page.getByRole("heading", { name: "Approvals" })).toBeVisible();

    const grant = page.getByRole("button", { name: "Grant" });
    await grant.focus();
    await page.keyboard.press("Enter");

    await expect(page.getByText("No pending approvals.")).toBeVisible();
  });

  test("onboarding flow completes workspace setup and creates first session", async ({ page }) => {
    // Mock a fresh install where onboarding is incomplete and no providers are configured.
    await mockApi(page, { onboardingComplete: false, modelConfigured: false });
    await page.goto("/");

    // Verify the onboarding modal appears.
    const onboardingDialog = page.getByRole("dialog", { name: "Welcome to Agentheim Code" });
    await expect(onboardingDialog).toBeVisible();

    // Type a workspace path into the input.
    const workspaceInput = page.getByLabel("Workspace");
    await workspaceInput.fill("/tmp/agentheim-workspace");

    // Click through to complete onboarding.
    await page.getByRole("button", { name: "Start first session" }).click();

    // Verify the onboarding modal disappears.
    await expect(onboardingDialog).toHaveCount(0);

    // Verify a session was created by checking the Runs panel.
    await page.getByRole("button", { name: "Runs" }).click();
    await expect(page.getByText("sess-1")).toBeVisible();
  });

  test("provider management workspace opens from settings", async ({ page }) => {
    const templates: WizardTemplate[] = [
      {
        kind: "openai_v1",
        display_name: "OpenAI",
        endpoint: "https://api.openai.com/v1",
        auth_mode: "bearer",
        provider_type: "openai",
        capabilities: ["text", "json", "streaming"],
        docs_url: "https://platform.openai.com/docs",
        support_state: "stable",
        wizard_fields: [
          { name: "api_key", label: "API Key", type: "password", required: false },
        ],
      },
    ];

    await mockApi(page, { modelConfigured: false, wizardTemplates: templates });
    await page.goto("/");

    // Open Settings via the rail button.
    await page.getByRole("button", { name: "Settings" }).click();
    await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();

    // Open the provider management workspace.
    await page.getByRole("button", { name: "Open Providers & Models" }).click();
    const workspaceDialog = page.getByRole("dialog", { name: "Providers & Models" });
    await expect(workspaceDialog).toBeVisible();

    // Verify tabs are present
    await expect(page.getByRole("button", { name: "Accounts", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Models", exact: true })).toBeVisible();

    // Close the workspace
    await page.keyboard.press("Escape");
    await expect(workspaceDialog).toHaveCount(0);
  });

  test("provider management workspace opens from command palette", async ({ page }) => {
    await mockApi(page, { modelConfigured: true });
    await page.goto("/");

    await expect(page.locator("main.shell")).toBeVisible();

    await page.keyboard.press("Control+K");
    await expect(page.getByRole("dialog", { name: "Command palette" })).toBeVisible();
    await page.getByPlaceholder("Search commands").fill("providers");
    await page.keyboard.press("Enter");

    const workspaceDialog = page.getByRole("dialog", { name: "Providers & Models" });
    await expect(workspaceDialog).toBeVisible();

    // Verify tabs are present
    await expect(page.getByRole("button", { name: "Accounts" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Models" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Defaults" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Diagnostics" })).toBeVisible();
  });

  test("provider management lifecycle supports draft test, rotation, discovery, import-export, and manual fallback", async ({
    page,
  }) => {
    const templates: WizardTemplate[] = [
      {
        kind: "openai_compatible",
        display_name: "OpenAI-compatible",
        endpoint: "https://example.com/v1",
        auth_mode: "bearer",
        provider_type: "openai_compatible",
        capabilities: ["text", "json", "streaming"],
        docs_url: "https://example.com/docs",
        support_state: "beta",
        wizard_fields: [],
      },
      {
        kind: "aws_bedrock",
        display_name: "AWS Bedrock",
        endpoint: "-",
        auth_mode: "aws_chain",
        provider_type: "aws_bedrock",
        capabilities: ["text", "json"],
        docs_url: "https://docs.aws.amazon.com/bedrock/",
        support_state: "experimental",
        wizard_fields: [],
      },
    ];

    await mockApi(page, {
      modelConfigured: true,
      wizardTemplates: templates,
      initialSessions: [],
      initialView: null,
    });
    await page.goto("/");

    await page.getByRole("button", { name: "Settings" }).click();
    await page.getByRole("button", { name: "Open Providers & Models" }).click();
    const workspaceDialog = page.getByRole("dialog", { name: "Providers & Models" });
    await expect(workspaceDialog).toBeVisible();

    await page.getByRole("button", { name: "+ New Profile" }).click();
    await page.getByLabel("Profile Name").fill("cloud");
    await page.getByRole("button", { name: "Save" }).click();
    await expect(page.getByLabel("Profile", { exact: true })).toHaveValue("cloud");

    await page.getByRole("button", { name: "+ Add Account" }).click();
    await page.getByLabel("Template").selectOption("openai_compatible");
    await page.getByLabel("Account ID").fill("openai-cloud");
    await page.getByLabel("Display Name").fill("OpenAI Cloud");
    await page.getByLabel("Endpoint").fill("https://api.openai.com/v1");
    await page.getByLabel("Secret").fill("example-openai-secret");
    await page.getByRole("button", { name: "Test Connection" }).click();
    await expect(page.getByText(/Connection successful/i)).toBeVisible();
    await page.getByRole("button", { name: "Add Account", exact: true }).click();
    await expect(page.getByText(/Secret saved for openai-cloud/i)).toBeVisible();

    await page.getByRole("button", { name: "Rotate Secret" }).click();
    await page.getByLabel("New Secret").fill("example-openai-secret-rotated");
    await page.getByRole("button", { name: "Save Secret" }).click();
    await expect(page.getByText(/Secret rotated for openai-cloud/i)).toBeVisible();

    await page.getByRole("button", { name: "Discover Models" }).click();
    await expect(page.getByText("GPT-4.1 Mini")).toBeVisible();
    await page.getByRole("checkbox").check();
    await page.getByRole("button", { name: "Import Selected" }).click();

    await page.getByRole("button", { name: "Models", exact: true }).click();
    await expect(page.getByText("GPT-4.1 Mini")).toBeVisible();
    await page.getByRole("table").getByRole("button", { name: "Set Default" }).click();

    await page.getByRole("button", { name: "Accounts", exact: true }).click();
    await page.getByRole("button", { name: "+ Add Account" }).click();
    await page.getByLabel("Template").selectOption("aws_bedrock");
    await page.getByLabel("Account ID").fill("bedrock");
    await page.getByLabel("Display Name").fill("Bedrock");
    await page.getByRole("button", { name: "Add Account", exact: true }).click();
    await page.getByRole("button", { name: "Discover Models" }).nth(1).click();
    await expect(
      page.getByText(/does not support automatic model discovery/i),
    ).toBeVisible();
    await page
      .getByRole("dialog", { name: /Discover Models — Bedrock/i })
      .getByText("Close", { exact: true })
      .click();

    await page.getByRole("button", { name: "Export" }).click();
    await expect(page.getByText("Export Profile")).toBeVisible();
    const exported = await page.getByLabel("Profile JSON").inputValue();
    await page.getByText("Close", { exact: true }).click();

    await page.getByRole("button", { name: "Import" }).click();
    await page.getByLabel("Profile Name").fill("imported-cloud");
    await page.getByLabel("Exported Profile JSON").fill(exported);
    await page.getByRole("button", { name: "Import" }).nth(1).click();
    await expect(page.getByLabel("Profile", { exact: true })).toHaveValue("imported-cloud");
  });

  test("session creation and streaming shows assistant response and status changes", async ({ page }) => {
    await mockApi(page, { streamDelayMs: 600 });
    await page.goto("/");

    // Create a new session.
    await page.getByRole("navigation", { name: "Main" }).getByRole("button", { name: "New session" }).click();

    // Verify the session appears in the Runs panel.
    await page.getByRole("button", { name: "Runs" }).click();
    await expect(page.getByText("sess-1")).toBeVisible();

    // Select the session to activate it.
    await page.getByText("sess-1").click();

    // Verify the empty state before sending a message.
    const chat = page.getByRole("log", { name: "Conversation transcript" });
    await expect(chat.getByText("No messages yet")).toBeVisible();

    // Send a prompt.
    const prompt = page.getByRole("textbox", { name: "Prompt" });
    await prompt.click();
    await prompt.fill("Build a todo app");
    await page.keyboard.press("Control+Enter");

    // Verify the user message appears immediately.
    await expect(chat.getByText("Build a todo app")).toBeVisible();

    // While the stream is in progress the chat should be busy.
    await expect(chat).toHaveAttribute("aria-busy", "true");

    // Wait for the streamed assistant message to appear.
    await expect(chat.getByText("Done from stream.")).toBeVisible();

    // After streaming completes the chat should no longer be busy.
    await expect(chat).toHaveAttribute("aria-busy", "false");

    // Verify the session status in the runs panel remains idle after streaming.
    await page.getByRole("button", { name: "Runs" }).click();
    await expect(page.getByText("idle")).toBeVisible();
  });

  test("files panel loads paged results and previews a file", async ({ page }) => {
    const session = {
      session_id: "sess-1",
      status: "idle",
      mode: "code",
      trust_mode: "ask",
      workspace_root: ".",
      model_selection: {
        profile: "local",
        provider: "ollama",
        model: "llama3.2",
      },
      changed_files: ["src/file0.ts"],
    };
    const firstPage = Array.from({ length: 100 }, (_, index) => ({
      path: `src/file${index}.ts`,
      type: "file",
    }));
    const secondPage = Array.from({ length: 20 }, (_, index) => ({
      path: `src/file${index + 100}.ts`,
      type: "file",
    }));

    await mockApi(page, {
      initialSessions: [session],
      initialView: buildSessionView(session),
      fileBrowserPages: {
        "|0": { items: firstPage, has_more: true, next_offset: 100, query: "" },
        "|100": { items: secondPage, has_more: false, next_offset: null, query: "" },
      },
      filePreviews: {
        "src/file0.ts": "export const preview = true;",
      },
    });
    await page.goto("/");

    await page.getByRole("button", { name: "Runs" }).click();
    await page.getByRole("button", { name: /sess-1/i }).click();
    await page.getByRole("button", { name: "Files" }).click();
    await expect(page.getByText("100 entries loaded")).toBeVisible();
    await page.getByRole("button", { name: "Load next 100" }).click();
    await expect(page.getByText("120 entries loaded")).toBeVisible();
    await page.getByLabel("Preview src/file0.ts").click();
    await expect(page.getByText("export const preview = true;")).toBeVisible();
  });

  test("command palette opens usage and runs filter narrows visible sessions", async ({ page }) => {
    const sessionOne = {
      session_id: "sess-1",
      status: "completed",
      mode: "code",
      trust_mode: "ask",
      workspace_root: ".",
      model_selection: {
        profile: "local",
        provider: "ollama",
        model: "llama3.2",
      },
    };
    const sessionTwo = {
      session_id: "sess-2",
      status: "failed",
      mode: "review",
      trust_mode: "ask",
      workspace_root: ".",
      model_selection: {
        profile: "local",
        provider: "ollama",
        model: "llama3.2",
      },
    };

    await mockApi(page, {
      initialSessions: [sessionOne, sessionTwo],
      initialView: buildSessionView(sessionOne),
    });
    await page.goto("/");

    await page.getByRole("button", { name: "Runs" }).click();
    await page.getByRole("button", { name: /sess-1/i }).click();
    await page.keyboard.press("Control+K");
    await page.keyboard.type("usage");
    await page.keyboard.press("Enter");
    await expect(page.getByRole("heading", { name: "Usage" })).toBeVisible();
    await expect(page.getByText("1.5k")).toBeVisible();

    await page.getByRole("button", { name: "Runs" }).click();
    const filter = page.getByPlaceholder("Filter sessions...");
    await filter.fill("sess-2");
    await expect(page.getByRole("button", { name: /sess-2/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /sess-1/i })).toHaveCount(0);
  });
});
