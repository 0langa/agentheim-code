import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

import { WorkspaceExplorer } from "../WorkspaceExplorer";

const mockApi = vi.fn();
vi.mock("../../api", () => ({
  api: <T,>(path: string, _init?: RequestInit): Promise<T> => mockApi(path) as Promise<T>,
}));

describe("WorkspaceExplorer", () => {
  it("caps displayed files at 500 for large workspaces", async () => {
    const manyFiles = Array.from({ length: 1000 }, (_, i) => ({
      path: `file${i}.txt`,
      type: "file" as const,
    }));
    mockApi.mockResolvedValueOnce(manyFiles);

    render(<WorkspaceExplorer workspaceRoot="." changedFiles={[]} />);

    await waitFor(() => {
      const rows = screen.getAllByText(/file\d+\.txt/);
      expect(rows.length).toBe(500);
    });
  });
});
