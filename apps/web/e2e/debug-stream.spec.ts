import { test, expect, type Page } from "@playwright/test";

async function mockApi(page: Page) {
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const method = route.request().method();
    const json = async (payload: unknown) => {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(payload) });
    };

    if (path === "/api/config") {
      await json({ onboarding_complete: true, onboarding_dismissed: false, default_workspace: ".", theme: "dark" });
      return;
    }
    if (path === "/api/coder/commands") {
      await json([{ id: "new", label: "New Session", cli: "/new", surface: "global" }]);
      return;
    }
    if (path === "/api/coder/models") {
      await json({ configured: true, default_profile: "local", profiles: [{ name: "local", default: true, providers: [{ id: "ollama", kind: "ollama", auth_mode: "none", endpoint: "http://localhost:11434/v1" }], models: [{ id: "planner", role: "planner", provider: "ollama", model: "llama3.2", display_name: "Llama 3.2" }] }] });
      return;
    }
    if (path === "/api/coder/sessions" && method === "GET") {
      await json([]);
      return;
    }
    if (path === "/api/providers/profiles") {
      await json({ configured: true, profiles: [{ name: "local", default: true, providers: [{ id: "ollama", kind: "ollama", auth_mode: "none", endpoint: "http://localhost:11434/v1" }], models: [{ id: "planner", role: "planner", provider: "ollama", model: "llama3.2" }] }] });
      return;
    }
    if (path === "/api/coder/sessions" && method === "POST") {
      const session = { session_id: "sess-1", status: "idle", mode: "code", trust_mode: "ask", workspace_root: ".", model_selection: { profile: "local", provider: "ollama", model: "llama3.2" } };
      await json(session);
      return;
    }
    if (path === "/api/coder/sessions/sess-1/view") {
      await json({
        session: { session_id: "sess-1", status: "idle", mode: "code", trust_mode: "ask", workspace_root: ".", model_selection: { profile: "local", provider: "ollama", model: "llama3.2" }, transcript: [] },
        queued_prompts: [],
        available_commands: ["new"],
        approvals: [],
        events: [],
        command_results: [],
        diffs: [],
        artifacts: [],
      });
      return;
    }
    if (path === "/api/coder/sessions/sess-1/messages/stream") {
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
    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ error: `Unhandled route ${method} ${path}` }) });
  });
}

test("debug stream", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  await page.getByRole("button", { name: "New session" }).click();
  await page.getByRole("button", { name: "Runs" }).click();
  await page.getByText("sess-1").click();
  
  const prompt = page.getByRole("textbox", { name: "Prompt" });
  await prompt.click();
  await prompt.fill("Build a todo app");
  await page.keyboard.press("Control+Enter");
  
  await page.waitForTimeout(2000);
  const html = await page.content();
  console.log("PAGE HTML:", html);
});
