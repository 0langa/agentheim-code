import React, { useState } from "react";
import { Copy, ChevronDown, ChevronUp } from "lucide-react";
import { stripAnsi } from "../utils/ansi";
import { formatRelativeTime } from "../utils/time";
import type { CommandResult } from "../types";

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={() => {
        navigator.clipboard.writeText(text).catch(() => {});
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      }}
      style={{ fontSize: "11px" }}
    >
      {copied ? "Copied" : <Copy size={12} />}
    </button>
  );
}

function shouldInsertSeparator(prev: CommandResult, curr: CommandResult): boolean {
  if (prev.exit_code !== 0 || curr.exit_code !== 0) return false;
  const prevTime = prev.timestamp ? new Date(prev.timestamp).getTime() : 0;
  const currTime = curr.timestamp ? new Date(curr.timestamp).getTime() : 0;
  if (!prevTime || !currTime) return false;
  return currTime - prevTime > 5000;
}

export function TerminalPanel({ results }: { results: CommandResult[] }) {
  const allText = results
    .map((r) => {
      const parts: string[] = [];
      if (r.stdout) parts.push(r.stdout);
      if (r.stderr) parts.push(r.stderr);
      return parts.join("\n");
    })
    .filter(Boolean)
    .join("\n\n");

  return (
    <div className="panel-list">
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "8px 12px",
          borderBottom: "1px solid var(--border)",
        }}
      >
        <span style={{ fontSize: "12px", fontWeight: 600 }}>
          {results.length} {results.length === 1 ? "command" : "commands"}
        </span>
        {allText && <CopyButton text={allText} />}
      </div>
      {results.length === 0 && <p className="panel-empty">No command output yet.</p>}
      {results.map((result, index) => (
        <React.Fragment key={index}>
          {index > 0 && shouldInsertSeparator(results[index - 1], result) && (
            <hr
              style={{
                border: 0,
                borderTop: "1px solid var(--border)",
                margin: "4px 12px",
              }}
            />
          )}
          <TerminalItem result={result} />
        </React.Fragment>
      ))}
    </div>
  );
}

function TerminalItem({ result }: { result: CommandResult }) {
  const [expanded, setExpanded] = useState(true);
  const command = result.command?.join(" ") || "command";
  const ok = result.exit_code === 0 || result.exit_code === null;

  return (
    <article className="panel-item terminal-item">
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
        <span
          className="badge"
          style={{
            background: ok
              ? "color-mix(in srgb, var(--success) 25%, transparent)"
              : "color-mix(in srgb, var(--error) 25%, transparent)",
          }}
        >
          {ok ? "OK" : `Exit ${result.exit_code}`}
        </span>
        <code style={{ fontSize: "12px" }}>{command}</code>
        {result.timestamp && (
          <span style={{ marginLeft: "auto", fontSize: "11px", color: "var(--muted)" }}>
            {formatRelativeTime(result.timestamp)}
          </span>
        )}
        <button
          type="button"
          aria-label={expanded ? "Collapse" : "Expand"}
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </button>
        <CopyButton text={command} />
      </div>
      {expanded && (
        <div style={{ display: "grid", gap: 4 }}>
          {result.stdout && (
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: "11px", color: "var(--muted)" }}>stdout</span>
                <CopyButton text={result.stdout} />
              </div>
              <pre style={{ maxHeight: 240, overflow: "auto" }}>{stripAnsi(result.stdout)}</pre>
            </div>
          )}
          {result.stderr && (
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: "11px", color: "var(--muted)" }}>stderr</span>
                <CopyButton text={result.stderr} />
              </div>
              <pre style={{ maxHeight: 240, overflow: "auto", color: "var(--error)" }}>
                {stripAnsi(result.stderr)}
              </pre>
            </div>
          )}
        </div>
      )}
    </article>
  );
}
