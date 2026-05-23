import React, { useEffect, useState } from "react";

import { api } from "../api";
import type { CoderCommand, Session, SessionView, ProviderProfile } from "../types";
import { DiffViewer } from "./DiffViewer";
import { SessionUsage } from "./SessionUsage";
import { TerminalPanel } from "./TerminalPanel";
import { WorkspaceExplorer } from "./WorkspaceExplorer";

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
  onAttachFile?: (path: string) => void;
  sessionFilter?: string;
  onSessionFilterChange?: (value: string) => void;
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
  onAttachFile,
  sessionFilter = "",
  onSessionFilterChange,
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
          <div style={{ padding: "8px 12px", borderBottom: "1px solid var(--border)" }}>
            <input
              type="text"
              placeholder="Filter sessions..."
              value={sessionFilter}
              onChange={(e) => onSessionFilterChange?.(e.target.value)}
              style={{ width: "100%", fontSize: "13px" }}
            />
          </div>
          {sessions.length === 0 && <EmptyPanel message="No sessions yet." />}
          {sessions
            .filter(
              (s) =>
                !sessionFilter ||
                s.session_id.toLowerCase().includes(sessionFilter.toLowerCase()) ||
                s.status.toLowerCase().includes(sessionFilter.toLowerCase()) ||
                s.mode.toLowerCase().includes(sessionFilter.toLowerCase())
            )
            .map((session) => (
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
            <DiffViewer key={`${diff.path}-${index}`} diff={diff} />
          ))}
        </div>
      )}

      {inspector === "terminal" && (
        <TerminalPanel results={active?.command_results ?? []} />
      )}

      {inspector === "files" && (
        <WorkspaceExplorer
          workspaceRoot={active?.session.workspace_root}
          changedFiles={active?.session.changed_files}
          onAttach={onAttachFile}
        />
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
