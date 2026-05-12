import { Card, PageHeader, EmptyState, Tag } from "@/components/Card";
import { getActiveProfile, getSmsHistory } from "@/lib/queries";
import { safe } from "@/lib/api-helpers";
import { SmsSendForm } from "@/components/sms/SmsSendForm";

export const dynamic = "force-dynamic";

function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

export default async function SmsPage() {
  const profile = await safe("sms.profile", getActiveProfile(), null);
  const tenantId = profile?.tenant_id || "";
  const history = tenantId
    ? await safe("sms.history", getSmsHistory(tenantId, 50), [])
    : [];

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="SMS"
        subtitle="Outbound messaging · multi-provider (Phase 1: Twilio; Phase 2 adds Telnyx + Plivo failover)"
      />

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* Send form — left pane */}
        <div className="lg:col-span-2">
          <Card title="Send a message" subtitle="Single-recipient send · TCPA-checked at send time">
            <SmsSendForm />
          </Card>
        </div>

        {/* Recent sends — right pane */}
        <div className="lg:col-span-3">
          <Card title="Recent sends" subtitle={`Last ${history.length} · provider-aware`} noPadding>
            {history.length === 0 ? (
              <div className="p-5">
                <EmptyState message="No sends recorded yet. Phase 1 logs land in the Sun Biz Agent's tmp/sms_log.jsonl; Phase 2 migration 044 (sms_sends) mirrors them here." />
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="border-b border-bg-border">
                    <tr className="text-left text-[10px] uppercase tracking-[0.14em] text-fg-muted font-bold">
                      <th className="px-5 py-3">When</th>
                      <th className="px-5 py-3">To (hash)</th>
                      <th className="px-5 py-3">Provider</th>
                      <th className="px-5 py-3">Status</th>
                      <th className="px-5 py-3">Preview</th>
                    </tr>
                  </thead>
                  <tbody>
                    {history.map((row) => (
                      <tr key={row.id} className="border-b border-bg-border last:border-0 hover:bg-bg-hover/30 transition-colors">
                        <td className="px-5 py-3 text-fg-dim text-xs font-mono">{fmtTime(row.sent_at)}</td>
                        <td className="px-5 py-3 text-fg-muted text-xs font-mono">{row.to_hash || "—"}</td>
                        <td className="px-5 py-3 text-fg text-xs">
                          <Tag tone="info">{row.provider || "—"}</Tag>
                        </td>
                        <td className="px-5 py-3 text-xs">
                          <Tag
                            tone={
                              row.status === "sent" || row.status === "delivered"
                                ? "engaged"
                                : row.status === "queued" || row.status === "sending"
                                  ? "info"
                                  : "hot"
                            }
                          >
                            {row.status || "—"}
                          </Tag>
                        </td>
                        <td className="px-5 py-3 text-fg-muted text-xs">
                          {row.body_preview || "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
