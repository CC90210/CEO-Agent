import Link from "next/link";
import { Bot, CheckCircle2, Clock, Database, MessageSquare, ShieldCheck, Zap } from "lucide-react";
import { Card, PageHeader, Stat, Tag } from "@/components/Card";
import {
  SUNBIZ_DEMO_LEADS,
  SUNBIZ_DEMO_RENEWALS_SUMMARY,
  SUNBIZ_DEMO_RENEWAL_ROWS,
  SUNBIZ_DEMO_SMS_HISTORY,
} from "@/lib/sunbiz-demo-data";

function money(n: number): string {
  return "$" + n.toLocaleString("en-US", { maximumFractionDigits: 0 });
}

export function SunBizDashboard({ demoMode = false }: { demoMode?: boolean }) {
  const renewalVolume = SUNBIZ_DEMO_RENEWAL_ROWS.reduce(
    (sum, row) => sum + Number(row.funded_amount_usd || 0),
    0
  );
  const unassigned = SUNBIZ_DEMO_RENEWAL_ROWS.filter((row) => !row.lender_name).length;
  const hotLeads = SUNBIZ_DEMO_LEADS.filter((lead) => (lead.score || 0) >= 80).length;

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="Sun Biz Command"
        subtitle="Solara is the funding-ops agent for Sun Biz Funding: lead intake, SMS follow-up, applications, lender routing, funded deals, commissions, and renewal pressure."
        action={<Tag tone={demoMode ? "warm" : "accent"}>{demoMode ? "demo data" : "live tenant"}</Tag>}
      />

      <section className="grid grid-cols-2 lg:grid-cols-6 gap-4">
        <Stat label="Hot leads" value={hotLeads} accent hint="score 80+" />
        <Stat label="Applications" value="12" hint="4 need docs" />
        <Stat label="Offers out" value="5" hint="2 expiring soon" />
        <Stat label="Renewal volume" value={money(renewalVolume)} hint="tracked funded deals" />
        <Stat label="Est. commission" value={money(SUNBIZ_DEMO_RENEWALS_SUMMARY.est_commission_total_usd)} hint="next 30 days" />
        <Stat label="Lender gaps" value={unassigned} hint="needs assignment" />
      </section>

      <section className="grid lg:grid-cols-[1.1fr_1.4fr] gap-6">
        <Card
          title="Solara"
          subtitle="The agent in charge of Sun Biz funding operations"
          action={<Tag tone="accent">sunbiz</Tag>}
        >
          <div className="space-y-4">
            <div className="rounded-xl border border-amber-300/30 bg-gradient-to-br from-amber-300/10 via-bg-elev to-bg-panel p-4">
              <div className="flex items-center gap-3">
                <div className="w-11 h-11 rounded-xl border border-amber-300/40 bg-amber-300/15 text-amber-200 flex items-center justify-center">
                  <Bot size={22} />
                </div>
                <div>
                  <div className="text-fg font-bold">Solara online path</div>
                  <div className="text-xs text-fg-muted">Funding ops, renewal intelligence, compliant outreach</div>
                </div>
              </div>
              <p className="text-sm text-fg-muted leading-relaxed mt-4">
                Solara models Sun Biz like a funding desk: speed-to-lead, document completeness,
                lender fit, renewal timing, commission clarity, and compliance risk.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Link href="/agent" className="btn-primary inline-flex items-center gap-1.5 text-sm">
                <MessageSquare size={14} /> Message Solara
              </Link>
              <Link href="/renewals" className="btn-secondary inline-flex items-center gap-1.5 text-sm">
                <Zap size={14} /> Review renewals
              </Link>
            </div>
          </div>
        </Card>

        <Card title="Today's funding desk" subtitle="The work Solara should drive first">
          <div className="space-y-3">
            {[
              ["Past-due renewal", "Northline Logistics is overdue. Escalate call + lender fit check.", "hot"],
              ["Missing docs", "Four applications need bank statements before lender routing.", "warm"],
              ["SMS follow-up", "Three hot leads need compliant text follow-up before end of day.", "accent"],
              ["Commission protection", "Two funded deals have no lender assigned, so commission math is incomplete.", "info"],
            ].map(([title, body, tone]) => (
              <div key={title} className="rounded-lg border border-bg-border bg-bg-elev/50 p-3">
                <div className="flex items-center gap-2">
                  <Tag tone={tone as "hot" | "warm" | "accent" | "info"}>{title}</Tag>
                </div>
                <div className="text-sm text-fg mt-2">{body}</div>
              </div>
            ))}
          </div>
        </Card>
      </section>

      <section className="grid lg:grid-cols-3 gap-6">
        <Card title="Lead radar" subtitle="Sample tenant data for the client demo">
          <ul className="space-y-3">
            {SUNBIZ_DEMO_LEADS.map((lead) => (
              <li key={lead.id} className="rounded-lg border border-bg-border bg-bg-elev/40 p-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="text-fg font-medium">{lead.name}</div>
                  <Tag tone={(lead.score || 0) >= 85 ? "engaged" : "info"}>score {lead.score}</Tag>
                </div>
                <div className="text-xs text-fg-muted mt-1">{lead.company} · {lead.phone || "no phone"}</div>
              </li>
            ))}
          </ul>
        </Card>

        <Card title="Renewal pressure" subtitle="Deals grouped by urgency">
          <ul className="space-y-3">
            {SUNBIZ_DEMO_RENEWAL_ROWS.slice(0, 4).map((deal) => (
              <li key={deal.id} className="rounded-lg border border-bg-border bg-bg-elev/40 p-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="text-fg font-medium">{deal.merchant_name}</div>
                  <span className="text-xs font-mono text-accent">{money(Number(deal.funded_amount_usd || 0))}</span>
                </div>
                <div className="text-xs text-fg-muted mt-1">
                  {deal.lender_name || "No lender assigned"} · renewal {deal.next_renewal_date || "missing"}
                </div>
              </li>
            ))}
          </ul>
        </Card>

        <Card title="Client wiring" subtitle="What turns demo into live operations">
          <ul className="space-y-3 text-sm">
            <SetupItem done label="Command Center profile" detail="Sun Biz shell + Solara agent identity" />
            <SetupItem done label="Demo data mode" detail="Safe sample data, no CC tenant leakage" />
            <SetupItem label="Turso database" detail="Client-isolated funding ops schema" />
            <SetupItem label="Hosted Solara service" detail="FastAPI agent runtime + health endpoints" />
            <SetupItem label="Client machine bridge" detail="File/tools access on their computer" />
            <SetupItem label="Twilio + JotForm" detail="Live SMS and application ingestion" />
          </ul>
        </Card>
      </section>

      <Card title="Recent SMS activity" subtitle="Demo history; live sends unlock after hosted Solara is connected">
        <div className="grid md:grid-cols-2 gap-3">
          {SUNBIZ_DEMO_SMS_HISTORY.map((sms) => (
            <div key={sms.id} className="rounded-lg border border-bg-border bg-bg-elev/40 p-3">
              <div className="flex items-center justify-between">
                <Tag tone={sms.status === "delivered" ? "engaged" : "info"}>{sms.status}</Tag>
                <span className="text-[10px] font-mono text-fg-dim">{sms.to_hash}</span>
              </div>
              <div className="text-sm text-fg-muted mt-2">{sms.body_preview}</div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

function SetupItem({ done = false, label, detail }: { done?: boolean; label: string; detail: string }) {
  return (
    <li className="flex items-start gap-2">
      {done ? (
        <CheckCircle2 className="w-4 h-4 text-status-engaged mt-0.5 flex-shrink-0" />
      ) : label.includes("Turso") ? (
        <Database className="w-4 h-4 text-status-warm mt-0.5 flex-shrink-0" />
      ) : label.includes("bridge") ? (
        <ShieldCheck className="w-4 h-4 text-status-warm mt-0.5 flex-shrink-0" />
      ) : (
        <Clock className="w-4 h-4 text-fg-dim mt-0.5 flex-shrink-0" />
      )}
      <span>
        <span className="text-fg font-medium">{label}</span>
        <span className="block text-xs text-fg-muted mt-0.5">{detail}</span>
      </span>
    </li>
  );
}
