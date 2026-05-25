import { spawn } from "node:child_process";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

import { chromium } from "@playwright/test";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const webRoot = path.resolve(__dirname, "..");
const repoRoot = path.resolve(webRoot, "..", "..");
const docsAssetsRoot = path.join(repoRoot, "docs", "assets");
const baseUrl = "http://127.0.0.1:4173";
function buildSessionView(session) {
  return {
    session: {
      ...session,
      transcript: session.transcript ?? [],
      current_assistant_message: session.current_assistant_message ?? "",
    },
    queued_prompts: [],
    available_commands: ["new", "files", "usage"],
    events: [
      {
        event_id: "evt-1",
        type: "tool",
        message: "Indexed workspace context",
        timestamp: "2026-05-25T12:00:00Z",
      },
      {
        event_id: "evt-2",
        type: "message",
        message: "Prepared implementation notes",
        timestamp: "2026-05-25T12:00:04Z",
      },
    ],
    approvals: [],
    command_results: [
      {
        command: ["pytest", "-q"],
        exit_code: 0,
        status: "ok",
        stdout: "47 passed in 30.81s",
        stderr: "",
        timestamp: "2026-05-25T12:00:09Z",
      },
    ],
    diffs: [
      {
        path: "src/agentheim_code/backend.py",
        status: "modified",
        before: "return payload",
        after: "return SessionViewResponse.model_validate(payload)",
        timestamp: "2026-05-25T12:00:10Z",
      },
    ],
    artifacts: [],
  };
}

async function waitForServer(url, timeoutMs = 120_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok) {
        return;
      }
    } catch {
      // keep waiting until the Vite server is ready
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`Timed out waiting for dev server at ${url}`);
}

async function installMockApi(page) {
  const session = {
    session_id: "sess-1",
    status: "idle",
    mode: "code",
    trust_mode: "ask",
    workspace_root: "C:/Users/juliu/source/repos/agentheim-code",
    model_selection: {
      profile: "local",
      provider: "ollama",
      model: "llama3.2",
    },
    repair_attempts: 0,
    last_failure_reason: "",
    changed_files: [
      "src/agentheim_code/backend.py",
      "apps/web/src/App.tsx",
      "docs/USER_GUIDE.md",
    ],
    transcript: [
      {
        role: "user",
        content: "Summarize the repo health and call out risky files.",
        timestamp: "2026-05-25T12:00:01Z",
      },
      {
        role: "assistant",
        content:
          "Repo health looks good. Focus next on `backend.py`, `App.tsx`, and release docs before any 2.0.0 claim.",
        timestamp: "2026-05-25T12:00:05Z",
      },
    ],
  };

  const filePages = {
    "|0": {
      items: [
        { path: "src/agentheim_code/backend.py", type: "file" },
        { path: "apps/web/src/App.tsx", type: "file" },
        { path: "apps/web/src/components/WorkspaceExplorer.tsx", type: "file" },
        { path: "docs/USER_GUIDE.md", type: "file" },
      ],
      has_more: false,
      next_offset: null,
      query: "",
    },
  };

  const previews = {
    "src/agentheim_code/backend.py":
      "class SessionViewResponse(BaseModel):\n    session: SessionResponse\n    events: list[SessionEventResponse] = []\n",
  };

  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const pathName = url.pathname;
    const method = route.request().method();

    const json = async (payload) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(payload),
      });
    };

    if (pathName === "/api/config") {
      await json({
        onboarding_complete: true,
        onboarding_dismissed: false,
        default_workspace: ".",
        theme: "dark",
      });
      return;
    }

    if (pathName === "/api/coder/commands") {
      await json([
        { id: "new", label: "New Session", cli: "/new", surface: "global" },
        { id: "files", label: "Open Files", cli: "/files", surface: "global" },
        { id: "usage", label: "Open Usage", cli: "/usage", surface: "global" },
      ]);
      return;
    }

    if (pathName === "/api/coder/sessions" && method === "GET") {
      await json([session]);
      return;
    }

    if (pathName === "/api/coder/models") {
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

    if (pathName === "/api/coder/sessions/sess-1/view") {
      await json(buildSessionView(session));
      return;
    }

    if (pathName === "/api/coder/files/browser") {
      const key = `${url.searchParams.get("q") ?? ""}|${url.searchParams.get("offset") ?? "0"}`;
      await json(
        filePages[key] ?? {
          items: [],
          has_more: false,
          next_offset: null,
          query: url.searchParams.get("q") ?? "",
        },
      );
      return;
    }

    if (pathName === "/api/coder/files/preview") {
      const previewPath = url.searchParams.get("path") ?? "";
      await json(previews[previewPath] ?? "No preview available.");
      return;
    }

    if (pathName === "/api/coder/sessions/sess-1/usage") {
      await json({
        session_id: "sess-1",
        input_tokens: 1200,
        output_tokens: 340,
        total_tokens: 1540,
        estimated_cost_usd: 0.0123,
        calls: 2,
        breakdown: [
          {
            sequence: 1,
            timestamp: "2026-05-25T12:00:00Z",
            model: "llama3.2",
            provider: "ollama",
            input_tokens: 800,
            output_tokens: 200,
            total_tokens: 1000,
            estimated_cost_usd: 0.008,
          },
          {
            sequence: 2,
            timestamp: "2026-05-25T12:01:00Z",
            model: "llama3.2",
            provider: "ollama",
            input_tokens: 400,
            output_tokens: 140,
            total_tokens: 540,
            estimated_cost_usd: 0.0043,
          },
        ],
      });
      return;
    }

    if (pathName === "/api/providers/profiles") {
      await json({
        configured: true,
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
              },
            ],
          },
        ],
      });
      return;
    }

    await route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ error: `Unhandled route ${method} ${pathName}` }),
    });
  });
}

async function main() {
  await mkdir(docsAssetsRoot, { recursive: true });

  const server =
    process.platform === "win32"
      ? spawn("cmd.exe", ["/c", "npm run dev -- --host 127.0.0.1 --port 4173"], {
          cwd: webRoot,
          stdio: "pipe",
          windowsHide: true,
        })
      : spawn("npm", ["run", "dev", "--", "--host", "127.0.0.1", "--port", "4173"], {
          cwd: webRoot,
          stdio: "pipe",
        });

  let serverFailed = false;
  server.stderr.on("data", (chunk) => {
    const text = chunk.toString();
    if (text.toLowerCase().includes("error")) {
      serverFailed = true;
      process.stderr.write(text);
    }
  });

  try {
    await waitForServer(baseUrl);
    if (serverFailed) {
      throw new Error("Vite dev server reported an error while starting.");
    }

    const browser = await chromium.launch();
    try {
      const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
      await installMockApi(page);
      await page.goto(baseUrl, { waitUntil: "networkidle" });
      await page.getByRole("button", { name: "Runs" }).click();
      await page.getByRole("button", { name: /sess-1/i }).click();
      await page.screenshot({
        path: path.join(docsAssetsRoot, "workbench-overview.png"),
        fullPage: true,
      });

      await page.getByRole("button", { name: "Files" }).click();
      await page.getByLabel("Preview src/agentheim_code/backend.py").click();
      await page.screenshot({
        path: path.join(docsAssetsRoot, "workbench-files.png"),
        fullPage: true,
      });

      await page.getByRole("button", { name: "Usage" }).click();
      await page.screenshot({
        path: path.join(docsAssetsRoot, "workbench-usage.png"),
        fullPage: true,
      });
    } finally {
      await browser.close();
    }
  } finally {
    if (process.platform === "win32") {
      spawn("cmd.exe", ["/c", `taskkill /PID ${server.pid} /T /F`], {
        stdio: "ignore",
        windowsHide: true,
      });
      await new Promise((resolve) => setTimeout(resolve, 1000));
    } else {
      server.kill("SIGTERM");
      await new Promise((resolve) => server.once("exit", resolve));
    }
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
