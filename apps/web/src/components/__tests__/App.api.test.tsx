import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import React from "react";

import { App } from "../../App";

const mockApi = vi.fn();
const mockFetchModeCatalog = vi.fn();
const mockStreamSessionMessage = vi.fn();
const mockPickDesktopWorkspace = vi.fn();
const mockGetDesktopBackendLaunchError = vi.fn();
const mockIsDesktopApp = vi.fn(() => false);
vi.mock("../../api", () => ({
  api: <T,>(path: string, init?: RequestInit): Promise<T> => mockApi(path, init) as Promise<T>,
  fetchModeCatalog: () => mockFetchModeCatalog(),
  streamSessionMessage: (...args: unknown[]) => mockStreamSessionMessage(...args),
  pickDesktopWorkspace: () => mockPickDesktopWorkspace(),
  getDesktopBackendLaunchError: () => mockGetDesktopBackendLaunchError(),
  isDesktopApp: () => mockIsDesktopApp(),
  ApiError: class ApiError extends Error {
    constructor(public status: number, message: string) {
      super(message);
    }
  },
}));

describe("App API integration", () => {
  beforeEach(() => {
    mockApi.mockReset();
    mockFetchModeCatalog.mockReset();
    mockStreamSessionMessage.mockReset();
    mockPickDesktopWorkspace.mockReset();
    mockGetDesktopBackendLaunchError.mockReset();
    mockIsDesktopApp.mockReset();
    mockIsDesktopApp.mockReturnValue(false);
    mockFetchModeCatalog.mockResolvedValue({
      modes: [
        { id: "ask", label: "Ask", description: "Answer directly.", edits_expected: false, legacy_aliases: ["plan"] },
        { id: "code", label: "Code", description: "Implement and verify.", edits_expected: true, legacy_aliases: ["fix", "docs", "test"] },
        { id: "review", label: "Review", description: "Inspect critically.", edits_expected: false, legacy_aliases: [] },
      ],
      trust_modes: [
        { id: "ask", label: "ask", description: "Pause for risky tools." },
        { id: "read_only", label: "read_only", description: "Inspect only." },
        { id: "workspace", label: "workspace", description: "Allow workspace edits." },
      ],
    });
  });

  it("creates session with dot workspace_root when default workspace is current directory", async () => {
    mockApi
      .mockResolvedValueOnce({
        onboarding_complete: true,
        onboarding_dismissed: false,
        default_workspace: ".",
        theme: "dark",
      }) // /config
      .mockResolvedValueOnce([]) // /coder/commands
      .mockResolvedValueOnce([]) // /coder/sessions
      .mockResolvedValueOnce({ configured: false, profiles: [] }) // /coder/models
      .mockResolvedValueOnce({
        session_id: "sess-1",
        status: "idle",
        mode: "code",
        workspace_root: ".",
      }) // POST /coder/sessions
      .mockResolvedValueOnce({
        session: {
          session_id: "sess-1",
          status: "idle",
          mode: "code",
          workspace_root: ".",
        },
        queued_prompts: [],
        available_commands: [],
      }); // GET /coder/sessions/sess-1/view

    render(<App />);

    // Wait for initial data load to finish
    await waitFor(() => expect(mockApi).toHaveBeenCalledTimes(4));

    const topBar = document.querySelector(".topbar");
    expect(topBar).not.toBeNull();
    const newButton = within(topBar as HTMLElement).getByRole("button", {
      name: "New session",
    });
    fireEvent.click(newButton);

    await waitFor(() => {
      const calls = mockApi.mock.calls;
      const postCall = calls.find(
        (c) => c[0] === "/coder/sessions" && c[1]?.method === "POST",
      );
      expect(postCall).toBeTruthy();
      const body = JSON.parse(postCall![1].body);
      expect(body).toEqual({ workspace_root: ".", trust_mode: "ask", mode: "code" });
    });

    await waitFor(() => {
      expect(mockApi).toHaveBeenCalledWith("/coder/sessions/sess-1/view", undefined);
    });
  });

  it("selecting a session fetches /view", async () => {
    mockApi
      .mockResolvedValueOnce({
        onboarding_complete: true,
        onboarding_dismissed: false,
        default_workspace: ".",
        theme: "dark",
      })
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([
        { session_id: "sess-2", status: "idle", mode: "code", workspace_root: "." },
      ])
      .mockResolvedValueOnce({ configured: false, profiles: [] })
      .mockResolvedValueOnce({
        session: {
          session_id: "sess-2",
          status: "idle",
          mode: "code",
          workspace_root: ".",
        },
        queued_prompts: [],
        available_commands: [],
      });

    render(<App />);

    await waitFor(() => expect(mockApi).toHaveBeenCalledTimes(4));
    fireEvent.click(screen.getByTitle("Runs"));

    const sessionButton = await screen.findByText("sess-2");
    fireEvent.click(sessionButton);

    await waitFor(() => {
      expect(mockApi).toHaveBeenCalledWith("/coder/sessions/sess-2/view", undefined);
    });
  });

  it("streams prompt updates before refetching full session view", async () => {
    mockApi
      .mockResolvedValueOnce({
        onboarding_complete: true,
        onboarding_dismissed: false,
        default_workspace: ".",
        theme: "dark",
      })
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([
        { session_id: "sess-3", status: "idle", mode: "code", workspace_root: "." },
      ])
      .mockResolvedValueOnce({ configured: false, profiles: [] })
      .mockResolvedValueOnce({
        session: {
          session_id: "sess-3",
          status: "idle",
          mode: "code",
          workspace_root: ".",
          transcript: [],
        },
        queued_prompts: [],
        available_commands: [],
        events: [],
        command_results: [],
      })
      .mockResolvedValueOnce({
        session: {
          session_id: "sess-3",
          status: "idle",
          mode: "code",
          workspace_root: ".",
          transcript: [{ role: "assistant", content: "done" }],
        },
        queued_prompts: [],
        available_commands: [],
        events: [{ type: "message", message: "done" }],
        command_results: [],
      });
    mockStreamSessionMessage.mockImplementation(
      async (
        _sessionId: string,
        _prompt: string,
        handlers: { onToken: (token: string) => void },
      ) => {
        handlers.onToken("streamed ");
        handlers.onToken("draft");
      },
    );

    render(<App />);

    await waitFor(() => expect(mockApi).toHaveBeenCalledTimes(4));
    fireEvent.click(screen.getByTitle("Runs"));
    fireEvent.click(await screen.findByText("sess-3"));
    await waitFor(() => expect(mockApi).toHaveBeenCalledTimes(5));

    fireEvent.change(screen.getByPlaceholderText(/Ask Agentheim Code/), {
      target: { value: "build it" },
    });
    fireEvent.click(screen.getByText(/Send/));

    await waitFor(() => {
      expect(mockStreamSessionMessage).toHaveBeenCalledWith(
        "sess-3",
        "build it",
        expect.objectContaining({ onToken: expect.any(Function) }),
        expect.any(AbortSignal),
        [],
        ".",
      );
      expect(screen.getByText("streamed draft")).toBeInTheDocument();
      expect(mockApi).toHaveBeenLastCalledWith(
        "/coder/sessions/sess-3/view",
        undefined,
      );
    });
  });

  it("auto-creates a session on first send when none is active", async () => {
    mockApi
      .mockResolvedValueOnce({
        onboarding_complete: true,
        onboarding_dismissed: false,
        default_workspace: ".",
        theme: "dark",
      })
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce({ configured: false, profiles: [] })
      .mockResolvedValueOnce({
        session_id: "sess-auto",
        status: "idle",
        mode: "code",
        workspace_root: "C:/tmp/project",
      })
      .mockResolvedValueOnce({
        session: {
          session_id: "sess-auto",
          status: "idle",
          mode: "code",
          trust_mode: "ask",
          workspace_root: "C:/tmp/project",
          transcript: [],
          model_selection: { profile: "auto", provider: "auto", model: "auto" },
        },
        queued_prompts: [],
        available_commands: [],
        events: [],
        command_results: [],
        approvals: [],
        diffs: [],
        artifacts: [],
      })
      .mockResolvedValueOnce({
        session: {
          session_id: "sess-auto",
          status: "idle",
          mode: "code",
          trust_mode: "ask",
          workspace_root: "C:/tmp/project",
          transcript: [{ role: "assistant", content: "ok" }],
          model_selection: { profile: "auto", provider: "auto", model: "auto" },
        },
        queued_prompts: [],
        available_commands: [],
        events: [],
        command_results: [],
        approvals: [],
        diffs: [],
        artifacts: [],
      });
    mockStreamSessionMessage.mockResolvedValue(undefined);

    render(<App />);

    await waitFor(() => expect(mockApi).toHaveBeenCalledTimes(4));

    fireEvent.change(screen.getByPlaceholderText(/Ask Agentheim Code/), {
      target: { value: "hello" },
    });
    fireEvent.click(screen.getByText(/Send/));

    await waitFor(() => {
      expect(mockApi).toHaveBeenCalledWith(
        "/coder/sessions",
        expect.objectContaining({
          method: "POST",
          body: expect.any(String),
        }),
      );
      const postCall = mockApi.mock.calls.find(
        (c) => c[0] === "/coder/sessions" && c[1]?.method === "POST",
      );
      expect(postCall).toBeTruthy();
      expect(JSON.parse(postCall![1].body)).toEqual({
        workspace_root: ".",
        trust_mode: "ask",
        mode: "code",
      });
      expect(mockStreamSessionMessage).toHaveBeenCalledWith(
        "sess-auto",
        "hello",
        expect.objectContaining({ onToken: expect.any(Function) }),
        expect.any(AbortSignal),
        [],
        "C:/tmp/project",
      );
    });
  });

  it("uses configured default workspace when auto-creating a session", async () => {
    mockApi
      .mockResolvedValueOnce({
        onboarding_complete: true,
        onboarding_dismissed: false,
        default_workspace: "C:/work/demo-app",
        theme: "dark",
      })
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce({ configured: false, profiles: [] })
      .mockResolvedValueOnce({
        session_id: "sess-ws",
        status: "idle",
        mode: "code",
        workspace_root: "C:/work/demo-app",
      })
      .mockResolvedValueOnce({
        session: {
          session_id: "sess-ws",
          status: "idle",
          mode: "code",
          trust_mode: "ask",
          workspace_root: "C:/work/demo-app",
          transcript: [],
          model_selection: { profile: "auto", provider: "auto", model: "auto" },
          changed_files: [],
        },
        queued_prompts: [],
        available_commands: [],
        events: [],
        command_results: [],
        approvals: [],
        diffs: [],
        artifacts: [],
      })
      .mockResolvedValueOnce({
        session: {
          session_id: "sess-ws",
          status: "completed",
          mode: "code",
          trust_mode: "ask",
          workspace_root: "C:/work/demo-app",
          transcript: [{ role: "assistant", content: "done" }],
          model_selection: { profile: "auto", provider: "auto", model: "auto" },
          changed_files: ["docs/plan.md", "src/app.ts"],
        },
        queued_prompts: [],
        available_commands: [],
        events: [],
        command_results: [{ command: "write docs/plan.md", timestamp: "now", status: "completed" }],
        approvals: [],
        diffs: [],
        artifacts: ["final_report.md", "run.json"],
      });
    mockStreamSessionMessage.mockResolvedValue(undefined);

    render(<App />);

    await waitFor(() => expect(mockApi).toHaveBeenCalledTimes(4));

    fireEvent.change(screen.getByPlaceholderText(/Ask Agentheim Code/), {
      target: { value: "hello" },
    });
    fireEvent.click(screen.getByText(/Send/));

    await waitFor(() => {
      expect(mockApi).toHaveBeenCalledWith(
        "/coder/sessions",
        expect.objectContaining({
          method: "POST",
          body: expect.any(String),
        }),
      );
      const postCall = mockApi.mock.calls.find(
        (c) => c[0] === "/coder/sessions" && c[1]?.method === "POST",
      );
      expect(postCall).toBeTruthy();
      expect(JSON.parse(postCall![1].body)).toEqual({
        workspace_root: "C:/work/demo-app",
        trust_mode: "ask",
        mode: "code",
      });
    });

    expect(await screen.findByText(/session effects/i)).toBeInTheDocument();
    expect(screen.getByText(/Changed files: docs\/plan.md, src\/app.ts/)).toBeInTheDocument();
  });

  it("shows clear session error when auto-create fails", async () => {
    mockApi
      .mockResolvedValueOnce({
        onboarding_complete: true,
        onboarding_dismissed: false,
        default_workspace: ".",
        theme: "dark",
      })
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce({ configured: false, profiles: [] })
      .mockRejectedValueOnce(new Error("Backend unavailable"));

    render(<App />);

    await waitFor(() => expect(mockApi).toHaveBeenCalledTimes(4));

    fireEvent.change(screen.getByPlaceholderText(/Ask Agentheim Code/), {
      target: { value: "hello" },
    });
    fireEvent.click(screen.getByText(/Send/));

    expect(await screen.findByText(/Backend unavailable/)).toBeInTheDocument();
    expect(mockStreamSessionMessage).not.toHaveBeenCalled();
  });

  it("persists default workspace from settings for consistent new sessions", async () => {
    mockApi
      .mockResolvedValueOnce({
        onboarding_complete: true,
        onboarding_dismissed: false,
        default_workspace: ".",
        theme: "dark",
      })
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce({ configured: false, profiles: [] })
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce({
        onboarding_complete: true,
        onboarding_dismissed: false,
        default_workspace: "C:/repo/demo",
        theme: "dark",
      })
      .mockResolvedValueOnce({
        session_id: "sess-settings",
        status: "idle",
        mode: "code",
        trust_mode: "ask",
        workspace_root: "C:/repo/demo",
        model_selection: { profile: "auto", provider: "auto", model: "auto" },
      })
      .mockResolvedValueOnce({
        session: {
          session_id: "sess-settings",
          status: "idle",
          mode: "code",
          trust_mode: "ask",
          workspace_root: "C:/repo/demo",
          transcript: [],
          model_selection: { profile: "auto", provider: "auto", model: "auto" },
        },
        queued_prompts: [],
        available_commands: [],
        events: [],
        command_results: [],
        approvals: [],
        diffs: [],
        artifacts: [],
      });

    render(<App />);
    await waitFor(() => expect(mockApi).toHaveBeenCalledTimes(4));

    fireEvent.click(screen.getByTitle("Settings"));
    fireEvent.change(screen.getByLabelText("Default workspace"), {
      target: { value: "C:/repo/demo" },
    });

    await waitFor(() => {
      expect(mockApi).toHaveBeenCalledWith(
        "/config",
        expect.objectContaining({
          method: "PATCH",
          body: JSON.stringify({ default_workspace: "C:/repo/demo" }),
        }),
      );
    });

    fireEvent.click(screen.getAllByRole("button", { name: "New session" })[1]);

    await waitFor(() => {
      const postCall = mockApi.mock.calls.find(
        (c) => c[0] === "/coder/sessions" && c[1]?.method === "POST",
      );
      expect(JSON.parse(postCall![1].body)).toEqual({
        workspace_root: "C:/repo/demo",
        trust_mode: "ask",
        mode: "code",
      });
    });
  });

  it("uses desktop picker when no workspace is configured", async () => {
    mockIsDesktopApp.mockReturnValue(true);
    mockPickDesktopWorkspace.mockResolvedValue("C:/picked/workspace");
    mockApi
      .mockResolvedValueOnce({
        onboarding_complete: true,
        onboarding_dismissed: false,
        default_workspace: "",
        theme: "dark",
      })
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce({ configured: false, profiles: [] })
      .mockResolvedValueOnce({
        onboarding_complete: true,
        onboarding_dismissed: false,
        default_workspace: "C:/picked/workspace",
        theme: "dark",
      })
      .mockResolvedValueOnce({
        session_id: "sess-picked",
        status: "idle",
        mode: "code",
        trust_mode: "ask",
        workspace_root: "C:/picked/workspace",
        model_selection: { profile: "auto", provider: "auto", model: "auto" },
      })
      .mockResolvedValueOnce({
        session: {
          session_id: "sess-picked",
          status: "idle",
          mode: "code",
          trust_mode: "ask",
          workspace_root: "C:/picked/workspace",
          transcript: [],
          model_selection: { profile: "auto", provider: "auto", model: "auto" },
        },
        queued_prompts: [],
        available_commands: [],
        events: [],
        command_results: [],
        approvals: [],
        diffs: [],
        artifacts: [],
      })
      .mockResolvedValueOnce({
        session: {
          session_id: "sess-picked",
          status: "idle",
          mode: "code",
          trust_mode: "ask",
          workspace_root: "C:/picked/workspace",
          transcript: [{ role: "assistant", content: "ok" }],
          model_selection: { profile: "auto", provider: "auto", model: "auto" },
        },
        queued_prompts: [],
        available_commands: [],
        events: [],
        command_results: [],
        approvals: [],
        diffs: [],
        artifacts: [],
      });
    mockStreamSessionMessage.mockResolvedValue(undefined);

    render(<App />);
    await waitFor(() => expect(mockApi).toHaveBeenCalledTimes(4));

    fireEvent.change(screen.getByPlaceholderText(/Ask Agentheim Code/), {
      target: { value: "hello" },
    });
    fireEvent.click(screen.getByText(/Send/));

    await waitFor(() => {
      expect(mockPickDesktopWorkspace).toHaveBeenCalledTimes(1);
      expect(mockApi).toHaveBeenCalledWith(
        "/config",
        expect.objectContaining({
          method: "PATCH",
          body: JSON.stringify({ default_workspace: "C:/picked/workspace" }),
        }),
      );
    });
  });

  it("shows desktop backend launch error instead of endless loading", async () => {
    mockIsDesktopApp.mockReturnValue(true);
    mockGetDesktopBackendLaunchError.mockResolvedValue("Desktop backend did not become ready for workspace C:/broken.");
    mockApi
      .mockResolvedValueOnce({
        onboarding_complete: true,
        onboarding_dismissed: false,
        default_workspace: "C:/broken",
        theme: "dark",
      })
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce({ configured: false, profiles: [] })
      .mockRejectedValueOnce(new Error("Backend unavailable"));

    render(<App />);
    await waitFor(() => expect(mockApi).toHaveBeenCalledTimes(4));

    fireEvent.click(screen.getByText(/New session/i));

    expect(
      await screen.findByText(/Desktop backend did not become ready for workspace C:\/broken\./),
    ).toBeInTheDocument();
  });

  it("keeps workspace_root on session-scoped follow-up calls", async () => {
    mockApi
      .mockResolvedValueOnce({
        onboarding_complete: true,
        onboarding_dismissed: false,
        default_workspace: ".",
        theme: "dark",
      })
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([
        {
          session_id: "sess-9",
          status: "idle",
          mode: "code",
          workspace_root: "C:/workspace/test-app",
        },
      ])
      .mockResolvedValueOnce({ configured: false, profiles: [] })
      .mockResolvedValueOnce({
        session: {
          session_id: "sess-9",
          status: "idle",
          mode: "code",
          trust_mode: "ask",
          workspace_root: "C:/workspace/test-app",
          transcript: [],
          model_selection: { profile: "auto", provider: "auto", model: "auto" },
        },
        queued_prompts: [],
        available_commands: [],
        events: [],
        command_results: [],
        approvals: [],
        diffs: [],
        artifacts: [],
      })
      .mockResolvedValueOnce({
        session: {
          session_id: "sess-9",
          status: "idle",
          mode: "code",
          trust_mode: "ask",
          workspace_root: "C:/workspace/test-app",
          transcript: [{ role: "assistant", content: "ok" }],
          model_selection: { profile: "auto", provider: "auto", model: "auto" },
        },
        queued_prompts: [],
        available_commands: [],
        events: [],
        command_results: [],
        approvals: [],
        diffs: [],
        artifacts: [],
      });
    mockStreamSessionMessage.mockResolvedValue(undefined);

    render(<App />);

    await waitFor(() => expect(mockApi).toHaveBeenCalledTimes(4));
    fireEvent.click(screen.getByTitle("Runs"));
    fireEvent.click(await screen.findByText("sess-9"));

    await waitFor(() => {
      expect(mockApi).toHaveBeenCalledWith(
        "/coder/sessions/sess-9/view?workspace_root=C%3A%2Fworkspace%2Ftest-app",
        undefined,
      );
    });

    fireEvent.change(screen.getByPlaceholderText(/Ask Agentheim Code/), {
      target: { value: "hello there" },
    });
    fireEvent.click(screen.getByText(/Send/));

    await waitFor(() => {
      expect(mockStreamSessionMessage).toHaveBeenCalledWith(
        "sess-9",
        "hello there",
        expect.objectContaining({ onToken: expect.any(Function) }),
        expect.any(AbortSignal),
        [],
        "C:/workspace/test-app",
      );
      expect(mockApi).toHaveBeenLastCalledWith(
        "/coder/sessions/sess-9/view?workspace_root=C%3A%2Fworkspace%2Ftest-app",
        undefined,
      );
    });
  });

  it("sends selected trust mode when creating a session", async () => {
    mockApi
      .mockResolvedValueOnce({
        onboarding_complete: true,
        onboarding_dismissed: false,
        default_workspace: ".",
        theme: "dark",
      })
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce({ configured: false, profiles: [] })
      .mockResolvedValueOnce({
        session_id: "sess-4",
        status: "idle",
        mode: "code",
        workspace_root: ".",
      })
      .mockResolvedValueOnce({
        session: {
          session_id: "sess-4",
          status: "idle",
          mode: "code",
          workspace_root: ".",
        },
        queued_prompts: [],
        available_commands: [],
      });

    render(<App />);
    await waitFor(() => expect(mockApi).toHaveBeenCalledTimes(4));
    fireEvent.change(screen.getByLabelText("Trust mode"), {
      target: { value: "workspace" },
    });
    const topBar = document.querySelector(".topbar");
    expect(topBar).not.toBeNull();
    fireEvent.click(
      within(topBar as HTMLElement).getByRole("button", { name: "New session" }),
    );

    await waitFor(() => {
      const postCall = mockApi.mock.calls.find(
        (c) => c[0] === "/coder/sessions" && c[1]?.method === "POST",
      );
      expect(JSON.parse(postCall![1].body)).toEqual({
        workspace_root: ".",
        trust_mode: "workspace",
        mode: "code",
      });
    });
  });

  it("updates the active session when the mode changes", async () => {
    mockApi
      .mockResolvedValueOnce({
        onboarding_complete: true,
        onboarding_dismissed: false,
        default_workspace: ".",
        theme: "dark",
      })
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([
        {
          session_id: "sess-mode",
          status: "idle",
          mode: "code",
          trust_mode: "ask",
          workspace_root: ".",
        },
      ])
      .mockResolvedValueOnce({ configured: false, profiles: [] })
      .mockResolvedValueOnce({
        session: {
          session_id: "sess-mode",
          status: "idle",
          mode: "ask",
          trust_mode: "ask",
          workspace_root: ".",
          model_selection: { profile: "auto", provider: "auto", model: "auto" },
        },
        queued_prompts: [],
        available_commands: [],
      })
      .mockResolvedValueOnce({
        session_id: "sess-mode",
        status: "idle",
        mode: "review",
        trust_mode: "ask",
        workspace_root: ".",
        model_selection: { profile: "auto", provider: "auto", model: "auto" },
      })
      .mockResolvedValueOnce({
        session: {
          session_id: "sess-mode",
          status: "idle",
          mode: "review",
          trust_mode: "ask",
          workspace_root: ".",
          model_selection: { profile: "auto", provider: "auto", model: "auto" },
        },
        queued_prompts: [],
        available_commands: [],
      });

    render(<App />);
    await waitFor(() => expect(mockApi).toHaveBeenCalledTimes(4));
    fireEvent.click(screen.getByTitle("Runs"));
    fireEvent.click(await screen.findByText("sess-mode"));

    await waitFor(() => {
      expect(mockApi).toHaveBeenCalledWith("/coder/sessions/sess-mode/view", undefined);
    });

    await waitFor(() => {
      expect(
        within(document.querySelector(".composer .modes") as HTMLElement).getByRole("button", {
          name: "ask",
        }),
      ).toHaveAttribute("aria-pressed", "true");
    });

    fireEvent.click(within(document.querySelector(".composer .modes") as HTMLElement).getByRole("button", { name: "review" }));

    await waitFor(() => {
      expect(mockApi).toHaveBeenCalledWith(
        "/coder/sessions/sess-mode/mode",
        expect.objectContaining({
          method: "PATCH",
          body: JSON.stringify({ mode: "review" }),
        }),
      );
    });
  });

  it("updates the active session when trust mode changes", async () => {
    mockApi
      .mockResolvedValueOnce({
        onboarding_complete: true,
        onboarding_dismissed: false,
        default_workspace: ".",
        theme: "dark",
      })
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([
        {
          session_id: "sess-trust",
          status: "idle",
          mode: "code",
          trust_mode: "ask",
          workspace_root: ".",
        },
      ])
      .mockResolvedValueOnce({ configured: false, profiles: [] })
      .mockResolvedValueOnce({
        session: {
          session_id: "sess-trust",
          status: "idle",
          mode: "code",
          trust_mode: "read_only",
          workspace_root: ".",
          model_selection: { profile: "auto", provider: "auto", model: "auto" },
        },
        queued_prompts: [],
        available_commands: [],
      })
      .mockResolvedValueOnce({
        session_id: "sess-trust",
        status: "idle",
        mode: "code",
        trust_mode: "workspace",
        workspace_root: ".",
        model_selection: { profile: "auto", provider: "auto", model: "auto" },
      })
      .mockResolvedValueOnce({
        session: {
          session_id: "sess-trust",
          status: "idle",
          mode: "code",
          trust_mode: "workspace",
          workspace_root: ".",
          model_selection: { profile: "auto", provider: "auto", model: "auto" },
        },
        queued_prompts: [],
        available_commands: [],
      });

    render(<App />);
    await waitFor(() => expect(mockApi).toHaveBeenCalledTimes(4));
    fireEvent.click(screen.getByTitle("Runs"));
    fireEvent.click(await screen.findByText("sess-trust"));

    await waitFor(() => {
      expect(mockApi).toHaveBeenCalledWith("/coder/sessions/sess-trust/view", undefined);
    });

    await waitFor(() => {
      expect(screen.getByLabelText("Trust mode")).toHaveValue("read_only");
    });

    fireEvent.change(screen.getByLabelText("Trust mode"), {
      target: { value: "workspace" },
    });

    await waitFor(() => {
      expect(mockApi).toHaveBeenCalledWith(
        "/coder/sessions/sess-trust/trust-mode",
        expect.objectContaining({
          method: "PATCH",
          body: JSON.stringify({ trust_mode: "workspace" }),
        }),
      );
    });
  });

  it("does not auto-switch the inspector when approvals are pending", async () => {
    mockApi
      .mockResolvedValueOnce({
        onboarding_complete: true,
        onboarding_dismissed: false,
        default_workspace: ".",
        theme: "dark",
      })
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([
        { session_id: "sess-approval", status: "awaiting_approval", mode: "code", workspace_root: "." },
      ])
      .mockResolvedValueOnce({ configured: false, profiles: [] })
      .mockResolvedValueOnce({
        session: {
          session_id: "sess-approval",
          status: "awaiting_approval",
          mode: "code",
          trust_mode: "ask",
          workspace_root: ".",
          model_selection: { profile: "auto", provider: "auto", model: "auto" },
          pending_assistant_message: "Approval needed.",
        },
        queued_prompts: [],
        available_commands: [],
        events: [],
        approvals: [
          {
            request_id: "req-1",
            tool_id: "shell.execute",
            risk_level: "medium",
            reason: "Run tests",
            status: "pending",
            params: { command: ["pytest", "-q"] },
            target: "pytest -q",
            action_kind: "shell",
          },
        ],
      });

    render(<App />);
    await waitFor(() => expect(mockApi).toHaveBeenCalledTimes(4));
    fireEvent.click(screen.getByTitle("Runs"));
    fireEvent.click(await screen.findByText("sess-approval"));

    await waitFor(() => {
      expect(mockApi).toHaveBeenCalledWith("/coder/sessions/sess-approval/view", undefined);
    });

    expect(await screen.findByText("Approval needed.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open approvals" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Runs" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Approvals" })).not.toBeInTheDocument();
    expect(screen.queryByText("Grant")).not.toBeInTheDocument();
  });

  it("surfaces resume when a session is cancelled and calls the resume route", async () => {
    mockApi
      .mockResolvedValueOnce({
        onboarding_complete: true,
        onboarding_dismissed: false,
        default_workspace: ".",
        theme: "dark",
      })
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([
        { session_id: "sess-resume", status: "cancelled", mode: "code", workspace_root: "." },
      ])
      .mockResolvedValueOnce({ configured: false, profiles: [] })
      .mockResolvedValueOnce({
        session: {
          session_id: "sess-resume",
          status: "cancelled",
          mode: "code",
          trust_mode: "ask",
          workspace_root: ".",
          transcript: [],
          model_selection: { profile: "auto", provider: "auto", model: "auto" },
        },
        queued_prompts: [],
        available_commands: [],
        approvals: [],
        events: [],
        command_results: [],
        diffs: [],
        artifacts: [],
      })
      .mockResolvedValueOnce({
        session_id: "sess-resume",
        status: "idle",
        mode: "code",
        trust_mode: "ask",
        workspace_root: ".",
        model_selection: { profile: "auto", provider: "auto", model: "auto" },
      })
      .mockResolvedValueOnce({
        session: {
          session_id: "sess-resume",
          status: "idle",
          mode: "code",
          trust_mode: "ask",
          workspace_root: ".",
          transcript: [],
          model_selection: { profile: "auto", provider: "auto", model: "auto" },
        },
        queued_prompts: [],
        available_commands: [],
        approvals: [],
        events: [],
        command_results: [],
        diffs: [],
        artifacts: [],
      });

    render(<App />);
    await waitFor(() => expect(mockApi).toHaveBeenCalledTimes(4));
    fireEvent.click(screen.getByTitle("Runs"));
    fireEvent.click(await screen.findByText("sess-resume"));

    expect(await screen.findByText("Resume")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Resume"));

    await waitFor(() => {
      expect(mockApi).toHaveBeenCalledWith(
        "/coder/sessions/sess-resume/resume",
        expect.objectContaining({ method: "POST" }),
      );
      expect(mockApi).toHaveBeenCalledWith(
        "/coder/sessions/sess-resume/view",
        undefined,
      );
    });
  });

  it("opens onboarding for fresh config and no providers", async () => {
    mockApi
      .mockResolvedValueOnce({
        onboarding_complete: false,
        onboarding_dismissed: false,
        default_workspace: ".",
        theme: "dark",
      })
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce({ configured: false, profiles: [] })
      .mockResolvedValueOnce([]);

    render(<App />);

    expect(await screen.findByText("Welcome to Agentheim Code")).toBeInTheDocument();
    await waitFor(() => {
      expect(mockApi).toHaveBeenCalledWith("/onboarding/local-providers", undefined);
    });
  });

  it("skips onboarding by persisting dismissed state", async () => {
    mockApi
      .mockResolvedValueOnce({
        onboarding_complete: false,
        onboarding_dismissed: false,
        default_workspace: ".",
        theme: "dark",
      })
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce({ configured: false, profiles: [] })
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce({
        onboarding_complete: false,
        onboarding_dismissed: true,
        default_workspace: ".",
        theme: "dark",
      });

    render(<App />);

    fireEvent.click(await screen.findByText("Skip for now"));

    await waitFor(() => {
      expect(mockApi).toHaveBeenCalledWith(
        "/config",
        expect.objectContaining({
          method: "PATCH",
          body: JSON.stringify({ onboarding_dismissed: true }),
        }),
      );
      expect(screen.queryByText("Welcome to Agentheim Code")).not.toBeInTheDocument();
    });
  });

  it("applies configured theme to the document", async () => {
    mockApi
      .mockResolvedValueOnce({
        onboarding_complete: true,
        onboarding_dismissed: false,
        default_workspace: ".",
        theme: "high_contrast",
      })
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce({ configured: false, profiles: [] });

    render(<App />);

    await waitFor(() => {
      expect(document.documentElement.dataset.theme).toBe("high_contrast");
    });
  });

  it("does not show unsupported backend commands in the palette", async () => {
    mockApi
      .mockResolvedValueOnce({
        onboarding_complete: true,
        onboarding_dismissed: false,
        default_workspace: ".",
        theme: "dark",
      })
      .mockResolvedValueOnce([
        { id: "unsupported", label: "Unsupported", cli: "/unsupported", surface: "cli" },
      ])
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce({ configured: false, profiles: [] });

    render(<App />);
    await waitFor(() => expect(mockApi).toHaveBeenCalledTimes(4));

    fireEvent.keyDown(window, { ctrlKey: true, key: "k" });

    await waitFor(() => {
      expect(screen.queryByText("Open Settings")).toBeInTheDocument();
      expect(screen.queryByText("Unsupported")).not.toBeInTheDocument();
    });
  });

  it("supports opening runs from the command palette", async () => {
    mockApi
      .mockResolvedValueOnce({
        onboarding_complete: true,
        onboarding_dismissed: false,
        default_workspace: ".",
        theme: "dark",
      })
      .mockResolvedValueOnce([
        { id: "runs", label: "Open Runs", cli: "agentheim-code runs", surface: "drawer" },
      ])
      .mockResolvedValueOnce([
        { session_id: "sess-5", status: "idle", mode: "code", workspace_root: "." },
      ])
      .mockResolvedValueOnce({ configured: false, profiles: [] });

    render(<App />);
    await waitFor(() => expect(mockApi).toHaveBeenCalledTimes(4));

    fireEvent.keyDown(window, { ctrlKey: true, key: "k" });
    fireEvent.click((await screen.findAllByText("Open Runs"))[0]);

    expect(await screen.findByPlaceholderText("Filter sessions...")).toBeInTheDocument();
    expect(screen.getByText("sess-5")).toBeInTheDocument();
  });
});
