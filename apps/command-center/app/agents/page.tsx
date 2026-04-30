import { Card, PageHeader, EmptyState, Tag } from "@/components/Card";
import { timeAgo, truncate } from "@/lib/fmt";
import { agentStates, recentEvents, getActiveProfile, integrationsHealth } from "@/lib/queries";
import { ALL_AGENT_KEYS, getAgentInfo } from "@/lib/agents";

export const dynamic = "force-dynamic";

// An agent is "live" if its state_snapshot ticked in the last 15 minutes
const FRESHNESS_MS = 15 * 60 * 1000;

export default async function AgentsPage() {
  const profile = await getActiveProfile();
  const [states, events, integrations] = await Promise.all([
    agentStates(),
    recentEvents(25),
    integrationsHealth(profile?.tenant_id || null),
  ]);

  const enabled = profile?.agents_enabled || ALL_AGENT_KEYS;
  const byName = new Map(states.map((s) => [s.agent_name, s]));
  const integrationByName = new Map(integrations.map((i) => [i.service, i]));

  const rows = enabled.map((name) => {
    const state = byName.get(name) || null;
    // Fall back to integrations_health for agents that ping there instead of state_snapshot
    const intg = integrationByName.get(name) || null;
    const lastTickMs = state?.last_tick_at ? new Date(state.last_tick_at).getTime() : 0;
    const lastPingMs = intg?.last_ping_at ? new Date(intg.last_ping_at).getTime() : 0;
    const freshestMs = Math.max(lastTickMs, lastPingMs);
    const live = freshestMs > 0 && Date.now() - freshestMs < FRESHNESS_MS;
    return {
      name,
      info: getAgentInfo(name),
      state,
      intg,
      live,
      lastSignalAt: freshestMs ? new Date(freshestMs).toISOString() : null,
    };
  });

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="Agents"
        subtitle="Every agent wired to your Command Center, plus the live event bus tape."
        action={
          <Tag tone="accent">
            {rows.filter((r) => r.live).length} / {enabled.length} live
          </Tag>
        }
      />

      <Card title="Agent family" subtitle={`Primary: ${profile?.primary_agent || "—"}`}>
        <ul className="grid md:grid-cols-2 gap-4">
          {rows.map((r) => (
            <li
              key={r.name}
              className="rounded-lg border border-bg-border bg-bg-elev p-4 transition-all hover:border-accent-muted/40"
            >
              <div className="flex justify-between items-center">
                <div className="flex items-center gap-2">
                  <div
                    className={`w-2 h-2 rounded-full ${
                      r.live
                        ? "bg-status-engaged shadow-[0_0_6px_rgba(16,185,129,0.6)] animate-pulse-slow"
                        : r.lastSignalAt
                          ? "bg-status-warm"
                          : "bg-fg-faint"
                    }`}
                  />
                  <span className="text-accent font-bold uppercase tracking-[0.14em] text-sm">
                    {r.name}
                  </span>
                </div>
                {r.live ? (
                  <span className="text-xs text-status-engaged font-mono">
                    live · {r.state ? `tick ${r.state.tick_count}` : "ping"}
                  </span>
                ) : r.lastSignalAt ? (
                  <span className="text-xs text-status-warm">
                    idle · {timeAgo(r.lastSignalAt)}
                  </span>
                ) : (
                  <span className="text-xs text-fg-dim">never seen</span>
                )}
              </div>
              <div className="text-sm text-fg mt-2.5">{r.info.role}</div>
              <div className="text-xs text-fg-dim mt-1.5 font-mono">{r.info.location}</div>
              {r.lastSignalAt && (
                <div className="text-xs text-fg-muted mt-3 pt-3 border-t border-bg-border">
                  Last signal {timeAgo(r.lastSignalAt)}
                  {r.state?.last_tick_id && (
                    <>
                      {" "}
                      ·{" "}
                      <span className="font-mono">{truncate(r.state.last_tick_id, 12)}</span>
                    </>
                  )}
                </div>
              )}
            </li>
          ))}
        </ul>
      </Card>

      <Card title="Event bus" subtitle="Cross-agent coordination, most recent first">
        {events.length === 0 ? (
          <EmptyState message="No events yet. Events publish when the reasoning loop ticks or n8n inbound fires." />
        ) : (
          <ul className="divide-y divide-bg-border">
            {events.map((e) => {
              const payload = e.payload || {};
              const cls = (payload as Record<string, unknown>).classification as
                | Record<string, unknown>
                | undefined;
              const subject = (payload as Record<string, unknown>).subject as string | undefined;
              return (
                <li key={e.id} className="py-2.5">
                  <div className="flex justify-between items-baseline gap-3">
                    <Tag tone="accent">{e.event_type}</Tag>
                    <span className="text-xs text-fg-dim">
                      {e.publisher_agent} · {timeAgo(e.published_at)}
                    </span>
                  </div>
                  {subject && (
                    <div className="text-fg mt-1.5 text-sm">{truncate(subject, 100)}</div>
                  )}
                  {cls && (
                    <div className="text-xs text-fg-muted mt-1">
                      intent: {String(cls.intent || "—")} · priority:{" "}
                      {String(cls.priority || "—")} · sentiment:{" "}
                      {String(cls.sentiment || "—")}
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </Card>
    </div>
  );
}
