import { describe, expect, it } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import { DiffViewer, computeDiffLines } from "../DiffViewer";
import type { SessionDiff } from "../../types";

function makeLines(prefix: string, count: number): string {
  return Array.from({ length: count }, (_, index) => `${prefix} ${index}`).join("\n");
}

function makeDiff(overrides: Partial<SessionDiff> = {}): SessionDiff {
  return {
    path: "test.txt",
    status: "modified",
    before: "",
    after: "",
    timestamp: "2026-05-25T12:00:00Z",
    ...overrides,
  };
}

describe("computeDiffLines", () => {
  it("falls back to side-by-side for very large inputs", () => {
    const result = computeDiffLines(makeLines("before", 250), makeLines("after", 250));

    expect(result.kind).toBe("sidebyside");
  });

  it("includes line numbers in diff output", () => {
    const result = computeDiffLines("a\nb\nc", "a\nx\nc");

    expect(result.kind).toBe("diff");
    if (result.kind !== "diff") return;

    const sameLines = result.lines.filter((l) => l.type === "same");
    expect(sameLines[0].oldLine).toBe(1);
    expect(sameLines[0].newLine).toBe(1);
    expect(sameLines[1].oldLine).toBe(3);
    expect(sameLines[1].newLine).toBe(3);

    const rem = result.lines.find((l) => l.type === "rem");
    expect(rem?.oldLine).toBe(2);

    const add = result.lines.find((l) => l.type === "add");
    expect(add?.newLine).toBe(2);
  });
});

describe("DiffViewer", () => {
  it("collapses large runs of unchanged lines", () => {
    const before = Array.from({ length: 20 }, (_, i) => `line ${i}`).join("\n");
    const after = Array.from({ length: 20 }, (_, i) => `line ${i}`).join("\n");
    const diff = makeDiff({ before, after });

    render(<DiffViewer diff={diff} />);

    expect(screen.getByText(/unchanged lines/)).toBeInTheDocument();
  });

  it("renders line numbers", () => {
    const diff = makeDiff({ before: "a\nb", after: "a\nc" });

    render(<DiffViewer diff={diff} />);

    expect(screen.getAllByText("1").length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText("2").length).toBeGreaterThanOrEqual(2);
  });

  it("shows a side-by-side view for very large diffs", () => {
    const diff = makeDiff({
      before: makeLines("before", 250),
      after: makeLines("after", 250),
    });

    render(<DiffViewer diff={diff} />);

    expect(screen.getByText("Before")).toBeInTheDocument();
    expect(screen.getByText("After")).toBeInTheDocument();
  });

  it("shows a 'Show full diff' button when diff is truncated", () => {
    const before = Array.from({ length: 250 }, (_, i) => `line ${i}`).join("\n");
    const after = Array.from({ length: 80 }, (_, i) => `line ${i}`).join("\n");
    const diff = makeDiff({ before, after });

    render(<DiffViewer diff={diff} />);

    expect(screen.getByText("Show full diff")).toBeInTheDocument();
  });

  it("expands collapsed unchanged lines on click", () => {
    const before = Array.from({ length: 20 }, (_, i) => `line ${i}`).join("\n");
    const after = Array.from({ length: 20 }, (_, i) => `line ${i}`).join("\n");
    const diff = makeDiff({ before, after });

    render(<DiffViewer diff={diff} />);

    const collapseLine = screen.getByText(/unchanged lines/);
    fireEvent.click(collapseLine);

    // After expanding, one of the previously hidden lines should be visible
    expect(screen.getByText("line 3")).toBeInTheDocument();
  });
});
