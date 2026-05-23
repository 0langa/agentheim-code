import { expect, test, type Page } from "@playwright/test";

type SessionState = {
  activeSessionId: string | null;
  sessions: Array<Record<string, unknown>>;
  view: Record<string, unknown> | null;
};

function createMockState(withApproval = false): SessionState {
  return {
    activeSessionId: null,
    sessions: [],
    view: withApproval
      ? {
          session: {
            session_id: "sess-1",
            status: "idle",
            mode: "code",
            trust_mode: "ask",
            workspace_root: ".",
            transcript: [],
            model_selection: {
              profile: "local",
              provider: "ollama",
              model: "llama3.2",
            },
          },
          queued_prompts: [],
          available_commands: ["new"],
          approvals: [
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
          ],
          events: [],
          command_results: [],
          diffs: [],
          artifacts: [],
        }
      : null,
  };
}

async function mockApi(page: Page, withApproval = false) {
  const state = createMockState(withApproval);

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
      return;
    }

    if (path === "/api/coder/sessions" && method === "GET") {
      await json(state.sessions);
      return;
    }

    if (path === "/api/providers/profiles") {
      await json({
        configured: true,
        profiles: [
          {
            name: "local",
            default: true,
            providers: [{ id: "ollama", kind: "ollama", auth_mode: "none", endpoint: "http://localhost:11434/v1" }],
            models: [{ id: "planner", role: "planner", provider: "ollama", model: "llama3.2" }],
          },
        ],
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
});
