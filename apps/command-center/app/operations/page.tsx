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
import { getServiceSupabase } from "@/lib/supabase-server";
import { ALL_AGENT_KEYS, getAgentInfo } from "@/lib/agents";
import { timeAgo, truncate } from "@/lib/fmt";

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

export default async function OperationsPage() {
  const profile = await getActiveProfile();

  // Agents (worker state)
  let snaps: AgentSnap[] = [];
  try {
    const db = getServiceSupabase();
    const { data } = await db
      .from("agent_state_snapshot")
      .select("agent_name, tick_count, last_tick_at, last_tick_id, health_status")
      .order("last_tick_at", { ascending: false });
    snaps = (data as AgentSnap[]) || [];
  } catch {
    snaps = [];
  }
  const snapByName = new Map(snaps.map((s) => [s.agent_name, s] as const));

  // Local bridges (cron-host visibility)
  let pairings: BridgePair[] = [];
  if (profile?.tenant_id) {
    try {
      const db = getServiceSupabase();
      const { data } = await db
        .from("bridge_pairings")
        .select("id, label, machine_fingerprint, last_seen_at, created_at")
        .eq("tenant_id", profile.tenant_id)
        .is("revoked_at", null)
        .order("last_seen_at", { ascending: false });
      pairings = (data as BridgePair[]) || [];
    } catch {
      pairings = [];
    }
  }

  // Recent events (the activity tape — proxy for cron-fires + agent-ticks)
  const events = await recentEvents(50).catch(() => []);

  const enabled = profile?.agents_enabled || ALL_AGENT_KEYS;
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

      <Card title="Agent workers" subtitle={`Tick = the agent's autonomous reasoning loop ran. Fresh = within the last 15 min.`}>
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
                  <span className="text-xs text-fg-dim font-mono">
                    {snap?.last_tick_at ? `tick ${snap.tick_count ?? 0}` : "no ticks yet"}
                  </span>
                </div>
                <div className="text-xs text-fg-muted mt-1.5">{info.tagline}</div>
                <div className="text-[10px] text-fg-dim mt-2 font-mono">
                  {snap?.last_tick_at
                    ? `last tick ${timeAgo(snap.last_tick_at)}${snap.last_tick_id ? ` · ${truncate(snap.last_tick_id, 12)}` : ""}`
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
        title="Activity tape"
        subtitle="50 most-recent events across the agent family — cron fires, reasoning loops, inbound classifications."
      >
        {events.length === 0 ? (
          <EmptyState message="No events yet. Events publish when an agent's reasoning loop ticks or an inbound webhook fires." />
        ) : (
          <ul className="divide-y divide-bg-border">
            {events.slice(0, 30).map((e) => (
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
