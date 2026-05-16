/**
 * /health — single-pane "is the system healthy" dashboard.
 *
 * Round 3 R3-13. Operator request: "no errors-in-last-24h view, no
 * stuck-thread alerts, no Telegram on daemon crashes ... operator
 * has no way to tell if system is OK at a glance."
 *
 * Four data tiles:
 *
 *   1. Recent error/warn events from agent_events (last 24h)
 *      Sources: daemon crashes (Round 3 R3-11 notify path), cron
 *      failures that ERROR-prefix their last_result, app-level
 *      route warnings (forms/submit stage_warning, etc.).
 *
 *   2. Crons that failed their last run
 *      Joins empire `cron_jobs` (last_result starts with 'ERROR' or
 *      'FAILED' or 'unknown_action_type') + tenant `tenant_cron_jobs`
 *      (last_run_status = 'error').
 *
 *   3. Lender threads stuck at status='sent' > 7 days
 *      Means a shop-out went out, no reply within the SLA window,
 *      and the classifier daemon's SLA-sweep hasn't auto-flipped
 *      them to 'no_response' yet. Operator should chase manually.
 *
 *   4. Leads stuck in the same stage > 14 days
 *      Pipeline stall. Drip sequences should have moved them or the
 *      operator should disposition. Listed by stage so operator can
 *      see WHERE the pipeline is sticking.
 *
 * Page is server-rendered + dynamic (no caching) so the operator
 * always sees the current state. Refresh = page reload.
 */

import { PageHeader, Card, Tag } from "@/components/Card";
import { getServiceSupabase } from "@/lib/supabase-server";
import { resolveTenantId } from "@/lib/api-auth";
import { getTenantEnabledAgents } from "@/lib/manifest/tenant-scope";
import { redirect } from "next/navigation";
import Link from "next/link";
import { AlertCircle, AlertTriangle, Clock, Activity, CheckCircle2 } from "lucide-react";

export const dynamic = "force-dynamic";

type ErrorEvent = {
  id: string;
  event_type: string;
  severity: string;
  publisher_agent: string | null;
  payload: Record<string, unknown> | null;
  published_at: string;
};

type FailedCron = {
  id: string;
  name: string;
  schedule: string;
  last_run_at: string | null;
  last_result: string | null;
  source: "empire" | "tenant";
};

type StuckThread = {
  id: string;
  application_id: string;
  lender_id: string | null;
  recipient_email: string | null;
  status: string;
  sent_at: string | null;
};

type StuckLead = {
  id: string;
  data: Record<string, unknown>;
  updated_at: string;
};

async function loadHealth(tenantId: string, enabledAgents: string[]) {
  const db = getServiceSupabase();
  const now = Date.now();
  const dayAgoIso = new Date(now - 24 * 60 * 60 * 1000).toISOString();
  const weekAgoIso = new Date(now - 7 * 24 * 60 * 60 * 1000).toISOString();
  const twoWeeksAgoIso = new Date(now - 14 * 24 * 60 * 60 * 1000).toISOString();

  // All four lookups are independent — fire in parallel so the page
  // renders in max(query) instead of sum(query).
  //
  // 1. Recent error/warn events from agent_events. The table has no
  //    tenant_id column (legacy schema debt); scope by the tenant's
  //    enabled-agent set, same posture todayCounts takes. Empty
  //    enabled-agents → resolved promise of empty list, no round trip.
  const recentErrorsPromise = enabledAgents.length > 0
    ? db
        .from("agent_events")
        .select("id, event_type, severity, publisher_agent, payload, published_at")
        .in("publisher_agent", enabledAgents)
        .in("severity", ["error", "warn"])
        .gte("published_at", dayAgoIso)
        .order("published_at", { ascending: false })
        .limit(50)
        .then((res) => (res.data as ErrorEvent[]) || [])
    : Promise.resolve<ErrorEvent[]>([]);

  // 2a + 2b. Failed crons across both registries.
  const empireFailedPromise = db
    .from("cron_jobs")
    .select("id, name, schedule, last_run_at, last_result")
    .or(
      "last_result.like.ERROR%,last_result.like.FAILED%,last_result.like.unknown_action_type%",
    )
    .order("last_run_at", { ascending: false })
    .limit(20);
  const tenantFailedPromise = db
    .from("tenant_cron_jobs")
    .select("id, name, schedule, last_run_at, last_run_status, last_run_error")
    .eq("tenant_id", tenantId)
    .eq("last_run_status", "error")
    .order("last_run_at", { ascending: false })
    .limit(20);

  // 3. Lender threads stuck at sent>7d.
  const stuckThreadsPromise = db
    .from("application_lender_threads")
    .select("id, application_id, lender_id, recipient_email, status, sent_at")
    .eq("tenant_id", tenantId)
    .eq("status", "sent")
    .lt("sent_at", weekAgoIso)
    .order("sent_at", { ascending: true })
    .limit(50)
    .then((res) => (res.data as StuckThread[]) || []);

  // 4. Lead rows with updated_at >14d. Cap at 50 — the operator only
  //    needs the worst offenders; if there are more, the count tile
  //    will under-report but the list stays scannable.
  const stuckLeadsPromise = db
    .from("tenant_records")
    .select("id, data, updated_at")
    .eq("tenant_id", tenantId)
    .eq("entity_type", "lead")
    .lt("updated_at", twoWeeksAgoIso)
    .order("updated_at", { ascending: true })
    .limit(50)
    .then((res) => (res.data as StuckLead[]) || []);

  const [recentErrors, empireFailed, tenantFailed, stuckThreads, stuckLeads] =
    await Promise.all([
      recentErrorsPromise,
      empireFailedPromise,
      tenantFailedPromise,
      stuckThreadsPromise,
      stuckLeadsPromise,
    ]);

  const failedCrons: FailedCron[] = [
    ...((empireFailed.data || []) as Array<{
      id: string;
      name: string;
      schedule: string;
      last_run_at: string | null;
      last_result: string | null;
    }>).map((c) => ({ ...c, source: "empire" as const })),
    ...((tenantFailed.data || []) as Array<{
      id: string;
      name: string;
      schedule: string;
      last_run_at: string | null;
      last_run_error: string | null;
    }>).map((c) => ({
      id: c.id,
      name: c.name,
      schedule: c.schedule,
      last_run_at: c.last_run_at,
      last_result: c.last_run_error,
      source: "tenant" as const,
    })),
  ];

  return { recentErrors, failedCrons, stuckThreads, stuckLeads };
}

export default async function HealthPage() {
  const tenantId = await resolveTenantId();
  if (!tenantId) redirect("/login");
  const enabledAgents = await getTenantEnabledAgents(tenantId);
  const { recentErrors, failedCrons, stuckThreads, stuckLeads } = await loadHealth(
    tenantId,
    enabledAgents,
  );

  const totalSignals =
    recentErrors.length + failedCrons.length + stuckThreads.length + stuckLeads.length;
  const overallHealthy = totalSignals === 0;

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="System health"
        subtitle="Errors, failed crons, stuck threads, and leads that haven't moved in 14 days. One pane to know if anything needs you."
        action={
          overallHealthy ? (
            <Tag tone="engaged">
              <CheckCircle2 className="w-3 h-3 inline mr-1" />
              All clear
            </Tag>
          ) : (
            <Tag tone="warm">{totalSignals} signal{totalSignals === 1 ? "" : "s"}</Tag>
          )
        }
      />

      {/* ── Tile grid ──────────────────────────────────────────── */}
      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <HealthTile
          label="Errors (24h)"
          count={recentErrors.length}
          icon={<AlertCircle className="w-4 h-4" />}
          tone={recentErrors.length === 0 ? "engaged" : "warm"}
        />
        <HealthTile
          label="Failed crons"
          count={failedCrons.length}
          icon={<AlertTriangle className="w-4 h-4" />}
          tone={failedCrons.length === 0 ? "engaged" : "warm"}
        />
        <HealthTile
          label="Stuck shop-outs (>7d)"
          count={stuckThreads.length}
          icon={<Clock className="w-4 h-4" />}
          tone={stuckThreads.length === 0 ? "engaged" : "accent"}
        />
        <HealthTile
          label="Stale leads (>14d)"
          count={stuckLeads.length}
          icon={<Activity className="w-4 h-4" />}
          tone={stuckLeads.length === 0 ? "engaged" : "accent"}
        />
      </div>

      {/* ── Error events ────────────────────────────────────────── */}
      <Card title={`Recent errors / warnings`} subtitle="Last 24h from agent_events">
        {recentErrors.length === 0 ? (
          <div className="text-sm text-fg-muted">No errors or warnings in the last 24 hours.</div>
        ) : (
          <ul className="space-y-2 text-sm">
            {recentErrors.map((ev) => (
              <li key={ev.id} className="rounded-lg border border-bg-border bg-bg-deep/40 p-3">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <Tag tone={ev.severity === "error" ? "warm" : "accent"}>{ev.severity}</Tag>
                    <span className="font-mono text-[11px] text-fg-dim">{ev.event_type}</span>
                    {ev.publisher_agent && (
                      <span className="text-[10px] uppercase tracking-wider text-fg-dim">
                        {ev.publisher_agent}
                      </span>
                    )}
                  </div>
                  <span className="text-[10px] text-fg-dim">
                    {new Date(ev.published_at).toLocaleString()}
                  </span>
                </div>
                {ev.payload && (
                  <div className="mt-1 text-[11px] text-fg-muted font-mono break-words max-h-24 overflow-y-auto">
                    {JSON.stringify(ev.payload).slice(0, 400)}
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>

      {/* ── Failed crons ────────────────────────────────────────── */}
      <Card title="Failed crons" subtitle="Crons whose last run errored. Fix the underlying handler or disable the job.">
        {failedCrons.length === 0 ? (
          <div className="text-sm text-fg-muted">Every cron's last run completed cleanly.</div>
        ) : (
          <ul className="space-y-2 text-sm">
            {failedCrons.map((c) => (
              <li key={`${c.source}-${c.id}`} className="rounded-lg border border-status-warm/30 bg-status-warm/5 p-3">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-fg">{c.name}</span>
                    <Tag tone={c.source === "empire" ? "accent" : "info"}>{c.source}</Tag>
                    <span className="font-mono text-[11px] text-fg-dim">{c.schedule}</span>
                  </div>
                  <span className="text-[10px] text-fg-dim">
                    {c.last_run_at ? new Date(c.last_run_at).toLocaleString() : "never"}
                  </span>
                </div>
                {c.last_result && (
                  <div className="mt-1 text-[11px] text-status-warm font-mono break-words">
                    {c.last_result.slice(0, 300)}
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>

      {/* ── Stuck lender threads ────────────────────────────────── */}
      <Card title="Stuck shop-outs" subtitle="Sent >7 days ago with no reply yet. Operator should chase or close-loop.">
        {stuckThreads.length === 0 ? (
          <div className="text-sm text-fg-muted">No shop-outs stuck past 7 days.</div>
        ) : (
          <ul className="space-y-2 text-sm">
            {stuckThreads.map((t) => {
              const ageDays = t.sent_at
                ? Math.floor((Date.now() - new Date(t.sent_at).getTime()) / 86400000)
                : 0;
              return (
                <li key={t.id} className="rounded-lg border border-bg-border bg-bg-deep/40 p-3 flex items-center justify-between gap-2">
                  <div>
                    <div className="text-fg">
                      <Link
                        href={`/t/sun/applications/${t.application_id}`}
                        className="text-accent hover:underline"
                      >
                        App {t.application_id.slice(0, 8)}…
                      </Link>{" "}
                      → {t.recipient_email || <span className="text-fg-dim italic">no recipient</span>}
                    </div>
                    <div className="text-[11px] text-fg-dim mt-0.5">
                      Sent {ageDays}d ago · status={t.status}
                    </div>
                  </div>
                  <Tag tone="accent">{ageDays}d</Tag>
                </li>
              );
            })}
          </ul>
        )}
      </Card>

      {/* ── Stale leads ─────────────────────────────────────────── */}
      <Card title="Stale leads (>14d)" subtitle="Leads whose last update is more than two weeks old. Drips should have moved them or operator should disposition.">
        {stuckLeads.length === 0 ? (
          <div className="text-sm text-fg-muted">Pipeline is moving — no leads stale past 14 days.</div>
        ) : (
          <ul className="space-y-2 text-sm">
            {stuckLeads.map((l) => {
              const ageDays = Math.floor((Date.now() - new Date(l.updated_at).getTime()) / 86400000);
              const stage =
                (typeof l.data.stage === "string" && l.data.stage) ||
                (typeof l.data.status === "string" && l.data.status) ||
                "unset";
              const name =
                (typeof l.data.name === "string" && l.data.name) ||
                (typeof l.data.company === "string" && l.data.company) ||
                "—";
              return (
                <li key={l.id} className="rounded-lg border border-bg-border bg-bg-deep/40 p-3 flex items-center justify-between gap-2">
                  <div>
                    <Link
                      href={`/t/sun/leads/${l.id}`}
                      className="font-bold text-fg hover:text-accent"
                    >
                      {name}
                    </Link>
                    <div className="text-[11px] text-fg-dim mt-0.5">
                      Stage: <span className="text-fg-muted">{stage}</span>
                    </div>
                  </div>
                  <Tag tone={ageDays > 30 ? "warm" : "accent"}>{ageDays}d</Tag>
                </li>
              );
            })}
          </ul>
        )}
      </Card>
    </div>
  );
}

function HealthTile({
  label,
  count,
  icon,
  tone,
}: {
  label: string;
  count: number;
  icon: React.ReactNode;
  tone: "engaged" | "warm" | "accent";
}) {
  const toneClasses =
    tone === "engaged"
      ? "border-status-engaged/40 bg-status-engaged/5 text-status-engaged"
      : tone === "warm"
        ? "border-status-warm/40 bg-status-warm/5 text-status-warm"
        : "border-accent/40 bg-accent/5 text-accent";
  return (
    <div className={`rounded-xl border p-4 ${toneClasses}`}>
      <div className="flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-wider font-bold opacity-70">{label}</span>
        {icon}
      </div>
      <div className="mt-2 text-3xl font-bold">{count}</div>
    </div>
  );
}
