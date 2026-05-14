import Link from "next/link";
import {
  ArrowRight,
  BookOpen,
  Bot,
  CheckCircle2,
  CircleAlert,
  Clock3,
  MessageSquareText,
  RefreshCcw,
  ShieldCheck,
  SunMedium,
  Workflow,
} from "lucide-react";
import { Card, PageHeader, Stat, Tag } from "@/components/Card";
import { safe } from "@/lib/api-helpers";
import {
  getActiveProfile,
  getLeadsForTenant,
  getRenewalsSummary,
  integrationsHealth,
  type RenewalsSummary,
} from "@/lib/queries";
import { SUNBIZ_DEMO_LEADS, SUNBIZ_DEMO_RENEWALS_SUMMARY } from "@/lib/sunbiz-demo-data";
import { demoHref } from "@/lib/demo-href";
import type { IntegrationHealth, Lead } from "@/lib/supabase";

type Props = {
  demoMode?: boolean;
};

type ServiceStatus = IntegrationHealth["status"];

const MANUAL_STEPS = [
  {
    slug: "01-getting-started",
    title: "Meet Solara",
    body: "What your digital employee owns from lead intake to renewals.",
  },
  {
    slug: "02-safe-interaction",
    title: "How to work with Solara",
    body: "What to ask for, what to review, and how to keep the lane clean.",
  },
  {
    slug: "03-when-to-call-cc",
    title: "When to loop in CC",
    body: "The few moments when a human opinion or approval matters.",
  },
  {
    slug: "04-pause-and-rollback",
    title: "Pause and correct",
    body: "How to stop, fix, and move forward without drama.",
  },
];

const DEMO_HEALTH: IntegrationHealth[] = [
  demoHealthRow("jotform", "healthy"),
  demoHealthRow("text_torrent", "healthy"),
  demoHealthRow("turso", "healthy"),
];

function demoHealthRow(service: string, status: ServiceStatus): IntegrationHealth {
  return {
    id: `demo-${service}`,
    profile_id: null,
    tenant_id: null,
    service,
    status,
    last_ping_at: new Date().toISOString(),
    last_error: null,
    metadata: {},
    updated_at: new Date().toISOString(),
  };
}

function firstNameOf(name: string | null | undefined, fallback = "Jordan"): string {
  const raw = (name || "").trim();
  if (!raw) return fallback;
  return raw.split(/\s+/)[0] || fallback;
}

function statusTone(status: ServiceStatus): "neutral" | "engaged" | "warm" | "hot" {
  if (status === "healthy") return "engaged";
  if (status === "degraded") return "warm";
  if (status === "down") return "hot";
  return "neutral";
}

function statusLabel(status: ServiceStatus): string {
  if (status === "healthy") return "Connected";
  if (status === "degraded") return "Needs attention";
  if (status === "down") return "Offline";
  return "Not connected";
}

function automationStatus(statuses: ServiceStatus[]): ServiceStatus {
  if (statuses.every((status) => status === "healthy")) return "healthy";
  if (statuses.some((status) => status === "down")) return "down";
  if (statuses.some((status) => status === "degraded")) return "degraded";
  return statuses.some((status) => status === "healthy") ? "degraded" : "unconfigured";
}

function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "Waiting for first check-in";
  const diffMs = Date.now() - new Date(iso).getTime();
  if (diffMs < 60_000) return "Checked just now";
  if (diffMs < 60 * 60_000) return `Checked ${Math.floor(diffMs / 60_000)}m ago`;
  if (diffMs < 24 * 60 * 60_000) return `Checked ${Math.floor(diffMs / (60 * 60_000))}h ago`;
  return `Checked ${Math.floor(diffMs / (24 * 60 * 60_000))}d ago`;
}

function rankLeads(leads: Lead[]): Lead[] {
  return [...leads].sort((a, b) => {
    const scoreDelta = (b.score || 0) - (a.score || 0);
    if (scoreDelta !== 0) return scoreDelta;
    return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime();
  });
}

function serviceMessage(service: "jotform" | "text_torrent" | "turso", status: ServiceStatus): string {
  if (service === "jotform") {
    return status === "healthy"
      ? "Ready to receive new lead forms."
      : "Connect JotForm so Solara can receive new leads.";
  }
  if (service === "text_torrent") {
    return status === "healthy"
      ? "Ready to send lead follow-ups."
      : "Connect Text Torrent so Solara can text prospects.";
  }
  return status === "healthy"
    ? "Solara's Local Brain is active on this machine."
    : "Finish setting up Solara's Local Brain on this machine.";
}

function readyLine(service: string, status: ServiceStatus): string {
  if (service === "jotform") {
    return status === "healthy"
      ? "Solara is connected to JotForm. She is ready to receive leads."
      : "Connect JotForm to start new inbound leads.";
  }
  if (service === "text_torrent") {
    return status === "healthy"
      ? "Solara is connected to Text Torrent. She is ready to send follow-ups."
      : "Connect Text Torrent to start automated follow-up.";
  }
  return status === "healthy"
    ? "Solara's Local Brain is active and ready."
    : "Finish Solara's Local Brain setup on this machine.";
}

export async function SunBizDashboard({ demoMode = false }: Props) {
  const profile = await safe("sun.dashboard.profile", getActiveProfile(), null);
  const tenantId = demoMode ? "" : profile?.tenant_id || "";
  const link = (real: string) => demoHref(real, { demoMode });
  const [liveHealthRows, liveLeads, liveRenewals] = demoMode
    ? [DEMO_HEALTH, SUNBIZ_DEMO_LEADS, SUNBIZ_DEMO_RENEWALS_SUMMARY]
    : await Promise.all([
        safe("sun.dashboard.health", integrationsHealth(tenantId || null), [] as IntegrationHealth[]),
        tenantId ? safe("sun.dashboard.leads", getLeadsForTenant(tenantId, 100), [] as Lead[]) : Promise.resolve([] as Lead[]),
        tenantId
          ? safe("sun.dashboard.renewals", getRenewalsSummary(tenantId), SUNBIZ_DEMO_RENEWALS_SUMMARY as RenewalsSummary)
          : Promise.resolve(SUNBIZ_DEMO_RENEWALS_SUMMARY as RenewalsSummary),
      ]);

  const healthByService = new Map(liveHealthRows.map((row) => [row.service, row] as const));
  const jotform = healthByService.get("jotform") || demoHealthRow("jotform", "unconfigured");
  const textTorrent = healthByService.get("text_torrent") || demoHealthRow("text_torrent", "unconfigured");
  const localBrain = healthByService.get("turso") || demoHealthRow("turso", "unconfigured");
  const combinedStatus = automationStatus([jotform.status, textTorrent.status, localBrain.status]);

  const sortedLeads = rankLeads(liveLeads);
  const priorityLead = sortedLeads[0] || null;
  const actionableLeads = liveLeads.filter((lead) => !["won", "lost", "archived"].includes(lead.status || "")).length;
  const hotLeads = liveLeads.filter((lead) => (lead.score || 0) >= 80).length;
  const clientName = firstNameOf(profile?.display_name || profile?.full_name, demoMode ? "Jordan" : "there");
  const liveConnections = [jotform, textTorrent, localBrain].filter((row) => row.status === "healthy").length;

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="Welcome to your Command Center"
        subtitle="Solara is your digital employee for lead intake, follow-up, applications, offers, funded deals, and renewals."
        action={
          <div className="flex items-center gap-2">
            {demoMode && <Tag tone="info">demo</Tag>}
            <Tag tone={statusTone(combinedStatus)}>
              {combinedStatus === "healthy" ? "Solara ready" : "Setup in progress"}
            </Tag>
          </div>
        }
      />

      <section className="grid gap-6 xl:grid-cols-[1.45fr,0.95fr]">
        <section className="relative overflow-hidden rounded-[28px] border border-amber-300/30 bg-[radial-gradient(circle_at_top_left,rgba(251,191,36,0.22),transparent_34%),linear-gradient(135deg,rgba(24,24,27,0.96),rgba(15,23,42,0.94))] p-6 shadow-[0_24px_80px_-36px_rgba(251,191,36,0.55)]">
          <div className="absolute right-5 top-5 hidden h-16 w-16 rounded-3xl border border-amber-300/25 bg-amber-300/10 text-amber-200 shadow-[0_0_36px_-12px_rgba(251,191,36,0.85)] sm:flex items-center justify-center">
            <SunMedium size={30} strokeWidth={2.1} />
          </div>
          <div className="inline-flex items-center gap-2 rounded-full border border-amber-300/25 bg-amber-300/10 px-3 py-1 text-[11px] font-bold uppercase tracking-[0.18em] text-amber-100">
            <Bot className="h-3.5 w-3.5" />
            Digital Employee
          </div>
          <h2 className="mt-4 max-w-2xl text-3xl font-black tracking-tight text-white sm:text-[2.4rem]">
            Welcome {clientName}. Solara is on shift.
          </h2>
          <p className="mt-3 max-w-2xl text-sm leading-7 text-amber-50/80 sm:text-base">
            She watches new leads, follow-up timing, applications, offers, and renewal opportunities from one place so your team can stay focused on funded deals.
          </p>

          <div className="mt-6 grid gap-3">
            <PulseLine label="JotForm" status={jotform.status} body={readyLine("jotform", jotform.status)} />
            <PulseLine label="Text Torrent" status={textTorrent.status} body={readyLine("text_torrent", textTorrent.status)} />
            <PulseLine label="Local Brain" status={localBrain.status} body={readyLine("turso", localBrain.status)} />
          </div>

          <div className="mt-6 flex flex-wrap gap-3">
            <Link href={link("/playbook")} className="btn-send inline-flex items-center gap-2">
              Open Playbook <ArrowRight className="h-4 w-4" />
            </Link>
            <Link href={link("/agent")} className="btn-secondary inline-flex items-center gap-2">
              Chat with Solara <MessageSquareText className="h-4 w-4" />
            </Link>
          </div>
        </section>

        <Card
          title="Unified Onboarding Manual"
          subtitle="The four pages every Sun Biz teammate should read first."
          className="overflow-hidden"
        >
          <div className="space-y-3">
            {MANUAL_STEPS.map((step, index) => (
              <Link
                key={step.slug}
                href={link(`/playbook/${step.slug}`)}
                className="group flex items-start gap-3 rounded-2xl border border-bg-border bg-bg-elev/40 px-4 py-3 transition-all hover:border-amber-300/35 hover:bg-amber-300/6"
              >
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-2xl border border-amber-300/25 bg-amber-300/10 text-xs font-black tracking-[0.18em] text-amber-100">
                  {(index + 1).toString().padStart(2, "0")}
                </div>
                <div className="min-w-0">
                  <div className="text-sm font-semibold text-fg transition-colors group-hover:text-amber-200">
                    {step.title}
                  </div>
                  <div className="mt-1 text-xs leading-6 text-fg-muted">{step.body}</div>
                </div>
              </Link>
            ))}
          </div>
          <div className="mt-4 flex items-center justify-between rounded-2xl border border-bg-border bg-bg-elev/35 px-4 py-3 text-xs text-fg-muted">
            <span>Read these once in order, then come back whenever the team needs a reset.</span>
            <Link href={link("/playbook")} className="text-amber-200 hover:text-amber-100">
              View full Playbook
            </Link>
          </div>
        </Card>
      </section>

      <section className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        <Stat
          label="Leads needing action"
          value={actionableLeads}
          hint={hotLeads > 0 ? `${hotLeads} high-priority lead${hotLeads === 1 ? "" : "s"}` : "No hot leads waiting"}
          accent
        />
        <Stat
          label="Renewals this month"
          value={liveRenewals.this_month_count}
          hint={
            liveRenewals.this_month_count > 0
              ? `${liveRenewals.past_due_count} overdue`
              : "No renewal pressure right now"
          }
        />
        <Stat
          label="Connections live"
          value={`${liveConnections}/3`}
          hint={combinedStatus === "healthy" ? "Everything is connected" : "Finish the remaining setup"}
        />
        <Stat
          label="Estimated renewals"
          value={`$${Math.round(liveRenewals.est_commission_total_usd || 0).toLocaleString()}`}
          hint="Current opportunity on the board"
        />
      </section>

      <section className="grid gap-6 xl:grid-cols-[1.05fr,0.95fr]">
        <Card
          title="What Solara should do next"
          subtitle="A quick operator read before you start the day."
        >
          <div className="space-y-4">
            {priorityLead ? (
              <ActionRow
                icon={<Workflow className="h-4 w-4" />}
                title={`Start with ${priorityLead.name || "this lead"}`}
                body={`${priorityLead.company || "Funding prospect"} is your best current lead${priorityLead.score ? ` with a score of ${priorityLead.score}` : ""}. Open Leads, confirm the latest context, then let Solara draft the next move.`}
                href={link("/leads")}
                cta="Open Leads"
              />
            ) : (
              <ActionRow
                icon={<Workflow className="h-4 w-4" />}
                title="Connect your first inbound lane"
                body="Once JotForm is connected, new lead forms will start landing here automatically for Solara to sort and follow up."
                href={link("/integrations")}
                cta="Open Integrations"
              />
            )}

            <ActionRow
              icon={<RefreshCcw className="h-4 w-4" />}
              title="Review renewal pressure"
              body={
                liveRenewals.past_due_count > 0
                  ? `${liveRenewals.past_due_count} renewal${liveRenewals.past_due_count === 1 ? "" : "s"} are already overdue. This is the fastest place to create revenue today.`
                  : `${liveRenewals.this_month_count} renewal${liveRenewals.this_month_count === 1 ? "" : "s"} are coming up this month. Keep Solara ahead of the follow-up window.`
              }
              href={link("/renewals")}
              cta="Open Renewals"
            />

            <ActionRow
              icon={<BookOpen className="h-4 w-4" />}
              title="Share the manual with your team"
              body="The Playbook explains how Solara works, what to ask her for, when to bring in CC, and how to pause changes if something feels off."
              href={link("/playbook")}
              cta="Open Playbook"
            />
          </div>
        </Card>

        <div className="grid gap-4">
          <PulseCard
            title="JotForm"
            status={jotform.status}
            body={serviceMessage("jotform", jotform.status)}
            stamp={demoMode ? "Demo connection" : timeAgo(jotform.last_ping_at)}
          />
          <PulseCard
            title="Text Torrent"
            status={textTorrent.status}
            body={serviceMessage("text_torrent", textTorrent.status)}
            stamp={demoMode ? "Demo connection" : timeAgo(textTorrent.last_ping_at)}
          />
          <PulseCard
            title="Local Brain"
            status={localBrain.status}
            body={serviceMessage("turso", localBrain.status)}
            stamp={demoMode ? "Demo connection" : timeAgo(localBrain.last_ping_at)}
          />
          <PulseCard
            title="Automation"
            status={combinedStatus}
            body={
              combinedStatus === "healthy"
                ? "Lead intake, follow-up, and deal tracking are fully ready."
                : "Finish the remaining connections so Solara can run the full funding pipeline."
            }
            stamp={combinedStatus === "healthy" ? "Ready for day one" : "Needs one more pass"}
          />
        </div>
      </section>
    </div>
  );
}

function PulseLine({
  label,
  status,
  body,
}: {
  label: string;
  status: ServiceStatus;
  body: string;
}) {
  return (
    <div className="flex items-start gap-3 rounded-2xl border border-white/10 bg-white/6 px-4 py-3 backdrop-blur-sm">
      <div className={`mt-0.5 ${status === "healthy" ? "text-emerald-300" : "text-amber-200"}`}>
        {status === "healthy" ? <CheckCircle2 className="h-4 w-4" /> : <CircleAlert className="h-4 w-4" />}
      </div>
      <div>
        <div className="text-[11px] font-bold uppercase tracking-[0.16em] text-amber-100/80">{label}</div>
        <div className="mt-1 text-sm leading-6 text-white/85">{body}</div>
      </div>
    </div>
  );
}

function ActionRow({
  icon,
  title,
  body,
  href,
  cta,
}: {
  icon: React.ReactNode;
  title: string;
  body: string;
  href: string;
  cta: string;
}) {
  return (
    <div className="rounded-2xl border border-bg-border bg-bg-elev/35 p-4">
      <div className="flex items-start gap-3">
        <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-2xl border border-amber-300/25 bg-amber-300/10 text-amber-200">
          {icon}
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold text-fg">{title}</div>
          <div className="mt-1 text-sm leading-6 text-fg-muted">{body}</div>
          <Link href={href} className="mt-3 inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-amber-200 hover:text-amber-100">
            {cta} <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </div>
      </div>
    </div>
  );
}

function PulseCard({
  title,
  status,
  body,
  stamp,
}: {
  title: string;
  status: ServiceStatus;
  body: string;
  stamp: string;
}) {
  return (
    <Card
      title={title}
      subtitle={body}
      action={<Tag tone={statusTone(status)}>{statusLabel(status)}</Tag>}
    >
      <div className="flex items-center gap-2 text-xs text-fg-dim">
        <Clock3 className="h-3.5 w-3.5" />
        <span>{stamp}</span>
      </div>
    </Card>
  );
}
