import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";

import { WorkspaceExplorer } from "../WorkspaceExplorer";

const mockApi = vi.fn();
vi.mock("../../api", () => ({
  api: <T,>(path: string, _init?: RequestInit): Promise<T> => mockApi(path) as Promise<T>,
}));

describe("WorkspaceExplorer", () => {
  it("shows files in batches of 100 with a load-more button", async () => {
    const manyFiles = Array.from({ length: 250 }, (_, i) => ({
      path: `file${i}.txt`,
      type: "file" as const,
    }));
    mockApi.mockResolvedValueOnce(manyFiles);

    render(<WorkspaceExplorer workspaceRoot="." changedFiles={[]} />);

    await waitFor(() => {
      const rows = screen.getAllByText(/file\d+\.txt/);
      expect(rows.length).toBe(100);
    });

    expect(screen.getByText("Showing 100 of 250 files")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Load more"));

    await waitFor(() => {
      const rows = screen.getAllByText(/file\d+\.txt/);
      expect(rows.length).toBe(200);
    });

    expect(screen.getByText("Showing 200 of 250 files")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Load more"));

    await waitFor(() => {
      const rows = screen.getAllByText(/file\d+\.txt/);
      expect(rows.length).toBe(250);
    });

    expect(screen.getByText("250 files total")).toBeInTheDocument();
  });

  it("shows truncation message when backend caps at 500 files", async () => {
    const manyFiles = Array.from({ length: 500 }, (_, i) => ({
      path: `file${i}.txt`,
      type: "file" as const,
    }));
    mockApi.mockResolvedValueOnce(manyFiles);

    render(<WorkspaceExplorer workspaceRoot="." changedFiles={[]} />);

    await waitFor(() => {
      expect(screen.getByText(/Large workspace/)).toBeInTheDocument();
    });
  });
});
