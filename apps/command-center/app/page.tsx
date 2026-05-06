import Link from "next/link";
import { Card, Stat, EmptyState, PageHeader, Tag } from "@/components/Card";
import { MRRProgressChart } from "@/components/charts/MRRProgressChart";
import { PipelineFunnel } from "@/components/charts/PipelineFunnel";
import { TodayBlockToggle } from "@/components/TodayBlockToggle";
import { LiveClock } from "@/components/LiveClock";
import { timeAgo, truncate, formatTimeRange } from "@/lib/fmt";
import {
  formatOperatorDate,
  operatorDateKey,
  operatorIsWeekend,
} from "@/lib/dates";
import {
  todayCounts,
  pipelineBreakdown,
  getActiveProfile,
  getTodayPlan,
  getLeadById,
  mrrSnapshot,
  mrrHistory,
  recentInbound,
  topClientConcentration,
  outreachReplyRate,
  activePipeline,
  topOpenLead,
} from "@/lib/queries";

export const dynamic = "force-dynamic";

export default async function TodayPage() {
  const profile = await getActiveProfile();
  if (!profile) {
    return (
      <div>
        <PageHeader title="Today" subtitle="No operator profile found." />
        <Card title="Set up your profile">
          <EmptyState message="Sign in to load your profile." />
        </Card>
      </div>
    );
  }

  const tenantId = profile.tenant_id || "";

  // Same hardening pattern as layout.tsx — each query gets a default value
  // so one failing reader (e.g. a brand-new tenant with no leads, an RLS
  // edge case, a Supabase blip) can never 500 the whole Today page.
  // This is the bug class that took down the dashboard when Hermes was
  // toggled — never again.
  const safe = async <T,>(p: Promise<T>, fallback: T): Promise<T> =>
    p.catch(() => fallback);

  const [counts, pipeline, mrr, history, plan, inbound, concentration, replyRate, activePipe, topLead] =
    await Promise.all([
      safe(todayCounts(tenantId), { outbound: 0, inbound: 0, decisions: 0, hot: 0 }),
      safe(pipelineBreakdown(tenantId), { stages: {} as Record<string, number>, total: 0, sources: {} as Record<string, number> }),
      safe(mrrSnapshot(), { current: 0, target: 5000, pct: 0 }),
      safe(mrrHistory(30), [] as Array<{ date: string; mrr: number; synthetic: boolean }>),
      safe(getTodayPlan(profile.id), null),
      safe(recentInbound(tenantId, 5), []),
      safe(topClientConcentration(tenantId), { client_name: "—", pct_of_mrr: 0, is_at_risk: false }),
      safe(outreachReplyRate(tenantId, 7), { sends: 0, replies: 0, rate_pct: 0 }),
      safe(activePipeline(tenantId), { total_active: 0, qualified: 0, proposal: 0 }),
      safe(topOpenLead(tenantId), null),
    ]);

  const primaryLead = plan?.primary_lead_id
    ? await safe(getLeadById(plan.primary_lead_id), null)
    : topLead; // auto-promote highest-score open lead if no plan-level pin

  const targetDate = profile.mrr_target_date ? new Date(profile.mrr_target_date) : null;
  const daysToTarget = targetDate
    ? Math.max(0, Math.round((targetDate.getTime() - Date.now()) / (1000 * 60 * 60 * 24)))
    : null;
  const gap = Math.max(0, mrr.target - mrr.current);

  const todayKey = operatorDateKey();
  const todayLabel = formatOperatorDate({
    weekday: "long",
    month: "long",
    day: "numeric",
  });
  const isWeekend = operatorIsWeekend();
  const missionLine =
    plan?.mission ||
    (isWeekend
      ? "Weekend mode"
      : "Set a mission for today in Settings → Plan Templates");

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="Today"
        subtitle={
          <>
            <LiveClock initialDateKey={todayKey} /> · {profile.brand} · {missionLine}
          </>
        }
        action={<Tag tone={isWeekend ? "info" : "accent"}>{isWeekend ? "weekend" : "weekday"}</Tag>}
      />

      {/* Hero band — 6 metrics that actually matter */}
      <section className="grid grid-cols-2 lg:grid-cols-6 gap-4">
        <Stat
          label="Net MRR"
          value={`$${Math.round(mrr.current).toLocaleString()}`}
          accent
          hint={`${mrr.pct.toFixed(1)}% of $${Math.round(mrr.target).toLocaleString()}`}
        />
        <Stat
          label="Gap to goal"
          value={`$${Math.round(gap).toLocaleString()}`}
          hint={daysToTarget !== null ? `${daysToTarget}d to deadline` : ""}
        />
        <Stat
          label="Days left"
          value={daysToTarget !== null ? `${daysToTarget}` : "—"}
          hint={targetDate ? `until ${targetDate.toISOString().slice(5, 10)}` : ""}
        />
        <Stat
          label="Replies (7d)"
          value={`${replyRate.replies}`}
          hint={replyRate.replies > 0 ? "Inbound waiting on you" : "No replies this week"}
        />
        <Stat
          label="MRR added (7d)"
          value={(() => {
            const last = history[history.length - 1]?.mrr ?? mrr.current;
            const wkAgo = history[history.length - 8]?.mrr ?? last;
            const delta = Math.round(last - wkAgo);
            return delta >= 0 ? `+$${delta.toLocaleString()}` : `-$${Math.abs(delta).toLocaleString()}`;
          })()}
          hint={history[0]?.synthetic ? "projected (no real history yet)" : "real delta"}
        />
        <Stat
          label="Top client share"
          value={concentration.pct_of_mrr > 0 ? `${concentration.pct_of_mrr.toFixed(0)}%` : "—"}
          hint={
            concentration.is_at_risk
              ? `⚠ ${truncate(concentration.client_name, 18)}`
              : truncate(concentration.client_name, 22)
          }
        />
      </section>

      {/* Secondary band — pipeline health */}
      <section className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Stat
          label="Active pipeline"
          value={activePipe.total_active}
          hint={`${activePipe.qualified} qualified · ${activePipe.proposal} proposal`}
        />
        <Stat
          label="Reply rate (7d)"
          value={replyRate.sends > 0 ? `${replyRate.rate_pct.toFixed(1)}%` : "—"}
          hint={`${replyRate.replies} replies / ${replyRate.sends} sent`}
        />
        <Stat
          label="Decisions today"
          value={counts.decisions}
          hint={counts.decisions > 0 ? "agent ticks" : "quiet"}
        />
        <Stat
          label="Pipeline (all)"
          value={pipeline.total}
          hint={`${pipeline.stages.qualified || 0} qualified · ${pipeline.stages.won || 0} won`}
        />
      </section>

      <section className="grid lg:grid-cols-3 gap-6">
        <Card
          title="MRR · 30-day trajectory"
          subtitle={`Target ${targetDate?.toISOString().slice(0, 10) || "—"}`}
          action={history[0]?.synthetic ? <Tag tone="warm">projected</Tag> : null}
        >
          <MRRProgressChart data={history} target={mrr.target} />
        </Card>

        <Card
          title="Primary lead"
          subtitle={
            primaryLead
              ? `Top open · ${primaryLead.company || primaryLead.name}`
              : "No active lead"
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
                <div className="text-fg font-semibold mt-2">{primaryLead.name}</div>
                <div className="text-fg-muted text-sm">{primaryLead.company}</div>
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
            <EmptyState message="No active lead in the pipeline." />
          )}
        </Card>
      </section>

      {plan?.schedule && plan.schedule.length > 0 ? (
        <Card
          title="The day"
          subtitle={`${plan.schedule.filter((s) => s.completed).length} / ${plan.schedule.length} done`}
        >
          <ul className="divide-y divide-bg-border">
            {plan.schedule.map((slot, i) => (
              <li
                key={i}
                className={`grid grid-cols-[1.75rem_7rem_1fr] gap-3 py-3.5 ${
                  slot.intensity === "break" ? "opacity-70" : ""
                } ${slot.completed ? "opacity-60" : ""}`}
              >
                <TodayBlockToggle index={i} initial={!!slot.completed} schedule={plan.schedule} />
                <div className="text-accent text-xs font-bold tracking-wider self-start mt-0.5">
                  {formatTimeRange(slot.time_label)}
                </div>
                <div>
                  <div
                    className={`text-fg font-semibold flex items-center gap-2 ${slot.completed ? "line-through text-fg-muted" : ""}`}
                  >
                    {slot.intensity === "intense" && <span className="text-accent">▲</span>}
                    {slot.intensity === "break" && <span className="text-fg-dim">○</span>}
                    {slot.intensity === "carryover" && (
                      <Tag tone="warm">carried from yesterday</Tag>
                    )}
                    {slot.title}
                  </div>
                  <div className="text-fg-muted text-sm mt-1 leading-relaxed">{slot.body}</div>
                </div>
              </li>
            ))}
          </ul>
        </Card>
      ) : (
        <Card
          title="The day"
          subtitle={`No ${isWeekend ? "weekend" : "weekday"} template yet`}
          action={
            <Link
              href="/settings"
              className="btn-primary inline-flex items-center gap-1.5 !text-xs !py-1.5"
            >
              Set up in Settings
            </Link>
          }
        >
          <EmptyState
            message={`Open Settings → ${isWeekend ? "Weekend" : "Weekday"} Template, click "Load defaults" + Save, and today's plan auto-fills.`}
          />
        </Card>
      )}

      <section className="grid lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <Card
            title="Recent inbound"
            subtitle={
              inbound.length > 0
                ? `${inbound.length} latest · most recent ${timeAgo(inbound[0].created_at)}`
                : "n8n inbound bridge — see diagnostic if stale"
            }
            action={
              <Link
                href="/integrations"
                className="text-xs text-fg-muted hover:text-accent transition-colors"
              >
                {inbound.length === 0 || (inbound[0] && Date.now() - new Date(inbound[0].created_at).getTime() > 7 * 24 * 60 * 60 * 1000)
                  ? "Check n8n →"
                  : null}
              </Link>
            }
          >
            {inbound.length === 0 ? (
              <EmptyState
                message="No inbound rows yet. If you've received emails recently, the n8n 'OASIS Inbound Qualifier' workflow on Hostinger may be down. Run scripts/n8n_inbound_doctor.py to diagnose."
              />
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
                        <span className="text-xs text-fg-dim">{timeAgo(i.created_at)}</span>
                      </div>
                      <div className="text-fg mt-1.5 text-sm">{truncate(i.subject, 80)}</div>
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
