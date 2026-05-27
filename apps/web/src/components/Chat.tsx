import React, { useEffect, useRef } from "react";
import rehypeHighlight from "rehype-highlight";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

import type { SessionView, TranscriptEntry } from "../types";

interface ChatProps {
  active: SessionView | null;
  onOpenApprovals?: () => void;
}

function summarizeRunEffects(active: SessionView): string | null {
  const changedFiles = active.session.changed_files ?? [];
  const artifacts = active.artifacts ?? [];
  const commandResults = active.command_results ?? [];
  const parts: string[] = [];

  if (changedFiles.length) {
    parts.push(
      `Changed files: ${changedFiles.slice(0, 3).join(", ")}${changedFiles.length > 3 ? ` +${changedFiles.length - 3} more` : ""}.`,
    );
  }
  if (artifacts.length) {
    parts.push(
      `Artifacts: ${artifacts.slice(0, 3).join(", ")}${artifacts.length > 3 ? ` +${artifacts.length - 3} more` : ""}.`,
    );
  }
  if (commandResults.length) {
    const latest = commandResults[commandResults.length - 1];
    if (latest?.command) {
      parts.push(`Latest command: ${latest.command}.`);
    }
  }

  return parts.length ? parts.join(" ") : null;
}

function textFromNode(node: React.ReactNode): string {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(textFromNode).join("");
  if (React.isValidElement<{ children?: React.ReactNode }>(node)) {
    return textFromNode(node.props.children);
  }
  return "";
}

const markdownComponents: Components = {
  pre({ children }) {
    return <>{children}</>;
  },
  code({ children, className, ...props }) {
    const content = textFromNode(children).replace(/\n$/, "");
    if (!className?.includes("language-")) {
      return (
        <code className={className} {...props}>
          {children}
        </code>
      );
    }
    return (
      <div className="code-block">
        <div className="code-block-header">
          <span>{className.replace("hljs", "").replace("language-", "").trim()}</span>
          <button
            type="button"
            aria-label="Copy code block"
            onClick={() => navigator.clipboard?.writeText(content)}
          >
            Copy
          </button>
        </div>
        <pre>
          <code className={className} {...props}>
            {content}
          </code>
        </pre>
      </div>
    );
  },
};

function MarkdownMessage({ content }: { content: string }) {
  return (
    <div className="markdown-message">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeHighlight]}
        components={markdownComponents}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

function MessageBubble({ entry }: { entry: TranscriptEntry }) {
  const isUser = entry.role === "user";
  return (
    <div
      className="message"
      style={{
        alignSelf: isUser ? "flex-end" : "flex-start",
        borderColor: isUser
          ? "color-mix(in srgb, var(--accent) 34%, transparent)"
          : "color-mix(in srgb, var(--ai) 34%, transparent)",
        maxWidth: "720px",
        width: "100%",
      }}
    >
      <strong
        style={{
          fontSize: "12px",
          textTransform: "uppercase",
          color: isUser ? "var(--accent)" : "var(--ai)",
        }}
      >
        {entry.role}
      </strong>
      <MarkdownMessage content={entry.content} />
      {entry.timestamp && (
        <span style={{ fontSize: "11px", color: "var(--muted)" }}>
          {entry.timestamp}
        </span>
      )}
    </div>
  );
}

export function Chat({ active, onOpenApprovals }: ChatProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const lastSummaryKeyRef = useRef<string | null>(null);
  const liveMessage = !active
    ? "No active session."
    : active.session.status === "running"
      ? "Assistant is responding."
      : "Conversation ready.";

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [
    active?.session?.transcript,
    active?.session?.current_assistant_message,
  ]);

  const runEffectsSummary = active ? summarizeRunEffects(active) : null;
  const runEffectsKey = active
    ? JSON.stringify({
        sessionId: active.session.session_id,
        changedFiles: active.session.changed_files ?? [],
        artifacts: active.artifacts ?? [],
        commandCount: active.command_results?.length ?? 0,
      })
    : null;

  useEffect(() => {
    if (!runEffectsKey || !runEffectsSummary || active?.session.status === "running") {
      return;
    }
    if (lastSummaryKeyRef.current === runEffectsKey) {
      return;
    }
    lastSummaryKeyRef.current = runEffectsKey;
  }, [runEffectsKey, runEffectsSummary, active?.session.status]);

  if (!active) {
    return (
      <section
        className="chat"
        aria-label="Conversation transcript"
        role="log"
        aria-live="polite"
        aria-relevant="additions text"
      >
        <p className="sr-only" aria-live="polite">
          {liveMessage}
        </p>
        <div className="empty">
          <strong>Start a focused coding session</strong>
          <span>Use the composer, command palette, or session rail.</span>
        </div>
      </section>
    );
  }

  const entries = active.session.transcript ?? [];
  const pendingAssistantMessage = active.session.pending_assistant_message;
  const showApprovalReply =
    active.session.status === "awaiting_approval" &&
    Boolean(pendingAssistantMessage) &&
    active.approvals?.length;

  return (
    <section
      className="chat"
      aria-label="Conversation transcript"
      role="log"
      aria-live="polite"
      aria-relevant="additions text"
      aria-busy={active.session.status === "running"}
      style={{ display: "flex", flexDirection: "column", gap: "12px" }}
    >
      <p className="sr-only" aria-live="polite">
        {liveMessage}
      </p>
      {entries.length === 0 && (
        <div className="empty">
          <strong>No messages yet</strong>
          <span>Type a prompt below to start the conversation.</span>
        </div>
      )}
      {entries.map((entry, idx) => (
        <MessageBubble key={idx} entry={entry} />
      ))}
      {active.session.status === "running" &&
        active.session.current_assistant_message &&
        !showApprovalReply && (
        <div
          className="message"
          style={{
            alignSelf: "flex-start",
            borderColor:
              "color-mix(in srgb, var(--ai) 34%, transparent)",
            opacity: 0.8,
          }}
        >
          <strong
            style={{
              fontSize: "12px",
              textTransform: "uppercase",
              color: "var(--ai)",
            }}
          >
            assistant
          </strong>
          <MarkdownMessage content={active.session.current_assistant_message} />
        </div>
      )}
      {showApprovalReply && (
        <div
          className="message"
          style={{
            alignSelf: "flex-start",
            borderColor: "color-mix(in srgb, var(--warning) 34%, transparent)",
            background: "color-mix(in srgb, var(--warning) 9%, transparent)",
          }}
        >
          <strong
            style={{
              fontSize: "12px",
              textTransform: "uppercase",
              color: "var(--warning)",
            }}
          >
            assistant
          </strong>
          <MarkdownMessage content={pendingAssistantMessage ?? ""} />
          <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
            <button className="secondary small" onClick={onOpenApprovals} type="button">
              Open approvals
            </button>
            <span style={{ fontSize: "12px", color: "var(--muted)" }}>
              This turn is paused until you approve or deny the requested action.
            </span>
          </div>
        </div>
      )}
      {runEffectsSummary && active.session.status !== "running" && (
        <div
          className="message"
          style={{
            alignSelf: "flex-start",
            borderColor: "color-mix(in srgb, var(--warning) 34%, transparent)",
            background: "color-mix(in srgb, var(--warning) 8%, transparent)",
          }}
        >
          <strong
            style={{
              fontSize: "12px",
              textTransform: "uppercase",
              color: "var(--warning)",
            }}
          >
            session effects
          </strong>
          <div style={{ fontSize: "13px", lineHeight: 1.5 }}>{runEffectsSummary}</div>
        </div>
      )}
      <div ref={bottomRef} />
    </section>
  );
}
