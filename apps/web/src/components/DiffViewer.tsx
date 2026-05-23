import React, { useState } from "react";
import { Copy, ChevronDown, ChevronUp } from "lucide-react";
import type { SessionDiff } from "../types";

export type DiffLine = {
  type: "same" | "add" | "rem";
  a?: string;
  b?: string;
  oldLine?: number;
  newLine?: number;
};

export type DiffResult =
  | { kind: "diff"; lines: DiffLine[]; truncated: boolean }
  | { kind: "sidebyside"; before: string[]; after: string[] };

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

type ChunkedItem =
  | { kind: "line"; line: DiffLine }
  | { kind: "collapse"; count: number; lines: DiffLine[]; chunkIndex: number };

let globalChunkIndex = 0;

function chunkDiffLines(lines: DiffLine[]): ChunkedItem[] {
  const result: ChunkedItem[] = [];
  let i = 0;
  globalChunkIndex = 0;
  while (i < lines.length) {
    if (lines[i].type === "same") {
      let start = i;
      while (i < lines.length && lines[i].type === "same") i++;
      const runLength = i - start;
      if (runLength <= 3) {
        for (let k = start; k < i; k++) {
          result.push({ kind: "line", line: lines[k] });
        }
      } else {
        for (let k = start; k < start + 3; k++) {
          result.push({ kind: "line", line: lines[k] });
        }
        result.push({
          kind: "collapse",
          count: runLength - 3,
          lines: lines.slice(start + 3, i),
          chunkIndex: globalChunkIndex++,
        });
      }
    } else {
      result.push({ kind: "line", line: lines[i] });
      i++;
    }
  }
  return result;
}

export function computeDiffLines(before: string, after: string): DiffResult {
  const a = splitLines(before);
  const b = splitLines(after);
  if (a.length * b.length > MAX_DIFF_MATRIX_CELLS) {
    return { kind: "sidebyside", before: a, after: b };
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
  let i = 0,
    j = 0,
    oldLine = 1,
    newLine = 1;
  while (i < a.length || j < b.length) {
    if (i < a.length && j < b.length && a[i] === b[j]) {
      lines.push({ type: "same", a: a[i], b: b[j], oldLine, newLine });
      oldLine++;
      newLine++;
      i++;
      j++;
    } else if (j >= b.length || (i < a.length && dp[i + 1][j] >= dp[i][j + 1])) {
      lines.push({ type: "rem", a: a[i], oldLine });
      oldLine++;
      i++;
    } else {
      lines.push({ type: "add", b: b[j], newLine });
      newLine++;
      j++;
    }
  }
  return { kind: "diff", lines, truncated: lines.length > MAX_RENDERED_LINES };
}

export function DiffViewer({ diff }: { diff: SessionDiff }) {
  const [expanded, setExpanded] = useState(true);
  const [showFull, setShowFull] = useState(false);
  const [expandedChunks, setExpandedChunks] = useState<Set<number>>(new Set());

  const result = computeDiffLines(diff.before || "", diff.after || "");

  const toggleChunk = (index: number) => {
    setExpandedChunks((prev) => {
      const next = new Set(prev);
      if (next.has(index)) {
        next.delete(index);
      } else {
        next.add(index);
      }
      return next;
    });
  };

  const copyPatch = () => {
    if (result.kind === "sidebyside") {
      const patch = `--- before\n+++ after\n\n${result.before.join("\n")}\n\n${result.after.join("\n")}`;
      navigator.clipboard.writeText(patch).catch(() => {});
      return;
    }
    const source =
      result.truncated && !showFull ? clampDiffLines(result.lines) : result.lines;
    const patch = source
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
        <>
          {result.kind === "sidebyside" ? (
            <div
              className="diff-lines"
              style={{
                display: "flex",
                gap: 8,
                fontFamily: "monospace",
                fontSize: "12px",
                overflow: "auto",
              }}
            >
              <div style={{ flex: 1, overflow: "auto" }}>
                <div style={{ fontWeight: "bold", marginBottom: 4 }}>Before</div>
                <pre style={{ margin: 0 }}>
                  {result.before.map((l, idx) => `${idx + 1} | ${l}`).join("\n")}
                </pre>
              </div>
              <div style={{ flex: 1, overflow: "auto" }}>
                <div style={{ fontWeight: "bold", marginBottom: 4 }}>After</div>
                <pre style={{ margin: 0 }}>
                  {result.after.map((l, idx) => `${idx + 1} | ${l}`).join("\n")}
                </pre>
              </div>
            </div>
          ) : (
            <>
              {result.truncated && !showFull && (
                <button
                  type="button"
                  onClick={() => setShowFull(true)}
                  style={{
                    fontSize: "11px",
                    marginBottom: 4,
                    padding: "4px 8px",
                  }}
                >
                  Show full diff
                </button>
              )}
              <div
                className="diff-lines"
                style={{ fontFamily: "monospace", fontSize: "12px", overflow: "auto" }}
              >
                {chunkDiffLines(
                  result.truncated && !showFull ? clampDiffLines(result.lines) : result.lines,
                ).map((item, idx) => {
                  if (item.kind === "collapse") {
                    if (expandedChunks.has(item.chunkIndex)) {
                      return item.lines.map((line, j) => (
                        <div
                          key={`${idx}-${j}`}
                          style={{
                            display: "flex",
                            gap: 8,
                            padding: "1px 4px",
                          }}
                        >
                          <span style={{ width: 16, flexShrink: 0, userSelect: "none" }}> </span>
                          <span
                            style={{
                              width: 40,
                              flexShrink: 0,
                              textAlign: "right",
                              color: "var(--muted)",
                              userSelect: "none",
                            }}
                          >
                            {line.oldLine ?? ""}
                          </span>
                          <span
                            style={{
                              width: 40,
                              flexShrink: 0,
                              textAlign: "right",
                              color: "var(--muted)",
                              marginLeft: 4,
                              userSelect: "none",
                            }}
                          >
                            {line.newLine ?? ""}
                          </span>
                          <span style={{ whiteSpace: "pre" }}>{line.a}</span>
                        </div>
                      ));
                    }
                    return (
                      <div
                        key={idx}
                        onClick={() => toggleChunk(item.chunkIndex)}
                        style={{
                          display: "flex",
                          gap: 8,
                          padding: "1px 4px",
                          cursor: "pointer",
                          color: "var(--muted)",
                        }}
                      >
                        <span style={{ width: 16, flexShrink: 0, userSelect: "none" }}> </span>
                        <span style={{ width: 40, flexShrink: 0 }} />
                        <span style={{ width: 40, flexShrink: 0, marginLeft: 4 }} />
                        <span style={{ whiteSpace: "pre" }}>
                          ... {item.count} unchanged lines ...
                        </span>
                      </div>
                    );
                  }

                  const line = item.line;
                  return (
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
                      <span
                        style={{
                          width: 40,
                          flexShrink: 0,
                          textAlign: "right",
                          color: "var(--muted)",
                          userSelect: "none",
                        }}
                      >
                        {line.type === "add" ? "" : line.oldLine ?? ""}
                      </span>
                      <span
                        style={{
                          width: 40,
                          flexShrink: 0,
                          textAlign: "right",
                          color: "var(--muted)",
                          marginLeft: 4,
                          userSelect: "none",
                        }}
                      >
                        {line.type === "rem" ? "" : line.newLine ?? ""}
                      </span>
                      <span style={{ whiteSpace: "pre" }}>
                        {line.type === "add" ? line.b : line.a}
                      </span>
                    </div>
                  );
                })}
              </div>
            </>
          )}
        </>
      )}
    </article>
  );
}
