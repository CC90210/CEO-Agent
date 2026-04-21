import { Card, Stat, EmptyState } from "@/components/Card";
import { timeAgo, truncate, statusColor, intentColor } from "@/lib/fmt";
import {
  todayCounts,
  pipelineBreakdown,
  recentDecisions,
  recentInbound,
  channelUtilization,
} from "@/lib/queries";

export const dynamic = "force-dynamic";  // live dashboard — always fetch on request, never at build time.

export default async function TodayPage() {
  const [counts, pipeline, decisions, inbound, caps] = await Promise.all([
    todayCounts(),
    pipelineBreakdown(),
    recentDecisions(8),
    recentInbound(8),
    channelUtilization(),
  ]);

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-2xl font-bold tracking-tight">Today</h1>
        <p className="text-sm text-fg-muted mt-1">
          Everything Bravo, Atlas, and Maven have done since midnight. Live.
        </p>
      </header>

      {/* Top-row counters */}
      <section className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Stat label="Outbound sends" value={counts.outbound} accent />
        <Stat label="Inbound received" value={counts.inbound} />
        <Stat label="Agent decisions" value={counts.decisions} />
        <Stat
          label="Hot / escalated"
          value={counts.hot}
          hint={counts.hot > 0 ? "Check Inbound tab" : "Quiet"}
        />
      </section>

      {/* Channel caps */}
      <Card
        title="Daily channel caps"
        subtitle="Gateway refuses sends once caps hit"
      >
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {caps.map((c) => (
            <div key={c.channel} className="rounded border border-bg-border p-3">
              <div className="flex justify-between text-xs text-fg-muted uppercase tracking-wider">
                <span>{c.channel}</span>
                <span>{c.used}/{c.cap}</span>
              </div>
              <div className="mt-2 h-2 w-full bg-bg-raised rounded-full overflow-hidden">
                <div
                  className={`h-full ${
                    c.pct >= 90
                      ? "bg-status-hot"
                      : c.pct >= 60
                        ? "bg-status-warm"
                        : "bg-accent"
                  }`}
                  style={{ width: `${Math.min(c.pct, 100)}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      </Card>

      {/* Two-column recent activity */}
      <section className="grid md:grid-cols-2 gap-6">
        <Card title="Recent decisions" subtitle={`${decisions.length} latest`}>
          {decisions.length === 0 ? (
            <EmptyState message="No decisions yet today. Run python scripts/autonomous_agent.py tick" />
          ) : (
            <ul className="space-y-3 text-sm">
              {decisions.map((d) => (
                <li key={d.id} className="border-b border-bg-border pb-3 last:border-0">
                  <div className="flex justify-between gap-3">
                    <span className="font-mono text-xs text-fg-muted">
                      {d.decision_type}
                    </span>
                    <span className={`text-xs ${statusColor(d.outcome_status)}`}>
                      {d.outcome_status || d.chosen_action}
                    </span>
                  </div>
                  <div className="text-fg mt-1">
                    {truncate(d.target_description, 90)}
                  </div>
                  <div className="text-xs text-fg-dim mt-1">
                    {timeAgo(d.created_at)}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="Recent inbound" subtitle={`${inbound.length} latest`}>
          {inbound.length === 0 ? (
            <EmptyState message="No inbound today. (Is the IMAP cron running?)" />
          ) : (
            <ul className="space-y-3 text-sm">
              {inbound.map((i) => {
                const meta = (i.metadata || {}) as Record<string, unknown>;
                const cls = (meta.classification || {}) as Record<string, unknown>;
                return (
                  <li key={i.id} className="border-b border-bg-border pb-3 last:border-0">
                    <div className="flex justify-between gap-3">
                      <span className={`text-xs ${intentColor(cls.intent as string)}`}>
                        {(cls.intent as string) || "unclassified"}
                      </span>
                      <span className={`text-xs ${statusColor(cls.priority as string)}`}>
                        {(cls.priority as string) || "—"}
                      </span>
                    </div>
                    <div className="text-fg mt-1">{truncate(i.subject, 90)}</div>
                    <div className="text-xs text-fg-dim mt-1">
                      {(meta.from_identity as string) || "—"} · {timeAgo(i.created_at)}
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </Card>
      </section>

      {/* Pipeline */}
      <Card title="Pipeline" subtitle={`${pipeline.total} leads total`}>
        <div className="grid grid-cols-3 md:grid-cols-6 gap-3 text-center">
          {(["new", "contacted", "qualified", "proposal", "won", "lost"] as const).map((stage) => (
            <div key={stage} className="rounded border border-bg-border p-3">
              <div className="text-xs uppercase tracking-wider text-fg-muted">
                {stage}
              </div>
              <div className="text-2xl font-bold text-fg mt-1">
                {pipeline.stages[stage] || 0}
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
