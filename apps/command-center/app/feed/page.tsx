/**
 * /feed — V6 Apex Phase 3 live event-bus tape.
 *
 * Server-rendered initial snapshot of the last hour of agent_events. The
 * server component reads via getServiceSupabase, then a tiny client island
 * re-fetches every 5s so the operator sees sibling-agent activity land in
 * near-real-time without paying for Supabase Realtime websocket quotas.
 *
 * The router daemon (scripts/event_router.py) maintains state/event_router.log
 * as the local-side projection. This page is the cloud-side view of the same
 * events — both read from agent_events; the router is the on-machine
 * observability tail, the feed is the operator-facing tail.
 */

import { headers } from "next/headers";
import { Activity, Radio, ArrowUpRight } from "lucide-react";
import { Card, PageHeader, Tag } from "@/components/Card";
import { getServiceSupabase } from "@/lib/supabase-server";
import { FeedRefresher } from "./refresher";

export const dynamic = "force-dynamic";
export const revalidate = 0;

type EventRow = {
  id: string;
  event_type: string;
  source_agent: string | null;
  target_agent: string | null;
  severity: string | null;
  payload: Record<string, unknown> | null;
  published_at: string | null;
  created_at: string | null;
  status: string | null;
};

function relativeTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const t = new Date(iso).getTime();
  const diff = Date.now() - t;
  if (diff < 60_000)        return `${Math.round(diff / 1000)}s ago`;
  if (diff < 3_600_000)     return `${Math.round(diff / 60_000)}m ago`;
  if (diff < 86_400_000)    return `${Math.round(diff / 3_600_000)}h ago`;
  return `${Math.round(diff / 86_400_000)}d ago`;
}

function preview(payload: Record<string, unknown> | null): string {
  if (!payload || typeof payload !== "object") return "—";
  const keys = ["note", "preview", "kind", "lead_id", "channel", "intent",
                "platform", "post_url", "amount_cad", "amount_usd",
                "net_mrr_usd", "v6_mode", "client", "invoice_id"];
  const pairs: string[] = [];
  for (const k of keys) {
    const v = (payload as Record<string, unknown>)[k];
    if (v === null || v === undefined || v === "") continue;
    const s = typeof v === "object" ? JSON.stringify(v) : String(v);
    pairs.push(`${k}=${s.slice(0, 80)}`);
  }
  return pairs.length > 0 ? pairs.join(" · ") : "—";
}

function severityTone(s: string | null): "neutral" | "accent" | "warm" | "hot" {
  if (s === "error" || s === "critical") return "hot";
  if (s === "warn"  || s === "warning")  return "warm";
  if (s === "info")                       return "accent";
  return "neutral";
}

async function fetchInitial(): Promise<{ rows: EventRow[]; error?: string }> {
  try {
    const db = getServiceSupabase();
    const cutoff = new Date(Date.now() - 60 * 60 * 1000).toISOString();
    const r = await db
      .from("agent_events")
      .select(
        "id, event_type, source_agent, target_agent, severity, payload, " +
          "published_at, created_at, status",
      )
      .gte("created_at", cutoff)
      .order("created_at", { ascending: false })
      .limit(100);
    if (r.error) return { rows: [], error: r.error.message };
    return { rows: ((r.data || []) as unknown) as EventRow[] };
  } catch (err) {
    return { rows: [], error: err instanceof Error ? err.message : "fetch failed" };
  }
}

export default async function FeedPage() {
  await headers();
  const { rows, error } = await fetchInitial();

  const sources = Array.from(new Set(rows.map((r) => r.source_agent || "unknown"))).sort();

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="Event Feed"
        subtitle="V6 cross-agent event-bus tape. The event_router daemon projects every agent_events row to state/event_router.log on CC's machine; this page is the cloud-side view of the same stream."
        action={
          <div className="flex items-center gap-2">
            <Tag tone="accent">{rows.length} events / 1h</Tag>
            <FeedRefresher />
          </div>
        }
      />

      {error && (
        <Card>
          <div className="flex items-start gap-3 p-2">
            <Activity size={20} className="text-status-hot shrink-0 mt-0.5" />
            <div>
              <div className="font-bold text-fg">Could not load event feed</div>
              <p className="text-sm text-fg-muted mt-1">{error}</p>
            </div>
          </div>
        </Card>
      )}

      {!error && rows.length === 0 && (
        <Card>
          <div className="text-sm text-fg-muted p-2">
            No agent events in the last hour. Idle window — siblings are quiet.
          </div>
        </Card>
      )}

      {sources.length > 0 && (
        <Card>
          <div className="text-xs text-fg-dim uppercase tracking-wider mb-2">
            Active sources (1h)
          </div>
          <div className="flex flex-wrap gap-2">
            {sources.map((s) => (
              <Tag key={s} tone="neutral">{s}</Tag>
            ))}
          </div>
        </Card>
      )}

      <Card>
        <div className="flex items-center gap-2 mb-3">
          <Radio size={14} className="text-accent" />
          <h2 className="text-xs font-bold uppercase tracking-wider text-fg-muted">
            Stream (newest first)
          </h2>
        </div>
        <div className="space-y-2 max-h-[70vh] overflow-y-auto pr-2">
          {rows.map((row) => (
            <div
              key={row.id}
              className="flex items-start gap-3 py-2 border-b border-bg-border last:border-0"
            >
              <div className="font-mono text-xs text-fg-faint w-20 shrink-0 pt-0.5">
                {relativeTime(row.created_at)}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-bold text-sm text-fg">{row.event_type}</span>
                  <Tag tone={severityTone(row.severity)}>{row.severity || "info"}</Tag>
                  <span className="text-xs text-fg-dim">
                    {row.source_agent || "unknown"}
                  </span>
                  <ArrowUpRight size={12} className="text-fg-faint" />
                  <span className="text-xs text-fg-dim">
                    {row.target_agent || "broadcast"}
                  </span>
                </div>
                <div className="text-xs text-fg-muted font-mono mt-1 truncate">
                  {preview(row.payload)}
                </div>
              </div>
              <span className="text-xs text-fg-faint shrink-0 pt-0.5">
                {row.status || "pending"}
              </span>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
