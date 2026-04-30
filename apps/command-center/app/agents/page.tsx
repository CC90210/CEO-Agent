import { Card, PageHeader, EmptyState, Tag } from "@/components/Card";
import { timeAgo, truncate } from "@/lib/fmt";
import { agentStates, recentEvents, getActiveProfile } from "@/lib/queries";

export const dynamic = "force-dynamic";

const AGENT_DESCRIPTIONS: Record<string, { role: string; location: string }> = {
  bravo: {
    role: "Lead architect · business ops · content voice",
    location: "this repo",
  },
  codex: {
    role: "Backend executor · deep debugging · adversarial review",
    location: "Codex companion",
  },
  atlas: {
    role: "CFO · finance · tax · trading · budget",
    location: "C:\\Users\\User\\APPS\\CFO-Agent",
  },
  maven: {
    role: "CMO · content production · paid ads · funnels",
    location: "C:\\Users\\User\\CMO-Agent",
  },
  aura: {
    role: "Life · home · habits · voice",
    location: "C:\\Users\\User\\AURA",
  },
  hermes: {
    role: "Commerce agent · POS · EDI · chargebacks",
    location: "C:\\Users\\User\\hermes",
  },
};

export default async function AgentsPage() {
  const [states, events, profile] = await Promise.all([
    agentStates(),
    recentEvents(25),
    getActiveProfile(),
  ]);

  // Show all agents the operator has enabled, fallback to all known agents
  const enabled = profile?.agents_enabled || Object.keys(AGENT_DESCRIPTIONS);
  const byName = new Map(states.map((s) => [s.agent_name, s]));
  const rows = enabled.map((name) => ({
    name,
    info: AGENT_DESCRIPTIONS[name] || {
      role: "Custom agent",
      location: "—",
    },
    state: byName.get(name) || null,
  }));

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="Agents"
        subtitle="Every agent wired to this Command Center, plus the live event bus tape."
        action={<Tag tone="accent">{enabled.length} enabled</Tag>}
      />

      <Card title="Agent family" subtitle={`Primary: ${profile?.primary_agent || "—"}`}>
        <ul className="grid md:grid-cols-2 gap-4">
          {rows.map((r) => (
            <li
              key={r.name}
              className="rounded-lg border border-bg-border bg-bg-elev p-4"
            >
              <div className="flex justify-between items-center">
                <div className="flex items-center gap-2">
                  <div
                    className={`w-2 h-2 rounded-full ${
                      r.state
                        ? "bg-status-engaged shadow-[0_0_6px_rgba(16,185,129,0.6)]"
                        : "bg-fg-faint"
                    }`}
                  />
                  <span className="text-accent font-bold uppercase tracking-[0.14em] text-sm">
                    {r.name}
                  </span>
                </div>
                {r.state ? (
                  <span className="text-xs text-status-engaged font-mono">
                    tick {r.state.tick_count}
                  </span>
                ) : (
                  <span className="text-xs text-fg-dim">idle</span>
                )}
              </div>
              <div className="text-sm text-fg mt-2.5">{r.info.role}</div>
              <div className="text-xs text-fg-dim mt-1.5 font-mono">
                {r.info.location}
              </div>
              {r.state && (
                <div className="text-xs text-fg-muted mt-3 pt-3 border-t border-bg-border">
                  Last tick {timeAgo(r.state.last_tick_at)} ·{" "}
                  <span className="font-mono">{truncate(r.state.last_tick_id || "", 12)}</span>
                </div>
              )}
            </li>
          ))}
        </ul>
      </Card>

      <Card title="Event bus" subtitle="Cross-agent coordination, most recent first">
        {events.length === 0 ? (
          <EmptyState message="No events yet. Events are published when the reasoning loop ticks or n8n inbound fires." />
        ) : (
          <ul className="divide-y divide-bg-border">
            {events.map((e) => {
              const payload = e.payload || {};
              const cls = (payload as Record<string, unknown>).classification as
                | Record<string, unknown>
                | undefined;
              const subject =
                (payload as Record<string, unknown>).subject as string | undefined;
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
                      intent: {String(cls.intent || "—")} ·{" "}
                      priority: {String(cls.priority || "—")} ·{" "}
                      sentiment: {String(cls.sentiment || "—")}
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
