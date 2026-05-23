import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { TerminalPanel } from "../TerminalPanel";

describe("TerminalPanel", () => {
  it("renders terminal output without raw ansi escapes", () => {
    render(
      <TerminalPanel
        results={[
          {
            command: ["pytest"],
            stdout: "\u001b[31mFAIL\u001b[0m",
            stderr: "",
            exit_code: 1,
          },
        ]}
      />,
    );
    expect(screen.getByText("FAIL")).toBeInTheDocument();
    expect(screen.queryByText("\u001b[31mFAIL\u001b[0m")).not.toBeInTheDocument();
  });
});
