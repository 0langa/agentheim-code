import React, { useState } from "react";
import { Copy, ChevronDown, ChevronUp } from "lucide-react";
import type { SessionDiff } from "../types";

export type DiffLine = { type: "same" | "add" | "rem"; a?: string; b?: string };

const MAX_DIFF_MATRIX_CELLS = 20_000;
const MAX_RENDERED_LINES = 241;

function splitLines(text: string): string[] {
  return text ? text.split("\n") : [];
}

function truncatedMarker(omittedLines: number): DiffLine {
  const message = `... ${omittedLines} lines omitted for performance ...`;
  return { type: "same", a: message, b: message };
}

function clampDiffLines(lines: DiffLine[]): DiffLine[] {
  if (lines.length <= MAX_RENDERED_LINES) {
    return lines;
  }

  const headCount = 120;
  const tailCount = 120;
  const omittedCount = lines.length - headCount - tailCount;
  return [
    ...lines.slice(0, headCount),
    truncatedMarker(omittedCount),
    ...lines.slice(-tailCount),
  ];
}

function buildFallbackDiffLines(beforeLines: string[], afterLines: string[]): DiffLine[] {
  return clampDiffLines([
    ...beforeLines.map((line) => ({ type: "rem", a: line }) satisfies DiffLine),
    ...afterLines.map((line) => ({ type: "add", b: line }) satisfies DiffLine),
  ]);
}

export function computeDiffLines(before: string, after: string): DiffLine[] {
  const a = splitLines(before);
  const b = splitLines(after);
  if (a.length * b.length > MAX_DIFF_MATRIX_CELLS) {
    return buildFallbackDiffLines(a, b);
  }
  const dp: number[][] = Array(a.length + 1)
    .fill(null)
    .map(() => Array(b.length + 1).fill(0));
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      if (a[i] === b[j]) {
        dp[i][j] = 1 + dp[i + 1][j + 1];
      } else {
        dp[i][j] = Math.max(dp[i + 1][j], dp[i][j + 1]);
      }
    }
  }
  const lines: DiffLine[] = [];
  let i = 0, j = 0;
  while (i < a.length || j < b.length) {
    if (i < a.length && j < b.length && a[i] === b[j]) {
      lines.push({ type: "same", a: a[i], b: b[j] });
      i++;
      j++;
    } else if (j >= b.length || (i < a.length && dp[i + 1][j] >= dp[i][j + 1])) {
      lines.push({ type: "rem", a: a[i] });
      i++;
    } else {
      lines.push({ type: "add", b: b[j] });
      j++;
    }
  }
  return clampDiffLines(lines);
}

export function DiffViewer({ diff }: { diff: SessionDiff }) {
  const [expanded, setExpanded] = useState(true);
  const lines = computeDiffLines(diff.before || "", diff.after || "");

  const copyPatch = () => {
    const patch = lines
      .map((l) => {
        if (l.type === "same") return " " + (l.a ?? "");
        if (l.type === "add") return "+" + (l.b ?? "");
        return "-" + (l.a ?? "");
      })
      .join("\n");
    navigator.clipboard.writeText(patch).catch(() => {});
  };

  return (
    <article className="panel-item diff-item">
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
        <strong>{diff.path ?? "changed file"}</strong>
        <span className="badge">{diff.status ?? "changed"}</span>
        <button
          type="button"
          aria-label={expanded ? "Collapse diff" : "Expand diff"}
          onClick={() => setExpanded((v) => !v)}
          style={{ marginLeft: "auto" }}
        >
          {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </button>
        <button type="button" aria-label="Copy diff" onClick={copyPatch}>
          <Copy size={14} />
        </button>
      </div>
      {expanded && (
        <div className="diff-lines" style={{ fontFamily: "monospace", fontSize: "12px", overflow: "auto" }}>
          {lines.map((line, idx) => (
            <div
              key={idx}
              style={{
                display: "flex",
                gap: 8,
                padding: "1px 4px",
                background:
                  line.type === "add"
                    ? "color-mix(in srgb, var(--success) 15%, transparent)"
                    : line.type === "rem"
                    ? "color-mix(in srgb, var(--error) 15%, transparent)"
                    : "transparent",
              }}
            >
              <span style={{ width: 16, flexShrink: 0, userSelect: "none" }}>
                {line.type === "add" ? "+" : line.type === "rem" ? "-" : " "}
              </span>
              <span style={{ whiteSpace: "pre" }}>{line.type === "add" ? line.b : line.a}</span>
            </div>
          ))}
        </div>
      )}
    </article>
  );
}
