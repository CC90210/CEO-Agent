import { Card, Stat, EmptyState, PageHeader, Tag } from "@/components/Card";
import { MRRProgressChart } from "@/components/charts/MRRProgressChart";
import { PipelineFunnel } from "@/components/charts/PipelineFunnel";
import { ChannelGauge } from "@/components/charts/ChannelGauge";
import { timeAgo, truncate, statusColor } from "@/lib/fmt";
import {
  todayCounts,
  pipelineBreakdown,
  channelUtilization,
  getActiveProfile,
  getTodayPlan,
  getLeadById,
  mrrSnapshot,
  mrrHistory,
  recentInbound,
} from "@/lib/queries";

export const dynamic = "force-dynamic";

export default async function TodayPage() {
  const profile = await getActiveProfile();
  if (!profile) {
    return (
      <div>
        <PageHeader
          title="Today"
          subtitle="No operator profile found."
        />
        <Card title="Set up your profile">
          <EmptyState
            message="Run the OASIS AI setup wizard to create your operator profile, or seed it manually with `python scripts/seed_profile.py`."
          />
        </Card>
      </div>
    );
  }

  const [counts, pipeline, caps, mrr, history, plan, inbound] = await Promise.all([
    todayCounts(),
    pipelineBreakdown(),
    channelUtilization(),
    mrrSnapshot(),
    mrrHistory(30),
    getTodayPlan(profile.id),
    recentInbound(5),
  ]);

  const primaryLead = plan?.primary_lead_id
    ? await getLeadById(plan.primary_lead_id)
    : null;

  const targetDate = profile.mrr_target_date
    ? new Date(profile.mrr_target_date)
    : null;
  const daysToTarget = targetDate
    ? Math.max(
        0,
        Math.round(
          (targetDate.getTime() - Date.now()) / (1000 * 60 * 60 * 24)
        )
      )
    : null;
  const gap = Math.max(0, mrr.target - mrr.current);

  const today = new Date();
  const todayLabel = today.toLocaleDateString(undefined, {
    weekday: "long",
    month: "long",
    day: "numeric",
  });

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="Today"
        subtitle={`${todayLabel} · ${profile.brand} · ${plan?.mission || "No mission set for today."}`}
      />

      {/* Hero stat band — MRR + key counters */}
      <section className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Stat
          label="Net MRR"
          value={`$${Math.round(mrr.current).toLocaleString()}`}
          accent
          hint={`${mrr.pct.toFixed(1)}% to $${Math.round(mrr.target).toLocaleString()}`}
        />
        <Stat
          label="Gap to goal"
          value={`$${Math.round(gap).toLocaleString()}`}
          hint={daysToTarget !== null ? `${daysToTarget} days left` : "—"}
        />
        <Stat
          label="Calls today"
          value={`${counts.outbound}`}
          hint={plan?.target_calls ? `target ${plan.target_calls}` : ""}
        />
        <Stat
          label="Hot inbound"
          value={`${counts.hot}`}
          hint={counts.hot > 0 ? "Check Pipeline" : "Quiet"}
        />
      </section>

      {/* Two-col: MRR chart + Primary Lead */}
      <section className="grid lg:grid-cols-3 gap-6">
        <Card
          title="MRR · 30-day trajectory"
          subtitle={`Target ${targetDate?.toISOString().slice(0, 10) || "—"}`}
          action={
            history[0]?.synthetic ? <Tag tone="warm">projected</Tag> : null
          }
        >
          <MRRProgressChart data={history} target={mrr.target} />
        </Card>

        <Card
          title="Primary lead"
          subtitle={
            primaryLead
              ? `Today's #1 — ${primaryLead.company || primaryLead.name}`
              : "No primary lead set"
          }
        >
          {primaryLead ? (
            <div className="space-y-3">
              <div>
                <div className="flex items-center gap-2">
                  <Tag tone={primaryLead.status === "qualified" ? "engaged" : "accent"}>
                    {primaryLead.status || "new"}
                  </Tag>
                  <span className="text-xs text-fg-muted">
                    score {primaryLead.score ?? "—"}
                  </span>
                </div>
                <div className="text-fg font-semibold mt-2">
                  {primaryLead.name}
                </div>
                <div className="text-fg-muted text-sm">
                  {primaryLead.company}
                </div>
                {primaryLead.phone && (
                  <div className="text-xs text-fg-dim font-mono mt-1">
                    {primaryLead.phone}
                  </div>
                )}
              </div>
              {plan?.primary_lead_play && (
                <div className="bg-accent-soft border-l-2 border-accent rounded-r-md px-3 py-2.5 text-sm text-fg">
                  {plan.primary_lead_play}
                </div>
              )}
            </div>
          ) : (
            <EmptyState message="No primary lead pinned for today." />
          )}
        </Card>
      </section>

      {/* Pipeline + channel caps */}
      <section className="grid lg:grid-cols-2 gap-6">
        <Card
          title="Pipeline"
          subtitle={`${pipeline.total} leads across all stages`}
        >
          <PipelineFunnel stages={pipeline.stages} />
        </Card>

        <Card
          title="Channel caps"
          subtitle="Send gateway enforces these"
        >
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {caps.map((c) => (
              <ChannelGauge key={c.channel} {...c} />
            ))}
          </div>
        </Card>
      </section>

      {/* Today's schedule */}
      {plan?.schedule && plan.schedule.length > 0 && (
        <Card title="The day" subtitle={`${plan.schedule.length} blocks scheduled`}>
          <ul className="divide-y divide-bg-border">
            {plan.schedule.map((slot, i) => (
              <li
                key={i}
                className={`grid grid-cols-[7rem_1fr] gap-5 py-3.5 ${
                  slot.intensity === "break" ? "opacity-70" : ""
                }`}
              >
                <div className="text-accent text-xs font-bold tracking-wider self-start mt-0.5">
                  {slot.time_label}
                </div>
                <div>
                  <div className="text-fg font-semibold flex items-center gap-2">
                    {slot.intensity === "intense" && (
                      <span className="text-accent">▲</span>
                    )}
                    {slot.intensity === "break" && (
                      <span className="text-fg-dim">○</span>
                    )}
                    {slot.title}
                  </div>
                  <div className="text-fg-muted text-sm mt-1 leading-relaxed">
                    {slot.body}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {/* Recent inbound + manifesto */}
      <section className="grid lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <Card title="Recent inbound" subtitle={`${inbound.length} latest`}>
            {inbound.length === 0 ? (
              <EmptyState message="No inbound yet today." />
            ) : (
              <ul className="divide-y divide-bg-border">
                {inbound.map((i) => {
                  const meta = (i.metadata || {}) as Record<string, unknown>;
                  const cls = (meta.classification || {}) as Record<string, unknown>;
                  return (
                    <li key={i.id} className="py-3">
                      <div className="flex items-center gap-2">
                        <Tag
                          tone={
                            (cls.intent as string) === "booking"
                              ? "engaged"
                              : (cls.intent as string) === "objection"
                                ? "hot"
                                : "neutral"
                          }
                        >
                          {(cls.intent as string) || "unclassified"}
                        </Tag>
                        <span className="text-xs text-fg-dim">
                          {timeAgo(i.created_at)}
                        </span>
                      </div>
                      <div className="text-fg mt-1.5 text-sm">
                        {truncate(i.subject, 80)}
                      </div>
                      <div className="text-xs text-fg-dim mt-0.5 font-mono">
                        {(meta.from_identity as string) || "—"}
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </Card>
        </div>

        {profile.manifesto && (
          <Card title="Direction" subtitle="Read this when you don't feel like making the next call">
            <div className="prose-manifesto text-sm">
              {profile.manifesto.split("\n\n").slice(0, 6).map((para, i) => (
                <p key={i}>{para}</p>
              ))}
              <p className="closing">— {profile.full_name}</p>
            </div>
          </Card>
        )}
      </section>
    </div>
  );
}
