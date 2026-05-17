import Link from "next/link";
import { redirect } from "next/navigation";
import { Card, EmptyState, PageHeader, Tag } from "@/components/Card";
import { canManageTeam, getSessionContext } from "@/lib/team";
import { getServiceSupabase } from "@/lib/supabase-server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type AuditRow = {
  id: string;
  actor_email: string | null;
  actor_user_id: string | null;
  action_type: string;
  target_table: string | null;
  target_id: string | null;
  before: unknown;
  after: unknown;
  metadata: unknown;
  created_at: string;
};

function formatTime(value: string): string {
  try {
    return new Intl.DateTimeFormat("en", {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(value));
  } catch {
    return value;
  }
}

function previewJson(value: unknown): string {
  if (value == null) return "";
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

export default async function AuditLogPage({
  searchParams,
}: {
  searchParams?: Promise<{ action?: string }>;
}) {
  const ctx = await getSessionContext();
  if (!ctx) redirect("/login?next=/settings/audit-log");
  if (!(ctx.isOwner || canManageTeam(ctx.teamRole))) redirect("/settings");

  const params = (await searchParams) || {};
  const action = typeof params.action === "string" ? params.action.trim() : "";
  const service = getServiceSupabase();
  let query = service
    .from("tenant_audit_log")
    .select(
      "id, actor_email, actor_user_id, action_type, target_table, target_id, before, after, metadata, created_at",
    )
    .eq("tenant_id", ctx.tenantId)
    .order("created_at", { ascending: false })
    .limit(100);

  if (action) query = query.eq("action_type", action);

  const { data, error } = await query;
  const rows = (data || []) as AuditRow[];
  const actionTypes = Array.from(new Set(rows.map((row) => row.action_type))).sort();

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="Audit Log"
        subtitle="Read-only trail of team, invite, and AI key changes for this tenant."
        action={
          <Link href="/settings" className="btn-secondary text-xs">
            Back to settings
          </Link>
        }
      />

      <Card
        title="Recent events"
        subtitle="Last 100 events. Actor is stamped by the database from the signed-in session."
        action={<Tag tone="engaged">Admin only</Tag>}
      >
        {error ? (
          <EmptyState message={`Could not load audit log: ${error.message}`} />
        ) : rows.length === 0 ? (
          <EmptyState message="No audit events recorded yet." />
        ) : (
          <div className="space-y-4">
            <div className="flex flex-wrap gap-2">
              <Link
                href="/settings/audit-log"
                className={`rounded-md border px-2 py-1 text-[11px] font-bold ${
                  action ? "border-bg-border text-fg-muted" : "border-accent text-accent bg-accent/10"
                }`}
              >
                All
              </Link>
              {actionTypes.map((type) => (
                <Link
                  key={type}
                  href={`/settings/audit-log?action=${encodeURIComponent(type)}`}
                  className={`rounded-md border px-2 py-1 text-[11px] font-bold ${
                    action === type
                      ? "border-accent text-accent bg-accent/10"
                      : "border-bg-border text-fg-muted"
                  }`}
                >
                  {type}
                </Link>
              ))}
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-[10px] uppercase tracking-wider text-fg-dim">
                  <tr className="border-b border-bg-border">
                    <th className="text-left py-2 pr-3">Time</th>
                    <th className="text-left py-2 pr-3">Action</th>
                    <th className="text-left py-2 pr-3">Actor</th>
                    <th className="text-left py-2 pr-3">Target</th>
                    <th className="text-left py-2">After</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.id} className="border-b border-bg-border/70 align-top">
                      <td className="py-2 pr-3 text-fg-muted whitespace-nowrap">
                        {formatTime(row.created_at)}
                      </td>
                      <td className="py-2 pr-3">
                        <Tag tone="info">{row.action_type}</Tag>
                      </td>
                      <td className="py-2 pr-3 text-fg-muted">
                        {row.actor_email || row.actor_user_id || "unknown"}
                      </td>
                      <td className="py-2 pr-3 text-fg-muted">
                        <div>{row.target_table || "-"}</div>
                        {row.target_id && (
                          <div className="font-mono text-[11px] text-fg-dim break-all">
                            {row.target_id}
                          </div>
                        )}
                      </td>
                      <td className="py-2 text-fg-dim font-mono text-[11px] max-w-md break-all">
                        {previewJson(row.after || row.metadata)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
