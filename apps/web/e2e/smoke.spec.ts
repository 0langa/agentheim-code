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
    await expect(page.getByText("✓ Connection successful")).toBeVisible();

    // Save the provider.
    await page.getByRole("button", { name: "Save Provider" }).click();

    // Verify the wizard closes.
    await expect(wizardDialog).toHaveCount(0);

    // Refresh the Settings panel to verify the provider list updated.
    await page.getByRole("button", { name: "Runs" }).click();
    await page.getByRole("button", { name: "Settings" }).click();
    await expect(page.locator(".provider-row").getByText("My OpenAI")).toBeVisible();
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
