import React, { useState } from "react";
import { Copy, ChevronDown, ChevronUp } from "lucide-react";
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

export function TerminalPanel({ results }: { results: CommandResult[] }) {
  return (
    <div className="panel-list">
      {results.length === 0 && (
        <p className="panel-empty">No command output yet.</p>
      )}
      {results.map((result, index) => (
        <TerminalItem key={index} result={result} />
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
        <button
          type="button"
          aria-label={expanded ? "Collapse" : "Expand"}
          onClick={() => setExpanded((v) => !v)}
          style={{ marginLeft: "auto" }}
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
              <pre style={{ maxHeight: 240, overflow: "auto" }}>{result.stdout}</pre>
            </div>
          )}
          {result.stderr && (
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: "11px", color: "var(--muted)" }}>stderr</span>
                <CopyButton text={result.stderr} />
              </div>
              <pre style={{ maxHeight: 240, overflow: "auto", color: "var(--error)" }}>{result.stderr}</pre>
            </div>
          )}
        </div>
      )}
    </article>
  );
}
