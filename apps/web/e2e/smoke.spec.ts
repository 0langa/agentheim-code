import { expect, test, type Page } from "@playwright/test";

type SessionState = {
  activeSessionId: string | null;
  sessions: Array<Record<string, unknown>>;
  view: Record<string, unknown> | null;
  providersConfigured: boolean;
  providers: Array<Record<string, unknown>>;
  onboardingComplete: boolean;
  onboardingDismissed: boolean;
};

function createMockState(): SessionState {
  return {
    activeSessionId: null,
    sessions: [],
    view: null,
    providersConfigured: false,
    providers: [],
    onboardingComplete: true,
    onboardingDismissed: false,
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
};

async function mockApi(page: Page, options: boolean | MockApiOptions = {}) {
  const opts = typeof options === "boolean" ? { withApproval: options } : options;
  const {
    withApproval = false,
    onboardingComplete = true,
    onboardingDismissed = false,
    modelConfigured = true,
    wizardTemplates = [],
  } = opts;

  const state = createMockState();
  state.onboardingComplete = onboardingComplete;
  state.onboardingDismissed = onboardingDismissed;
  state.providersConfigured = modelConfigured;

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
      state.view ??= {
        session: {
          ...session,
          transcript: [],
        },
        queued_prompts: [],
        available_commands: ["new"],
        approvals: withApproval
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
        events: [],
        command_results: [],
        diffs: [],
        artifacts: [],
      };
      await json(session);
      return;
    }

    if (path === "/api/coder/sessions/sess-1/view") {
      await json(state.view);
      return;
    }

    if (path === "/api/coder/sessions/sess-1/messages/stream") {
      const body = route.request().postDataJSON() as { prompt: string };
      state.view = {
        ...state.view,
        session: {
          ...(state.view?.session as Record<string, unknown>),
          status: "idle",
          transcript: [
            { role: "user", content: body.prompt },
            { role: "assistant", content: "Done from stream." },
          ],
          current_assistant_message: "",
        },
      };
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

    await expect(page.getByText("Done from stream.")).toBeVisible();
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

  test("provider wizard flow adds a new provider via settings", async ({ page }) => {
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

    // Open the provider wizard.
    await page.getByRole("button", { name: "+ Add Provider" }).click();
    const wizardDialog = page.getByRole("dialog", { name: "Add AI Provider" });
    await expect(wizardDialog).toBeVisible();

    // Select the OpenAI template.
    await page.locator('button.provider-card[title="OpenAI"]').click();

    // Fill in the configuration fields.
    await page.getByLabel("Profile Name").fill("My OpenAI");
    await page.getByLabel("Provider ID").fill("openai");
    await page.getByLabel("Model ID").fill("gpt-4.1");
    await page.getByLabel("API Key").fill("sk-test-key");

    // Test the connection.
    await page.getByRole("button", { name: "Test Connection" }).click();
    await expect(page.getByText("Connection successful")).toBeVisible();

    // Save the provider.
    await page.getByRole("button", { name: "Save Provider" }).click();

    // Verify the wizard closes.
    await expect(wizardDialog).toHaveCount(0);

    // Refresh the Settings panel to verify the provider list updated.
    await page.getByRole("button", { name: "Runs" }).click();
    await page.getByRole("button", { name: "Settings" }).click();
    await expect(page.getByText("My OpenAI")).toBeVisible();
  });

  test("session creation and streaming shows assistant response and status changes", async ({ page }) => {
    await mockApi(page);

    // Override the stream endpoint with a delayed response so the "running" state is observable.
    // Playwright routes are checked in reverse registration order, so this must be added AFTER mockApi.
    await page.route("**/api/coder/sessions/sess-1/messages/stream", async (route) => {
      const body = route.request().postDataJSON() as { prompt: string };
      await new Promise((r) => setTimeout(r, 600));
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
    });
    await page.goto("/");

    // Create a new session.
    await page.getByRole("button", { name: "New session" }).click();

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
    await expect(page.getByText("Done from stream.")).toBeVisible();

    // After streaming completes the chat should no longer be busy.
    await expect(chat).toHaveAttribute("aria-busy", "false");

    // Verify the session status in the runs panel remains idle after streaming.
    await page.getByRole("button", { name: "Runs" }).click();
    await expect(page.getByText("idle")).toBeVisible();
  });
});
