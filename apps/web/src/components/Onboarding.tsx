import React, { useEffect, useState } from "react";

import { api } from "../api";
import { useModalA11y } from "../hooks/useModalA11y";
import type { LocalProvider, UiConfig } from "../types";

interface OnboardingProps {
  config: UiConfig;
  onSkip: () => void;
  onOpenProviderWizard: () => void;
  onComplete: (workspace: string) => void;
}

export function Onboarding({
  config,
  onSkip,
  onOpenProviderWizard,
  onComplete,
}: OnboardingProps) {
  const [workspace, setWorkspace] = useState(config.default_workspace || ".");
  const [providers, setProviders] = useState<LocalProvider[]>([]);
  const dialogRef = React.useRef<HTMLDivElement>(null);
  const workspaceRef = React.useRef<HTMLInputElement>(null);
  const titleId = React.useId();
  const descriptionId = React.useId();

  useEffect(() => {
    api<LocalProvider[]>("/onboarding/local-providers")
      .then(setProviders)
      .catch(() => setProviders([]));
  }, []);

  useModalA11y({
    containerRef: dialogRef,
    initialFocusRef: workspaceRef,
    onEscape: onSkip,
  });

  const ollama = providers.find((provider) => provider.kind === "ollama");
  const ollamaModels = ollama?.models ?? [];

  return (
    <div
      ref={dialogRef}
      className="onboarding"
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
      aria-describedby={descriptionId}
      tabIndex={-1}
    >
      <section className="onboarding-panel">
        <div className="onboarding-copy">
          <p>First run</p>
          <h1 id={titleId}>Welcome to Agentheim Code</h1>
          <span id={descriptionId}>
            Choose a workspace, connect a provider, then start your first session.
          </span>
        </div>

        <label className="form-group" htmlFor="onboarding-workspace">
          Workspace
          <input
            id="onboarding-workspace"
            ref={workspaceRef}
            value={workspace}
            onChange={(event) => setWorkspace(event.target.value)}
          />
        </label>

        <div className="onboarding-provider">
          <strong>Provider</strong>
          {ollama?.detected ? (
            <p>
              Ollama detected at {ollama.endpoint}
              {ollamaModels.length > 0 ? ` (${ollamaModels.join(", ")})` : ""}
            </p>
          ) : (
            <p>No local Ollama server detected. Add an API provider or skip setup.</p>
          )}
          <button className="secondary" onClick={onOpenProviderWizard} type="button">
            Add API provider
          </button>
        </div>

        <div className="onboarding-actions">
          <button className="secondary" onClick={onSkip} type="button">
            Skip for now
          </button>
          <button className="primary" onClick={() => onComplete(workspace)} type="button">
            Start first session
          </button>
        </div>
      </section>
    </div>
  );
}
