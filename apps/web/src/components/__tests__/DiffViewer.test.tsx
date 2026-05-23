import { describe, expect, it } from "vitest";

import { computeDiffLines } from "../DiffViewer";

function makeLines(prefix: string, count: number): string {
  return Array.from({ length: count }, (_, index) => `${prefix} ${index}`).join("\n");
}

describe("computeDiffLines", () => {
  it("falls back to a bounded diff for very large inputs", () => {
    const lines = computeDiffLines(makeLines("before", 250), makeLines("after", 250));

    expect(lines.length).toBeLessThan(500);
    expect(
      lines.some(
        (line) =>
          line.type === "same" &&
          ((line.a ?? "").includes("lines omitted") || (line.b ?? "").includes("lines omitted")),
      ),
    ).toBe(true);
  });
});
