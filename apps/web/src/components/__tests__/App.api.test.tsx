import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import React from "react";

import { App } from "../../App";

const mockApi = vi.fn();
const mockStreamSessionMessage = vi.fn();
vi.mock("../../api", () => ({
  api: <T,>(path: string, init?: RequestInit): Promise<T> => mockApi(path, init) as Promise<T>,
  streamSessionMessage: (...args: unknown[]) => mockStreamSessionMessage(...args),
  ApiError: class ApiError extends Error {
    constructor(public status: number, message: string) {
      super(message);
    }
  },
}));

describe("App API integration", () => {
  beforeEach(() => {
    mockApi.mockReset();
    mockStreamSessionMessage.mockReset();
  });

  it("creates session without workspace_root and then fetches /view", async () => {
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
      expect(body).not.toHaveProperty("workspace_root");
      expect(body).toEqual({ trust_mode: "ask", mode: "code" });
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
        workspace_root: ".",
      })
      .mockResolvedValueOnce({
        session: {
          session_id: "sess-auto",
          status: "idle",
          mode: "code",
          trust_mode: "ask",
          workspace_root: ".",
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
          workspace_root: ".",
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
        expect.objectContaining({ method: "POST" }),
      );
      expect(mockStreamSessionMessage).toHaveBeenCalledWith(
        "sess-auto",
        "hello",
        expect.objectContaining({ onToken: expect.any(Function) }),
        expect.any(AbortSignal),
        [],
        ".",
      );
    });
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
        trust_mode: "workspace",
        mode: "code",
      });
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
