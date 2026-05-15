"use client";

/**
 * BackgroundWorkersPanel — read-only view of the operator's local PM2
 * daemons + standalone Skool daemon. Renders below the cron-jobs list on
 * /automations so the operator can see at a glance:
 *   - Which background workers should be running on their machine
 *   - Which are alive (status: healthy) vs stopped (down) vs unknown
 *     (bridge hasn't pushed a snapshot recently)
 *   - When each was last reported
 *
 * The bridge daemon (bravo_cli/local_bridge.py) is what populates the
 * underlying data — it calls `pm2 jlist` on each 60s heartbeat and POSTs
 * the snapshot to /api/bridge/ping. If the bridge itself is offline, this
 * panel will say so + degrade gracefully (all workers as "unknown").
 */

import { useEffect, useState } from "react";
import { Cpu, CheckCircle2, AlertCircle, MinusCircle, HelpCircle, Activity } from "lucide-react";

type Worker = {
  service: string;
  label: string;
  purpose: string;
  status: "healthy" | "degraded" | "down" | "unconfigured";
  metadata: Record<string, unknown>;
  last_ping_at: string | null;
};

type ApiResponse = {
  ok: boolean;
  bridge_online: boolean;
  last_seen_at: string | null;
  workers: Worker[];
  error?: string;
};

export function BackgroundWorkersPanel() {
  const [data, setData] = useState<ApiResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    try {
      const res = await fetch("/api/automations/background-workers");
      const j = (await res.json()) as ApiResponse;
      if (!j.ok) {
        setError(j.error || `http_${res.status}`);
        return;
      }
      setData(j);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "load_failed");
    }
  }

  useEffect(() => {
    refresh();
    // 30s refresh so newly-started/stopped daemons surface fast without
    // polling so hard we eat tons of dashboard requests.
    const t = setInterval(refresh, 30_000);
    return () => clearInterval(t);
  }, []);

  if (error) {
    return (
      <div className="rounded-xl border border-status-warm/40 bg-status-warm/10 p-3 text-sm text-status-warm flex items-start gap-2">
        <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
        <span>Couldn&apos;t load background workers: {error}</span>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="rounded-xl border border-bg-border bg-bg-elev/30 p-4 text-xs text-fg-muted">
        Loading background workers…
      </div>
    );
  }

  const healthy = data.workers.filter((w) => w.status === "healthy").length;
  const total = data.workers.length;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Cpu className="w-4 h-4 text-fg-muted" />
          <div className="text-sm font-bold text-fg">Background workers</div>
          <span className="text-[10px] uppercase tracking-wider text-fg-dim border border-bg-border rounded-full px-1.5 py-0.5">
            {healthy}/{total} healthy
          </span>
        </div>
        {data.last_seen_at && (
          <div className="text-[11px] text-fg-dim inline-flex items-center gap-1.5">
            <Activity className="w-3 h-3" />
            Bridge last seen {new Date(data.last_seen_at).toLocaleTimeString()}
          </div>
        )}
      </div>

      {!data.bridge_online && (
        <div className="rounded-lg border border-bg-border bg-bg-deep/40 p-3 text-xs text-fg-muted">
          Bridge hasn&apos;t pinged in the last 2 minutes — worker statuses
          below may be stale. Run <span className="font-mono text-fg">pm2 restart claude-bridge-ping</span> on your machine.
        </div>
      )}

      <div className="grid sm:grid-cols-2 gap-2">
        {data.workers.map((w) => (
          <WorkerRow key={w.service} worker={w} />
        ))}
      </div>
    </div>
  );
}

function WorkerRow({ worker }: { worker: Worker }) {
  const Icon =
    worker.status === "healthy"
      ? CheckCircle2
      : worker.status === "down"
        ? MinusCircle
        : worker.status === "degraded"
          ? AlertCircle
          : HelpCircle;
  const iconClass =
    worker.status === "healthy"
      ? "text-status-engaged"
      : worker.status === "down"
        ? "text-status-warm"
        : worker.status === "degraded"
          ? "text-accent"
          : "text-fg-dim";
  // metadata fields the bridge pushes: pm2_status, pid, restart_count,
  // uptime_ms, memory_bytes, cpu_pct. Render the operator-meaningful
  // subset on the row; pid + memory + cpu live in the hover-only tooltip
  // (title attr) so the card stays scannable.
  // Metadata field names mirror what detect_pm2_daemons() in
  // bravo_cli/local_bridge.py writes — keep these two in sync.
  const meta = worker.metadata || {};
  const pid = (meta.pid as number) || 0;
  const restartCount = (meta.restart_count as number) || 0;
  const uptimeMs = (meta.uptime_ms as number) || 0;
  const memBytes = (meta.memory_bytes as number) || 0;
  const cpuPct = (meta.cpu_pct as number) || 0;
  const memMb = memBytes ? Math.round(memBytes / 1024 / 1024) : 0;
  const uptimeStr = uptimeMs ? formatUptime(Date.now() - uptimeMs) : null;

  return (
    <div
      className={`rounded-lg border p-3 ${
        worker.status === "healthy"
          ? "border-bg-border bg-bg-elev/30"
          : worker.status === "down"
            ? "border-status-warm/30 bg-status-warm/5"
            : "border-bg-border bg-bg-deep/40 opacity-80"
      }`}
      title={pid ? `PID ${pid} · ${memMb}MB · ${cpuPct}% CPU · ${restartCount} restarts` : worker.service}
    >
      <div className="flex items-start gap-2">
        <Icon className={`w-4 h-4 shrink-0 mt-0.5 ${iconClass}`} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <div className="font-bold text-sm text-fg truncate">{worker.label}</div>
            <span className="text-[10px] uppercase tracking-wider text-fg-dim font-mono">
              {worker.service.replace(/^pm2\./, "")}
            </span>
          </div>
          <div className="text-[11px] text-fg-muted mt-0.5 leading-relaxed">{worker.purpose}</div>
          {uptimeStr && (
            <div className="text-[10px] text-fg-dim mt-1 font-mono">
              up {uptimeStr}
              {restartCount > 0 ? ` · ${restartCount} restart${restartCount === 1 ? "" : "s"}` : ""}
              {memMb > 0 ? ` · ${memMb}MB` : ""}
            </div>
          )}
          {worker.status === "unconfigured" && (
            <div className="text-[10px] text-fg-dim mt-1 italic">
              Not running on your machine.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function formatUptime(ms: number): string {
  if (ms < 60_000) return `${Math.round(ms / 1000)}s`;
  if (ms < 3_600_000) return `${Math.round(ms / 60_000)}m`;
  if (ms < 86_400_000) return `${Math.round(ms / 3_600_000)}h`;
  return `${Math.round(ms / 86_400_000)}d`;
}
