import { Card, PageHeader, Stat, EmptyState, Tag } from "@/components/Card";
import { Flame, Clock, CalendarDays, TrendingUp, Phone, Mail, ChevronRight } from "lucide-react";
import {
  getActiveProfile,
  getRenewalsSummary,
  getRenewalsRows,
  type FundedDealRow,
} from "@/lib/queries";
import { safe } from "@/lib/api-helpers";
import { cookies } from "next/headers";
import { DEMO_CLIENT_PROFILE_COOKIE } from "@/lib/client-profiles";
import {
  SUNBIZ_DEMO_RENEWALS_SUMMARY,
  SUNBIZ_DEMO_RENEWAL_ROWS,
} from "@/lib/sunbiz-demo-data";

export const dynamic = "force-dynamic";

function fmtCurrency(value: number | null | undefined): string {
  if (value === null || value === undefined) return "-";
  return "$" + Number(value).toLocaleString("en-US", { maximumFractionDigits: 0 });
}

function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "-";
  const date = new Date(iso);
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function daysUntil(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const ms = new Date(iso).getTime() - Date.now();
  return Math.round(ms / (1000 * 60 * 60 * 24));
}

function initialsOf(name: string | null | undefined): string {
  if (!name) return "??";
  const parts = name.trim().split(/\s+/).slice(0, 2);
  return parts.map((part) => part[0]?.toUpperCase() || "").join("") || "??";
}

function groupRows(rows: FundedDealRow[]): { label: string; rows: FundedDealRow[]; subtotal: number }[] {
  const now = new Date();
  const in60 = new Date(now);
  in60.setDate(in60.getDate() + 60);

  const past: FundedDealRow[] = [];
  const next60: FundedDealRow[] = [];
  const later: FundedDealRow[] = [];
  const noDate: FundedDealRow[] = [];

  for (const row of rows) {
    if (!row.next_renewal_date) {
      noDate.push(row);
      continue;
    }
    const date = new Date(row.next_renewal_date);
    if (date < now) past.push(row);
    else if (date <= in60) next60.push(row);
    else later.push(row);
  }

  const subtotal = (group: FundedDealRow[]) =>
    group.reduce((sum, row) => sum + Number(row.funded_amount_usd || 0), 0);

  const grouped: { label: string; rows: FundedDealRow[]; subtotal: number }[] = [];
  if (past.length) grouped.push({ label: "PAST DUE", rows: past, subtotal: subtotal(past) });
  if (next60.length) grouped.push({ label: "NEXT 60 DAYS", rows: next60, subtotal: subtotal(next60) });
  if (later.length) grouped.push({ label: "LATER", rows: later, subtotal: subtotal(later) });
  if (noDate.length) grouped.push({ label: "NO DATE SET", rows: noDate, subtotal: subtotal(noDate) });
  return grouped;
}

export default async function RenewalsPage() {
  const demoProfile = (await cookies()).get(DEMO_CLIENT_PROFILE_COOKIE)?.value || null;
  const demoMode = demoProfile === "sun";
  const profile = await safe("renewals.profile", getActiveProfile(), null);
  const tenantId = demoMode ? "" : profile?.tenant_id || "";

  const [summary, rows] = demoMode
    ? [SUNBIZ_DEMO_RENEWALS_SUMMARY, SUNBIZ_DEMO_RENEWAL_ROWS]
    : await Promise.all([
        tenantId
          ? safe("renewals.summary", getRenewalsSummary(tenantId), {
              past_due_count: 0,
              this_week_count: 0,
              this_month_count: 0,
              est_commission_total_usd: 0,
              total_with_dates: 0,
              total_no_date: 0,
            })
          : Promise.resolve({
              past_due_count: 0,
              this_week_count: 0,
              this_month_count: 0,
              est_commission_total_usd: 0,
              total_with_dates: 0,
              total_no_date: 0,
            }),
        tenantId ? safe("renewals.rows", getRenewalsRows(tenantId, 50), [] as FundedDealRow[]) : Promise.resolve([] as FundedDealRow[]),
      ]);

  const groups = groupRows(rows);

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="Renewals"
        subtitle={
          demoMode
            ? "Sun demo mode · sample renewal data is loaded so you can see the workflow"
            : summary.total_with_dates + summary.total_no_date === 0
              ? "Funded deals will appear here as renewals come due"
              : `${summary.total_with_dates} ${summary.total_with_dates === 1 ? "deal" : "deals"} with renewal dates · ${summary.total_no_date} missing date`
        }
      />

      <section className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.14em] text-fg-muted font-bold mb-2">
            <Flame size={12} className="text-status-hot" />
            <span>Past Due</span>
          </div>
          <Stat
            label=""
            value={String(summary.past_due_count)}
            hint={summary.past_due_count === 0 ? "all clear" : "overdue - escalate"}
          />
        </Card>
        <Card>
          <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.14em] text-fg-muted font-bold mb-2">
            <Clock size={12} className="text-accent" />
            <span>This Week</span>
          </div>
          <Stat
            label=""
            value={String(summary.this_week_count)}
            hint={summary.this_week_count === 0 ? "none this week" : "imminent"}
          />
        </Card>
        <Card>
          <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.14em] text-fg-muted font-bold mb-2">
            <CalendarDays size={12} className="text-accent" />
            <span>This Month</span>
          </div>
          <Stat
            label=""
            value={String(summary.this_month_count)}
            hint={
              summary.this_month_count === 0
                ? "$0 potential volume"
                : `${fmtCurrency(summary.est_commission_total_usd)} potential volume`
            }
          />
        </Card>
        <Card>
          <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.14em] text-fg-muted font-bold mb-2">
            <TrendingUp size={12} className="text-status-engaged" />
            <span>Est. Commission</span>
          </div>
          <Stat
            label=""
            value={fmtCurrency(summary.est_commission_total_usd)}
            hint="from actionable renewals"
            accent
          />
        </Card>
      </section>

      <div className="flex flex-wrap items-center gap-2">
        <button className="px-3 py-1.5 rounded-full bg-accent-soft text-accent text-xs font-semibold border border-accent/30">
          All ({rows.length})
        </button>
        <button className="px-3 py-1.5 rounded-full bg-bg-elev text-fg-muted text-xs font-medium border border-bg-border hover:bg-bg-hover">
          Next 60 Days ({summary.this_week_count + summary.this_month_count})
        </button>
        <button className="px-3 py-1.5 rounded-full bg-bg-elev text-fg-muted text-xs font-medium border border-bg-border hover:bg-bg-hover">
          No Date Set ({summary.total_no_date})
        </button>
      </div>

      {rows.length === 0 ? (
        <Card>
          <EmptyState message="No funded deals yet. Renewal cards will populate as deals close and the renewal scanner runs nightly." />
        </Card>
      ) : (
        <div className="space-y-6">
          {groups.map((group) => (
            <section key={group.label}>
              <div className="flex items-baseline gap-3 mb-3 px-1">
                <span className="text-[10px] uppercase tracking-[0.14em] text-fg-muted font-bold">
                  {group.label} · {group.rows.length}
                </span>
                <span className="text-xs font-mono text-fg-dim">
                  {fmtCurrency(group.subtotal)}
                </span>
              </div>
              <Card noPadding>
                <div className="divide-y divide-bg-border">
                  {group.rows.map((row) => (
                    <RenewalRow key={row.id} row={row} />
                  ))}
                </div>
              </Card>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}

function RenewalRow({ row }: { row: FundedDealRow }) {
  const days = daysUntil(row.next_renewal_date);
  const hasLender = !!row.lender_name;
  return (
    <div className="flex items-center gap-4 px-5 py-3 hover:bg-bg-hover/30 transition-colors">
      <div className="w-8 h-8 rounded-full bg-bg-elev border border-bg-border flex items-center justify-center text-fg-muted text-[10px] font-bold flex-shrink-0">
        {initialsOf(row.merchant_name)}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-fg text-sm font-medium truncate">{row.merchant_name || "-"}</span>
          {days !== null && days >= 0 && days <= 60 && (
            <Tag tone={days <= 7 ? "warm" : "info"}>in {days}d</Tag>
          )}
        </div>
        <div className="text-fg-dim text-xs">
          {row.contact_name || "-"} · {hasLender ? row.lender_name : "No lender assigned"}
        </div>
      </div>
      <div className="text-right flex-shrink-0">
        <div className="text-[10px] uppercase tracking-wider text-fg-faint">Renewal</div>
        <div className="text-fg text-sm font-mono">{fmtDate(row.next_renewal_date)}</div>
      </div>
      <div className="text-right flex-shrink-0 min-w-[100px]">
        <div className="text-[10px] uppercase tracking-wider text-fg-faint">Funded</div>
        <div className="text-fg text-sm font-mono">{fmtCurrency(row.funded_amount_usd)}</div>
        {row.factor_rate != null && (
          <div className="text-fg-faint text-[10px] font-mono">x{Number(row.factor_rate).toFixed(3).replace(/\.?0+$/, "")}</div>
        )}
      </div>
      <div className="text-right flex-shrink-0 min-w-[90px]">
        <div className="text-[10px] uppercase tracking-wider text-fg-faint">Commission</div>
        <div
          className={`text-sm font-mono ${hasLender && row.est_commission_usd ? "text-status-engaged" : "text-fg-faint"}`}
        >
          {hasLender && row.est_commission_usd ? fmtCurrency(row.est_commission_usd) : "-"}
        </div>
      </div>
      <div className="flex items-center gap-2 text-fg-dim flex-shrink-0">
        <button
          className="hover:text-fg p-1 transition-colors"
          title={`Call ${row.contact_name || "merchant"}`}
        >
          <Phone size={14} />
        </button>
        <button
          className="hover:text-fg p-1 transition-colors"
          title={`Email ${row.contact_name || "merchant"}`}
        >
          <Mail size={14} />
        </button>
        <ChevronRight size={14} className="text-fg-faint" />
      </div>
    </div>
  );
}
