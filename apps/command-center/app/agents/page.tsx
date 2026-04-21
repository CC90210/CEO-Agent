import { Card, EmptyState } from "@/components/Card";
import { timeAgo, truncate } from "@/lib/fmt";
import { agentStates, recentEvents } from "@/lib/queries";

export const dynamic = "force-dynamic";

const AGENT_DESCRIPTIONS: Record<string, { role: string; location: string }> = {
  bravo: {
    role: "Lead architect · business ops · content voice",
    location: "this repo",
  },
  codex: {
    role: "Backend executor · deep debugging · adversarial review",
    location: "this repo (Codex extension)",
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
    role: "Life / home · Raspberry Pi · voice · habits",
    location: "C:\\Users\\User\\AURA",
  },
};

export default async function AgentsPage() {
  const [states, events] = await Promise.all([
    agentStates(),
    recentEvents(25),
  ]);

  // Merge known-agent stubs so the page shows the full family even when
  // some agents haven't checked in yet.
  const knownAgents = Object.keys(AGENT_DESCRIPTIONS);
  const byName = new Map(states.map((s) => [s.agent_name, s]));
  const rows = knownAgents.map((name) => ({
    name,
    info: AGENT_DESCRIPTIONS[name],
    state: byName.get(name) || null,
  }));

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold tracking-tight">Agents</h1>
        <p className="text-sm text-fg-muted mt-1">
          Every agent in CC's empire, their current state, and the event bus
          tape showing what they're publishing to each other.
        </p>
      </header>

      <Card title="C-Suite family" subtitle="Bravo, Codex, Atlas, Maven, Aura">
        <ul className="grid md:grid-cols-2 gap-4">
          {rows.map((r) => (
            <li
              key={r.name}
              className="rounded border border-bg-border bg-bg-raised p-4"
            >
              <div className="flex justify-between items-baseline">
                <span className="text-accent font-bold uppercase tracking-wider">
                  {r.name}
                </span>
                {r.state ? (
                  <span className="text-xs text-status-engaged">
                    healthy · tick {r.state.tick_count}
                  </span>
                ) : (
                  <span className="text-xs text-fg-dim">not yet ticked</span>
                )}
              </div>
              <div className="text-sm text-fg mt-2">{r.info.role}</div>
              <div className="text-xs text-fg-dim mt-2 font-mono">
                {r.info.location}
              </div>
              {r.state && (
                <div className="text-xs text-fg-muted mt-3">
                  Last tick {timeAgo(r.state.last_tick_at)} ·{" "}
                  <span className="font-mono">{r.state.last_tick_id}</span>
                </div>
              )}
            </li>
          ))}
        </ul>
      </Card>

      <Card title="Event bus" subtitle="Cross-agent coordination, most recent first">
        {events.length === 0 ? (
          <EmptyState message="No events yet. Events are published when the reasoning loop ticks or N8N inbound fires." />
        ) : (
          <ul className="space-y-2 text-sm">
            {events.map((e) => {
              const payload = e.payload || {};
              const cls = (payload as Record<string, unknown>).classification as
                | Record<string, unknown>
                | undefined;
              const subject =
                (payload as Record<string, unknown>).subject as string | undefined;
              return (
                <li
                  key={e.id}
                  className="border-b border-bg-border last:border-0 pb-2"
                >
                  <div className="flex justify-between items-baseline gap-3">
                    <span className="font-mono text-xs text-accent">
                      {e.event_type}
                    </span>
                    <span className="text-xs text-fg-dim">
                      {e.publisher_agent} · {timeAgo(e.published_at)}
                    </span>
                  </div>
                  {subject && (
                    <div className="text-fg mt-1">{truncate(subject, 100)}</div>
                  )}
                  {cls && (
                    <div className="text-xs text-fg-muted mt-1">
                      {String(cls.intent || "—")} ·{" "}
                      {String(cls.priority || "—")} ·{" "}
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
