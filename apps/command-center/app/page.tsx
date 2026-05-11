import Link from "next/link";
import { Card, Stat, EmptyState, PageHeader, Tag } from "@/components/Card";
import { MRRProgressChart } from "@/components/charts/MRRProgressChart";
import { PipelineFunnel } from "@/components/charts/PipelineFunnel";
import { TodayBlockToggle } from "@/components/TodayBlockToggle";
import { TodayBlockEditableField } from "@/components/TodayBlockEditableField";
import { FinalizeDayButton } from "@/components/FinalizeDayButton";
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
import { computeStreak } from "@/lib/streak";
import { safe } from "@/lib/api-helpers";
import { GoalCountdownCard } from "@/components/GoalCountdownCard";

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

  // safe(label, p, fallback) imported from @/lib/api-helpers — used across
  // every dynamic page so one bad reader can't 500 the whole render. The
  // label tags failures in Vercel logs ([safe:today.counts] ...) so a
  // silently-empty Stat is debuggable. This is the Hermes-toggle bug class.
  const [counts, pipeline, mrr, history, plan, inbound, concentration, replyRate, activePipe, topLead, streak] =
    await Promise.all([
      safe("today.counts", todayCounts(tenantId), { outbound: 0, inbound: 0, decisions: 0, hot: 0 }),
      safe("today.pipeline_breakdown", pipelineBreakdown(tenantId), { stages: {} as Record<string, number>, total: 0, sources: {} as Record<string, number> }),
      safe("today.mrr_snapshot", mrrSnapshot(), { current: 0, target: 5000, pct: 0 }),
      safe("today.mrr_history", mrrHistory(30), [] as Array<{ date: string; mrr: number; synthetic: boolean }>),
      safe("today.plan", getTodayPlan(profile.id), null),
      safe("today.recent_inbound", recentInbound(tenantId, 5), []),
      safe("today.top_client_concentration", topClientConcentration(tenantId), { client_name: "—", pct_of_mrr: 0, is_at_risk: false }),
      safe("today.outreach_reply_rate", outreachReplyRate(tenantId, 7), { sends: 0, replies: 0, rate_pct: 0 }),
      safe("today.active_pipeline", activePipeline(tenantId), { total_active: 0, qualified: 0, proposal: 0 }),
      safe("today.top_open_lead", topOpenLead(tenantId), null),
      safe("today.streak", computeStreak(profile.id, 7), { streak: 0, missed: 0, daysWithPlan: 0, byDay: [] }),
    ]);

  const primaryLead = plan?.primary_lead_id
    ? await safe("today.primary_lead", getLeadById(plan.primary_lead_id), null)
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

      <GoalCountdownCard
        current={mrr.current}
        target={mrr.target}
        daysLeft={daysToTarget}
        targetDate={targetDate ? targetDate.toISOString().slice(0, 10) : null}
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
        (() => {
          const remaining = plan.schedule.filter((s) => !s.completed);
          const completed = plan.schedule.filter((s) => s.completed);
          const allDone = remaining.length === 0 && plan.schedule.length > 0;
          const finalizedAt = (plan as Record<string, unknown>).finalized_at as
            | string
            | null
            | undefined;
          return (
            <Card
              title="The day"
              subtitle={`${completed.length} / ${plan.schedule.length} done`}
              action={
                streak.daysWithPlan > 0 ? (
                  streak.streak > 0 ? (
                    <Tag tone="engaged">{`🔥 ${streak.streak}-day streak`}</Tag>
                  ) : streak.missed > 0 ? (
                    <Tag tone="warm">{`${streak.missed} missed day${streak.missed === 1 ? "" : "s"} this week`}</Tag>
                  ) : null
                ) : null
              }
            >
              {remaining.length === 0 && !finalizedAt ? (
                <div className="rounded-lg border border-status-engaged/30 bg-status-engaged/5 p-4 text-sm text-status-engaged text-center">
                  Every item checked. Hit <strong>Finalize day</strong> below to wrap.
                </div>
              ) : (
                <ul className="divide-y divide-bg-border">
                  {remaining.map((slot) => {
                    const i = plan.schedule.indexOf(slot);
                    return (
                      <li
                        key={i}
                        className={`grid grid-cols-[1.75rem_7rem_1fr] gap-3 py-3.5 ${
                          slot.intensity === "break" ? "opacity-70" : ""
                        }`}
                      >
                        <TodayBlockToggle index={i} initial={false} schedule={plan.schedule} />
                        <div className="text-accent text-xs font-bold tracking-wider self-start mt-0.5">
                          {formatTimeRange(slot.time_label)}
                        </div>
                        <div>
                          <div className="text-fg font-semibold flex items-center gap-2">
                            {slot.intensity === "intense" && <span className="text-accent">▲</span>}
                            {slot.intensity === "break" && <span className="text-fg-dim">○</span>}
                            <TodayBlockEditableField
                              index={i}
                              field="title"
                              initial={slot.title || ""}
                              schedule={plan.schedule}
                              className="flex-1"
                            />
                          </div>
                          <div className="text-fg-muted text-sm mt-1 leading-relaxed">
                            <TodayBlockEditableField
                              index={i}
                              field="body"
                              initial={slot.body || ""}
                              schedule={plan.schedule}
                              multiline
                            />
                          </div>
                        </div>
                      </li>
                    );
                  })}
                </ul>
              )}

              {/* Completed today — collapsible, click-only-when-needed */}
              {completed.length > 0 && (
                <details className="mt-4 group">
                  <summary className="cursor-pointer text-xs text-fg-muted hover:text-accent inline-flex items-center gap-1 select-none">
                    <span className="group-open:rotate-90 transition-transform inline-block">›</span>
                    {completed.length} completed today
                  </summary>
                  <ul className="mt-2 divide-y divide-bg-border opacity-60">
                    {completed.map((slot) => {
                      const i = plan.schedule.indexOf(slot);
                      const completedAt = (slot as Record<string, unknown>).completed_at as
                        | string
                        | null
                        | undefined;
                      return (
                        <li
                          key={i}
                          className="grid grid-cols-[1.75rem_7rem_1fr] gap-3 py-2"
                        >
                          <TodayBlockToggle index={i} initial={true} schedule={plan.schedule} />
                          <div className="text-fg-dim text-xs font-mono self-start mt-0.5">
                            {formatTimeRange(slot.time_label)}
                          </div>
                          <div>
                            <div className="text-fg-muted text-sm line-through">{slot.title}</div>
                            {completedAt && (
                              <div className="text-[10px] text-status-engaged font-mono mt-0.5">
                                ✓ {new Date(completedAt).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}
                              </div>
                            )}
                          </div>
                        </li>
                      );
                    })}
                  </ul>
                </details>
              )}

              {/* Finalize day — operator's nightly checkpoint */}
              <div className="mt-5 pt-4 border-t border-bg-border flex items-center justify-between gap-3 flex-wrap">
                <div className="text-xs text-fg-muted">
                  {finalizedAt
                    ? `Day finalized at ${new Date(finalizedAt).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}. Tomorrow rebuilds fresh from your template.`
                    : allDone
                      ? "Every item checked off — you can finalize the day."
                      : `${remaining.length} item${remaining.length === 1 ? "" : "s"} left to finalize the day.`}
                </div>
                <FinalizeDayButton disabled={!allDone || !!finalizedAt} planId={plan.id || null} />
              </div>
            </Card>
          );
        })()
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
                  const intent = (cls.intent as string) || "unclassified";
                  const summary = (cls.summary as string) || "";
                  const action = (cls.agent_action as string) || "";
                  const tone =
                    intent === "hot_lead" || intent === "frustrated"
                      ? "hot"
                      : intent === "sales" || intent === "business_opportunity" || intent === "partnership" || intent === "booking"
                        ? "engaged"
                        : intent === "strategic" || intent === "pricing_question"
                          ? "accent"
                          : intent === "ambiguous" || intent === "security"
                            ? "warm"
                            : "neutral";
                  return (
                    <li key={i.id} className="py-3">
                      <Link
                        href={`/interactions/${i.id}`}
                        className="block -mx-2 px-2 py-1 rounded-md hover:bg-bg-elev transition-colors"
                      >
                        <div className="flex items-center gap-2">
                          <Tag tone={tone}>{intent}</Tag>
                          {action && action !== "silent_skip" && (
                            <span className="text-[10px] uppercase tracking-wider font-bold text-fg-dim">
                              {action.replace("_", " ")}
                            </span>
                          )}
                          <span className="text-xs text-fg-dim ml-auto">{timeAgo(i.created_at)}</span>
                        </div>
                        <div className="text-fg mt-1.5 text-sm">{truncate(i.subject, 80)}</div>
                        {summary ? (
                          <div className="text-xs text-fg-muted mt-1 leading-relaxed">{truncate(summary, 140)}</div>
                        ) : (
                          <div className="text-xs text-fg-dim mt-0.5 font-mono">
                            {(meta.from_identity as string) || "—"}
                          </div>
                        )}
                      </Link>
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
