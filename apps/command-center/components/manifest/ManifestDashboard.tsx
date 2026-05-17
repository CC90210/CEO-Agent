import Link from "next/link";
import { Bot, Flame, AlertTriangle, BadgeCheck, RefreshCw, ArrowRight, Sparkles, MessageSquare } from "lucide-react";
import { Card } from "@/components/Card";
import { listRecords, type TenantRecord } from "@/lib/manifest/data";
import type { TenantManifest } from "@/lib/manifest/schema";
import { getServiceSupabase } from "@/lib/supabase-server";
import { LEAD_PIPELINE_STAGES, OPPORTUNITY_PIPELINE_STAGES, type StageMeta } from "@/lib/sunbiz-stage-meta";
import { formatMoney, timeAgo } from "@/lib/fmt";

type AgentAlertRow = {
  id: string;
  alert_type: string;
  severity: "info" | "warn" | "urgent";
  subject_type: string | null;
  subject_id: string | null;
  title: string;
  body: string | null;
  created_at: string;
};

type Props = {
  manifest: TenantManifest;
  tenantId: string | null;
  demoRowsByEntity?: Record<string, TenantRecord[]>;
};

/**
 * ManifestDashboard — the operator's "what needs my attention" landing.
 *
 * Redesigned 2026-05-17 from a bland count-tile grid into a real
 * work-oriented surface. Five sections, top to bottom:
 *
 *   1. Open alerts row (red/amber chips) — missing-info, urgent items
 *      raised by AI classifiers.
 *   2. KPI hero row (4 colored cards) — Hot Leads, Missing Info,
 *      Funded This Month, Renewals Due. Each clickable straight to
 *      the filtered pipeline view.
 *   3. Pipeline-at-a-glance — Lead Pipeline + Opportunity Pipeline
 *      shown as stacked bars with verbatim Salesforce stage colors.
 *      Hover/tap a segment to jump to that stage filter.
 *   4. Today's focus — top 5 urgent leads + top 3 renewals due,
 *      side-by-side, each row clickable to the lead/deal detail.
 *   5. Agents — Solara / Helios cards with "Chat" CTAs.
 *
 * Tenants without the SunBiz entity model fall back to a generic
 * entity-count grid so OASIS HQ + SUGA still render sensibly.
 */
export async function ManifestDashboard({ manifest, tenantId, demoRowsByEntity }: Props) {
  const entities = manifest.data_model || [];
  const enabledAgents = manifest.agents.filter((a) => a.enabled);
  const isSunBizShape =
    entities.some((e) => e.name === "lead") &&
    entities.some((e) => e.name === "application");

  if (entities.length === 0) {
    return (
      <Card title="Dashboard">
        <div className="text-sm text-fg-muted leading-relaxed">
          This workspace has no data model yet. Open the AI editor and ask:{" "}
          <em>&quot;Add a lead entity with name, phone, and stage fields.&quot;</em>
        </div>
      </Card>
    );
  }

  // Fetch every entity's rows once. listRecords is async + parallel.
  const allRows = await Promise.all(
    entities.map(async (entity) => {
      if (!tenantId) {
        const demo = demoRowsByEntity?.[entity.name] || [];
        return { entity, rows: demo, total: demo.length };
      }
      const r = await listRecords({
        tenant_id: tenantId,
        entity: entity.name,
        limit: 500,
      }).catch(() => ({ rows: [], total: 0 }));
      return { entity, rows: r.rows, total: r.total };
    }),
  );
  const rowsByEntity: Record<string, TenantRecord[]> = {};
  for (const { entity, rows } of allRows) rowsByEntity[entity.name] = rows;

  const openAlerts: AgentAlertRow[] = await (async () => {
    if (!tenantId) return [];
    try {
      const sb = getServiceSupabase();
      const { data, error } = await sb
        .from("agent_alerts")
        .select("id, alert_type, severity, subject_type, subject_id, title, body, created_at")
        .eq("tenant_id", tenantId)
        .is("resolved_at", null)
        .order("created_at", { ascending: false })
        .limit(10);
      if (error) return [];
      return (data || []) as AgentAlertRow[];
    } catch {
      return [];
    }
  })();

  const slug = manifest.tenant_slug;

  return (
    <div className="space-y-6">
      {openAlerts.length > 0 && <OpenAlertsRow alerts={openAlerts} slug={slug} />}

      {isSunBizShape ? (
        <SunBizHeroKpis
          slug={slug}
          leads={rowsByEntity.lead || []}
          applications={rowsByEntity.application || []}
          fundedDeals={rowsByEntity.funded_deal || []}
        />
      ) : (
        <GenericKpis allRows={allRows} />
      )}

      {isSunBizShape && (
        <div className="grid gap-4 lg:grid-cols-2">
          <PipelineGlanceCard
            title="Lead Pipeline"
            href={`/t/${slug}/leads`}
            stages={LEAD_PIPELINE_STAGES}
            rows={rowsByEntity.lead || []}
            stageField="stage"
          />
          <PipelineGlanceCard
            title="Opportunity Pipeline"
            href={`/t/${slug}/applications`}
            stages={OPPORTUNITY_PIPELINE_STAGES}
            rows={rowsByEntity.application || []}
            stageField="status"
          />
        </div>
      )}

      {isSunBizShape && (
        <div className="grid gap-4 lg:grid-cols-2">
          <TopUrgentLeads slug={slug} leads={rowsByEntity.lead || []} />
          <RenewalsDueSoon slug={slug} fundedDeals={rowsByEntity.funded_deal || []} />
        </div>
      )}

      {enabledAgents.length > 0 && (
        <Card
          title="Your agents"
          subtitle={
            enabledAgents.length === 1
              ? "One agent on this workspace."
              : `${enabledAgents.length} agents on this workspace — switch between them in chat.`
          }
        >
          <ul className="grid gap-2 sm:grid-cols-2">
            {enabledAgents.map((agent) => (
              <li
                key={agent.slug}
                className="group flex items-center justify-between rounded-lg border border-bg-border bg-bg-elev/40 hover:bg-bg-elev/70 transition-colors px-3 py-2.5"
              >
                <div className="flex items-center gap-2.5">
                  <div className="rounded-md bg-accent/15 border border-accent/30 p-1.5">
                    <Bot className="h-4 w-4 text-accent" aria-hidden />
                  </div>
                  <div>
                    <div className="font-semibold text-sm text-fg">{agent.display_name}</div>
                    <div className="text-[10px] uppercase tracking-wider text-fg-dim">
                      {agent.primary ? "primary agent" : "sub-agent"}
                    </div>
                  </div>
                </div>
                <Link
                  href={`/agent?agent=${encodeURIComponent(agent.slug)}`}
                  className="inline-flex items-center gap-1 text-xs font-bold text-accent hover:text-accent/80 opacity-80 group-hover:opacity-100 transition-opacity"
                >
                  <MessageSquare className="w-3 h-3" />
                  Chat
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}

/* ----------------------------------------------------------------- *
 * Open alerts row
 * ----------------------------------------------------------------- */

function OpenAlertsRow({ alerts, slug }: { alerts: AgentAlertRow[]; slug: string }) {
  return (
    <Card
      title={`${alerts.length} open alert${alerts.length === 1 ? "" : "s"}`}
      subtitle="What your agents flagged for you. Click in to resolve."
    >
      <ul className="space-y-2">
        {alerts.map((alert) => {
          const palette =
            alert.severity === "urgent"
              ? "border-red-500/50 bg-red-500/10 text-red-100 hover:bg-red-500/15"
              : alert.severity === "warn"
                ? "border-amber-400/50 bg-amber-400/10 text-amber-100 hover:bg-amber-400/15"
                : "border-bg-border bg-bg-elev/40 text-fg-muted hover:bg-bg-elev/70";
          const href =
            alert.subject_type === "lead" && alert.subject_id
              ? `/t/${slug}/leads/${alert.subject_id}`
              : alert.subject_type === "application" && alert.subject_id
                ? `/t/${slug}/applications/${alert.subject_id}`
                : null;
          const Inner = (
            <div className={`rounded-lg border px-3 py-2.5 text-[12.5px] transition-colors ${palette}`}>
              <div className="flex items-baseline justify-between gap-2">
                <span className="font-semibold inline-flex items-center gap-1.5">
                  <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
                  {alert.title}
                </span>
                <span className="text-[10.5px] font-mono opacity-70 shrink-0">
                  {timeAgo(alert.created_at)}
                </span>
              </div>
              {alert.body && (
                <div className="mt-1 text-[11.5px] opacity-90 break-words leading-relaxed">
                  {alert.body}
                </div>
              )}
            </div>
          );
          return (
            <li key={alert.id}>
              {href ? (
                <Link href={href} className="block">
                  {Inner}
                </Link>
              ) : (
                Inner
              )}
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

/* ----------------------------------------------------------------- *
 * SunBiz hero KPI cards — 4 colored panels with click-through
 * ----------------------------------------------------------------- */

function SunBizHeroKpis({
  slug,
  leads,
  applications,
  fundedDeals,
}: {
  slug: string;
  leads: TenantRecord[];
  applications: TenantRecord[];
  fundedDeals: TenantRecord[];
}) {
  const hotLeads = leads.filter((l) => l.data.stage === "hot_lead").length;
  const missingInfo = leads.filter((l) => {
    const m = l.data.missing_info;
    return Array.isArray(m) && m.length > 0;
  }).length;

  // "Funded this month": funded_deals with funded_at in the current month.
  const now = new Date();
  const monthStart = new Date(now.getFullYear(), now.getMonth(), 1).getTime();
  const fundedThisMonth = fundedDeals.filter((d) => {
    const t = typeof d.data.funded_at === "string" ? Date.parse(d.data.funded_at) : NaN;
    return !Number.isNaN(t) && t >= monthStart;
  });
  const fundedAmountThisMonth = fundedThisMonth.reduce((sum, d) => {
    const amt = d.data.amount_funded;
    return sum + (typeof amt === "number" ? amt : 0);
  }, 0);

  // Renewals due: funded_deals at 40-50%+ through their term.
  const renewalsDue = fundedDeals.filter((d) => {
    const fundedAt = typeof d.data.funded_at === "string" ? Date.parse(d.data.funded_at) : NaN;
    const term = typeof d.data.term_months === "number" ? d.data.term_months : 0;
    if (!Number.isNaN(fundedAt) && term > 0) {
      const termMs = term * 30 * 24 * 60 * 60 * 1000;
      const elapsed = Date.now() - fundedAt;
      const pct = elapsed / termMs;
      return pct >= 0.4;
    }
    return false;
  }).length;

  const oppPositive = applications.filter((a) => {
    const s = String(a.data.status || "");
    return s === "submitted_to_underwriting" || s === "approved_open_offers" || s === "contracts_ordered";
  }).length;

  return (
    <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <KpiCard
        href={`/t/${slug}/leads?stage=hot_lead`}
        title="Hot leads"
        value={hotLeads}
        accent="#FFB81C"
        icon={<Flame className="w-5 h-5" />}
        sub="actively engaging"
      />
      <KpiCard
        href={`/t/${slug}/leads?stage=missing_info`}
        title="Missing info"
        value={missingInfo}
        accent="#C23934"
        icon={<AlertTriangle className="w-5 h-5" />}
        sub={missingInfo > 0 ? "needs docs from the lead" : "everyone's caught up"}
      />
      <KpiCard
        href={`/t/${slug}/applications`}
        title="In motion"
        value={oppPositive}
        accent="#0070D2"
        icon={<Sparkles className="w-5 h-5" />}
        sub="open opportunities"
      />
      <KpiCard
        href={`/t/${slug}/funded-deals`}
        title="Funded this month"
        value={fundedThisMonth.length}
        accent="#3BA755"
        icon={<BadgeCheck className="w-5 h-5" />}
        sub={fundedAmountThisMonth > 0 ? formatMoney(fundedAmountThisMonth) + " total" : "no fundings yet"}
      />
      {renewalsDue > 0 && (
        <KpiCard
          href={`/t/${slug}/renewals`}
          title="Renewals due"
          value={renewalsDue}
          accent="#E96F2D"
          icon={<RefreshCw className="w-5 h-5" />}
          sub="40%+ through term"
        />
      )}
    </section>
  );
}

function KpiCard({
  href,
  title,
  value,
  accent,
  icon,
  sub,
}: {
  href: string;
  title: string;
  value: number;
  accent: string;
  icon: React.ReactNode;
  sub: string;
}) {
  return (
    <Link
      href={href}
      className="group block rounded-xl border bg-bg-elev/40 hover:bg-bg-elev/70 transition-all hover:-translate-y-[1px] hover:shadow-lg"
      style={{ borderColor: `${accent}55` }}
    >
      <div className="p-4">
        <div className="flex items-start justify-between gap-2 mb-3">
          <div
            className="inline-flex items-center justify-center w-9 h-9 rounded-lg"
            style={{ background: `${accent}22`, color: accent }}
          >
            {icon}
          </div>
          <ArrowRight className="w-3.5 h-3.5 text-fg-dim opacity-0 group-hover:opacity-100 transition-opacity" />
        </div>
        <div className="text-[10px] uppercase tracking-[0.14em] font-bold text-fg-dim mb-1">
          {title}
        </div>
        <div className="text-3xl font-black text-fg leading-none">
          {value}
        </div>
        <div className="mt-1 text-[11px] text-fg-muted">{sub}</div>
      </div>
    </Link>
  );
}

/* ----------------------------------------------------------------- *
 * Generic KPI grid for non-SunBiz tenants
 * ----------------------------------------------------------------- */

function GenericKpis({ allRows }: { allRows: Array<{ entity: { name: string; label: string; fields: unknown[] }; total: number }> }) {
  return (
    <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {allRows.map(({ entity, total }) => (
        <div
          key={entity.name}
          className="rounded-xl border border-bg-border bg-bg-elev/40 p-4"
        >
          <div className="text-[10px] uppercase tracking-[0.14em] font-bold text-fg-dim mb-1">
            {entity.label}
          </div>
          <div className="text-3xl font-black text-fg leading-none">{total}</div>
          <div className="mt-1 text-[11px] text-fg-muted">{entity.fields.length} fields</div>
        </div>
      ))}
    </section>
  );
}

/* ----------------------------------------------------------------- *
 * Pipeline-at-a-glance — stacked color bar with Salesforce hex codes
 * ----------------------------------------------------------------- */

function PipelineGlanceCard({
  title,
  href,
  stages,
  rows,
  stageField,
}: {
  title: string;
  href: string;
  stages: StageMeta[];
  rows: TenantRecord[];
  stageField: string;
}) {
  const counts: Record<string, number> = {};
  for (const r of rows) {
    const s = String(r.data[stageField] || "");
    if (s) counts[s] = (counts[s] || 0) + 1;
  }
  const total = rows.length;

  return (
    <Card
      title={title}
      subtitle={`${total} ${total === 1 ? "record" : "records"} across ${stages.length} stages`}
      action={
        <Link
          href={href}
          className="inline-flex items-center gap-1 text-xs font-semibold text-accent hover:text-accent/80"
        >
          Open <ArrowRight className="w-3 h-3" />
        </Link>
      }
    >
      <div className="space-y-3">
        {/* Stacked color bar */}
        <div className="flex w-full h-3 rounded-full overflow-hidden bg-bg-deep">
          {total === 0 ? (
            <div className="flex-1 bg-bg-elev/60" />
          ) : (
            stages.map((s) => {
              const c = counts[s.key] || 0;
              if (c === 0) return null;
              const pct = (c / total) * 100;
              return (
                <Link
                  key={s.key}
                  href={`${href}?stage=${encodeURIComponent(s.key)}`}
                  className="block h-full transition-opacity hover:opacity-80"
                  style={{ width: `${pct}%`, background: s.bg }}
                  title={`${s.label}: ${c}`}
                />
              );
            })
          )}
        </div>

        {/* Top 3 stages by count */}
        <ul className="space-y-1.5">
          {stages
            .map((s) => ({ stage: s, count: counts[s.key] || 0 }))
            .filter(({ count }) => count > 0)
            .sort((a, b) => b.count - a.count)
            .slice(0, 4)
            .map(({ stage, count }) => (
              <li key={stage.key}>
                <Link
                  href={`${href}?stage=${encodeURIComponent(stage.key)}`}
                  className="flex items-center justify-between gap-2 text-[12px] hover:text-fg group"
                >
                  <span className="flex items-center gap-2 text-fg-muted group-hover:text-fg transition-colors min-w-0">
                    <span
                      className="inline-block w-2.5 h-2.5 rounded-sm shrink-0"
                      style={{ background: stage.bg }}
                    />
                    <span className="truncate">{stage.label}</span>
                  </span>
                  <span className="font-mono text-fg-dim group-hover:text-fg shrink-0">{count}</span>
                </Link>
              </li>
            ))}
          {total === 0 && (
            <li className="text-[11.5px] italic text-fg-dim text-center py-2">
              No records yet — they&apos;ll appear here as the pipeline fills.
            </li>
          )}
        </ul>
      </div>
    </Card>
  );
}

/* ----------------------------------------------------------------- *
 * Today's focus — top urgent leads + renewals due
 * ----------------------------------------------------------------- */

const STAGE_WEIGHT: Record<string, number> = {
  hot_lead: 100,
  signed_application: 90,
  viewed_application: 80,
  sent_application: 70,
  missing_info: 65,
  follow_up: 50,
  submitted: 40,
  imported: 20,
  not_interested: 0,
  declined: 0,
  default: 0,
  dead_file: 0,
  approved: 75,
};

function urgencyScore(lead: TenantRecord): number {
  const stage = String(lead.data.stage || "");
  const base = STAGE_WEIGHT[stage] ?? 30;
  const updatedMs = Date.parse(lead.updated_at || lead.created_at || "");
  const daysSinceTouch = Number.isNaN(updatedMs)
    ? 0
    : Math.max(0, Math.floor((Date.now() - updatedMs) / (24 * 60 * 60 * 1000)));
  const revenue = typeof lead.data.monthly_revenue === "number" ? lead.data.monthly_revenue : 0;
  const revBoost = revenue > 0 ? Math.log10(revenue) * 6 : 0;
  return base + Math.sqrt(daysSinceTouch) * 8 + revBoost;
}

function TopUrgentLeads({ slug, leads }: { slug: string; leads: TenantRecord[] }) {
  const top = [...leads]
    .filter((l) => {
      const s = String(l.data.stage || "");
      return s !== "default" && s !== "declined" && s !== "dead_file" && s !== "not_interested";
    })
    .sort((a, b) => urgencyScore(b) - urgencyScore(a))
    .slice(0, 5);

  return (
    <Card
      title="Today's focus — most urgent leads"
      subtitle="Ranked by stage weight × days-since-touch × revenue."
      action={
        <Link
          href={`/t/${slug}/leads`}
          className="inline-flex items-center gap-1 text-xs font-semibold text-accent hover:text-accent/80"
        >
          All leads <ArrowRight className="w-3 h-3" />
        </Link>
      }
    >
      {top.length === 0 ? (
        <div className="text-sm text-fg-dim italic text-center py-4">
          No active leads yet. Import a list or wait for inbound — they&apos;ll surface here.
        </div>
      ) : (
        <ul className="divide-y divide-bg-border">
          {top.map((lead) => {
            const stage = String(lead.data.stage || "");
            const stageMeta = LEAD_PIPELINE_STAGES.find((s) => s.key === stage);
            const name =
              (typeof lead.data.business_name === "string" && lead.data.business_name) ||
              (typeof lead.data.contact_name === "string" && lead.data.contact_name) ||
              `Lead ${lead.id.slice(0, 8)}`;
            return (
              <li key={lead.id}>
                <Link
                  href={`/t/${slug}/leads/${lead.id}`}
                  className="flex items-center justify-between gap-3 py-2 px-1 hover:bg-bg-elev/40 rounded transition-colors"
                >
                  <div className="min-w-0">
                    <div className="font-semibold text-sm text-fg truncate">{name}</div>
                    {typeof lead.data.monthly_revenue === "number" && (
                      <div className="text-[11px] text-fg-dim">{formatMoney(lead.data.monthly_revenue)}/mo</div>
                    )}
                  </div>
                  {stageMeta && (
                    <span
                      className="inline-block px-2 py-0.5 rounded text-[10px] font-bold whitespace-nowrap shrink-0"
                      style={{ background: stageMeta.bg, color: stageMeta.fg }}
                    >
                      {stageMeta.label}
                    </span>
                  )}
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}

function RenewalsDueSoon({ slug, fundedDeals }: { slug: string; fundedDeals: TenantRecord[] }) {
  const due = fundedDeals
    .map((d) => {
      const fundedAt = typeof d.data.funded_at === "string" ? Date.parse(d.data.funded_at) : NaN;
      const term = typeof d.data.term_months === "number" ? d.data.term_months : 0;
      if (Number.isNaN(fundedAt) || term <= 0) return null;
      const termMs = term * 30 * 24 * 60 * 60 * 1000;
      const elapsed = Date.now() - fundedAt;
      const pct = elapsed / termMs;
      return { deal: d, pct };
    })
    .filter((x): x is { deal: TenantRecord; pct: number } => !!x && x.pct >= 0.4)
    .sort((a, b) => b.pct - a.pct)
    .slice(0, 3);

  return (
    <Card
      title="Renewals due soon"
      subtitle="Funded deals 40%+ through their term."
      action={
        <Link
          href={`/t/${slug}/renewals`}
          className="inline-flex items-center gap-1 text-xs font-semibold text-accent hover:text-accent/80"
        >
          All renewals <ArrowRight className="w-3 h-3" />
        </Link>
      }
    >
      {due.length === 0 ? (
        <div className="text-sm text-fg-dim italic text-center py-4">
          No renewals due yet — deals reach 40% of their term before they qualify.
        </div>
      ) : (
        <ul className="divide-y divide-bg-border">
          {due.map(({ deal, pct }) => {
            const amount = typeof deal.data.amount_funded === "number" ? deal.data.amount_funded : 0;
            const pctLabel = `${Math.round(pct * 100)}% in`;
            const tone =
              pct >= 0.5 ? "#E96F2D" : "#0070D2"; // overdue-ish vs upcoming
            return (
              <li key={deal.id}>
                <Link
                  href={`/t/${slug}/funded-deals/${deal.id}`}
                  className="flex items-center justify-between gap-3 py-2 px-1 hover:bg-bg-elev/40 rounded transition-colors"
                >
                  <div className="min-w-0">
                    <div className="font-semibold text-sm text-fg truncate">
                      {formatMoney(amount)} deal
                    </div>
                    {typeof deal.data.term_months === "number" && (
                      <div className="text-[11px] text-fg-dim">{deal.data.term_months}-month term</div>
                    )}
                  </div>
                  <span
                    className="inline-block px-2 py-0.5 rounded text-[10px] font-bold whitespace-nowrap shrink-0"
                    style={{ background: `${tone}22`, color: tone, border: `1px solid ${tone}55` }}
                  >
                    {pctLabel}
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}

// formatMoney + timeAgo live in lib/fmt.ts (shared with the rest of the app).
