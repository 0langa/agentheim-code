import React, { useEffect, useState } from "react";

import { api } from "../api";
import type { UsageData } from "../types";

interface SessionUsageProps {
  sessionId: string | null;
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

function formatCost(cost: number | null): string {
  if (cost === null || cost === undefined) return "—";
  if (cost < 0.0001) return `< $0.0001`;
  return `$${cost.toFixed(4)}`;
}

export function SessionUsage({ sessionId }: SessionUsageProps) {
  const [usage, setUsage] = useState<UsageData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!sessionId) {
      setUsage(null);
      return;
    }
    let cancelled = false;
    const fetchUsage = async () => {
      try {
        const data = await api<UsageData>(`/coder/sessions/${sessionId}/usage`);
        if (!cancelled) {
          setUsage(data);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err));
        }
      }
    };
    fetchUsage();
    const interval = setInterval(fetchUsage, 5000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [sessionId]);

  if (!sessionId) {
    return <p className="panel-empty">No active session.</p>;
  }

  if (error) {
    return <p className="panel-empty">Unable to load usage.</p>;
  }

  if (!usage || usage.calls === 0) {
    return <p className="panel-empty">No usage data yet.</p>;
  }

  return (
    <div className="usage-panel">
      <div className="usage-summary">
        <div className="usage-metric">
          <span className="usage-value">{formatTokens(usage.total_tokens)}</span>
          <span className="usage-label">total tokens</span>
        </div>
        <div className="usage-metric">
          <span className="usage-value">{formatTokens(usage.input_tokens)}</span>
          <span className="usage-label">input</span>
        </div>
        <div className="usage-metric">
          <span className="usage-value">{formatTokens(usage.output_tokens)}</span>
          <span className="usage-label">output</span>
        </div>
        <div className="usage-metric">
          <span className="usage-value">{formatCost(usage.estimated_cost_usd)}</span>
          <span className="usage-label">est. cost</span>
        </div>
        <div className="usage-metric">
          <span className="usage-value">{usage.calls}</span>
          <span className="usage-label">calls</span>
        </div>
      </div>

      {usage.breakdown.length > 0 && (
        <details className="usage-breakdown">
          <summary>Breakdown ({usage.breakdown.length} calls)</summary>
          <ul>
            {usage.breakdown.map((item) => (
              <li key={item.sequence}>
                <span>{item.provider ?? "unknown"}</span>
                <span>{item.model ?? "unknown"}</span>
                <span>
                  {formatTokens(item.input_tokens)} → {formatTokens(item.output_tokens)}
                </span>
                <span>{formatCost(item.estimated_cost_usd)}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
