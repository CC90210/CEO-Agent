/**
 * /operations — what's running in the background.
 *
 * Reads three already-populated tables:
 *   - agent_state_snapshot   → which agents have ticked recently (workers)
 *   - bridge_pairings        → which local installs are heartbeating
 *   - agent_events (last 50) → cross-agent activity tape (cron + reasoning)
 *
 * No new schema. Surfaces what's already in motion so the operator can see
 * the back end at a glance: cron jobs that just ran, agents that ticked,
 * inbound events that landed.
 */

import { Card, PageHeader, Tag, EmptyState } from "@/components/Card";
import { getActiveProfile, recentEvents } from "@/lib/queries";
import { safe } from "@/lib/api-helpers";
import { getServiceSupabase } from "@/lib/supabase-server";
import { ALL_AGENT_KEYS, FAMILY_AGENT_KEYS, getAgentInfo } from "@/lib/agents";
import { timeAgo, truncate } from "@/lib/fmt";
import { WarmPoolPanel } from "@/components/WarmPoolPanel";

export const dynamic = "force-dynamic";

const FRESH_AGENT_MS = 15 * 60 * 1000;
const FRESH_BRIDGE_MS = 5 * 60 * 1000;

type AgentSnap = {
  agent_name: string;
  tick_count: number | null;
  last_tick_at: string | null;
  last_tick_id: string | null;
  health_status: string | null;
};

type BridgePair = {
  id: string;
  label: string;
  machine_fingerprint: string | null;
  last_seen_at: string | null;
  created_at: string;
};

export default async function OperationsPage({
  searchParams,
}: {
  searchParams?: Promise<{ showOlder?: string }>;
}) {
  const profile = await safe(getActiveProfile(), null);
  const db = getServiceSupabase();
  const sp = (await searchParams) || {};
  const showOlder = sp.showOlder === "1";

  const [snaps, pairings, events] = await Promise.all([
    safe(
      (async () => {
        const r = await db
          .from("agent_state_snapshot")
          .select("agent_name, tick_count, last_tick_at, last_tick_id, health_status")
          .order("last_tick_at", { ascending: false });
        return (r.data as AgentSnap[]) || [];
      })(),
      [] as AgentSnap[]
    ),
    profile?.tenant_id
      ? safe(
          (async () => {
            const r = await db
              .from("bridge_pairings")
              .select("id, label, machine_fingerprint, last_seen_at, created_at")
              .eq("tenant_id", profile.tenant_id)
              .is("revoked_at", null)
              .order("last_seen_at", { ascending: false });
            return (r.data as BridgePair[]) || [];
          })(),
          [] as BridgePair[]
        )
      : Promise.resolve([] as BridgePair[]),
    // Activity tape default: most recent 30 events regardless of age.
    // The previous "last 7 days only" default left the tape empty when
    // crons / inbound traffic had been quiet for a week — looked broken
    // even though the table had history. The "show older" link expands
    // to 100 events. CC explicitly asked for the tape to be functional.
    safe(
      recentEvents(showOlder ? 100 : 30, {
        sinceDays: 0,
        tenantId: profile?.tenant_id || null,
      }),
      []
    ),
  ]);
  const snapByName = new Map(snaps.map((s) => [s.agent_name, s] as const));

  // Show only family personas in the AGENT WORKERS card. Codex is a
  // backend executor, not a standalone agent — see lib/agents.ts.
  // Hermes / Lumen / others outside profile.agents_enabled still show
  // (just idle) so CC sees the full family, not a partial view.
  const familySet = new Set(FAMILY_AGENT_KEYS);
  const enabledRaw = profile?.agents_enabled || ALL_AGENT_KEYS;
  const enabled = Array.from(
    new Set([
      ...enabledRaw.filter((k) => familySet.has(k)),
      ...FAMILY_AGENT_KEYS,
    ])
  );
  const now = Date.now();

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="Operations"
        subtitle="Background workers, paired machines, and the live event tape — what's running right now."
        action={
          <Tag tone={pairings.some((p) => isFresh(p.last_seen_at, now, FRESH_BRIDGE_MS)) ? "engaged" : "warm"}>
            {pairings.filter((p) => isFresh(p.last_seen_at, now, FRESH_BRIDGE_MS)).length} bridge{pairings.length === 1 ? "" : "s"} online
          </Tag>
        }
      />

      <Card
        title="Agent workers"
        subtitle="Each agent runs an autonomous reasoning loop on its own machine. A green dot means it cycled within the last 15 min."
      >
        <div className="grid sm:grid-cols-2 gap-3">
          {enabled.map((key) => {
            const info = getAgentInfo(key);
            const snap = snapByName.get(key);
            const fresh = isFresh(snap?.last_tick_at || null, now, FRESH_AGENT_MS);
            return (
              <div
                key={key}
                className={`rounded-lg border bg-bg-elev px-4 py-3.5 ${
                  fresh ? "border-status-engaged/30" : "border-bg-border"
                }`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className={`w-2 h-2 rounded-full ${
                      fresh ? "bg-status-engaged animate-pulse-slow" : snap?.last_tick_at ? "bg-status-warm" : "bg-fg-faint"
                    }`} />
                    <span className={`font-bold uppercase tracking-[0.14em] text-sm ${info.textClass}`}>
                      {key}
                    </span>
                  </div>
                  <span
                    className="text-xs text-fg-dim font-mono"
                    title="One cycle = one autonomous reasoning loop (the agent woke up, decided what to fire, logged it). Higher count = more activity since the worker started."
                  >
                    {snap?.last_tick_at ? `${snap.tick_count ?? 0} cycle${snap.tick_count === 1 ? "" : "s"}` : "no activity yet"}
                  </span>
                </div>
                <div className="text-xs text-fg-muted mt-1.5">{info.tagline}</div>
                <div className="text-[10px] text-fg-dim mt-2 font-mono">
                  {snap?.last_tick_at
                    ? `last cycle ${timeAgo(snap.last_tick_at)}${snap.last_tick_id ? ` · ${truncate(snap.last_tick_id, 12)}` : ""}`
                    : "worker not running on any paired machine"}
                </div>
              </div>
            );
          })}
        </div>
      </Card>

      <Card title="Paired machines" subtitle="Local installs heartbeating to this dashboard. Run `bravo bridge start` on a machine to add it.">
        {pairings.length === 0 ? (
          <EmptyState message="No machines paired yet. After running the setup wizard, run `bravo bridge start` to begin pinging." />
        ) : (
          <ul className="divide-y divide-bg-border">
            {pairings.map((p) => {
              const online = isFresh(p.last_seen_at, now, FRESH_BRIDGE_MS);
              return (
                <li key={p.id} className="py-3 flex items-center justify-between gap-3">
                  <div className="flex items-center gap-3 min-w-0">
                    <span className={`w-2 h-2 rounded-full shrink-0 ${
                      online ? "bg-accent animate-pulse-slow" : "bg-fg-faint"
                    }`} />
                    <div className="min-w-0">
                      <div className="text-sm text-fg truncate">{p.label}</div>
                      <div className="text-[10px] text-fg-dim font-mono truncate">
                        {p.machine_fingerprint || "no fingerprint"}
                      </div>
                    </div>
                  </div>
                  <div className="text-xs text-fg-muted text-right shrink-0">
                    <div className={online ? "text-accent" : "text-fg-dim"}>
                      {online ? "online" : "offline"}
                    </div>
                    <div className="text-[10px] text-fg-dim font-mono">
                      {p.last_seen_at ? `last ${timeAgo(p.last_seen_at)}` : "never"}
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </Card>

      <Card
        title="Warm process pool"
        subtitle="Live state of the bridge's persistent claude processes. Each entry skips the cold-start (5–30s) on its next chat turn. Only visible when the local bridge is online."
      >
        <WarmPoolPanel />
      </Card>

      <Card
        title="Activity tape"
        subtitle={
          showOlder
            ? `All events (last 100) — cron fires, reasoning loops, outbound sends, inbound classifications.`
            : `Most recent ${events.length} events — cron fires, reasoning loops, outbound sends, inbound classifications.`
        }
        action={
          <a
            href={showOlder ? "?" : "?showOlder=1"}
            className="text-xs text-fg-dim hover:text-accent transition-colors"
          >
            {showOlder ? "← back to recent 30" : "show 100 →"}
          </a>
        }
      >
        {events.length === 0 ? (
          <EmptyState
            message="No events recorded yet. The event bus writes when crons fire (MRR snapshot, plan materialize), inbound webhooks land (n8n classifies email), or agents emit dashboard-action mutations."
          />
        ) : (
          <ul className="divide-y divide-bg-border">
            {events.map((e) => (
              <li key={e.id} className="py-2.5">
                <div className="flex items-center justify-between gap-3">
                  <Tag tone="accent">{e.event_type}</Tag>
                  <span className="text-xs text-fg-dim">
                    {e.publisher_agent} · {timeAgo(e.published_at)}
                  </span>
                </div>
                {(() => {
                  const subj = (e.payload as Record<string, unknown>)?.subject as string | undefined;
                  return subj ? (
                    <div className="text-fg mt-1.5 text-sm">{truncate(subj, 100)}</div>
                  ) : null;
                })()}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

function isFresh(ts: string | null, now: number, threshold: number): boolean {
  if (!ts) return false;
  return now - new Date(ts).getTime() < threshold;
}
