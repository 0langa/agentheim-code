import React, { useEffect, useState } from "react";

import { api } from "../api";
import type { CoderCommand, Session, SessionView, ProviderProfile } from "../types";
import { SessionUsage } from "./SessionUsage";

interface InspectorProps {
  inspector: string;
  sessions: Session[];
  active: SessionView | null;
  commands: CoderCommand[];
  onSelectSession: (sessionId: string) => void;
  onOpenProviderWizard: () => void;
  onGrantApproval: (requestId: string) => void;
  onDenyApproval: (requestId: string) => void;
  theme: "dark" | "light" | "high_contrast";
  onThemeChange: (theme: "dark" | "light" | "high_contrast") => void;
}

function EmptyPanel({ message }: { message: string }) {
  return <p className="panel-empty">{message}</p>;
}

const TRUST_DESCRIPTIONS: Record<string, string> = {
  read_only: "Inspect files and state without writes.",
  ask: "Pause for risky tools before acting.",
  workspace: "Allow workspace edits under policy.",
};

export function Inspector({
  inspector,
  sessions,
  active,
  commands,
  onSelectSession,
  onOpenProviderWizard,
  onGrantApproval,
  onDenyApproval,
  theme,
  onThemeChange,
}: InspectorProps) {
  const title = inspector[0].toUpperCase() + inspector.slice(1);
  const [profiles, setProfiles] = useState<ProviderProfile[]>([]);
  const [profilesConfigured, setProfilesConfigured] = useState(false);

  useEffect(() => {
    if (inspector === "settings") {
      api<{ configured: boolean; profiles: ProviderProfile[] }>("/providers/profiles")
        .then((data) => {
          setProfilesConfigured(data.configured);
          setProfiles(data.profiles);
        })
        .catch(() => {
          setProfilesConfigured(false);
          setProfiles([]);
        });
    }
  }, [inspector]);

  return (
    <aside className="inspector" aria-label="Inspector">
      <header>
        <h2>{title}</h2>
      </header>

      {inspector === "timeline" && (
        <div className="panel-list" aria-live="polite">
          {!active && <EmptyPanel message="Start or resume a session to see activity." />}
          {active?.events?.length === 0 && <EmptyPanel message="No activity yet." />}
          {active?.events?.map((event, index) => (
            <article key={event.event_id ?? index} className="panel-item">
              <strong>{event.type ?? "event"}</strong>
              <span>{event.timestamp ?? "live"}</span>
              {event.message && <p>{event.message}</p>}
            </article>
          ))}
        </div>
      )}

      {inspector === "runs" && (
        <div className="panel-list">
          {sessions.length === 0 && <EmptyPanel message="No sessions yet." />}
          {sessions.map((session) => (
            <button
              key={session.session_id}
              type="button"
              onClick={() => onSelectSession(session.session_id)}
            >
              <strong>{session.session_id}</strong>
              <span>
                {session.status} · {session.mode}
              </span>
              <span>{session.workspace_root}</span>
            </button>
          ))}
          {active?.diffs?.map((diff, index) => (
            <article key={`${diff.path}-${index}`} className="panel-item">
              <strong>{diff.path ?? "changed file"}</strong>
              <span>{diff.status ?? "changed"}</span>
            </article>
          ))}
        </div>
      )}

      {inspector === "terminal" && (
        <div className="panel-list">
          {!active && <EmptyPanel message="No active session." />}
          {active?.command_results?.length === 0 && (
            <EmptyPanel message="No command output yet." />
          )}
          {active?.command_results?.map((result, index) => (
            <article key={index} className="panel-item terminal-item">
              <strong>{result.command?.join(" ") || "command"}</strong>
              <span>
                {result.status ?? "finished"} · exit{" "}
                {result.exit_code === null || result.exit_code === undefined
                  ? "-"
                  : result.exit_code}
              </span>
              {result.stdout && <pre>{result.stdout}</pre>}
              {result.stderr && <pre>{result.stderr}</pre>}
            </article>
          ))}
        </div>
      )}

      {inspector === "usage" && (
        <div className="panel-list">
          <SessionUsage sessionId={active?.session.session_id ?? null} />
        </div>
      )}

      {inspector === "approvals" && (
        <div className="panel-list">
          {!active?.approvals?.length && <EmptyPanel message="No pending approvals." />}
          {active?.approvals?.map((approval) => (
            <article key={approval.request_id} className="panel-item approval-item">
              <strong>{approval.tool_id}</strong>
              <span>
                {approval.action_kind ?? "tool"} · {approval.risk_level} · {approval.status}
              </span>
              <span>{approval.target ?? approval.request_id}</span>
              <p>{approval.reason}</p>
              {approval.action_kind === "shell" && Array.isArray(approval.params?.command) && (
                <pre>{approval.params.command.map(String).join(" ")}</pre>
              )}
              {approval.action_kind === "file" && (
                <pre>{String(approval.params?.content ?? approval.target ?? "")}</pre>
              )}
              <div className="approval-actions">
                <button
                  className="primary small"
                  onClick={() => onGrantApproval(approval.request_id)}
                  type="button"
                >
                  Grant
                </button>
                <button
                  className="secondary small"
                  onClick={() => onDenyApproval(approval.request_id)}
                  type="button"
                >
                  Deny
                </button>
              </div>
            </article>
          ))}
        </div>
      )}

      {inspector === "settings" && (
        <div className="panel-list">
          <article className="panel-item">
            <strong>Session</strong>
            <label className="settings-field">
              Theme
              <select
                aria-label="Theme"
                value={theme}
                onChange={(event) =>
                  onThemeChange(event.target.value as "dark" | "light" | "high_contrast")
                }
              >
                <option value="dark">Dark</option>
                <option value="light">Light</option>
                <option value="high_contrast">High contrast</option>
              </select>
            </label>
            <span>mode: {active?.session.mode ?? "code"}</span>
            <span>trust: {active?.session.trust_mode ?? "ask"}</span>
            <span>
              {TRUST_DESCRIPTIONS[active?.session.trust_mode ?? "ask"]}
            </span>
            <span>
              model:{" "}
              {active?.session.model_selection?.model ??
                active?.session.model_selection?.provider ??
                "auto"}
            </span>
            <span>provider: {active?.session.model_selection?.provider ?? "auto"}</span>
          </article>

          <article className="panel-item">
            <strong>AI Providers</strong>
            {!profilesConfigured && (
              <EmptyPanel message="No providers configured. Add one to get started." />
            )}
            {profiles.map((profile) => (
              <div key={profile.name} className="provider-row">
                <span>
                  <strong>{profile.name}</strong>
                  {profile.default && <span className="badge">default</span>}
                </span>
                <span>
                  {profile.providers.map((p) => p.kind).join(", ")}
                </span>
                <span>
                  {profile.models.map((m) => m.model).join(", ")}
                </span>
              </div>
            ))}
            <button
              onClick={onOpenProviderWizard}
              style={{ marginTop: 8 }}
              className="primary small"
              type="button"
            >
              + Add Provider
            </button>
          </article>

          <article className="panel-item">
            <strong>Commands</strong>
            {commands.map((command) => (
              <span key={command.id}>
                {command.label} · {command.cli}
              </span>
            ))}
          </article>
        </div>
      )}
    </aside>
  );
}
