import React, { useEffect, useRef } from "react";

import type { SessionView, TranscriptEntry } from "../types";

interface ChatProps {
  active: SessionView | null;
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
      <strong style={{ fontSize: "12px", textTransform: "uppercase", color: isUser ? "var(--accent)" : "var(--ai)" }}>
        {entry.role}
      </strong>
      <p style={{ margin: "0.5rem 0 0", whiteSpace: "pre-wrap" }}>{entry.content}</p>
      {entry.timestamp && (
        <span style={{ fontSize: "11px", color: "var(--muted)" }}>{entry.timestamp}</span>
      )}
    </div>
  );
}

export function Chat({ active }: ChatProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [active?.transcript, active?.current_assistant_message]);

  if (!active) {
    return (
      <section className="chat" aria-live="polite">
        <div className="empty">
          <strong>Start a focused coding session</strong>
          <span>Use the composer, command palette, or session rail.</span>
        </div>
      </section>
    );
  }

  const entries = active.transcript ?? [];

  return (
    <section
      className="chat"
      aria-live="polite"
      style={{ display: "flex", flexDirection: "column", gap: "12px" }}
    >
      {entries.length === 0 && (
        <div className="empty">
          <strong>No messages yet</strong>
          <span>Type a prompt below to start the conversation.</span>
        </div>
      )}
      {entries.map((entry, idx) => (
        <MessageBubble key={idx} entry={entry} />
      ))}
      {active.current_assistant_message && (
        <div
          className="message"
          style={{
            alignSelf: "flex-start",
            borderColor: "color-mix(in srgb, var(--ai) 34%, transparent)",
            opacity: 0.8,
          }}
        >
          <strong style={{ fontSize: "12px", textTransform: "uppercase", color: "var(--ai)" }}>
            assistant
          </strong>
          <p style={{ margin: "0.5rem 0 0", whiteSpace: "pre-wrap" }}>
            {active.current_assistant_message}
          </p>
        </div>
      )}
      <div ref={bottomRef} />
    </section>
  );
}
