"use client";

/**
 * DevicesEditor — list paired machines for this tenant + revoke action.
 *
 * Each row in bridge_pairings is a local install (`bravo bridge start`
 * pinging /api/bridge/ping every 60s). Revoking sets revoked_at; the daemon
 * sees 403 on its next ping, exits, and the operator must re-pair via
 * `bravo setup` to bring it back online.
 */

import { useEffect, useState } from "react";
import { Loader2, Trash2, Check, AlertCircle, Monitor, RefreshCw } from "lucide-react";

type Device = {
  id: string;
  label: string;
  machine_fingerprint: string | null;
  last_seen_at: string | null;
  last_seen_ip: string | null;
  created_at: string;
  revoked_at: string | null;
};

const FRESH_MS = 5 * 60 * 1000;

function timeAgo(iso: string | null): string {
  if (!iso) return "never";
  const ms = Date.now() - new Date(iso).getTime();
  if (ms < 60_000) return "just now";
  if (ms < 60 * 60_000) return `${Math.floor(ms / 60_000)}m ago`;
  if (ms < 24 * 60 * 60_000) return `${Math.floor(ms / (60 * 60_000))}h ago`;
  return `${Math.floor(ms / (24 * 60 * 60_000))}d ago`;
}

export function DevicesEditor() {
  const [devices, setDevices] = useState<Device[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null); // device id being revoked
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      const r = await fetch("/api/devices");
      const j = await r.json();
      if (j.ok) setDevices(j.devices as Device[]);
      else setError(j.error || `http_${r.status}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "load_failed");
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function revoke(id: string) {
    if (!confirm("Revoke this device? The bridge daemon on that machine will stop pinging within 60 seconds. Re-pair via `bravo setup`.")) return;
    setBusy(id);
    setError(null);
    try {
      const r = await fetch(`/api/devices?id=${encodeURIComponent(id)}`, { method: "DELETE" });
      const j = await r.json();
      if (!j.ok) {
        setError(j.error || `http_${r.status}`);
      } else {
        await load();
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "revoke_failed");
    } finally {
      setBusy(null);
    }
  }

  if (devices === null) {
    return (
      <div className="text-fg-dim text-sm flex items-center gap-2">
        <Loader2 className="w-4 h-4 animate-spin" /> loading devices…
      </div>
    );
  }
  if (devices.length === 0) {
    return (
      <div className="space-y-3">
        <div className="text-fg-muted text-sm">
          No devices paired yet. Each machine you pair gets its own row + green dot once the bridge boots.
        </div>
        <div className="rounded-lg border border-accent/20 bg-accent/5 p-3 space-y-2">
          <div className="text-[11px] uppercase tracking-wider font-bold text-accent">
            Connect a machine — one paste per OS
          </div>
          <div className="space-y-1.5 text-xs text-fg-muted">
            <div>
              <span className="font-bold text-fg">Windows (PowerShell):</span>{" "}
              <code className="bg-bg-deep px-1.5 py-0.5 rounded text-accent">irm https://raw.githubusercontent.com/CC90210/CEO-Agent/main/install/quickstart.ps1 | iex</code>
            </div>
            <div>
              <span className="font-bold text-fg">macOS / Linux / WSL:</span>{" "}
              <code className="bg-bg-deep px-1.5 py-0.5 rounded text-accent">curl -fsSL https://raw.githubusercontent.com/CC90210/CEO-Agent/main/install/quickstart.sh | bash</code>
            </div>
            <div className="text-[11px] text-fg-dim pt-1">
              Each machine self-pairs against the dashboard on first boot — no copy-paste of tokens. Re-run the same one-liner to add another machine. Each gets its own row here.
            </div>
          </div>
        </div>
      </div>
    );
  }
  const active = devices.filter((d) => !d.revoked_at);
  const revoked = devices.filter((d) => d.revoked_at);

  return (
    <div className="space-y-3">
      {error && (
        <div className="rounded-md border border-status-warm/40 bg-status-warm/10 p-3 text-sm text-status-warm flex items-center gap-2">
          <AlertCircle className="w-4 h-4" />
          <span className="font-mono">{error}</span>
        </div>
      )}
      <div className="flex items-center justify-between">
        <div className="text-xs text-fg-muted">
          {active.length} active{revoked.length > 0 ? ` · ${revoked.length} revoked` : ""}
        </div>
        <button onClick={load} className="text-fg-dim hover:text-accent text-xs inline-flex items-center gap-1" title="Refresh">
          <RefreshCw className="w-3 h-3" /> refresh
        </button>
      </div>
      <ul className="divide-y divide-bg-border">
        {active.map((d) => {
          const fresh = d.last_seen_at && Date.now() - new Date(d.last_seen_at).getTime() < FRESH_MS;
          return (
            <li key={d.id} className="py-3 flex items-center justify-between gap-3">
              <div className="flex items-start gap-3 min-w-0 flex-1">
                <Monitor className={`w-4 h-4 mt-0.5 ${fresh ? "text-accent" : "text-fg-dim"}`} />
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm text-fg truncate">{d.label}</span>
                    <span className={`text-[10px] uppercase tracking-wider font-bold ${fresh ? "text-accent" : "text-fg-dim"}`}>
                      {fresh ? "online" : "offline"}
                    </span>
                  </div>
                  <div className="text-[10px] text-fg-dim font-mono mt-0.5 truncate">
                    {d.machine_fingerprint || "no fingerprint"}
                  </div>
                  <div className="text-[10px] text-fg-muted font-mono mt-1">
                    last ping {timeAgo(d.last_seen_at)} · paired {timeAgo(d.created_at)}
                    {d.last_seen_ip && ` · ${d.last_seen_ip}`}
                  </div>
                </div>
              </div>
              <button
                onClick={() => revoke(d.id)}
                disabled={busy === d.id}
                className="btn-danger inline-flex items-center gap-1 shrink-0"
                title="Revoke this pairing"
              >
                {busy === d.id ? <Loader2 className="w-3 h-3 animate-spin" /> : <Trash2 className="w-3 h-3" />}
                Revoke
              </button>
            </li>
          );
        })}
      </ul>
      {revoked.length > 0 && (
        <details className="text-xs text-fg-dim">
          <summary className="cursor-pointer hover:text-fg-muted">Revoked ({revoked.length})</summary>
          <ul className="mt-2 space-y-1.5 pl-4">
            {revoked.map((d) => (
              <li key={d.id} className="flex items-center gap-2">
                <Check className="w-3 h-3 text-fg-faint" />
                <span className="font-mono">{d.label}</span>
                <span>· revoked {timeAgo(d.revoked_at)}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
