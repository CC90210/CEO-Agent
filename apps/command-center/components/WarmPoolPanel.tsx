"use client";

/**
 * WarmPoolPanel — live view of the bridge's warm-process pool.
 *
 * Shows on /operations when the bridge is online. Pulls the live state
 * from `http://localhost:9100/warm-status` (the bridge's diagnostic
 * endpoint added when the warm pool shipped). Refreshes every 5s while
 * mounted.
 *
 * Why this exists: an operator who reports "this turn felt slow" can
 * now look here instead of guessing. Greeen rows = warm processes
 * waiting for input. Red dot + "BUSY" = a turn currently in flight.
 * Idle counter ticking up to 15 min = reaper window (process gets
 * killed at idle ≥ 900s).
 */

import { useEffect, useState } from "react";
import { Activity, Loader2, Zap } from "lucide-react";
import { BRIDGE_CHAT_BASE } from "@/lib/agent-roots";

type Process = {
  key: string;
  agent: string;
  alive: boolean;
  busy: boolean;
  age_s: number;
  idle_s: number;
  session_id: string | null;
};

type WarmStatus = {
  ok: boolean;
  size: number;
  max_size: number;
  idle_timeout_s: number;
  processes: Process[];
};

function fmtSeconds(s: number): string {
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m ${s % 60}s`;
  return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`;
}

export function WarmPoolPanel() {
  const [status, setStatus] = useState<WarmStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const ctl = new AbortController();
        const t = setTimeout(() => ctl.abort(), 1500);
        const r = await fetch(`${BRIDGE_CHAT_BASE}/warm-status`, { signal: ctl.signal });
        clearTimeout(t);
        if (!alive) return;
        if (!r.ok) {
          setError(`http_${r.status}`);
          return;
        }
        const j = (await r.json()) as WarmStatus;
        setStatus(j);
        setError(null);
      } catch (e) {
        if (!alive) return;
        setError(e instanceof Error ? e.message : "fetch_failed");
      }
    };
    tick();
    const id = setInterval(tick, 5000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  if (error) {
    return (
      <div className="text-xs text-fg-dim flex items-center gap-2">
        <Loader2 className="w-3 h-3" /> warm-status unreachable — bridge offline?
      </div>
    );
  }
  if (!status) {
    return (
      <div className="text-xs text-fg-dim flex items-center gap-2">
        <Loader2 className="w-3 h-3 animate-spin" /> loading pool state…
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="text-xs text-fg-muted">
        {status.size} / {status.max_size} processes ·{" "}
        idle reaper at {fmtSeconds(status.idle_timeout_s)} ·{" "}
        refreshes every 5s
      </div>
      {status.processes.length === 0 ? (
        <div className="text-xs text-fg-dim italic">
          Pool empty. Open a chat to spawn the first warm process.
        </div>
      ) : (
        <ul className="divide-y divide-bg-border">
          {status.processes.map((p) => {
            const reaperRemaining = Math.max(0, status.idle_timeout_s - p.idle_s);
            const dot = p.busy
              ? "bg-status-engaged animate-pulse-slow"
              : p.alive
                ? "bg-accent"
                : "bg-status-warm";
            const stateLabel = p.busy ? "busy" : p.alive ? "warm" : "dead";
            return (
              <li key={p.key} className="py-2.5 flex items-start justify-between gap-3 text-xs">
                <div className="flex items-start gap-2.5 min-w-0">
                  <span
                    className={`w-2 h-2 rounded-full shrink-0 mt-1 ${dot}`}
                    title={stateLabel}
                  />
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-bold uppercase tracking-[0.14em] text-fg">
                        {p.agent}
                      </span>
                      <span className="text-fg-dim font-mono text-[10px]">
                        {p.key}
                      </span>
                    </div>
                    <div className="text-fg-muted mt-0.5">
                      {p.busy ? (
                        <span className="inline-flex items-center gap-1">
                          <Zap className="w-3 h-3 text-status-engaged" /> turn in flight
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1">
                          <Activity className="w-3 h-3" />
                          warm · idle {fmtSeconds(p.idle_s)} ·{" "}
                          reaper in {fmtSeconds(reaperRemaining)}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
                <div className="text-right text-fg-dim font-mono shrink-0">
                  age {fmtSeconds(p.age_s)}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
