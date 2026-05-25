import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";

import { WorkspaceExplorer } from "../WorkspaceExplorer";

const mockApi = vi.fn();
vi.mock("../../api", () => ({
  api: <T,>(path: string, _init?: RequestInit): Promise<T> => mockApi(path) as Promise<T>,
  browseFiles: (query = "", offset = 0, limit = 100) =>
    mockApi(`/coder/files/browser?q=${query}&offset=${offset}&limit=${limit}`),
}));

describe("WorkspaceExplorer", () => {
  beforeEach(() => {
    mockApi.mockReset();
  });

  it("loads files in backend pages of 100 with a load-more button", async () => {
    const firstPage = Array.from({ length: 100 }, (_, i) => ({
      path: `file${i}.txt`,
      type: "file" as const,
    }));
    const secondPage = Array.from({ length: 100 }, (_, i) => ({
      path: `file${i + 100}.txt`,
      type: "file" as const,
    }));
    const finalPage = Array.from({ length: 50 }, (_, i) => ({
      path: `file${i + 200}.txt`,
      type: "file" as const,
    }));
    mockApi.mockImplementation((path: string) => {
      if (path.includes("offset=200")) {
        return Promise.resolve({
          items: finalPage,
          has_more: false,
          next_offset: null,
          query: "",
        });
      }
      if (path.includes("offset=100")) {
        return Promise.resolve({
          items: secondPage,
          has_more: true,
          next_offset: 200,
          query: "",
        });
      }
      return Promise.resolve({
        items: firstPage,
        has_more: true,
        next_offset: 100,
        query: "",
      });
    });

    render(<WorkspaceExplorer workspaceRoot="." changedFiles={[]} />);

    await waitFor(() => {
      const rows = screen.getAllByText(/file\d+\.txt/);
      expect(rows.length).toBe(100);
    });

    expect(screen.getByText("100 entries loaded")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Load next 100"));

    await waitFor(() => {
      const rows = screen.getAllByText(/file\d+\.txt/);
      expect(rows.length).toBe(200);
    });

    expect(screen.getByText("200 entries loaded")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Load next 100"));

    await waitFor(() => {
      const rows = screen.getAllByText(/file\d+\.txt/);
      expect(rows.length).toBe(250);
    });

    expect(screen.getByText("250 entries loaded")).toBeInTheDocument();
  }, 15000);

  it("switches to backend search when the query changes", async () => {
    mockApi.mockImplementation((path: string) => {
      if (path.includes("q=guide")) {
        return Promise.resolve({
          items: [
            {
              path: "docs/guide.md",
              type: "file" as const,
            },
          ],
          has_more: false,
          next_offset: null,
          query: "guide",
        });
      }
      return Promise.resolve({ items: [], has_more: false, next_offset: null, query: "" });
    });

    render(<WorkspaceExplorer workspaceRoot="." changedFiles={[]} />);

    const input = await screen.findByPlaceholderText("Search files...");
    fireEvent.change(input, { target: { value: "guide" } });

    await waitFor(() => {
      expect(screen.getByText("docs/guide.md")).toBeInTheDocument();
      expect(screen.getByText("1 matching entry loaded")).toBeInTheDocument();
    });
  });

  it("ignores stale file-browser responses when a newer search finishes later", async () => {
    let resolveInitial!: (value: {
      items: { path: string; type: "file" }[];
      has_more: boolean;
      next_offset: null;
      query: string;
    }) => void;
    const initialRequest = new Promise<{
      items: { path: string; type: "file" }[];
      has_more: boolean;
      next_offset: null;
      query: string;
    }>((resolve) => {
      resolveInitial = resolve;
    });

    mockApi.mockImplementation((path: string) => {
      if (path.includes("q=guide")) {
        return Promise.resolve({
          items: [{ path: "docs/guide.md", type: "file" as const }],
          has_more: false,
          next_offset: null,
          query: "guide",
        });
      }
      return initialRequest;
    });

    render(<WorkspaceExplorer workspaceRoot="." changedFiles={[]} />);

    const input = await screen.findByPlaceholderText("Search files...");
    fireEvent.change(input, { target: { value: "guide" } });

    await waitFor(() => {
      expect(screen.getByText("docs/guide.md")).toBeInTheDocument();
    });

    resolveInitial({
      items: [{ path: "stale.txt", type: "file" }],
      has_more: false,
      next_offset: null,
      query: "",
    });

    await waitFor(() => {
      expect(screen.queryByText("stale.txt")).not.toBeInTheDocument();
      expect(screen.getByText("docs/guide.md")).toBeInTheDocument();
    });
  });

  it("shows empty search state when no files match", async () => {
    mockApi.mockResolvedValue({
      items: [],
      has_more: false,
      next_offset: null,
      query: "",
    });

    render(<WorkspaceExplorer workspaceRoot="." changedFiles={[]} />);

    await waitFor(() => {
      expect(screen.getByText("No files found in this workspace yet.")).toBeInTheDocument();
    });
  });

  it("shows backend errors without crashing the panel", async () => {
    mockApi.mockRejectedValue(new Error("boom"));

    render(<WorkspaceExplorer workspaceRoot="." changedFiles={[]} />);

    await waitFor(() => {
      expect(screen.getByText("boom")).toBeInTheDocument();
    });
  });

  it("can preview files from the explorer", async () => {
    mockApi.mockImplementation((path: string) => {
      if (path.startsWith("/coder/files/preview")) {
        return Promise.resolve("preview text");
      }
      return Promise.resolve({
        items: [
          {
            path: "notes.txt",
            type: "file" as const,
          },
        ],
        has_more: false,
        next_offset: null,
        query: "",
      });
    });

    render(<WorkspaceExplorer workspaceRoot="." changedFiles={[]} />);

    await waitFor(() => {
      expect(screen.getByText("notes.txt")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByLabelText("Preview notes.txt"));

    await waitFor(() => {
      expect(screen.getByText("preview text")).toBeInTheDocument();
    });
  });
});
